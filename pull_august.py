"""Pull one month's pool events (August 2026 by default; FLASH_ARB_PERIOD=sep for September, see period.py) for the 12 universe pools, and reconcile them against archive state.

Stage 1 (fetch): every log of the 12 pools from the first block of 2026-08-01 to the last block of
  2026-08-31, from the public endpoint, in 20,000-block chunks (split further if the node refuses).
  Each chunk is decoded and saved to data/raw/aug/logs/, so a rerun resumes where it stopped.
Stage 2 (reconcile): checkpoints every 10,000 blocks (plus the last block). At each checkpoint the
  real pool state (sqrt price, tick, active liquidity; Camelot fees) is read from the archive node
  with one Multicall3 call. For every pool and window, the state is rebuilt from the window's events,
  starting from the archive state at the previous checkpoint:
    Swap        -> price, tick and liquidity are set to the values in the event
    Mint / Burn -> liquidity changes if the position's range covers the current tick
    Fee         -> Camelot's two directional fees are set
  A window whose rebuilt price or liquidity differs from the archive is refetched (that pool alone)
  and rebuilt again. If it still differs it is logged as a persistent mismatch.
Output: data/raw/aug_events.csv.gz (all decoded events, git-ignored) and
  data/aug_reconcile.csv (one row per pool and window).
"""
import csv
import glob
import gzip
import os
import time
from datetime import datetime, timezone

import pandas as pd
from web3 import Web3

import period
from pool_list import RPC, run, snapshot_block, w3

PUBLIC = "https://arb1.arbitrum.io/rpc"
logs_w3 = Web3(Web3.HTTPProvider(os.getenv("ARB_LOGS_RPC_URL") or PUBLIC, request_kwargs={"timeout": 120}))

WINDOW = 10_000
CHUNK = 20_000
OUT = period.RAW
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"

pools = pd.read_csv("data/pools.csv", comment="#")
POOLS = [Web3.to_checksum_address(a) for a in pools.pool]
DEX = dict(zip(POOLS, pools.dex))


def topic(sig):
    return Web3.keccak(text=sig).hex().removeprefix("0x")


EVENTS = {
    topic("Swap(address,address,int256,int256,uint160,uint128,int24)"): "swap",
    topic("Swap(address,address,int256,int256,uint160,uint128,int24,uint128,uint128)"): "swap",  # Pancake
    topic("Mint(address,address,int24,int24,uint128,uint256,uint256)"): "mint",
    topic("Burn(address,int24,int24,uint128,uint256,uint256)"): "burn",
    topic("Fee(uint16,uint16)"): "fee",  # Camelot V3 dynamic fee change
    topic("Collect(address,address,int24,int24,uint128,uint128)"): "collect",
    topic("CollectProtocol(address,address,uint128,uint128)"): "collect_protocol",
    topic("Flash(address,address,uint256,uint256,uint256,uint256)"): "flash",
    topic("Flash(address,address,uint256,uint256,uint256,uint256,uint256,uint256)"): "flash",
}
FIELDS = ["block", "ts", "tx_index", "log_index", "tx_hash", "pool", "event",
          "amount0", "amount1", "sqrtp", "liquidity", "tick", "tick_lower", "tick_upper", "owner",
          "fee_zto", "fee_otz"]


def word(data, i, signed=False):
    v = int.from_bytes(data[32 * i:32 * i + 32], "big")
    return v - (1 << 256) if signed and v >> 255 else v


def tint(t):
    v = int.from_bytes(t, "big")
    return v - (1 << 256) if v >> 255 else v


