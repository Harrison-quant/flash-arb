"""Opportunity scan, August 2026 (calibration). Method: JOURNAL.md entries "Opportunity scan: method"
and "plan approved with two changes".

Stages (each cached, so a rerun resumes):
  check    Check 1 (tick map vs archive liquidity at all checkpoints) and Check 2 (replay every swap
           with the exact maths, free and with the event's price as limit; revised version, see the
           journal). Writes data/<period>_checks.csv. The scan refuses to run if a check fails.
  aave     Aave V3 flash-loan premium and available balances at every checkpoint (comparison only).
  scan     Replays every transaction, screens both directions of the 14 pool pairs after each one,
           sizes flagged states exactly (flash swap on the buy-side pool), and builds opportunities.
           Writes data/raw/<period>_opportunities.csv. Period: see period.py (FLASH_ARB_PERIOD).
  capture  Fetches the receipt of every closing transaction (stops if more than 300,000), classifies
           it and writes data/raw/<period>_closing_txs.csv, then prints the summary.
Usage: python scan_august.py [check] [aave] [screen] [scan] [capture] | all   (stages run in that order;
  screen lists the blocks where a state passes the fee screen, for fetch_gas_aug.py screened)
"""
import csv
import glob
import gzip
import itertools
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from web3 import Web3

import period
import v3math
from pool_list import RPC, TOKENS, run, w3
from pull_august import DEX, POOLS, word

B0, B1 = period.B0, period.B1
WINDOW = 10_000
CPS = list(range(B0 - 1, B1, WINDOW)) + [B1]
GAS_UNITS = 350_000
EVENTS_FILE = period.EVENTS
MAX_CLOSING = 300_000

pools_df = pd.read_csv("data/pools.csv", comment="#")
PAIR = {Web3.to_checksum_address(p): pair for p, pair in zip(pools_df.pool, pools_df.pair)}
FEE_TEXT = {Web3.to_checksum_address(p): f for p, f in zip(pools_df.pool, pools_df.fee)}
LABEL = {p: f"{PAIR[p]} {DEX[p]} {FEE_TEXT[p].split(' (')[0].split('/')[0]}" for p in POOLS}
# Pool pairs: same pair, every combination. ARB pairs have one pool and drop out.
POOL_PAIRS = [(a, b) for a, b in itertools.combinations(POOLS, 2) if PAIR[a] == PAIR[b]]
# Directions: (A, B) means token0 is cheaper in A: pay token1 into A, sell token0 into B.
DIRECTIONS = [d for a, b in POOL_PAIRS for d in ((a, b), (b, a))]
DIRS_BY_POOL = {p: [d for d in DIRECTIONS if p in d] for p in POOLS}
REF = {"WETH/USDC": "0xC6962004f452bE9203591991D15f6b388e09E8D0",   # USD conversion pools
       "WETH/USDT": "0x641C00A822e8b671738d32a431a4Fb6074E5c79d"}
PROFIT_TOKEN = {"WETH/USDC": "USDC", "WETH/USDT": "USDT", "WBTC/WETH": "WETH"}  # token1 of each pair
DECIMALS = {"USDC": 6, "USDT": 6, "WETH": 18}


def fee_pips(p):
    return int(round(float(FEE_TEXT[p].split("%")[0]) * 10_000))


def checkpoint(block):
    rows = list(csv.DictReader(open(f"{period.RAW}/checkpoints/{block}.csv")))
    return {r["pool"]: r for r in rows}


