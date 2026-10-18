"""Exact-integer port of the Uniswap V3 swap maths, used to size trades and to replay swaps.

Mirrors TickMath, SqrtPriceMath, SwapMath and the swap loop of UniswapV3Pool, including rounding and
the tick-bitmap search that ends a step at a 256-tick word boundary. PancakeSwap V3 is identical.
Camelot V3 (Algebra 1.9) uses the same step maths, but its tick table is indexed by the raw tick (one
row = 256 raw ticks), not by tick / spacing. Pool takes that as `unit`: the tick spacing for
Uniswap/PancakeSwap, 1 for Camelot. Verified by replaying real swaps.
"""
from bisect import bisect_left, bisect_right, insort

MIN_TICK, MAX_TICK = -887272, 887272
MIN_SQRT = 4295128739
MAX_SQRT = 1461446703485210103287273052203988822378723970342
Q96 = 1 << 96
U256 = 1 << 256
FEE_DEN = 1_000_000

_TM = [(0x2, 0xfff97272373d413259a46990580e213a), (0x4, 0xfff2e50f5f656932ef12357cf3c7fdcc),
       (0x8, 0xffe5caca7e10e4e61c3624eaa0941cd0), (0x10, 0xffcb9843d60f6159c9db58835c926644),
       (0x20, 0xff973b41fa98c081472e6896dfb254c0), (0x40, 0xff2ea16466c96a3843ec78b326b52861),
       (0x80, 0xfe5dee046a99a2a811c461f1969c3053), (0x100, 0xfcbe86c7900a88aedcffc83b479aa3a4),
       (0x200, 0xf987a7253ac413176f2b074cf7815e54), (0x400, 0xf3392b0822b70005940c7a398e4b70f3),
       (0x800, 0xe7159475a2c29b7443b29c7fa6e889d9), (0x1000, 0xd097f3bdfd2022b8845ad8f792aa5825),
       (0x2000, 0xa9f746462d870fdf8a65dc1f90e061e5), (0x4000, 0x70d869a156d2a1b890bb3df62baf32f7),
       (0x8000, 0x31be135f97d08fd981231505542fcfa6), (0x10000, 0x9aa508b5b7a84e1c677de54f3e99bc9),
       (0x20000, 0x5d6af8dedb81196699c329225ee604), (0x40000, 0x2216e584f5fa1ea926041bedfe98),
       (0x80000, 0x48a170391f7dc42444e8fa2)]
_SQRT_CACHE = {}


def sqrt_at_tick(tick):
    r = _SQRT_CACHE.get(tick)
    if r is not None:
        return r
    a = abs(tick)
    if a > MAX_TICK:
        raise ValueError("tick out of range")
    ratio = 0xfffcb933bd6fad37aa2d162d1a594001 if a & 1 else 1 << 128
    for bit, m in _TM:
        if a & bit:
            ratio = (ratio * m) >> 128
    if tick > 0:
        ratio = (U256 - 1) // ratio
    r = (ratio >> 32) + (1 if ratio & 0xffffffff else 0)
    if len(_SQRT_CACHE) < 2_000_000:
        _SQRT_CACHE[tick] = r
    return r


def tick_at_sqrt(sp):
    """Greatest tick with sqrt_at_tick(tick) <= sp (same result as TickMath.getTickAtSqrtRatio)."""
    lo, hi = MIN_TICK, MAX_TICK
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if sqrt_at_tick(mid) <= sp:
            lo = mid
        else:
            hi = mid - 1
    return lo


def mul_div(a, b, d):
    return a * b // d


def mul_div_up(a, b, d):
    q, r = divmod(a * b, d)
    return q + (1 if r else 0)


def div_up(a, b):
    q, r = divmod(a, b)
    return q + (1 if r else 0)


