# flash-arb - handover for Claude Code

## What this is
A research project on flash-loan DEX arbitrage on Arbitrum One. Harrison brings the ideas and judgement;
Claude writes and runs the code. Explain what the code does in plain terms. Concise, no emojis.

The research question: **how much DEX arbitrage is actually available to a retail bot on Arbitrum,
and who captures it?** The bot is the measuring tool. We expect it to be unprofitable; an honest
"nothing is left for us, and here is why" is a valid result.

## Context to keep in mind
- Simple two-pool arbitrage is heavily competed. Arbitrum uses Timeboost: each minute an auction picks
  one "express lane" controller, and everyone else's transactions are delayed about 200ms. A 2026
  study found three entities win almost all auctions. So our bot starts structurally late.
- Flash-loan sources on Arbitrum: Balancer (zero fee, but limited liquidity on Arbitrum), Aave V3
  (small fee, deep liquidity), Uniswap V3 flash swaps. Confirm the current fees on-chain before using
  them in any calculation; don't trust blog numbers.

## Rules (same discipline as hyperliquid-strategy)
- JOURNAL.md is the research log: research content only, append new entries at the bottom, never
  edit old ones. Corrections go in a new entry.
- Fix pools, dates and thresholds BEFORE looking at results. Record them in the journal first.
- Calibration period: 2026-08-01 to 2026-08-31. Evaluation period: 2026-09-01 to 2026-09-30.
  Thresholds are chosen on August only. September is looked at once, after the design is frozen.
- Count every variant tried, as in the HL project.
- Security: never put a private key or RPC key in code or git. Use a .env file listed in .gitignore.
  Any live wallet is a fresh wallet with a few dollars only. Ask Harrison before any action that
  signs or sends a transaction.

## Phases
1. **Measure (no contract, no money).** Find historical price gaps between pools, net of all costs,
   and who closed them.
2. **Contract on a local fork.** Solidity + Foundry. Flash loan, two swaps, revert unless profit
   clears a threshold. Replay the real opportunities from phase 1 at their historical blocks.
3. **Shadow mode.** Live listener that detects, simulates and logs what it would have done and
   whether someone beat it. The equivalent of paper trading.
4. **Tiny live test** only if shadow mode is net positive after the gas cost of failed attempts.

## Phase 1 plan
- Universe (fixed rule, not hand-picked): pairs WETH/USDC (native USDC), WETH/USDT, WBTC/WETH,
  ARB/WETH, ARB/USDC on Uniswap V3, Camelot, SushiSwap and PancakeSwap V3. Include every pool for
  those pairs on those DEXs with TVL above $250k on 2026-08-01. Write the resulting pool list
  (addresses, fee tiers) into the journal before pulling any swap data.
- Data: an Arbitrum RPC with archive access (key in .env). Pull Swap/Sync events for the listed pools
  over Aug-Sep 2026, giving the pool price at every block where it changed. Also pull the gas price
  per block.
- Screen: per block, flag pairs where the price gap between two pools exceeds the sum of both pool
  fees. That is a cheap first filter that overcounts.
- Verify: for flagged blocks, compute the true optimal trade size and profit with exact pool math
  (or quoter calls on a fork at that block), net of pool fees, flash-loan fee and gas at that
  block's price. Gas units come from a fixed estimate first, replaced by the real figure from phase 2.
- Who captured it: for each real opportunity, find the transaction(s) that closed the gap, how many
  blocks it lasted, which contract/address took it, and whether it went through the express lane if
  that can be identified from the data.
- Report: number and total size of real opportunities, distribution by profit, how long they lasted,
  share taken by the top few addresses, and how much would be left for a bot that is 200ms+ behind.

## Next step
Step 1: set up the folder (git, .gitignore, .env template, requirements), then build the pool-list
script, run it, and add the fixed pool list to JOURNAL.md as a new entry. Stop there and report back
before pulling swap data.
