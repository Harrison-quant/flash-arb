"""Step 0a: tick maps for the 12 universe pools at the start of August 2026.

For each pool: find its creation block (first block with code, via the archive node), read its tick
spacing, then fetch every Mint and Burn from creation to the last block of July from the public
endpoint, and sum them into liquidityNet / liquidityGross per tick. Chunks are cached in
data/raw/ticks/<pool>/ so a rerun resumes. Output: data/raw/ticks/<pool>.csv (tick, net, gross) and
data/raw/ticks/meta.csv (pool, created_block, tick_spacing, mint_events, burn_events).
"""
import csv
import glob
import gzip
import os
import time

from web3 import Web3

from pool_list import run, w3
from pull_august import EVENTS, POOLS, decode, get_logs, topic

B0 = 489_802_914          # first block of August 2026
END = B0 - 1              # tick maps are built up to the end of July
CHUNK = 10_000_000
OUT = "data/raw/ticks"
MINT = topic("Mint(address,address,int24,int24,uint128,uint256,uint256)")
BURN = topic("Burn(address,int24,int24,uint128,uint256,uint256)")
assert EVENTS[MINT] == "mint" and EVENTS[BURN] == "burn"


def created_block(pool):
    lo, hi = 0, B0
    while lo < hi:
        mid = (lo + hi) // 2
        if w3.eth.get_code(pool, block_identifier=mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


def tick_spacing(pool):
    data = w3.eth.call({"to": pool, "data": "0x" + Web3.keccak(text="tickSpacing()")[:4].hex().removeprefix("0x")}, B0)
    v = int.from_bytes(data[:32], "big")
    return v - (1 << 256) if v >> 255 else v


def fetch_pool(pool, start):
    d = f"{OUT}/{pool}"
    os.makedirs(d, exist_ok=True)
    rows = []
    for lo in range(start, END + 1, CHUNK):
        hi = min(lo + CHUNK - 1, END)
        path = f"{d}/{lo}_{hi}.csv.gz"
        if not os.path.exists(path):
            logs = [l for l in get_logs([pool], lo, hi)
                    if l["topics"][0].hex().removeprefix("0x") in (MINT, BURN)]
            with gzip.open(path + ".tmp", "wt", newline="") as f:
                w = csv.writer(f)
                w.writerow(["block", "log_index", "event", "tick_lower", "tick_upper", "liquidity"])
                for l in logs:
                    r = decode(l)
                    w.writerow([r["block"], r["log_index"], r["event"], r["tick_lower"], r["tick_upper"], r["liquidity"]])
            os.replace(path + ".tmp", path)
        with gzip.open(path, "rt") as f:
            rows += list(csv.DictReader(f))
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    meta = []
    for pool in POOLS:
        t0 = time.time()
        cb, sp = created_block(pool), tick_spacing(pool)
        rows = fetch_pool(pool, cb)
        net, gross = {}, {}
        nm = nb = 0
        for r in rows:
            dl = int(r["liquidity"]) * (1 if r["event"] == "mint" else -1)
            nm += r["event"] == "mint"
            nb += r["event"] == "burn"
            for t, dn in ((int(r["tick_lower"]), dl), (int(r["tick_upper"]), -dl)):
                net[t] = net.get(t, 0) + dn
                gross[t] = gross.get(t, 0) + dl
        bad = [t for t, g in gross.items() if g < 0 or t % sp]
        if bad:
            raise RuntimeError(f"{pool}: invalid ticks {bad[:5]}")
        with open(f"{OUT}/{pool}.csv.tmp", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["tick", "net", "gross"])
            for t in sorted(gross):
                if gross[t] > 0:
                    w.writerow([t, net[t], gross[t]])
        os.replace(f"{OUT}/{pool}.csv.tmp", f"{OUT}/{pool}.csv")
        meta.append({"pool": pool, "created_block": cb, "tick_spacing": sp, "mint_events": nm, "burn_events": nb,
                     "initialised_ticks": sum(g > 0 for g in gross.values())})
        print(f"  {pool}: created {cb:,}, spacing {sp}, {nm:,} mints, {nb:,} burns, "
              f"{meta[-1]['initialised_ticks']:,} ticks ({time.time() - t0:.0f}s)", flush=True)
    with open(f"{OUT}/meta.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(meta[0]))
        w.writeheader()
        w.writerows(meta)


if __name__ == "__main__":
    run(main)
