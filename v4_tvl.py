"""Uniswap V4 TVL for the five pairs at the snapshot block. Reported only, not part of the universe.

V4 holds every pool inside one PoolManager contract, so per-pool token balances don't exist.
How it works:
1. Find V4 pools for the pairs from the PoolManager's Initialize events up to the snapshot block
   (WETH pairs are checked against both WETH and native ETH).
2. Replay each pool's ModifyLiquidity events to get net liquidity per tick range.
3. Check: liquidity of ranges covering the current tick must equal StateView.getLiquidity.
4. Convert each range to token amounts at the snapshot price; value with Chainlink (same feeds
   and block as pool_list.py). Excludes uncollected fees and anything hooks hold outside.
Writes data/v4_pools.csv.
"""
import csv
import math
from collections import defaultdict

from web3 import Web3

import os

from pool_list import FEEDS, PAIRS, TOKENS, ZERO, call, fn, run, snapshot_block, w3

POOL_MANAGER = "0x360e68faccca8ca495c1b759fd9eee466db9fb32"
STATE_VIEW = "0x76fd297e2d437cd7f76d50f01afe6160f86e9990"
DYNAMIC_FEE_FLAG = 0x800000

INIT_TOPIC = Web3.keccak(text="Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)")
MODLIQ_TOPIC = Web3.keccak(text="ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)")

SV_ABI = [
    fn("poolManager()", ["address"]),
    fn("getSlot0(bytes32)", ["uint160", "int24", "uint24", "uint24"]),
    fn("getLiquidity(bytes32)", ["uint128"]),
]
sv = w3.eth.contract(address=Web3.to_checksum_address(STATE_VIEW), abi=SV_ABI)
pm = Web3.to_checksum_address(POOL_MANAGER)

# Logs come from a separate endpoint: Alchemy's free tier allows only 10 blocks per eth_getLogs,
# while the public endpoint allows 10M. Logs are the same on any node; state still comes from w3.
LOGS_RPC = os.getenv("ARB_LOGS_RPC_URL") or "https://arb1.arbitrum.io/rpc"
logs_w3 = Web3(Web3.HTTPProvider(LOGS_RPC, request_kwargs={"timeout": 120}))
LOGS_SPAN = 10_000_000


def topic_addr(a):
    return "0x" + a.lower()[2:].rjust(64, "0")


def get_logs(topics, start, end):
    """eth_getLogs over [start, end], splitting the range whenever the provider refuses it."""
    stack = [(lo, min(lo + LOGS_SPAN - 1, end)) for lo in range(start, end + 1, LOGS_SPAN)][::-1]
    out = []
    while stack:
        lo, hi = stack.pop()
        try:
            out += logs_w3.eth.get_logs({"address": pm, "topics": topics, "fromBlock": lo, "toBlock": hi})
        except Exception:
            if hi == lo:
                raise
            mid = (lo + hi) // 2
            stack += [(mid + 1, hi), (lo, mid)]
    return sorted(out, key=lambda l: (l["blockNumber"], l["logIndex"]))


