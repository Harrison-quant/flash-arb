# Journal

My research log for this project: every step, result, decision and mistake, in order.
New entries go at the bottom; earlier entries aren't edited.

---

## 2026-10-17 - Idea and pre-commitments

- Goal: study flash-loan arbitrage between DEXs on Arbitrum One. Not a profit play. Simple two-pool
  arbitrage is one of the most competed trades in crypto, so I expect a retail bot to make roughly
  nothing. The question is how much is actually there for a bot like mine, and who takes it.
- Why Arbitrum: gas is cheap enough to test with a few dollars, and its transaction ordering is
  unusual. Since 2025 it runs Timeboost, an auction each minute for an "express lane"; everyone else's
  transactions are delayed about 200ms. A 2026 study found three entities win almost all auctions.
  That gives a concrete hypothesis: whatever arbitrage exists is taken by the express-lane holders,
  and a bot without it is structurally too late.
- Why flash loans: the trade borrows and repays inside one transaction, so it needs no capital beyond
  gas. A failed attempt still costs gas, which is the main way a bot like this loses money.

**Plan**
1. Measure historical opportunities net of all costs, and who captured them. No contract, no money.
2. Build the contract and replay real historical opportunities on a local fork.
3. Shadow mode: live detection and simulation, logged, no trades.
4. A tiny live test only if shadow mode is net positive after failed-attempt gas.

**Fixed before seeing any data**
- Pairs: WETH/USDC, WETH/USDT, WBTC/WETH, ARB/WETH, ARB/USDC.
- DEXs: Uniswap V3, Camelot, SushiSwap, PancakeSwap V3.
- Pools: every pool for those pairs on those DEXs with TVL above $250k on 2026-08-01.
- Calibration period: August 2026, used to set thresholds. Evaluation period: September 2026,
  looked at once after the design is frozen.
- Costs: pool fees, flash-loan fee and gas at each block's actual price, all included.

---

## Running totals
- Variants tested: 0.
- Evaluation period (Sep 2026): unspent.

## 2026-10-17 - Setup and pool-list method (list not built yet)

**Did**
- Set up the folder: git, .gitignore (ignores .env), .env.example, requirements.txt.
- Wrote pool_list.py. Method, fixed before the official run:
  - Snapshot block: the first block at or after 2026-08-01 00:00:00 UTC. That is block 489,802,914
    (timestamp exactly 00:00:00).
  - Discovery: ask each factory at that block for every pool of each pair. Factories: Uniswap V3,
    SushiSwap V2 and V3, PancakeSwap V3, Camelot V2 and V3 (Algebra). "SushiSwap" and "Camelot" are
    read as all of their versions on Arbitrum. For the V3-style factories I try 17 fee values, not
    just the standard tiers, so a non-standard tier can't be missed.
  - Checks: each pool must have code, the right two tokens, and must report the factory that
    returned it. Any mismatch stops the script.
  - TVL: the pool contract's balance of its two tokens at the snapshot block, priced with Chainlink
    USD feeds at the same block (ETH, WBTC, USDC, USDT, ARB; each feed's description is checked).
    Threshold: strictly above $250k.
  - Fees recorded per pool: the fee tier for the V3-style pools; for Camelot, the directional fees at
    the snapshot (they are dynamic on V3 and set per direction on V2).

**Blocker**
- The public endpoint arb1.arbitrum.io serves current state but not the state at 2026-08-01
  ("missing trie node"). It isn't an archive node. An archive RPC key in .env is needed, which phase
  1 needs anyway for the swap data.

**Checks**
- I ran the script on today's state (block 515,605,514) to test the code, not to build the list.
  All six factories responded, every pool's tokens and factory matched, and the Camelot V3 fee
  decoding was fixed (it returns two directional fees). The TVLs from that run aren't used. Several
  pools sit close to $250k, so the 2026-08-01 list may well differ.

**Decisions**
- Uniswap V4, Uniswap V2 and PancakeSwap V2 are excluded, because the universe names Uniswap V3 and
  PancakeSwap V3. If V4 turns out to hold a large share of the liquidity for these pairs, that is a
  limitation to report, not a reason to change the universe.

## 2026-10-17 - Planned follow-up: same measurement on Base

- After the Arbitrum study is frozen (September evaluation done and written up), I'll run the same
  measurement code, unchanged, on Base to compare ordering rules. Arbitrum orders by Timeboost
  (express-lane auction plus a 200ms delay for everyone else). Base has no express lane;
  transactions are ordered by priority fee. The question is whether a different ordering rule
  changes how much arbitrage is left and who takes it.
- "Unchanged" means the same logic, thresholds and cost model. Only the chain config changes
  (RPC, token, factory and feed addresses). The Base pool universe follows the same written rule,
  and is fixed in the journal before any Base data is pulled. Base's DEX mix is different (no
  Camelot; Aerodrome is large there), so whether to add Aerodrome has to be decided and recorded
  before the run, not after.