def next_sqrt_amount0_up(sp, L, amount, add):
    if amount == 0:
        return sp
    num1 = L << 96
    product = amount * sp
    if add:
        if product < U256:
            denom = num1 + product
            if denom < U256:
                return mul_div_up(num1, sp, denom)
        return div_up(num1, num1 // sp + amount)
    if product >= U256 or num1 <= product:
        raise ArithmeticError("amount0 out exceeds reserves")
    return mul_div_up(num1, sp, num1 - product)


def next_sqrt_amount1_down(sp, L, amount, add):
    if add:
        q = (amount << 96) // L if amount < (1 << 160) else mul_div(amount, Q96, L)
        return sp + q
    q = div_up(amount << 96, L) if amount < (1 << 160) else mul_div_up(amount, Q96, L)
    if sp <= q:
        raise ArithmeticError("amount1 out exceeds reserves")
    return sp - q


def amount0_delta(a, b, L, up):
    if a > b:
        a, b = b, a
    num1, num2 = L << 96, b - a
    if up:
        return div_up(mul_div_up(num1, num2, b), a)
    return mul_div(num1, num2, b) // a


def amount1_delta(a, b, L, up):
    if a > b:
        a, b = b, a
    return mul_div_up(L, b - a, Q96) if up else mul_div(L, b - a, Q96)


def swap_step_exact_in(cur, target, L, remaining, fee):
    """SwapMath.computeSwapStep for exact input. Returns (sqrt_next, amount_in, amount_out, fee_amount)."""
    zfo = cur >= target
    less_fee = mul_div(remaining, FEE_DEN - fee, FEE_DEN)
    amt_in = amount0_delta(target, cur, L, True) if zfo else amount1_delta(cur, target, L, True)
    if less_fee >= amt_in:
        nxt = target
    else:
        nxt = next_sqrt_amount0_up(cur, L, less_fee, True) if zfo else next_sqrt_amount1_down(cur, L, less_fee, True)
    reached = nxt == target
    if zfo:
        if not reached:
            amt_in = amount0_delta(nxt, cur, L, True)
        amt_out = amount1_delta(nxt, cur, L, False)
    else:
        if not reached:
            amt_in = amount1_delta(cur, nxt, L, True)
        amt_out = amount0_delta(cur, nxt, L, False)
    fee_amt = remaining - amt_in if not reached else mul_div_up(amt_in, fee, FEE_DEN - fee)
    return nxt, amt_in, amt_out, fee_amt


class Pool:
    """Pool state: price, tick, active liquidity, fee(s) and the initialised-tick map."""

    def __init__(self, spacing, sqrtp, tick, liquidity, fee_zfo, fee_ofz, unit=None):
        self.spacing = spacing
        self.unit = spacing if unit is None else unit   # bitmap index = tick // unit
        self.sqrtp, self.tick, self.liquidity = sqrtp, tick, liquidity
        self.fee_zfo, self.fee_ofz = fee_zfo, fee_ofz
        self.net = {}     # tick -> liquidityNet
        self.gross = {}   # tick -> liquidityGross
        self.init = []    # sorted ticks // unit with gross > 0

    # ---- tick map maintenance (Mint/Burn) ----
    def _update_tick(self, t, d_net, d_gross):
        g0 = self.gross.get(t, 0)
        g1 = g0 + d_gross
        self.gross[t] = g1
        self.net[t] = self.net.get(t, 0) + d_net
        c = t // self.unit
        if g0 == 0 and g1 > 0:
            insort(self.init, c)
        elif g0 > 0 and g1 == 0:
            self.init.pop(bisect_left(self.init, c))
            del self.gross[t]
            del self.net[t]
        elif g1 < 0:
            raise ValueError(f"negative liquidityGross at tick {t}")

    def modify(self, tl, tu, dl):
        """Apply a Mint (dl > 0) or Burn (dl < 0) of liquidity dl on range [tl, tu)."""
        if dl == 0:
            return
        self._update_tick(tl, dl, dl)
        self._update_tick(tu, -dl, dl)

    def active_from_map(self):
        """Active liquidity implied by the tick map at the current tick (sum of net at ticks <= tick)."""
        return sum(self.net[c * self.unit] for c in self.init[:bisect_right(self.init, self.tick // self.unit)])

    # ---- tick search (TickBitmap.nextInitializedTickWithinOneWord) ----
    def next_tick(self, tick, lte):
        s = self.unit
        comp = tick // s
        if lte:
            word = comp >> 8
            i = bisect_right(self.init, comp) - 1
            if i >= 0 and (self.init[i] >> 8) == word:
                return self.init[i] * s, True
            return (word << 8) * s, False
        comp += 1
        word = comp >> 8
        i = bisect_left(self.init, comp)
        if i < len(self.init) and (self.init[i] >> 8) == word:
            return self.init[i] * s, True
        return ((word << 8) + 255) * s, False

    # ---- exact-input swap (UniswapV3Pool.swap loop) ----
    def swap(self, zfo, amount_in, limit=None, commit=False):
        """Exact-input swap. Returns (amount_in_used, amount_out, end_sqrtp). Doesn't change state
        unless commit=True."""
        if limit is None:
            limit = MIN_SQRT + 1 if zfo else MAX_SQRT - 1
        fee = self.fee_zfo if zfo else self.fee_ofz
        sp, tick, L = self.sqrtp, self.tick, self.liquidity
        remaining, out = amount_in, 0
        while remaining != 0 and sp != limit:
            start = sp
            t_next, initialized = self.next_tick(tick, zfo)
            t_next = max(MIN_TICK, min(MAX_TICK, t_next))
            s_next = sqrt_at_tick(t_next)
            target = limit if (s_next < limit if zfo else s_next > limit) else s_next
            sp, a_in, a_out, f = swap_step_exact_in(sp, target, L, remaining, fee)
            remaining -= a_in + f
            out += a_out
            if sp == s_next:
                if initialized:
                    n = self.net.get(t_next, 0)
                    L += -n if zfo else n
                tick = t_next - 1 if zfo else t_next
            elif sp != start:
                tick = tick_at_sqrt(sp)
        if commit:
            self.sqrtp, self.tick, self.liquidity = sp, tick, L
        return amount_in - remaining, out, sp


def _selftest():
    assert sqrt_at_tick(MIN_TICK) == MIN_SQRT
    assert sqrt_at_tick(MAX_TICK) == MAX_SQRT
    assert sqrt_at_tick(0) == Q96
    for t in (-50000, -1, 0, 1, 12345, 200000):
        assert tick_at_sqrt(sqrt_at_tick(t)) == t
        assert tick_at_sqrt(sqrt_at_tick(t) - 1) == t - 1


_selftest()
