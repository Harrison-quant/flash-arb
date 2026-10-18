"""Step 0a (archive version): tick maps for the 12 universe pools at the end of July 2026.

Replaces build_ticks.py, which replayed every Mint/Burn since pool creation and would have taken days
on the public endpoint. Here the state is read directly from the archive node at block B0-1: the
pool's tick bitmap (tickBitmap on Uniswap/PancakeSwap, tickTable on Camelot), one word per 256
compressed ticks over the whole tick range, then ticks(t) for every set bit to get liquidityGross
and liquidityNet. All calls go through Multicall3 at the same block.

Sanity checks before writing: every set bit has liquidityGross > 0 and initialized = true, and the
active liquidity implied by the map at the pool's tick equals liquidity() at that block.
Output (same format build_ticks.py wrote): data/raw/ticks/<pool>.csv (tick, net, gross) and
data/raw/ticks/meta.csv (pool, tick_spacing, bitmap_unit, words_read, initialised_ticks, source_block).
"""
import csv
import os
import time

from web3 import Web3

import v3math
from pool_list import RPC, run, w3
from pull_august import DEX, POOLS, mc, word

B0 = 489_802_914
BLOCK = B0 - 1            # end of July; the scan starts from this state
OUT = "data/raw/ticks"
BATCH = 400


def sel(sig):
    return Web3.keccak(text=sig)[:4]


def enc_int(v, bits):
    return (v % (1 << 256)).to_bytes(32, "big") if v < 0 else v.to_bytes(32, "big")


def multicall(calls):
    out = []
    for i in range(0, len(calls), BATCH):
        part = [(to, False, data) for to, data in calls[i:i + BATCH]]
        for attempt in range(8):
            try:
                res = mc.functions.aggregate3(part).call(block_identifier=BLOCK)
                break
            except Exception as e:
                print(f"  multicall failed (attempt {attempt + 1}/8): {str(e).replace(RPC, '<rpc>')[:150]}", flush=True)
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError("multicall failed")
        for ok, data in res:
            if not ok:
                raise RuntimeError("a call inside multicall reverted")
            out.append(data)
    return out


def read_pool(p):
    sp = word(w3.eth.call({"to": p, "data": "0x" + sel("tickSpacing()").hex()}, BLOCK), 0, True)
    bitmap = sel("tickTable(int16)" if DEX[p] == "CamelotV3" else "tickBitmap(int16)")
    # Uniswap/PancakeSwap index the bitmap by tick / spacing; Camelot (Algebra 1.9) by the raw tick.
    unit = 1 if DEX[p] == "CamelotV3" else sp
    lo_w, hi_w = (v3math.MIN_TICK // unit) >> 8, (v3math.MAX_TICK // unit) >> 8
    words = list(range(lo_w, hi_w + 1))
    vals = multicall([(p, bitmap + enc_int(w, 16)) for w in words])
    comp = [(w << 8) + b for w, v in zip(words, vals) for b in range(256) if word(v, 0) >> b & 1]
    ticks = [c * unit for c in comp]
    if any(t % sp for t in ticks):
        raise RuntimeError(f"{p}: initialised tick not on the spacing")
    info = multicall([(p, sel("ticks(int24)") + enc_int(t, 24)) for t in ticks])
    rows = []
    for t, d in zip(ticks, info):
        gross, net, inited = word(d, 0), word(d, 1, True), word(d, 7)
        if gross == 0 or not inited:
            raise RuntimeError(f"{p}: bit set at tick {t} but gross={gross} initialized={inited}")
        rows.append((t, net, gross))
    s0 = w3.eth.call({"to": p, "data": "0x" + sel("globalState()" if DEX[p] == "CamelotV3" else "slot0()").hex()}, BLOCK)
    tick = word(s0, 1, True)
    liq = word(w3.eth.call({"to": p, "data": "0x" + sel("liquidity()").hex()}, BLOCK), 0)
    active = sum(n for t, n, _ in rows if t <= tick)
    if active != liq:
        raise RuntimeError(f"{p}: active liquidity from map {active} != liquidity() {liq}")
    return sp, unit, len(words), rows


def main():
    os.makedirs(OUT, exist_ok=True)
    meta = []
    for p in POOLS:
        t0 = time.time()
        sp, unit, nw, rows = read_pool(p)
        with open(f"{OUT}/{p}.csv.tmp", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["tick", "net", "gross"])
            w.writerows(rows)
        os.replace(f"{OUT}/{p}.csv.tmp", f"{OUT}/{p}.csv")
        meta.append({"pool": p, "tick_spacing": sp, "bitmap_unit": unit, "words_read": nw, "initialised_ticks": len(rows),
                     "source_block": BLOCK})
        print(f"  {p} {DEX[p]}: spacing {sp}, bitmap unit {unit}, {nw} words, {len(rows):,} ticks, active liquidity matches "
              f"({time.time() - t0:.0f}s)", flush=True)
    with open(f"{OUT}/meta.csv.tmp", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(meta[0]))
        w.writeheader()
        w.writerows(meta)
    os.replace(f"{OUT}/meta.csv.tmp", f"{OUT}/meta.csv")
    print("done", flush=True)


if __name__ == "__main__":
    run(main)