- Base periods to be fixed then. This doesn't touch the Arbitrum design or spend its evaluation
  period.

## 2026-10-17 - Universe decisions confirmed; Uniswap V4 TVL to be reported (method, before running)

**Decisions (confirmed by Harrison)**
- SushiSwap and Camelot include all their versions on Arbitrum (Sushi V2 and V3, Camelot V2 and V3).
- Uniswap V4 stays out of the universe.
- New: record Uniswap V4 TVL for the same five pairs at the same snapshot block (489,802,914), as
  context only. It doesn't add any pool to the universe and doesn't change the $250k rule.

**V4 method, fixed before running**
- V4 keeps all pools in one contract (the PoolManager), so token balances can't be read per pool.
  Instead:
  - Find pools from the PoolManager's Initialize events up to the snapshot block, filtered to the five
    pairs. In V4, WETH pairs are mostly listed against native ETH. Native-ETH and WETH pools are both
    counted, and each is labelled.
  - TVL per pool: replay every ModifyLiquidity event for that pool up to the snapshot, giving net
    liquidity per tick range. Convert each range to token amounts at the pool's price at the
    snapshot (StateView.getSlot0), and value them with the same Chainlink prices as the main list.
  - Check: the rebuilt liquidity active at the current tick has to equal StateView.getLiquidity at
    the snapshot. A pool that fails this is reported as failed, not estimated.
- Limitations: this leaves out uncollected fees and anything a hook holds outside the PoolManager's
  liquidity accounting, so for hooked pools it is a lower bound. Each pool's hook address is
  reported.

## 2026-10-17 - Fixed pool list (snapshot 2026-08-01)

**Did**
- Ran pool_list.py with the archive RPC. Snapshot block 489,802,914 (2026-08-01 00:00:00 UTC).
  Chainlink prices at that block: ETH 1,859.99, WBTC 62,900.02, USDC 0.9998, USDT 0.9990,
  ARB 0.0783.
- 74 candidate pools found across the six factories; all passed the token and factory checks.
  12 have TVL above $250k. This is the fixed phase-1 universe (also in data/pools.csv; every
  candidate is in data/pools_all.csv).

| Pair | DEX | Fee | TVL (USD) | Pool |
|---|---|---|---:|---|
| WETH/USDC | Uniswap V3 | 0.05% | 35,332,585 | 0xC6962004f452bE9203591991D15f6b388e09E8D0 |
| WETH/USDC | Uniswap V3 | 0.3% | 6,165,358 | 0xc473e2aEE3441BF9240Be85eb122aBB059A3B57c |
| WETH/USDC | PancakeSwap V3 | 0.05% | 865,830 | 0xd9e2a1a61B6E61b275cEc326465d417e52C1b95c |
| WETH/USDC | Camelot V3 | 0.01% each way (dynamic) | 442,950 | 0xB1026b8e7276e7AC75410F1fcbbe21796e8f7526 |
| WETH/USDC | PancakeSwap V3 | 0.01% | 410,417 | 0x7fCDC35463E3770c2fB992716Cd070B63540b947 |
| WETH/USDT | Uniswap V3 | 0.05% | 6,295,956 | 0x641C00A822e8b671738d32a431a4Fb6074E5c79d |
| WETH/USDT | Uniswap V3 | 0.3% | 328,624 | 0xc82819F72A9e77E2c0c3A69B3196478f44303cf4 |
| WBTC/WETH | Uniswap V3 | 0.05% | 32,636,808 | 0x2f5e87C9312fa29aed5c179E456625D79015299c |
| WBTC/WETH | PancakeSwap V3 | 0.01% | 1,026,658 | 0x4bfc22A4dA7f31F8a912a79A7e44a822398b4390 |
| WBTC/WETH | Uniswap V3 | 0.3% | 650,847 | 0x149e36E72726e0BceA5c59d40df2c43F60f5A22D |
| ARB/WETH | Uniswap V3 | 0.05% | 1,181,575 | 0xC6F780497A95e246EB9449f5e4770916DCd6396A |
| ARB/USDC | Uniswap V3 | 0.3% | 508,497 | 0xaEBDcA1Bc8d89177EbE2308d62af5e74885DcCc3 |