def decode(log):
    t0 = log["topics"][0].hex().removeprefix("0x")
    ev = EVENTS.get(t0, "unknown:" + t0[:10])
    d = bytes(log["data"])
    r = {"block": log["blockNumber"], "ts": int(log.get("blockTimestamp", "0x0"), 16)
         if isinstance(log.get("blockTimestamp"), str) else log.get("blockTimestamp"),
         "tx_index": log["transactionIndex"], "log_index": log["logIndex"],
         "tx_hash": "0x" + log["transactionHash"].hex().removeprefix("0x"),
         "pool": Web3.to_checksum_address(log["address"]), "event": ev}
    if ev == "swap":
        r.update(amount0=word(d, 0, True), amount1=word(d, 1, True), sqrtp=word(d, 2),
                 liquidity=word(d, 3), tick=word(d, 4, True))
    elif ev == "mint":  # data: sender, amount, amount0, amount1
        r.update(owner="0x" + log["topics"][1].hex()[-40:], tick_lower=tint(log["topics"][2]),
                 tick_upper=tint(log["topics"][3]), liquidity=word(d, 1), amount0=word(d, 2), amount1=word(d, 3))
    elif ev == "burn":  # data: amount, amount0, amount1
        r.update(owner="0x" + log["topics"][1].hex()[-40:], tick_lower=tint(log["topics"][2]),
                 tick_upper=tint(log["topics"][3]), liquidity=word(d, 0), amount0=word(d, 1), amount1=word(d, 2))
    elif ev == "fee":
        r.update(fee_zto=word(d, 0), fee_otz=word(d, 1))
    return r


def get_logs(addresses, lo, hi):
    """All logs for addresses in [lo, hi]. Splits the range on refusals/timeouts, backs off on 429."""
    out, stack, wait, fails = [], [(lo, hi)], 2, 0
    while stack:
        a, b = stack.pop()
        try:
            out += logs_w3.eth.get_logs({"address": addresses, "fromBlock": a, "toBlock": b})
            wait, fails = 2, 0
        except Exception as e:
            msg = str(e).replace(PUBLIC, "<logs rpc>")
            fails += 1
            if fails > 40:
                raise RuntimeError(f"giving up on logs {a}-{b}: {msg[:200]}")
            if "429" in msg or "Too Many" in msg or "rate" in msg.lower() or b - a < 50:
                time.sleep(wait)
                wait = min(wait * 2, 60)
                stack.append((a, b))
            else:
                m = (a + b) // 2
                stack += [(m + 1, b), (a, m)]
    keys = [(l["blockNumber"], l["logIndex"]) for l in out]
    if len(keys) != len(set(keys)):
        raise RuntimeError(f"duplicate logs in {lo}-{hi}")
    return sorted(out, key=lambda l: (l["blockNumber"], l["logIndex"]))


def save(rows, path):
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def load(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def fetch(b0, b1):
    os.makedirs(f"{OUT}/logs", exist_ok=True)
    starts = list(range(b0, b1 + 1, CHUNK))
    t0, done = time.time(), 0
    for i, lo in enumerate(starts):
        hi = min(lo + CHUNK - 1, b1)
        path = f"{OUT}/logs/{lo}_{hi}.csv.gz"
        if os.path.exists(path):
            continue
        save([decode(l) for l in get_logs(POOLS, lo, hi)], path + ".tmp")
        os.replace(path + ".tmp", path)
        done += 1
        if done % 25 == 0:
            el = time.time() - t0
            print(f"  fetched chunk {i + 1}/{len(starts)}  ({el / done * (len(starts) - i - 1) / 60:.0f} min left)",
                  flush=True)


# ---------- archive state at checkpoints ----------
MC_ABI = [{"type": "function", "name": "aggregate3", "stateMutability": "view",
           "inputs": [{"name": "calls", "type": "tuple[]", "components": [
               {"name": "target", "type": "address"}, {"name": "allowFailure", "type": "bool"},
               {"name": "callData", "type": "bytes"}]}],
           "outputs": [{"name": "r", "type": "tuple[]", "components": [
               {"name": "success", "type": "bool"}, {"name": "returnData", "type": "bytes"}]}]}]
mc = w3.eth.contract(address=MULTICALL3, abi=MC_ABI)
SEL = {s: Web3.keccak(text=s)[:4] for s in ["slot0()", "globalState()", "liquidity()"]}


def archive_state(block):
    calls = []
    for p in POOLS:
        calls.append((p, False, SEL["globalState()" if DEX[p] == "CamelotV3" else "slot0()"]))
        calls.append((p, False, SEL["liquidity()"]))
    for attempt in range(8):
        try:
            res = mc.functions.aggregate3(calls).call(block_identifier=block)
            break
        except Exception as e:
            msg = str(e).replace(RPC, "<rpc>")[:150]
            print(f"  archive call at block {block} failed (attempt {attempt + 1}/8), retrying: {msg}", flush=True)
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"archive state call failed at block {block}")
    st = {}
    for j, p in enumerate(POOLS):
        s0, liq = res[2 * j][1], res[2 * j + 1][1]
        st[p] = {"sqrtp": word(s0, 0), "tick": word(s0, 1, True), "liquidity": word(liq, 0)}
        if DEX[p] == "CamelotV3":
            st[p].update(fee_zto=word(s0, 2), fee_otz=word(s0, 3))
    return st