def initial_pools():
    """Pool objects at the end of July: archive state at block B0-1 plus the tick maps."""
    meta = {r["pool"]: r for r in csv.DictReader(open(f"{period.TICKS}/meta.csv"))}
    start = checkpoint(B0 - 1)
    pools = {}
    for p in POOLS:
        s = start[p]
        if DEX[p] == "CamelotV3":
            fz, fo = int(s["fee_zto"]), int(s["fee_otz"])
        else:
            fz = fo = fee_pips(p)
        pool = v3math.Pool(int(meta[p]["tick_spacing"]), int(s["sqrtp"]), int(s["tick"]), int(s["liquidity"]), fz, fo,
                           unit=int(meta[p]["bitmap_unit"]))
        for r in csv.DictReader(open(f"{period.TICKS}/{p}.csv")):
            t, net, gross = int(r["tick"]), int(r["net"]), int(r["gross"])
            pool.net[t], pool.gross[t] = net, gross
            pool.init.append(t // pool.unit)
        pool.init.sort()
        pools[p] = pool
    return pools


def transactions():
    """Stream August events grouped by transaction, in chain order."""
    with gzip.open(EVENTS_FILE, "rt") as f:
        cur, key = [], None
        for r in csv.DictReader(f):
            k = (r["block"], r["tx_hash"])
            if k != key and cur:
                yield cur
                cur = []
            key = k
            cur.append(r)
        if cur:
            yield cur


def apply(pool, e):
    """Apply one event to the pool state (the same rules the reconciliation verified)."""
    ev = e["event"]
    if ev == "swap":
        pool.sqrtp, pool.tick, pool.liquidity = int(e["sqrtp"]), int(e["tick"]), int(e["liquidity"])
    elif ev in ("mint", "burn"):
        tl, tu, dl = int(e["tick_lower"]), int(e["tick_upper"]), int(e["liquidity"])
        if ev == "burn":
            dl = -dl
        if tl <= pool.tick < tu:
            pool.liquidity += dl
        pool.modify(tl, tu, dl)
    elif ev == "fee":
        pool.fee_zfo, pool.fee_ofz = int(e["fee_zto"]), int(e["fee_otz"])


# ---------------------------------------------------------------- stage: check
def stage_check():
    pools = initial_pools()
    cp_iter = iter(CPS[1:])
    next_cp = next(cp_iter)
    c1_fail, c1_n = [], 0
    stats = {p: {"swaps": 0, "exact": 0, "free_exact": 0, "limit_exact": 0, "worst": ""} for p in POOLS}

    def run_check1(cp):
        nonlocal c1_n
        truth = checkpoint(cp)
        for p in POOLS:
            c1_n += 1
            from_map, arch = pools[p].active_from_map(), int(truth[p]["liquidity"])
            if from_map != arch or pools[p].liquidity != arch or pools[p].tick != int(truth[p]["tick"]):
                c1_fail.append((cp, p, from_map, arch))

    # Check 1 at the start state too
    truth0 = checkpoint(B0 - 1)
    for p in POOLS:
        c1_n += 1
        if pools[p].active_from_map() != int(truth0[p]["liquidity"]):
            c1_fail.append((B0 - 1, p, pools[p].active_from_map(), int(truth0[p]["liquidity"])))

    t0, n = time.time(), 0
    for tx in transactions():
        blk = int(tx[0]["block"])
        while next_cp is not None and blk > next_cp:
            run_check1(next_cp)
            next_cp = next(cp_iter, None)
        for e in tx:
            p = e["pool"]
            pool = pools[p]
            if e["event"] == "swap":
                a0, a1 = int(e["amount0"]), int(e["amount1"])
                zfo = a0 > 0
                amt, out_want = (a0, -a1) if zfo else (a1, -a0)
                if amt > 0:
                    # Revised Check 2 (journal 2026-10-18): reproduced if the free replay or the replay
                    # with the event's end price as limit gives exactly the event's input, output, price.
                    want = int(e["sqrtp"])
                    free = pool.swap(zfo, amt) == (amt, out_want, want)
                    lim = pool.swap(zfo, amt, limit=want) == (amt, out_want, want)
                    st = stats[p]
                    st["swaps"] += 1
                    st["free_exact"] += free
                    st["limit_exact"] += lim
                    st["exact"] += free or lim
                    if not (free or lim) and not st["worst"]:
                        st["worst"] = f"{e['block']}:{e['log_index']}"
            apply(pool, e)
        n += 1
        if n % 200_000 == 0:
            print(f"  check: {n:,} transactions, block {blk:,} ({time.time() - t0:.0f}s)", flush=True)
    while next_cp is not None:
        run_check1(next_cp)
        next_cp = next(cp_iter, None)

    rows, ok = [], not c1_fail
    scanned = {p for d in DIRECTIONS for p in d}
    for p in POOLS:
        st = stats[p]
        n = st["swaps"] or 1
        exact_share = st["exact"] / n
        passed = exact_share >= 0.999
        gating = p in scanned          # the ARB pools are reported but don't gate
        if gating:
            ok &= passed
        rows.append({"pool": p, "label": LABEL[p], "swaps": st["swaps"], "exact": st["exact"],
                     "exact_share": round(exact_share, 6), "free_exact_share": round(st["free_exact"] / n, 6),
                     "limit_exact_share": round(st["limit_exact"] / n, 6), "first_miss": st["worst"],
                     "gating": gating, "check2_pass": passed})
    df = pd.DataFrame(rows)
    df.to_csv(period.CHECKS, index=False)
    print(df[["label", "swaps", "exact_share", "free_exact_share", "limit_exact_share", "gating", "check2_pass"]].to_string(index=False))
    print(f"Check 1: {c1_n - len(c1_fail):,} of {c1_n:,} pool-checkpoints match"
          + ("" if not c1_fail else f"; first failures: {c1_fail[:3]}"))
    with open(period.CHECKS_STATUS, "w") as f:
        json.dump({"check1_checks": c1_n, "check1_failures": len(c1_fail), "all_pass": bool(ok)}, f)
    if not ok:
        sys.exit(f"A check failed: the scan will not run. See {period.CHECKS}.")
    print("All checks passed.")


# ---------------------------------------------------------------- stage: aave
AAVE_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
ATOKENS = {"USDC": "0x724dc807b04555b71ed48a6896b6F41593b8C637",
           "USDT": "0x6ab707Aca953eDAeFBc4fD23bA73294241490620",
           "WETH": "0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8"}


def stage_aave():
    from pull_august import mc
    path = f"{period.RAW}/aave_checkpoints.csv"
    have = set()
    if os.path.exists(path):
        have = {int(r["block"]) for r in csv.DictReader(open(path))}
    sel_prem = Web3.keccak(text="FLASHLOAN_PREMIUM_TOTAL()")[:4]
    sel_bal = Web3.keccak(text="balanceOf(address)")[:4]
    calls = [(AAVE_POOL, False, sel_prem)] + [
        (TOKENS[s], False, sel_bal + bytes(12) + bytes.fromhex(ATOKENS[s][2:])) for s in ("USDC", "USDT", "WETH")]
    new = [c for c in CPS if c not in have]
    rows = list(csv.DictReader(open(path))) if os.path.exists(path) else []
    for i, c in enumerate(new):
        for attempt in range(8):
            try:
                res = mc.functions.aggregate3(calls).call(block_identifier=c)
                break
            except Exception:
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"aave read failed at {c}")
        rows.append({"block": c, "premium_bps": word(res[0][1], 0), "USDC": word(res[1][1], 0),
                     "USDT": word(res[2][1], 0), "WETH": word(res[3][1], 0)})
        if (i + 1) % 50 == 0 or i == len(new) - 1:
            with open(path + ".tmp", "w", newline="") as f:  # whole file rewritten, then renamed
                w = csv.DictWriter(f, fieldnames=["block", "premium_bps", "USDC", "USDT", "WETH"])
                w.writeheader()
                w.writerows(rows)
            os.replace(path + ".tmp", path)
            print(f"  aave checkpoints {i + 1}/{len(new)}", flush=True)
    df = pd.read_csv(path).drop_duplicates("block").sort_values("block")
    if len(df) != len(CPS):
        sys.exit(f"aave checkpoints incomplete: {len(df)} of {len(CPS)}")
    print(f"Aave premium (bps) over August: {sorted(df.premium_bps.unique())}")