**What this means for the study**
- ARB/WETH and ARB/USDC each have only one pool above the threshold, so the universe has no
  same-pair two-pool arbitrage for ARB. The rule stays as written; I'm not lowering the threshold to
  bring ARB pools in. Two-pool comparisons left: WETH/USDC 10 pool pairs, WBTC/WETH 3, WETH/USDT 1,
  so 14 in total.
- Close to the line, now out: Sushi V3 WETH/USDC 0.05% ($237,778), PancakeSwap V3 WETH/USDT 0.05%
  ($246,614). Sushi has no pool in the universe, and Camelot has one.
- The Camelot V3 fee is dynamic. The 0.01% above is its value at the snapshot only; phase 1 has to
  read the fee at each block, not use this figure.

**Data source note**
- Alchemy's free tier limits eth_getLogs to 10 blocks per request. Logs come from the public endpoint
  (up to 10M blocks per request), and historical state comes from Alchemy. This affects how the swap
  pull is built, not the results.

## 2026-10-17 - Uniswap V4 TVL at the snapshot (reported only)

**Did**
- Ran v4_tvl.py using the method in the entry above. The PoolManager was deployed at block
  297,842,872. Found 720 V4 pools for the five pairs (native ETH and WETH variants), 547 of them with
  hooks. Every pool passed the liquidity check: the rebuilt active liquidity matched getLiquidity
  exactly. Per-pool detail is in data/v4_pools.csv. The run took about an hour because of the
  ModifyLiquidity replay.

**Result** (USD at block 489,802,914; ETH and WETH pools combined)

| Pair | Universe (12 pools) | All non-V4 candidates | Uniswap V4 | V4 share | V4 pools > $250k |
|---|---:|---:|---:|---:|---:|
| WETH/USDC | 43,217,140 | 43,642,999 | 3,717,199 | 7.8% | 2 |
| WETH/USDT | 6,624,580 | 7,170,121 | 1,013,248 | 12.4% | 1 |
| WBTC/WETH | 34,314,313 | 34,533,965 | 1,147,611 | 3.2% | 1 |
| ARB/WETH | 1,181,575 | 1,447,374 | 103,357 | 6.7% | 0 |
| ARB/USDC | 508,497 | 605,549 | 30,182 | 4.7% | 0 |

- The four V4 pools above $250k are all native ETH and have no hooks: ETH/USDC 0.05% ($2,256,661),
  ETH/USDC 0.3% ($1,308,943), ETH/WBTC 0.05% ($984,052), ETH/USDT 0.05% ($700,165).
- Hooked pools hold very little (largest pair total $60,280), so leaving out hook-held funds doesn't
  change the picture. Many pools have absurd fees (6% to 99%) and only a few thousand dollars each.

**What this means**
- V4 holds 3-12% of the liquidity for these pairs, so the universe covers most of it. The universe
  is unchanged. The limitation to report: arbitrage between V4 and V3 pools (for example, the V4
  ETH/USDT 0.05% pool against the two Uniswap V3 WETH/USDT pools) isn't measured. Part of what
  closes gaps in our pools may also be trades routed through V4, and that will show up when I look
  at who closed each gap.
- Variants tested: still 0. This was a measurement of context, not a design choice.

## 2026-10-17 - Scope: triangular arbitrage excluded

- Triangular arbitrage (cycles across three pairs, for example ARB -> WETH -> USDC -> ARB) is out of
  scope. The study measures same-pair, two-pool arbitrage only, which is what the universe and the
  screen were designed for. So the two ARB pools are in the data but have no same-pair partner in
  the universe. Cycles through them would be a separate study with its own pre-commitments.
