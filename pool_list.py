"""Build the fixed phase-1 pool list.

Rule (from JOURNAL.md): every pool for the five pairs on Uniswap V3, Camelot, SushiSwap and
PancakeSwap V3 with TVL above $250k on 2026-08-01.

How it works:
1. Find the first Arbitrum block at or after 2026-08-01 00:00:00 UTC (the snapshot block).
2. Ask each DEX factory, at that block, which pools exist for each pair (every fee tier).
3. Check each pool on-chain: it has code, its tokens match, and it reports the factory we asked.
4. TVL = the pool contract's balance of each of its two tokens at the snapshot block, valued
   in USD with Chainlink price feeds at the same block.
5. Write every candidate to data/pools_all.csv and the ones above $250k to data/pools.csv.
"""
import csv
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from web3 import Web3

load_dotenv()
RPC = os.getenv("ARB_RPC_URL") or "https://arb1.arbitrum.io/rpc"
w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 60}))

SNAPSHOT_UTC = datetime(2026, 8, 1, tzinfo=timezone.utc)
TVL_MIN_USD = 250_000
ZERO = "0x0000000000000000000000000000000000000000"

TOKENS = {
    "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # native USDC, not USDC.e
    "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    "WBTC": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
    "ARB": "0x912CE59144191C1204E64559FE8253a0e49E6548",
}
PAIRS = [("WETH", "USDC"), ("WETH", "USDT"), ("WBTC", "WETH"), ("ARB", "WETH"), ("ARB", "USDC")]

# Chainlink USD feeds on Arbitrum; description() is checked against the expected label.
FEEDS = {
    "WETH": ("0x639Fe6ab55C921f74e7fac1ee960C0B6293ba612", "ETH / USD"),
    "WBTC": ("0xd0C7101eACbB49F3deCcCc166d238410D6D46d57", "WBTC / USD"),
    "USDC": ("0x50834F3163758fcC1Df9973b6e91f0F0F0434aD3", "USDC / USD"),
    "USDT": ("0x3f3f5dF88dC9F13eac63DF89EC16ef6e7E25DdE7", "USDT / USD"),
    "ARB": ("0xb2A824043730FE05F3DA2efaFa1CBbe83fa548D6", "ARB / USD"),
}

# kind: "v3" = Uniswap-V3-style getPool(a, b, fee); "v2" = getPair(a, b); "algebra" = poolByPair(a, b)
DEXES = [
    ("UniswapV3", "v3", "0x1F98431c8aD98523631AE4a59f267346ea31F984"),
    ("SushiV3", "v3", "0x1af415a1EbA07a4986a52B6f2e7dE7003D82231e"),
    ("SushiV2", "v2", "0xc35DADB65012eC5796536bD9864eD8773aBc74C4"),
    ("PancakeV3", "v3", "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"),
    ("CamelotV3", "algebra", "0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B"),
    ("CamelotV2", "v2", "0x6EcCab422D763aC031210895C81787E87B43A652"),
]
# Fee values (hundredths of a bip) to try on V3-style factories. Wider than the standard tiers
# so a non-standard tier added by governance is not missed; unused values return no pool.
V3_FEES = [1, 5, 10, 50, 80, 100, 200, 250, 300, 400, 500, 1000, 2500, 3000, 5000, 10000, 20000]


def fn(sig, outs):
    """Minimal ABI entry from a signature like 'getPool(address,address,uint24)'."""
    name, args = sig.split("(")
    ins = [t for t in args.rstrip(")").split(",") if t]
    return {"type": "function", "name": name, "stateMutability": "view",
            "inputs": [{"name": f"a{i}", "type": t} for i, t in enumerate(ins)],
            "outputs": [{"name": f"o{i}", "type": t} for i, t in enumerate(outs)]}


ABI = [
    fn("getPool(address,address,uint24)", ["address"]),
    fn("getPair(address,address)", ["address"]),
    fn("poolByPair(address,address)", ["address"]),
    fn("token0()", ["address"]),
    fn("token1()", ["address"]),
    fn("factory()", ["address"]),
    fn("fee()", ["uint24"]),
    # Camelot V3 (Algebra 1.9 fork): price, tick, feeZto, feeOtz, timepointIndex, communityFee0/1, unlocked
    fn("globalState()", ["uint160", "int24", "uint16", "uint16", "uint16", "uint16", "uint16", "bool"]),
    fn("token0FeePercent()", ["uint16"]),
    fn("token1FeePercent()", ["uint16"]),
    fn("stableSwap()", ["bool"]),
    fn("balanceOf(address)", ["uint256"]),
    fn("decimals()", ["uint8"]),
    fn("description()", ["string"]),
    fn("latestRoundData()", ["uint80", "int256", "uint256", "uint256", "uint80"]),
]


def c(addr):
    return w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ABI)


def call(addr, name, *args, block):
    return getattr(c(addr).functions, name)(*args).call(block_identifier=block)


def try_call(addr, name, *args, block):
    try:
        return call(addr, name, *args, block=block)
    except Exception:
        return None


