"""Which month the pipeline runs on: the one setting allowed to change between August and September
(JOURNAL.md, design freeze). Set FLASH_ARB_PERIOD=sep for September; the default is August.
Only block ranges and file paths depend on it. August paths are the ones used for the August run.
"""
import os

PERIODS = {
    "aug": {"name": "August 2026", "b0": 489_802_914, "b1": 500_455_224},      # 2026-08-01 .. 08-31 UTC
    "sep": {"name": "September 2026", "b0": 500_455_225, "b1": 510_496_863},   # 2026-09-01 .. 09-30 UTC
}
KEY = os.getenv("FLASH_ARB_PERIOD", "aug")
if KEY not in PERIODS:
    raise SystemExit(f"FLASH_ARB_PERIOD must be one of {sorted(PERIODS)}, not {KEY!r}")
NAME, B0, B1 = PERIODS[KEY]["name"], PERIODS[KEY]["b0"], PERIODS[KEY]["b1"]

RAW = f"data/raw/{KEY}"                          # logs, checkpoints, gas parts, receipts, aave
EVENTS = f"data/raw/{KEY}_events.csv.gz"
RECONCILE = f"data/{KEY}_reconcile.csv"
GAS = f"data/raw/{KEY}_gas.csv"
TICKS = "data/raw/ticks" if KEY == "aug" else f"{RAW}/ticks"
CHECKS = f"data/{KEY}_checks.csv"
CHECKS_STATUS = f"data/{KEY}_checks_status.json"
OPPS = f"data/raw/{KEY}_opportunities.csv"
SCAN_COUNTS = f"data/raw/{KEY}_scan_counts.json"
CLOSING = f"data/raw/{KEY}_closing_txs.csv"
