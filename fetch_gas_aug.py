"""Base fee per block for one month (August 2026 by default; FLASH_ARB_PERIOD=sep, see period.py), fetched only at blocks where a universe pool had an event.

Method (JOURNAL.md, "Gas data: base fee at event blocks only"):
- Blocks: every block in data/raw/aug_events.csv.gz (written by pull_august.py after
  reconciliation) with at least one event of any type.
- For each, read baseFeePerGas from the block header via the archive RPC in .env.
- Between those blocks the last value is carried forward when the data is used (see base_fee_at).
- The L1 data fee is not covered; it is measured in phase 2.
Saves in parts of 10,000 blocks to data/raw/aug/gas/ (each written to a temp file, then renamed),
so a rerun resumes. Final file: data/raw/aug_gas.csv (block, ts, base_fee_wei).
"""
import bisect
import csv
import glob
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

import period
from pool_list import RPC, run

PART = 10_000
WORKERS = int(os.getenv("GAS_WORKERS", "8"))
OUT = f"{period.RAW}/gas"
session = requests.Session()


def header(block):
    """(block, timestamp, baseFeePerGas) for one block, retrying with backoff on errors."""
    wait = 1
    for _ in range(12):
        try:
            r = session.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber",
                                        "params": [hex(block), False]}, timeout=60)
            j = r.json()
            if j.get("result"):
                return block, int(j["result"]["timestamp"], 16), int(j["result"]["baseFeePerGas"], 16)
        except Exception:
            pass
        time.sleep(wait)
        wait = min(wait * 2, 60)
    raise RuntimeError(f"could not fetch header for block {block}")


def base_fee_at(gas, block):
    """Base fee at any block: the value at the latest fetched block at or before it."""
    i = bisect.bisect_right(gas.block.values, block) - 1
    if i < 0:
        raise ValueError(f"no fetched base fee at or before block {block}")
    return int(gas.base_fee_wei.values[i])


def main():
    src = period.EVENTS
    if not os.path.exists(src):
        sys.exit(f"{src} not found: run pull_august.py to completion first")
    blocks = sorted(pd.read_csv(src, usecols=["block"]).block.unique().tolist())
    parts = [blocks[i:i + PART] for i in range(0, len(blocks), PART)]
    os.makedirs(OUT, exist_ok=True)
    for t in glob.glob(f"{OUT}/*.tmp"):
        os.remove(t)
    print(f"{len(blocks):,} event blocks in {len(parts)} parts, {WORKERS} workers", flush=True)

    t0, done = time.time(), 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for k, part in enumerate(parts):
            path = f"{OUT}/part_{k:04d}.csv"
            if os.path.exists(path):
                continue
            rows = sorted(ex.map(header, part))
            with open(path + ".tmp", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["block", "ts", "base_fee_wei"])
                w.writerows(rows)
            os.replace(path + ".tmp", path)
            done += 1
            left = (time.time() - t0) / done * (len(parts) - k - 1) / 3600
            print(f"  part {k + 1}/{len(parts)}  ({left:.1f} h left)", flush=True)

    gas = pd.concat([pd.read_csv(p) for p in sorted(glob.glob(f"{OUT}/part_*.csv"))])
    gas = gas.sort_values("block").drop_duplicates("block")
    if gas.block.tolist() != blocks:
        sys.exit(f"coverage check failed: {len(gas):,} fetched vs {len(blocks):,} event blocks")
    gas.to_csv(period.GAS + ".tmp", index=False)
    os.replace(period.GAS + ".tmp", period.GAS)

    g = gas.base_fee_wei / 1e9
    changes = int((gas.base_fee_wei.diff().fillna(0) != 0).sum())
    print(f"\nCoverage: {len(gas):,} of {len(blocks):,} event blocks fetched")
    print(f"Base fee (gwei): min {g.min():.6f}  median {g.median():.6f}  max {g.max():.6f}  "
          f"distinct values {gas.base_fee_wei.nunique()}")
    print(f"Value changes between consecutive event blocks: {changes:,} "
          f"({changes / max(len(gas) - 1, 1):.1%})")
    print("Share of event blocks at the minimum value:", f"{(gas.base_fee_wei == gas.base_fee_wei.min()).mean():.1%}")


if __name__ == "__main__":
    run(main)
