# flash-arb - handover for Claude Code

## What this is
A research project on flash-loan DEX arbitrage on Arbitrum One. Harrison brings the ideas and judgement;
Claude writes and runs the code. Explain what the code does in plain terms. Concise, no emojis.

The research question: **how much DEX arbitrage is actually available to a retail bot on Arbitrum,
and who captures it?** The bot is the measuring tool. We expect it to be unprofitable; an honest
"nothing is left for us, and here is why" is a valid result.

## Status (2026-10-26)
- **Phase 1 (measure) is complete.** August calibrated, design frozen, September evaluated once on
  2026-10-19. The evaluation period is spent. Variants tested: 1.
- **Next up: phase 2** (contract on a local fork). Nothing for phase 2 has been written yet.
- JOURNAL.md has the full record; README.md is the public summary. If the two disagree, the journal
  wins and the README is fixed.

## Rules (same discipline as hyperliquid-strategy)
- JOURNAL.md is the research log: research content only, append new entries at the bottom, never
  edit old ones. Corrections go in a new entry. The "Running totals" section near the top is the one
  exception: it is a status block updated in place (variants count, corrections list).
- Fix pools, dates and thresholds BEFORE looking at results. Record them in the journal first.
- Calibration period: 2026-08-01 to 2026-08-31. Evaluation period: 2026-09-01 to 2026-09-30.
  September has been looked at. Any further analysis of September is descriptive only and must say
  so; nothing may be tuned on it.
- Count every variant tried. Distinguish in the journal between a variant (a method choice), a
  correction (a bug or mis-specified check), and an implementation change (same results, verified).
- Security: never put a private key or RPC key in code or git. Use a .env file listed in .gitignore.
  Any live wallet is a fresh wallet with a few dollars only. Ask Harrison before any action that
  signs or sends a transaction.

## Phase 1 setup (frozen)
- Universe: 12 pools with TVL > $250k at block 489,802,914 (2026-08-01 00:00 UTC) for WETH/USDC,
  WETH/USDT, WBTC/WETH, ARB/WETH, ARB/USDC on Uniswap V3, Camelot (V2+V3), SushiSwap (V2+V3),
  PancakeSwap V3. List in data/pools.csv. 14 same-pair pool pairs scanned (WETH/USDC 10, WBTC/WETH 3,
  WETH/USDT 1); the two ARB pools have no partner. Uniswap V4 and triangular routes are out of scope
  (V4 holds 3-12% of liquidity for these pairs, measured in v4_tvl.py).
- Data: every event of the 12 pools from the public endpoint, reconciled against archive state every
  10,000 blocks (0 mismatches both months). Base fee from block headers. L1 data fee not included.
- Maths: exact-integer Python port of Uniswap V3 swap maths (v3math.py), also used for PancakeSwap V3
  and Camelot V3 (Algebra; tick table indexed by raw tick). Tick maps read from the archive at the
  block before each period. Check 1 (liquidity at checkpoints) and revised Check 2 (every swap
  reproduced exactly) passed in both months; the top 10 September cases also match QuoterV2 on-chain.
- Financing: flash swap on the buy-side pool (primary); Aave V3 at 5 bps reported for comparison.
  Gas: fixed 350,000 L2 units x block base fee.
- Opportunity: maximal run of post-transaction states with net profit > 0, per pool pair and
  direction. Primary totals keep the largest opportunity per opening transaction. Late bot: still
  open after block open+N, N = 2 primary (1, 4, 8 shown).
- Code: period.py selects the month (FLASH_ARB_PERIOD=sep); pull_august.py, fetch_gas_aug.py,
  read_ticks.py, scan_august.py run for either month despite the names. Raw data in data/raw/
  (git-ignored); summaries in data/aug_scan_summary.txt and data/sep_scan_summary.txt.

## Phase 1 key results (flash swap, L1 fee excluded, so overstated)
| | August | September |
|---|---|---|
| Opportunities (largest per opening tx) | 14,837, $3,274 | 13,302, $35,318 |
| Same, ex top 3 events | $1,818 | $23,160 |
| Left for a bot 2 blocks late | 633, $352 | 566, $7,161 |
| Median opportunity | $0.011 | $0.011 |
- Profit is concentrated in rare shocks: August's top is two WBTC liquidations routed through a thin
  pool; 94.8% of September's total sits in one ~2-hour window on 24 Sep (multi-million-dollar WETH
  trades moving the deepest pool ~6%). Outside that window, September left $48 for a late bot.
- Who closes gaps: two-pool arbitrage 13.9% of profit in August, 46.8% in September; single-pool
  swaps most of the rest. Express lane share is small (September ~0.5% of profit; August's 50.9% of
  one-sided profit is the two liquidation backruns, ~7% without them).
- Most gaps close in the same or next block.

## Corrections and changes (all in the journal)
1. Camelot tick-table indexing bug in the maths port, fixed before any check ran.
2. Check 2 failed as written (did not allow for price-limited swaps); revised after seeing it fail,
   approved by Harrison, logged as a correction.
3. Tick maps read from the archive instead of replaying all history (too slow; verified identical
   on one pool).
4. Reporting: totals keep the largest opportunity per opening tx, top-3-removed shown alongside
   (decided before September).
5. Base fee fetched only at blocks passing the fee screen (identical results, verified on August);
   deterministic row order.
6. Capture label: any closing tx swapping in both pools in opposite directions counts as two-pool
   arbitrage, whoever receives the profit (both months recomputed, 2026-10-20).

## Open limitations to carry into phase 2
- L1 data fee not counted; 350,000 gas units is an estimate. Phase 2 measures both.
- Gas of failed attempts and competition among late bots for the same leftovers not modelled.
- Only two months, each dominated by one rare event.

## Phase 2 plan (next)
- Solidity + Foundry, local Arbitrum fork from the archive RPC (key in .env).
- Contract: flash swap on pool A, sell into pool B in the callback, repay, revert unless profit
  clears a threshold. Supports Uniswap V3, PancakeSwap V3 and Camelot V3 callbacks.
- Replay real phase-1 opportunities at their historical blocks (the top cases from both months plus a
  fixed random sample, chosen and written in the journal before running). Compare fork profit with
  the phase-1 model.
- Measure real L2 gas units and the L1 data fee per transaction, then recompute the phase-1 net
  figures with them as a correction entry (not a new variant).
- Write the plan into JOURNAL.md and get Harrison's approval before writing the contract.

## Later
- Phase 3 shadow mode, phase 4 tiny live test only if shadow mode is net positive after failed-attempt
  gas.
- Planned follow-up: same measurement on Base (journal entry 2026-10-17), after Arbitrum is written up.
- Idea only, not part of this study: trading behind liquidations routed through thin pools.