def deploy_block(end):
    lo, hi = 0, end
    while lo < hi:
        mid = (lo + hi) // 2
        if w3.eth.get_code(pm, block_identifier=mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


def s32(word):
    v = int.from_bytes(word, "big")
    return v - (1 << 256) if v >> 255 else v


def main():
    block = snapshot_block()
    if sv.functions.poolManager().call(block_identifier=block).lower() != POOL_MANAGER:
        raise SystemExit("StateView does not point at the PoolManager")
    start = deploy_block(block)
    print(f"Snapshot block {block}; PoolManager deployed at block {start}")

    price = {s: call(f, "latestRoundData", block=block)[1] / 10 ** call(f, "decimals", block=block)
             for s, (f, _) in FEEDS.items()}
    decimals = {s: call(a, "decimals", block=block) for s, a in TOKENS.items()}
    symbols = {a.lower(): s for s, a in TOKENS.items()}
    symbols[ZERO] = "ETH"
    price["ETH"], decimals["ETH"] = price["WETH"], 18

    rows = []
    for a, b in PAIRS:
        variants = [(TOKENS[a], TOKENS[b])]
        if "WETH" in (a, b):
            other = TOKENS[b] if a == "WETH" else TOKENS[a]
            variants.append((ZERO, other))
        for x, y in variants:
            c0, c1 = sorted([x.lower(), y.lower()], key=lambda s: int(s, 16))
            inits = get_logs([INIT_TOPIC, None, topic_addr(c0), topic_addr(c1)], start, block)
            for ev in inits:
                pid = ev["topics"][1]
                d = ev["data"]
                fee_key = int.from_bytes(d[0:32], "big")
                spacing = s32(d[32:64])
                hooks = "0x" + d[64 + 12:96].hex()
                s0, s1 = symbols[c0], symbols[c1]

                ranges = defaultdict(int)
                mods = get_logs([MODLIQ_TOPIC, "0x" + pid.hex()], ev["blockNumber"], block)
                for m in mods:
                    md = m["data"]
                    ranges[(s32(md[0:32]), s32(md[32:64]))] += s32(md[64:96])

                sqrtp_x96, tick, _, lp_fee = sv.functions.getSlot0(pid).call(block_identifier=block)
                active_onchain = sv.functions.getLiquidity(pid).call(block_identifier=block)
                active_rebuilt = sum(L for (tl, tu), L in ranges.items() if tl <= tick < tu)
                ok = active_rebuilt == active_onchain

                amt0 = amt1 = 0.0
                p = sqrtp_x96 / 2 ** 96
                for (tl, tu), L in ranges.items():
                    if L == 0:
                        continue
                    sa, sb = 1.0001 ** (tl / 2), 1.0001 ** (tu / 2)
                    if p <= sa:
                        amt0 += L * (sb - sa) / (sa * sb)
                    elif p >= sb:
                        amt1 += L * (sb - sa)
                    else:
                        amt0 += L * (sb - p) / (p * sb)
                        amt1 += L * (p - sa)
                bal0, bal1 = amt0 / 10 ** decimals[s0], amt1 / 10 ** decimals[s1]
                tvl = bal0 * price[s0] + bal1 * price[s1] if sqrtp_x96 else 0.0
                dyn = bool(fee_key & DYNAMIC_FEE_FLAG)
                rows.append({
                    "pair": f"{s0}/{s1}", "pool_id": "0x" + pid.hex(),
                    "fee": f"{lp_fee / 1e4:g}%" + (" (dynamic)" if dyn else ""),
                    "tick_spacing": spacing, "hooks": hooks,
                    "bal0": round(bal0, 6), "bal1": round(bal1, 6), "tvl_usd": round(tvl),
                    "liquidity_check": "ok" if ok else f"FAILED rebuilt={active_rebuilt} onchain={active_onchain}",
                    "modify_events": len(mods)})

    rows.sort(key=lambda r: (r["pair"], -r["tvl_usd"]))
    with open("data/v4_pools.csv", "w", newline="") as f:
        f.write(f"# snapshot_block={block} reported only, not part of the universe\n")
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"{len(rows)} V4 pools found; liquidity check failed for "
          f"{sum(r['liquidity_check'] != 'ok' for r in rows)}")
    for r in rows:
        if r["tvl_usd"] >= 1000 or r["liquidity_check"] != "ok":
            hook = "no hook" if r["hooks"] == ZERO else f"hook {r['hooks']}"
            print(f"{r['pair']:<10}{r['fee']:<18}{r['tvl_usd']:>13,}  {r['liquidity_check']:<6} {hook}  {r['pool_id']}")
    by_pair = defaultdict(float)
    for r in rows:
        by_pair[r["pair"]] += r["tvl_usd"]
    print("Totals by pair:", {k: f"{v:,.0f}" for k, v in sorted(by_pair.items())})


if __name__ == "__main__":
    run(main)