def load_aave():
    df = pd.read_csv(f"{period.RAW}/aave_checkpoints.csv").drop_duplicates("block").sort_values("block")
    return df.block.values, df


# ---------------------------------------------------------------- stage: scan
def golden_max(f, lo, hi):
    """Integer golden-section search for the max of a concave f on [lo, hi]."""
    cache = {}

    def F(x):
        if x not in cache:
            cache[x] = f(x)
        return cache[x]

    r = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - int((b - a) * r), a + int((b - a) * r)
    while b - a > max(3, int(1e-6 * b)):
        if c >= d:  # integer rounding collapsed the two probes
            c, d = (a + b) // 2, (a + b) // 2 + 1
        if F(c) < F(d):
            a, c = c, d                     # keep d as the new lower probe
            d = a + int((b - a) * r)
            if d <= c:
                d = c + 1
        else:
            b, d = d, c                     # keep c as the new upper probe
            c = b - int((b - a) * r)
            if c >= d:
                c = d - 1
    best = max(range(a, b + 1), key=F) if b - a <= 64 else max((a, (a + b) // 2, b), key=F)
    return best, F(best)


def size_trade(A, B, fee_rate_num=0, cap=None):
    """Best input x of token1 into A (then token0 into B). Returns (x, gross_token1, x_up) or None.
    fee_rate_num: flash-loan premium in bps (0 for the flash swap)."""
    if A.liquidity == 0 or B.liquidity == 0:
        return None
    k = math.sqrt((1e6 - A.fee_ofz) * (1e6 - B.fee_zfo)) / 1e6
    target = int(B.sqrtp * k)
    if target <= A.sqrtp:
        return None
    target = min(target, v3math.MAX_SQRT - 1)
    x_up, _, _ = A.swap(False, 1 << 200, limit=target)
    if cap is not None:
        x_up = min(x_up, cap)
    if x_up < 2:
        return None

    def g(x):
        if x <= 0:
            return 0
        _, out0, _ = A.swap(False, x)
        if out0 <= 0:
            return -x
        _, out1, _ = B.swap(True, out0)
        prem = (x * fee_rate_num + 5000) // 10000 if fee_rate_num else 0
        return out1 - x - prem

    x, gross = golden_max(g, 0, x_up)
    return x, gross, x_up


def usd_rates(pools):
    """USD per whole token for the profit tokens, from the reference pools' current mid prices."""
    s = pools[REF["WETH/USDC"]].sqrtp / 2 ** 96
    eth = s * s * 10 ** (18 - 6)
    s2 = pools[REF["WETH/USDT"]].sqrtp / 2 ** 96
    usdt_per_eth = s2 * s2 * 10 ** (18 - 6)
    return {"USDC": 1.0, "USDT": eth / usdt_per_eth, "WETH": eth}


def passes_screen(A, B):
    """Screen: p_B (1 - f_A)(1 - f_B) > p_A, marginal and exact up to float precision."""
    rA, rB = A.sqrtp / 2 ** 96, B.sqrtp / 2 ** 96
    return (rB * rB) * (1 - A.fee_ofz / 1e6) * (1 - B.fee_zfo / 1e6) > (rA * rA) * (1 - 1e-9)


def stage_screen():
    """Blocks with at least one state passing the screen: the only blocks whose base fee the scan
    uses (journal 2026-10-19, implementation change). Writes <RAW>/screen_blocks.csv."""
    st = json.load(open(period.CHECKS_STATUS))
    if not st["all_pass"]:
        sys.exit("Checks did not pass; not screening.")
    pools = initial_pools()
    blocks, n_states, n_flag = {}, 0, 0
    for tx in transactions():
        blk = int(tx[0]["block"])
        touched = []
        for e in tx:
            apply(pools[e["pool"]], e)
            if e["pool"] not in touched:
                touched.append(e["pool"])
        for d in {d for p in touched for d in DIRS_BY_POOL[p]}:
            n_states += 1
            if passes_screen(pools[d[0]], pools[d[1]]):
                n_flag += 1
                blocks[blk] = blocks.get(blk, 0) + 1
    path = f"{period.RAW}/screen_blocks.csv"
    pd.DataFrame({"block": sorted(blocks), "flagged_states": [blocks[b] for b in sorted(blocks)]}).to_csv(path + ".tmp", index=False)
    os.replace(path + ".tmp", path)
    print(f"Screen: {n_states:,} states, {n_flag:,} passed, in {len(blocks):,} distinct blocks -> {path}")


def stage_scan():
    st = json.load(open(period.CHECKS_STATUS))
    if not st["all_pass"]:
        sys.exit("Checks did not pass; not scanning.")
    pools = initial_pools()
    gas = pd.read_csv(period.GAS)
    base_fee = dict(zip(gas.block.values.tolist(), gas.base_fee_wei.values.tolist()))
    aave_blocks, aave = load_aave()

    def aave_terms(block, token):
        i = max(0, min(len(aave_blocks) - 2, int(aave_blocks.searchsorted(block, side="right")) - 1))
        lo, hi = aave.iloc[i], aave.iloc[i + 1]
        return int(max(lo.premium_bps, hi.premium_bps)), int(min(int(lo[token]), int(hi[token])))

    open_ep = {}
    episodes = []
    n_states = n_flag = 0
    t0 = time.time()
    for ti, tx in enumerate(transactions()):
        blk = int(tx[0]["block"])
        touched = []
        swaps = {}
        for e in tx:
            p = e["pool"]
            apply(pools[p], e)
            if p not in touched:
                touched.append(p)
            if e["event"] == "swap":
                swaps[p] = swaps.get(p, 0) + int(e["amount0"])
        dirs = {d for p in touched for d in DIRS_BY_POOL[p]}
        if not dirs:
            continue
        rates = usd_rates(pools)
        gas_usd = None   # only needed (and only fetched) at blocks where a state passes the screen
        for d in dirs:
            A, B = pools[d[0]], pools[d[1]]
            n_states += 1
            net = None
            if passes_screen(A, B):
                n_flag += 1
                if gas_usd is None:
                    gas_usd = GAS_UNITS * base_fee[blk] * rates["WETH"] / 1e18
                sized = size_trade(A, B)
                if sized:
                    tok = PROFIT_TOKEN[PAIR[d[0]]]
                    x, gross, _ = sized
                    gross_usd = gross / 10 ** DECIMALS[tok] * rates[tok]
                    net = gross_usd - gas_usd
            ep = open_ep.get(d)
            if net is not None and net > 0:
                rec = (blk, ti, net)
                if ep is None:
                    tok = PROFIT_TOKEN[PAIR[d[0]]]
                    prem, cap = aave_terms(blk, tok)
                    aave_sized = size_trade(A, B, prem, cap)
                    aave_net = (aave_sized[1] / 10 ** DECIMALS[tok] * rates[tok] - gas_usd) if aave_sized else None
                    open_ep[d] = {"buy_pool": d[0], "sell_pool": d[1], "pair": PAIR[d[0]],
                                  "open_block": blk, "open_tx": tx[0]["tx_hash"], "open_ts": tx[0]["ts"], "open_ti": ti,
                                  "open_net_usd": net, "open_size_token1": x, "open_size_usd":
                                  x / 10 ** DECIMALS[tok] * rates[tok], "open_gas_usd": gas_usd,
                                  "aave_net_usd": aave_net, "aave_premium_bps": prem,
                                  "states": [rec]}
                else:
                    ep["states"].append(rec)
            elif ep is not None:
                a_sw, b_sw = swaps.get(d[0]), swaps.get(d[1])
                ep.update(close_block=blk, close_tx=tx[0]["tx_hash"], close_ts=tx[0]["ts"], close_ti=ti,
                          close_swap_buy_pool=a_sw, close_swap_sell_pool=b_sw)
                episodes.append(ep)
                del open_ep[d]
        if ti % 200_000 == 0 and ti:
            print(f"  scan: {ti:,} txs, block {blk:,}, {n_flag:,} flagged states, {len(episodes) + len(open_ep):,} "
                  f"opportunities ({time.time() - t0:.0f}s)", flush=True)
    for ep in open_ep.values():
        ep.update(close_block=None, close_tx=None, close_ts=None, close_ti=None, close_swap_buy_pool=None,
                  close_swap_sell_pool=None)
        episodes.append(ep)

    out = []
    for ep in episodes:
        sts = ep.pop("states")
        ep["n_states"] = len(sts)
        ep["max_net_usd"] = max(s[2] for s in sts)
        ep["close_blocks_after_open"] = None if ep["close_block"] is None else ep["close_block"] - ep["open_block"]
        ep["universe_txs_between"] = None if ep["close_ti"] is None else ep["close_ti"] - ep["open_ti"] - 1
        for N in (1, 2, 4, 8):
            limit = ep["open_block"] + N
            still_open = ep["close_block"] is None or ep["close_block"] > limit
            last = [s for s in sts if s[0] <= limit]
            ep[f"reach_N{N}"] = still_open
            ep[f"net_at_N{N}"] = last[-1][2] if still_open and last else None
        out.append(ep)
    # Fixed row order: set iteration order varies between runs (string hashing), values don't.
    df = pd.DataFrame(out).sort_values(["open_ti", "buy_pool", "sell_pool"]).reset_index(drop=True)
    df.to_csv(period.OPPS + ".tmp", index=False)
    os.replace(period.OPPS + ".tmp", period.OPPS)
    with open(period.SCAN_COUNTS, "w") as f:
        json.dump({"states_evaluated": n_states, "states_flagged": n_flag, "opportunities": len(df)}, f)
    print(f"Scan done: {n_states:,} states evaluated, {n_flag:,} flagged by the screen, {len(df):,} opportunities")


# ---------------------------------------------------------------- stage: capture
TRANSFER = Web3.keccak(text="Transfer(address,address,uint256)").hex().removeprefix("0x")


def receipt_summary(h):
    s = requests.Session()
    wait = 1
    for _ in range(12):
        try:
            r = s.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt",
                                  "params": [h]}, timeout=60).json().get("result")
            if r:
                frm, to = r["from"].lower(), (r.get("to") or "").lower()
                parties = {frm, to}
                net = {}
                for lg in r["logs"]:
                    t = lg["topics"]
                    if len(t) == 3 and t[0].removeprefix("0x") == TRANSFER and lg["data"] not in ("0x", ""):
                        tok, a, b = lg["address"].lower(), "0x" + t[1][-40:], "0x" + t[2][-40:]
                        v = int(lg["data"][:66], 16)
                        if b in parties:
                            net[tok] = net.get(tok, 0) + v
                        if a in parties:
                            net[tok] = net.get(tok, 0) - v
                gain = bool(net) and all(v >= 0 for v in net.values()) and any(v > 0 for v in net.values())
                return {"tx_hash": h, "from": frm, "to": to, "status": int(r["status"], 16),
                        "timeboosted": bool(r.get("timeboosted")), "gas_used": int(r["gasUsed"], 16),
                        "gas_used_for_l1": int(r.get("gasUsedForL1", "0x0"), 16),
                        "effective_gas_price": int(r["effectiveGasPrice"], 16), "net_gain": gain}
        except Exception:
            pass
        time.sleep(wait)
        wait = min(wait * 2, 60)
    raise RuntimeError(f"receipt fetch failed for {h}")