CP_DIR = f"{OUT}/checkpoints"
CP_KEYS = ["block", "pool", "sqrtp", "tick", "liquidity", "fee_zto", "fee_otz"]


def complete(rows):
    """A checkpoint is complete if it has exactly the 12 pools, each with all its fields."""
    if sorted(r["pool"] for r in rows) != sorted(POOLS):
        return False
    need = lambda p: ["sqrtp", "tick", "liquidity"] + (["fee_zto", "fee_otz"] if DEX[p] == "CamelotV3" else [])
    return all(str(r[k]).lstrip("-").isdigit() for r in rows for k in need(r["pool"]))


def write_checkpoint(block, rows):
    """Write one checkpoint file atomically: temp file first, then rename over the final name."""
    path = f"{CP_DIR}/{block}.csv"
    with open(path + ".tmp", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CP_KEYS)
        w.writeheader()
        w.writerows(rows)
    os.replace(path + ".tmp", path)


def migrate_old_checkpoints():
    """The first run appended every checkpoint to one file and was killed mid-write. Keep its
    complete checkpoints as per-checkpoint files and drop the partial one."""
    old = f"{OUT}/checkpoints.csv"
    if not os.path.exists(old):
        return
    by_block = {}
    for r in load(old).to_dict("records"):
        by_block.setdefault(int(r["block"]), []).append(r)
    kept = 0
    for b, rows in by_block.items():
        if complete(rows):
            write_checkpoint(b, rows)
            kept += 1
        else:
            print(f"  dropping partial checkpoint {b} ({len(rows)}/12 pools) from the first run")
    os.replace(old, old + ".migrated")
    print(f"  migrated {kept} complete checkpoints from the first run")


def checkpoint_states(cps):
    os.makedirs(CP_DIR, exist_ok=True)
    migrate_old_checkpoints()
    for t in glob.glob(f"{CP_DIR}/*.tmp"):  # unfinished writes from a killed run
        os.remove(t)
    have = {}
    for path in glob.glob(f"{CP_DIR}/*.csv"):
        rows = load(path).to_dict("records")
        if not complete(rows):
            print(f"  dropping incomplete checkpoint file {os.path.basename(path)}")
            os.remove(path)
            continue
        have[int(os.path.basename(path)[:-4])] = {
            r["pool"]: {k: int(v) for k, v in r.items() if k not in ("block", "pool") and v != ""}
            for r in rows}
    new = [c for c in cps if c not in have]
    print(f"  {len(cps) - len(new)} checkpoints already saved, {len(new)} to fetch", flush=True)
    t0 = time.time()
    for i, c in enumerate(new):
        st = archive_state(c)
        write_checkpoint(c, [{"block": c, "pool": p, **v} for p, v in st.items()])
        have[c] = st
        if (i + 1) % 25 == 0 or i + 1 == len(new):
            left = (time.time() - t0) / (i + 1) * (len(new) - i - 1) / 60
            print(f"  archive checkpoints {i + 1}/{len(new)}  ({left:.0f} min left)", flush=True)
    return have


# ---------- rebuild ----------
def rebuild(start, evs, camelot):
    s = dict(start)
    for e in evs:
        ev = e["event"]
        if ev == "swap":
            s["sqrtp"], s["tick"], s["liquidity"] = int(e["sqrtp"]), int(e["tick"]), int(e["liquidity"])
        elif ev in ("mint", "burn"):
            if int(e["tick_lower"]) <= s["tick"] < int(e["tick_upper"]):
                s["liquidity"] += int(e["liquidity"]) * (1 if ev == "mint" else -1)
        elif ev == "fee" and camelot:
            s["fee_zto"], s["fee_otz"] = int(e["fee_zto"]), int(e["fee_otz"])
    return s