def snapshot_block(when=SNAPSHOT_UTC):
    """First block with timestamp >= when (binary search)."""
    target = int(when.timestamp())
    lo, hi = 0, w3.eth.block_number
    while lo < hi:
        mid = (lo + hi) // 2
        if w3.eth.get_block(mid)["timestamp"] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def main():
    block = snapshot_block()
    ts = w3.eth.get_block(block)["timestamp"]
    prev_ts = w3.eth.get_block(block - 1)["timestamp"]
    print(f"RPC: {'custom (.env)' if os.getenv('ARB_RPC_URL') else 'public arb1.arbitrum.io'}")
    print(f"Snapshot block {block}  ts {datetime.fromtimestamp(ts, timezone.utc)}  "
          f"(prev block ts {datetime.fromtimestamp(prev_ts, timezone.utc)})")

    decimals = {s: call(a, "decimals", block=block) for s, a in TOKENS.items()}
    price = {}
    for sym, (feed, label) in FEEDS.items():
        desc = call(feed, "description", block=block)
        if desc != label:
            sys.exit(f"Feed {feed} description {desc!r} != expected {label!r}")
        rd = call(feed, "latestRoundData", block=block)
        fd = call(feed, "decimals", block=block)
        age_h = (ts - rd[3]) / 3600
        price[sym] = rd[1] / 10 ** fd
        print(f"  {label:<11} {price[sym]:>12,.4f}  (feed updated {age_h:.1f}h before snapshot)")

    by_addr = {v.lower(): k for k, v in TOKENS.items()}
    rows = []
    for dex, kind, factory in DEXES:
        if not w3.eth.get_code(Web3.to_checksum_address(factory), block_identifier=block):
            sys.exit(f"No code at {dex} factory {factory}")
        for a, b in PAIRS:
            ta, tb = TOKENS[a], TOKENS[b]
            if kind == "v3":
                found = [(f, call(factory, "getPool", ta, tb, f, block=block)) for f in V3_FEES]
            elif kind == "v2":
                found = [(None, call(factory, "getPair", ta, tb, block=block))]
            else:
                found = [(None, call(factory, "poolByPair", ta, tb, block=block))]
            for fee_arg, pool in found:
                if pool == ZERO:
                    continue
                t0 = call(pool, "token0", block=block).lower()
                t1 = call(pool, "token1", block=block).lower()
                if {t0, t1} != {ta.lower(), tb.lower()}:
                    sys.exit(f"{dex} {pool}: tokens {t0},{t1} do not match {a}/{b}")
                pf = try_call(pool, "factory", block=block)
                if pf is not None and pf.lower() != factory.lower():
                    sys.exit(f"{dex} {pool}: factory() {pf} != {factory}")
                s0, s1 = by_addr[t0], by_addr[t1]
                if kind == "v3":
                    fee_onchain = call(pool, "fee", block=block)
                    if fee_onchain != fee_arg:
                        sys.exit(f"{dex} {pool}: fee() {fee_onchain} != {fee_arg}")
                    fee_txt = f"{fee_onchain / 1e4:g}%"
                elif kind == "algebra":
                    gs = call(pool, "globalState", block=block)
                    fee_txt = f"{gs[2] / 1e4:g}%/{gs[3] / 1e4:g}% (in {s0}/in {s1}, dynamic)"
                elif dex == "CamelotV2":
                    f0 = call(pool, "token0FeePercent", block=block)
                    f1 = call(pool, "token1FeePercent", block=block)
                    stable = call(pool, "stableSwap", block=block)
                    # Camelot V2 fee percents are in units of 1/100000 (FEE_DENOMINATOR = 100000)
                    fee_txt = (f"{f0 / 1e3:g}%/{f1 / 1e3:g}% (in {s0}/in {s1})"
                               + (", stable" if stable else ""))
                else:
                    fee_txt = "0.3%"
                bal0 = call(t0, "balanceOf", pool, block=block) / 10 ** decimals[s0]
                bal1 = call(t1, "balanceOf", pool, block=block) / 10 ** decimals[s1]
                tvl = bal0 * price[s0] + bal1 * price[s1]
                rows.append({"dex": dex, "pair": f"{a}/{b}", "pool": Web3.to_checksum_address(pool),
                             "fee": fee_txt, "token0": s0, "token1": s1,
                             "bal0": round(bal0, 6), "bal1": round(bal1, 6),
                             "tvl_usd": round(tvl), "included": tvl > TVL_MIN_USD})

    rows.sort(key=lambda r: (r["pair"], -r["tvl_usd"]))
    os.makedirs("data", exist_ok=True)
    meta = f"# snapshot_block={block} snapshot_ts={ts} tvl_min_usd={TVL_MIN_USD}\n"
    for path, subset in [("data/pools_all.csv", rows), ("data/pools.csv", [r for r in rows if r["included"]])]:
        with open(path, "w", newline="") as f:
            f.write(meta)
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(subset)

    print(f"\n{len(rows)} candidate pools, {sum(r['included'] for r in rows)} above ${TVL_MIN_USD:,}")
    for r in rows:
        mark = "IN " if r["included"] else "   "
        print(f"{mark}{r['pair']:<10}{r['dex']:<11}{r['fee']:<40}{r['tvl_usd']:>14,}  {r['pool']}")


def run(entry):
    """Run entry(), printing errors with the RPC URL (which contains the key) redacted."""
    try:
        entry()
    except Exception as e:
        sys.exit(f"{type(e).__name__}: {str(e).replace(RPC, '<rpc>')}")


if __name__ == "__main__":
    run(main)