def stage_capture():
    opp = pd.read_csv(period.OPPS)
    closing = sorted(set(opp.close_tx.dropna()))
    print(f"{len(opp):,} opportunities, {len(closing):,} distinct closing transactions")
    if len(closing) > MAX_CLOSING:
        sys.exit(f"More than {MAX_CLOSING:,} closing transactions: stopping before fetching (stop rule).")
    d = f"{period.RAW}/receipts"
    os.makedirs(d, exist_ok=True)
    done = set()
    for p in glob.glob(f"{d}/part_*.csv"):
        done |= set(pd.read_csv(p).tx_hash)
    todo = [h for h in closing if h not in done]
    parts = [todo[i:i + 5000] for i in range(0, len(todo), 5000)]
    start = len(glob.glob(f"{d}/part_*.csv"))
    with ThreadPoolExecutor(8) as ex:
        for k, part in enumerate(parts):
            rows = list(ex.map(receipt_summary, part))
            path = f"{d}/part_{start + k:04d}.csv"
            pd.DataFrame(rows).to_csv(path + ".tmp", index=False)
            os.replace(path + ".tmp", path)
            print(f"  receipts part {k + 1}/{len(parts)}", flush=True)
    rc = pd.concat([pd.read_csv(p) for p in glob.glob(f"{d}/part_*.csv")]).drop_duplicates("tx_hash")
    rc.to_csv(period.CLOSING, index=False)
    summarise(opp, rc)