def main():
    b0, b1 = period.B0, period.B1
    print(f"{period.NAME}: blocks {b0:,} to {b1:,} ({b1 - b0 + 1:,} blocks)")

    print("Stage 1: fetching logs")
    fetch(b0, b1)
    ev = pd.concat([load(p) for p in sorted(glob.glob(f"{OUT}/logs/*.csv.gz"))], ignore_index=True)
    ev["block"] = ev["block"].astype(int)
    ev["log_index"] = ev["log_index"].astype(int)
    ev = ev[(ev.block >= b0) & (ev.block <= b1)]

    print("Stage 2: reconciling against archive state")
    cps = list(range(b0 - 1, b1, WINDOW)) + [b1]
    states = checkpoint_states(cps)
    os.makedirs(f"{OUT}/refetch", exist_ok=True)

    groups = {k: g for k, g in ev.groupby(["pool", (ev.block - b0) // WINDOW])}
    replaced, rows = {}, []
    for k in range(1, len(cps)):
        lo, hi = cps[k - 1] + 1, cps[k]
        for p in POOLS:
            camelot = DEX[p] == "CamelotV3"
            g = groups.get((p, k - 1))
            evs = [] if g is None else g.sort_values(["block", "log_index"]).to_dict("records")
            start, truth = states[cps[k - 1]][p], states[hi][p]
            got = rebuild(start, evs, camelot)
            status, n_refetch, extra = "ok", None, ""
            if (got["sqrtp"], got["liquidity"]) != (truth["sqrtp"], truth["liquidity"]):
                fresh = [decode(l) for l in get_logs([p], lo, hi)]
                save(fresh, f"{OUT}/refetch/{p}_{lo}_{hi}.csv.gz")
                fresh = [{kk: str(v) if v is not None else "" for kk, v in r.items()} for r in fresh]
                n_refetch = len(fresh)
                got = rebuild(start, fresh, camelot)
                replaced[(p, k - 1)] = fresh
                if (got["sqrtp"], got["liquidity"]) == (truth["sqrtp"], truth["liquidity"]):
                    status = "fixed_by_refetch"
                else:
                    status = "persistent_mismatch"
                    extra = (f"sqrtp rebuilt={got['sqrtp']} archive={truth['sqrtp']}; "
                             f"liq rebuilt={got['liquidity']} archive={truth['liquidity']}")
            fee_ok = ""
            if camelot:
                fee_ok = (got["fee_zto"], got["fee_otz"]) == (truth["fee_zto"], truth["fee_otz"])
            rows.append({"pool": p, "dex": DEX[p], "window_start": lo, "window_end": hi,
                         "events": len(evs), "status": status, "refetched_events": n_refetch,
                         "tick_match": got["tick"] == truth["tick"], "camelot_fee_match": fee_ok,
                         "detail": extra})

    rec = pd.DataFrame(rows)
    rec.to_csv(period.RECONCILE + ".tmp", index=False)
    os.replace(period.RECONCILE + ".tmp", period.RECONCILE)

    if replaced:
        keep = ev[[(p, (b - b0) // WINDOW) not in replaced for p, b in zip(ev.pool, ev.block)]]
        ev = pd.concat([keep] + [pd.DataFrame(v) for v in replaced.values() if v], ignore_index=True)
        ev["block"] = ev["block"].astype(int)
        ev["log_index"] = ev["log_index"].astype(int)
    ev = ev.sort_values(["block", "log_index"])
    ev.to_csv(period.EVENTS + ".tmp", index=False, compression="gzip")
    os.replace(period.EVENTS + ".tmp", period.EVENTS)

    print(f"\nEvents: {len(ev):,} total")
    print(ev.groupby("event").size().to_string())
    print("\nReconciliation:", rec.status.value_counts().to_dict())
    print("Tick mismatches at checkpoints:", int((~rec.tick_match).sum()))
    cam = rec[rec.dex == "CamelotV3"]
    print("Camelot fee mismatches at checkpoints:", int((cam.camelot_fee_match == False).sum()))  # noqa: E712


if __name__ == "__main__":
    run(main)