def classify(row):
    if pd.isna(row.close_tx):
        return "unclosed"
    a, b = row.close_swap_buy_pool, row.close_swap_sell_pool
    if pd.notna(a) and pd.notna(b):
        # Correction (journal 2026-10-20): swaps in both pools in opposite directions count as two-pool
        # arbitrage whoever receives the profit. The old rule also required a net gain at tx.from/tx.to,
        # which mislabelled arbitrage contracts that pay the profit to a third address.
        if (a > 0) != (b > 0) and a != 0 and b != 0:
            return "two-pool arbitrage"
        return "other"
    if pd.notna(a) or pd.notna(b):
        return "one-sided swap"
    return "other"


def summarise(opp, rc):
    opp = opp.merge(rc, left_on="close_tx", right_on="tx_hash", how="left")
    opp["group"] = opp.apply(classify, axis=1)
    opp.to_csv(period.OPPS.replace(".csv", "_classified.csv"), index=False)
    counts = json.load(open(period.SCAN_COUNTS))
    P = opp.open_net_usd
    print(f"\n=== SUMMARY ({period.NAME}, primary = flash swap) ===")
    print(f"States evaluated {counts['states_evaluated']:,}; flagged by screen {counts['states_flagged']:,}; "
          f"opportunities {len(opp):,}")
    # Reporting correction (journal 2026-10-18): primary totals keep only the largest opportunity per
    # opening transaction; the same figures without the top 3 opening transactions are shown alongside.
    best = opp.sort_values("open_net_usd", ascending=False).drop_duplicates("open_tx")
    top3 = best.open_tx.head(3).tolist()
    print("Top 3 opening transactions (removed in the 'ex top 3' lines):")
    for t, b, v in zip(best.open_tx.head(3), best.open_block.head(3), best.open_net_usd.head(3)):
        print(f"  {t} block {b} ${v:,.2f}")
    for name, sub in (("PRIMARY, largest per opening tx", best),
                      ("largest per opening tx, ex top 3", best[~best.open_tx.isin(top3)]),
                      ("all pool pairs (overlapping)", opp)):
        print(f"\n  [{name}]")
        for b in (0, 0.10, 1, 10, 100):
            s = sub[sub.open_net_usd > b]
            print(f"  opening net > ${b:g}: {len(s):,} opportunities, total opening net ${s.open_net_usd.sum():,.2f}")
    print("\nOpening net USD percentiles (largest per opening tx):",
          best.open_net_usd.quantile([.5, .9, .99, 1]).round(4).to_dict())
    print("Opening net USD percentiles (all pool pairs):", P.quantile([.5, .9, .99, 1]).round(4).to_dict())
    print("Max net during run, total: $%.2f" % opp.max_net_usd.sum())
    print("\nBy pool pair (direction-agnostic):")
    opp["pool_pair"] = [" vs ".join(sorted([LABEL[a], LABEL[b]])) for a, b in zip(opp.buy_pool, opp.sell_pool)]
    print(opp.groupby("pool_pair").agg(n=("open_net_usd", "size"), total=("open_net_usd", "sum"),
                                       median=("open_net_usd", "median")).sort_values("total", ascending=False).round(3).to_string())
    closed = opp[opp.close_block.notna()]
    lag = closed.close_blocks_after_open
    print("Universe-pool transactions between opening and closing: median",
          closed.universe_txs_between.median(), "p90", closed.universe_txs_between.quantile(.9))
    print("\nDuration (blocks from opening to closing):",
          {"same block": int((lag == 0).sum()), "1": int((lag == 1).sum()), "2-4": int(lag.between(2, 4).sum()),
           "5-20": int(lag.between(5, 20).sum()), ">20": int((lag > 20).sum()), "unclosed": int(opp.close_block.isna().sum())})
    print("\nWho closed it:")
    tot_n, tot_p = len(opp), P.sum()
    for g, s in opp.groupby("group"):
        tb = s[s.timeboosted == True]  # noqa: E712
        print(f"  {g:<18} n={len(s):>8,} ({len(s) / tot_n:6.1%})  opening profit ${s.open_net_usd.sum():>12,.2f} "
              f"({s.open_net_usd.sum() / tot_p:6.1%})  express lane: {len(tb) / max(len(s), 1):6.1%} of count, "
              f"{tb.open_net_usd.sum() / max(s.open_net_usd.sum(), 1e-12):6.1%} of profit")
    for col in ("to", "from"):
        top = opp[opp.close_tx.notna()].groupby(col).open_net_usd.agg(["size", "sum"]).sort_values("sum", ascending=False)
        sh = top["sum"].cumsum() / max(top["sum"].sum(), 1e-12)
        shn = top["size"].sort_values(ascending=False).cumsum() / max(top["size"].sum(), 1)
        print(f"\nTop closers by tx.{col}: profit share top1 {sh.iloc[0]:.1%}, top3 {sh.iloc[min(2, len(sh) - 1)]:.1%}, "
              f"top10 {sh.iloc[min(9, len(sh) - 1)]:.1%}; count share top1 {shn.iloc[0]:.1%}, top3 "
              f"{shn.iloc[min(2, len(shn) - 1)]:.1%}, top10 {shn.iloc[min(9, len(shn) - 1)]:.1%}")
        print(top.head(10).round(2).to_string())
    print("\nLeft for a late bot:")
    n_events = opp.open_tx.nunique()
    for name, sub in (("PRIMARY, largest per opening tx", opp),
                      ("largest per opening tx, ex top 3", opp[~opp.open_tx.isin(top3)])):
        print(f"  [{name}]")
        for N in (1, 2, 4, 8):
            v = sub[sub[f"reach_N{N}"]].groupby("open_tx")[f"net_at_N{N}"].max().dropna()
            print(f"  N={N}: {len(v):,} opening txs still open ({len(v) / n_events:.1%} of {n_events:,}); "
                  f"net at that point total ${v.sum():,.2f}; > $1: {(v > 1).sum():,}; > $10: {(v > 10).sum():,}")
    print("  [all pool pairs (overlapping)]")
    for N in (1, 2, 4, 8):
        s = opp[opp[f"reach_N{N}"]]
        v = s[f"net_at_N{N}"].dropna()
        print(f"  N={N}: {len(s):,} still open ({len(s) / tot_n:.1%}); net at that point total ${v.sum():,.2f}; "
              f"> $1: {(v > 1).sum():,}; > $10: {(v > 10).sum():,}")
    a = opp.aave_net_usd
    print(f"\nAave comparison: positive for {(a > 0).sum():,} of {len(opp):,}; total ${a[a > 0].sum():,.2f} "
          f"vs flash swap ${P.sum():,.2f}")


def main():
    stages = set(sys.argv[1:]) or {"all"}
    if stages & {"check", "all"}:
        stage_check()
    if stages & {"aave", "all"}:
        stage_aave()
    if "screen" in stages:
        stage_screen()
    if stages & {"scan", "all"}:
        stage_scan()
    if stages & {"capture", "all"}:
        stage_capture()


if __name__ == "__main__":
    run(main)
