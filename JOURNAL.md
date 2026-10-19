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
(Status section, updated in place. Last updated 2026-10-20.)
- Variants tested: 1.
- Evaluation period (Sep 2026): spent, looked at once on 2026-10-19.
- Corrections and changes made (each in its own entry below):
  1. 2026-10-18: Camelot tick-table indexing fixed in the maths port (bug found when switching to
     archive tick reads).
  2. 2026-10-18: Check 2 revised after it failed as written (approved by Harrison).
  3. 2026-10-18: reporting correction, primary totals keep the largest opportunity per opening tx,
     and top-3-removed figures are shown alongside (before September).
  4. 2026-10-19: implementation change, base fee fetched only at blocks passing the fee screen
     (identical results, verified on August), plus fixed row order in the opportunity file.
  5. 2026-10-20: capture classification, any closing tx swapping in both pools in opposite
     directions counts as two-pool arbitrage, whoever receives the profit (both months recomputed).

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

## 2026-10-17 - Gas data: base fee at event blocks only (method, before fetching)

**Why**
- Base fee for every August block (10.65M headers) isn't feasible without paying. The public
  endpoint is rate-limited to about 12 blocks/s (about 250 hours), and Alchemy's free tier would
  need about 170M compute units against a 30M monthly limit. eth_feeHistory is refused for August
  blocks by both endpoints. Harrison decided: no paid plan, and no sampling.

**Method, fixed before fetching**
- Fetch baseFeePerGas only at blocks where at least one of the 12 universe pools emitted an event
  (any event type) in August, from the decoded logs in data/raw/aug/logs/.
- Between those blocks, carry the last fetched value forward. A gap can only appear or close at a
  block where a pool event happened, so every block where the screen can change has a fetched
  value. The carried-forward value is used only for blocks where nothing in our pools changed.
- Limitation: if the base fee spikes inside a quiet stretch, the carried-forward value misses it.
  Arbitrum's base fee sits near its floor most of the time, so I expect this to matter little.
  I'll report how often the fetched value changes between consecutive event blocks as a check.

**Not covered: the L1 data fee**
- On Arbitrum a transaction also pays for posting its data to Ethereum (L1). That charge depends
  on the L1 price estimate at the time and the transaction's size, and it isn't in the block header.
  It isn't covered here. It will be measured in phase 2 from the real contract transaction on a
  fork. Until then any cost figure is L2 gas only and understates the true cost.

## 2026-10-18 - August data pulled and reconciled; gas fetched

**Did**
- pull_august.py fetched every log of the 12 universe pools for blocks 489,802,914 to 500,455,224
  (all of August 2026, 10,652,311 blocks) from the public endpoint. It then rebuilt each pool's price
  and active liquidity from the events and checked them against archive state. The first run was
  killed mid-way (the session ended). The rerun reused the saved logs and the 112 complete archive
  checkpoints, dropped the one partial checkpoint and fetched the rest.
- fetch_gas_aug.py fetched baseFeePerGas at every block with a universe-pool event, as set out in the
  gas entry above.

**Checkpoints: 1,067, none skipped**
- 1,067 checkpoints: the start state (block 489,802,913, the last block of July) plus the end of
  each of 1,066 windows. Windows are 10,000 blocks; the last one is 2,311 blocks (500,452,914 to
  500,455,224).
- All 1,067 checkpoint files are present, each with all 12 pools. The 1,066 windows run back to back
  from 489,802,914 to 500,455,224 with no gaps. That is 12,792 pool-window checks (1,066 x 12).

**Reconciliation**
- 12,792 of 12,792 pool-windows matched the archive exactly: sqrt price and active liquidity, as
  integers. 0 mismatches, 0 refetches, 0 persistent mismatches.
- The tick also matched at every checkpoint. Camelot's two directional fees, rebuilt from its Fee
  events, matched the archive at all 1,066 checkpoints.
- So the event data is complete for these pools. The rebuild rules (a Swap sets price, tick and
  liquidity; a Mint or Burn changes liquidity when its range covers the current tick) hold for all
  three pool types.

**Events by pool** (August 2026; every log decoded to a known type, 0 unknown)

| Pool | Swap | Mint | Burn | Collect | Fee | Other | Total | Blocks with a swap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| WETH/USDC Uniswap V3 0.05% | 765,593 | 22,380 | 29,859 | 29,029 | 0 | 95 | 846,956 | 245,938 |
| WETH/USDT Uniswap V3 0.05% | 387,079 | 9,084 | 10,518 | 10,463 | 0 | 65 | 417,209 | 158,558 |
| WETH/USDC Camelot V3 | 242,937 | 303 | 657 | 650 | 159,425 | 0 | 403,972 | 193,532 |
| WBTC/WETH PancakeSwap V3 0.01% | 280,148 | 384 | 666 | 648 | 0 | 1 | 281,847 | 170,305 |
| WBTC/WETH Uniswap V3 0.05% | 219,958 | 4,609 | 12,421 | 11,797 | 0 | 60 | 248,845 | 104,370 |
| WETH/USDC PancakeSwap V3 0.01% | 211,596 | 762 | 944 | 919 | 0 | 1 | 214,222 | 184,054 |
| ARB/WETH Uniswap V3 0.05% | 203,130 | 1,918 | 3,590 | 3,562 | 0 | 60 | 212,260 | 156,477 |
| WETH/USDC PancakeSwap V3 0.05% | 111,734 | 2,381 | 3,342 | 3,143 | 0 | 1 | 120,601 | 69,205 |
| WETH/USDC Uniswap V3 0.3% | 63,752 | 1,591 | 3,168 | 3,069 | 0 | 60 | 71,640 | 18,346 |
| ARB/USDC Uniswap V3 0.3% | 24,184 | 250 | 287 | 284 | 0 | 60 | 25,065 | 19,333 |
| WETH/USDT Uniswap V3 0.3% | 10,880 | 271 | 382 | 379 | 0 | 60 | 11,972 | 9,120 |
| WBTC/WETH Uniswap V3 0.3% | 4,727 | 437 | 802 | 771 | 0 | 59 | 6,796 | 3,502 |
| **Total** | **2,525,718** | **44,370** | **66,636** | **64,714** | **159,425** | **522** | **2,861,385** | |

- "Other" is CollectProtocol (482) and Flash (40). Camelot's Fee events (its dynamic fee changing)
  are about 40% of its log count.
- 855,735 distinct blocks have at least one event in some universe pool, which is 8.0% of August's
  blocks. 798,528 of those have a swap.

**Gas**
- Coverage: 855,735 of 855,735 event blocks fetched, with no gaps.
- Base fee: min 0.020000 gwei (the floor), median 0.020034, 99th percentile 0.0280, max 0.677
  (block 497,099,509). 26.0% of event blocks are exactly at the floor, and 2,950 are above 0.05 gwei.
- The check promised in the gas entry: the value differs between 93.2% of consecutive event blocks,
  but by small amounts (median 0.26%, 90th percentile 1.4%, 99th percentile 5.2%). 1,003 changes are
  above 10%, and 256 of those span a gap of more than one block. Event blocks are a median of 3
  blocks apart (99th percentile 120, max 848). So carrying the value forward over quiet stretches
  costs little accuracy at these levels.
- At the median base fee, 350,000 gas units cost 0.000007 ETH, about $0.013 at the August 1 ETH
  price. The L1 data fee isn't included (see the gas entry).

**Files** (git-ignored, re-creatable with the scripts): data/raw/aug_events.csv.gz,
data/raw/aug_gas.csv, data/raw/aug/checkpoints/. The reconciliation table data/aug_reconcile.csv is
committed.

- Variants tested: still 0. September is untouched.

## 2026-10-18 - Opportunity scan: method, fixed before running (August only)

Nothing below has been run. This is the exact method, written before looking at any opportunity
result. It applies to August 2026 (calibration) only. September stays untouched.

**Scope**
- 14 pool pairs, same pair only: WETH/USDC 10 (the 5 universe pools pairwise), WBTC/WETH 3,
  WETH/USDT 1. The two ARB pools have no partner and aren't scanned. Triangular routes are out of
  scope.
- Both directions per pool pair. Route "A->B": pay token X into pool A, receive token Y, sell Y into
  pool B for X. The borrowed token is X, and profit is measured in X.

**Step 0: tick maps (needed for exact swaps)**
- For each pool, replay every Mint and Burn from pool creation to the end of August (public-endpoint
  logs) to get liquidityNet at every initialised tick. Combined with the August event stream, this
  gives the full pool state after every transaction.
- Check 1: at all 1,067 checkpoints, the active liquidity from the tick map at the archive tick must
  equal the archive liquidity exactly.
- Check 2: replay every August swap from its pre-swap state as an exact-input swap of the amount the
  pool received. The simulated post-swap sqrt price must equal the event's exactly for at least 99.9%
  of swaps in each pool, and be within 1e-9 (relative) for all of them. Exact-output swaps can differ
  by input rounding, which is why the bar is 99.9% and not 100%. If any pool fails either check, the
  scan stops and I report.

**Step 1: screen (when a gap can exist)**
- State is evaluated after every transaction that touches either pool of a pair, using the
  post-transaction state, not just the end of each block. On Arbitrum, gaps can open and close
  within one block, and those would be invisible at block level. States within a transaction aren't
  considered.
- Mid price p = token1 per token0 from sqrtPriceX96, adjusted for decimals. Fee f = the pool's fee
  tier; for Camelot, the directional fee for the side being traded, as tracked from its Fee events.
- Route A->B can be profitable at some size, before the loan fee and gas, only if the marginal price
  after both pools' fees is better than break-even. Buying token0 in A and selling it in B, that means
  p_B x (1 - f_A) x (1 - f_B) > p_A; the reverse direction mirrors it. This is exact at the margin, so
  it is a necessary condition. Unlike the simple "gap > sum of fees" rule, it doesn't overcount.

**Step 2: size and profit (exact pool maths)**
- Swaps are simulated with a Python port of the Uniswap V3 core libraries, using exact integers:
  TickMath.getSqrtRatioAtTick, SqrtPriceMath, SwapMath.computeSwapStep and FullMath.mulDiv with the
  same rounding. Swaps cross initialised ticks using the tick maps. PancakeSwap V3 uses identical
  maths (fee denominator 1e6). Camelot V3 (Algebra 1.9) uses the same step maths with its directional
  fee; Check 2 confirms it. The protocol fee is ignored because it doesn't change what the trader
  receives.
- Gross profit g(x) = out_B(out_A(x)) - x, for integer input x of token X. Search range: 1 unit up to
  the input that moves pool A's price to pool B's marginal price after fees, found by a swap with a
  price limit. g is concave along this range, so a golden-section search on x finds the optimum,
  stopping when the bracket is under max(1 unit, 1e-6 x).
- Financing (fees read on-chain at every checkpoint, together with the available balances):
  - Balancer V2 Vault (0xBA12222222228d8Ba445958a75a0704d566BF2C8): fee 0% at the snapshot
    (getFlashLoanFeePercentage = 0). Usable only up to the vault's balance of token X. The cap is the
    lower of its balances at the two checkpoints around the block. At the snapshot it held 104 WETH,
    19,173 USDC, 71,396 USDT and 2.96 WBTC.
  - Aave V3 Pool (0x794a61358D6845594F94dc1DB02A252b5b4814aD): FLASHLOAN_PREMIUM_TOTAL = 5 bps
    (0.05%) at the snapshot, with flash loans enabled for all five tokens. Capped by the aToken's
    underlying balance, the same way (30.2M USDC, 21,269 WETH, 10.7M USDT, 2,629 WBTC at the
    snapshot).
  - Rule: if the optimal x fits in Balancer, the loan fee is 0. Otherwise take the better of (a)
    Balancer at x = its cap with fee 0, and (b) re-optimising g(x) - 0.0005x with Aave.
  - Balancer V3 is ignored: at the snapshot its vault held almost nothing for these tokens
    (0.73 WETH, 592 USDC).
- Gas: 350,000 L2 gas units, fixed. This is my estimate for one flash loan plus two V3 swaps
  (including some tick crossings), repayment and a profit check. Gas cost = 350,000 x base fee at that
  block (fetched, or carried forward per the gas entry), converted to USD. It will be replaced by the
  measured figure from phase 2.
- The L1 data fee is excluded (see the gas entry), so every net figure here overstates profit
  slightly.
- USD conversion: the mid price of WETH/USDC Uniswap V3 0.05% in the same state, with USDC = $1.
  WBTC goes through WBTC/WETH Uniswap V3 0.05%.
- Net profit = g(x*) - loan fee - gas cost, in USD.

**Step 3: opportunities**
- An opportunity is a maximal run of consecutive post-transaction states, for one pool pair and one
  direction, in which net profit > 0.
- For each one I record the opening transaction (the first state where it appears), the opening
  block, net profit and size at opening, the maximum net profit during the run, the financing source,
  and the closing transaction (the first state where net profit is <= 0).
- Reporting bins, fixed now: net profit > $0, > $0.10, > $1, > $10, > $100. No bot threshold is chosen
  in this scan.

**Step 4: who captured it**
- For each closing transaction, fetch the transaction (from, to) and its receipt (status, timeboosted,
  gasUsed, gasUsedForL1, effectiveGasPrice, and all logs). Receipts on Arbitrum carry a timeboosted
  field (checked on one receipt).
- Classification, from the receipt's ERC-20 Transfer logs (WETH included):
  - "Atomic arbitrage": the combined net flow to {tx.from, tx.to} is >= 0 in every token and > 0 in
    at least one. Sub-type "two-pool" if the transaction swaps in both pools of the pair in opposite
    directions, otherwise "other route" (for example via Uniswap V4 or pools outside the universe).
  - "Liquidity change": no swap in the pair's pools, but a Mint or Burn there removed the profit.
  - "Other flow": everything else, for example an ordinary trade that happened to close the gap.
  - Known blind spot: profit sent to a third address, or paid in native ETH, will be misclassified
    as other flow.
- Capturer: tx.to (contract) and tx.from (sender). I'll report the share of opportunities and of total
  opening profit closed by the top 1, 3 and 10 addresses, each way. Address labels (router, known
  searcher) are looked up afterwards, for description only.
- Express lane: receipt.timeboosted = true. I'll report the share of opportunities and profit closed by
  express-lane transactions.
- Duration: blocks from opening to closing (0 = same block) and the number of transactions in between.
  Arbitrum timestamps have one-second resolution, so sub-second timing is measured in blocks.

**Step 5: what is left for a bot that is 200ms+ late**
- An opportunity counts as reachable if it is still open after the last transaction of block
  (opening block + N). Primary N = 2, about 0.5 s at roughly 0.25 s per block: the 200ms delay plus
  detecting and sending. N = 1, 4 and 8 are reported alongside, without choosing between them. For a
  reachable opportunity, the profit counted is the net profit in that later state, not at opening.
- Assumed: our bot isn't in the express lane and doesn't win priority ties.

**Stop rules and budget**
- If more than 300,000 closing transactions need fetching, stop and report before fetching
  (free-tier compute units).
- Step 0 runs first. If Check 1 or Check 2 fails, stop.

**Counting**
- This method is variant 1. Reporting the N values and profit bins alongside doesn't count as extra
  variants, because nothing is selected from them.
- Open question for Harrison before running: a Uniswap-style flash swap (borrow from pool A itself,
  repaid in the callback) needs no external loan and adds no fee beyond pool A's own, which is
  already in the maths. It is cheaper than Aave for large trades. Should financing include it? If
  added after the primary run, it counts as variant 2.

## 2026-10-18 - Opportunity scan: plan approved with two changes (before running)

Harrison approved the scan method in the entry above, with two changes. Both are recorded here
before any code runs. They are part of the main run (variant 1), not extra variants.

**Change 1: financing is a flash swap**
- Primary: a flash swap on the buy-side pool. Pool A sends the output token first; in the swap
  callback the bot sells it into pool B and pays pool A what it owes. Uniswap V3, PancakeSwap V3 and
  Camelot V3 all support this through their swap callbacks. The only cost is pool A's own fee, which
  is already inside the swap maths, so primary net profit = g(x*) - gas, with x* maximising g.
- Comparison only: the same opportunity financed by an Aave V3 flash loan. That is g(x) - premium x -
  gas, re-optimised over x, with the premium read on-chain (FLASHLOAN_PREMIUM_TOTAL, 5 bps at the
  snapshot). Size is capped by Aave's available balance of the borrowed token. The premium and the
  balances are read at every checkpoint, and the cap is the lower of the two checkpoints around the
  block. This number is reported next to the primary one and doesn't define what counts as an
  opportunity.
- Balancer is dropped from the method: with a flash swap there's nothing to borrow.
- Gas stays at 350,000 L2 gas units for both. A flash swap needs no separate loan call, so this is
  if anything generous. It will be replaced by the phase-2 measurement.

**Change 2: who captured it, three groups**
- "Atomic arbitrage": the closing transaction swaps in both pools of the pair, in opposite
  directions, and has a net gain. Net gain means the combined net ERC-20 flow to {tx.from, tx.to},
  from the receipt's Transfer logs, is >= 0 in every token and > 0 in at least one.
- "One-sided swap": the closing transaction swaps in exactly one of the pair's two pools. This could
  be a bot arbitraging against a centralised exchange or another venue, or an ordinary user.
- "Other": everything else (for example a Mint or Burn, a Camelot fee change, or both legs without a
  net gain).
- For each group: the count, the share of opportunities and of opening profit, and the express-lane
  share (receipt.timeboosted), by count and by profit. The top capturing addresses (tx.to and
  tx.from) are still reported, as in the plan.

**Details fixed during setup (not changes to the method)**
- Direction convention: for each pool pair there are two routes, depending on which pool has token0
  cheaper (pool A). The bot pays token1 into A, receives token0, and sells it into B for token1.
  So profit is in token1: USDC for WETH/USDC, USDT for WETH/USDT, WETH for WBTC/WETH.
- USDT is converted to USD by the ratio of the WETH/USDC and WETH/USDT Uniswap V3 0.05% mid prices in
  the same state, with USDC = $1.
- Swap stepping follows each pool's tick-search rules exactly: Uniswap V3 and PancakeSwap V3 search
  their tick bitmap one 256-tick word at a time, Camelot uses its tick table, and steps are clamped at
  the minimum and maximum tick. Without this, rounding wouldn't match the pools. Each pool's tick
  spacing is read on-chain. If Check 2 fails because my port is wrong (a bug, not a method choice),
  I fix the port and rerun the checks, and record it.

- Variants tested: 1 (this run) once it runs.

## 2026-10-18 - Tick maps: read from the archive instead of replaying history (before running)

Step 0 of the scan method said the tick maps would be built by replaying every Mint and Burn from
each pool's creation. On the public endpoint that has to download every log of the pool, swaps
included, and it was on pool 2 of 12 after about 2.7 hours. The busiest pools (WETH/USDC 0.05%
especially) have far more history, so the estimate was 1 to 3 more days. It was stopped.

Replacement: read the tick state directly from the archive node at block 489,802,913 (the last block
of July), which is the state the scan starts from. For each pool: read its tick spacing, read every
word of the tick bitmap over the full tick range (tickBitmap on Uniswap V3 and PancakeSwap V3,
tickTable on Camelot V3), then call ticks(t) for every set bit to get liquidityGross and
liquidityNet. All through Multicall3 at that one block. Before writing, two sanity checks: every set
bit must be an initialised tick with gross > 0, and the active liquidity implied by the map at the
pool's tick must equal liquidity() at that block. August Mints and Burns are already in the event
stream and are applied on top during the scan, as before.

This changes where the starting tick map comes from, not what it should be, so it isn't a new
variant. Checks 1 and 2 still run unchanged and are what verify it. As a cross-check, the one pool
finished by the old method (ARB/USDC Uniswap V3 0.3%, 309 initialised ticks) is compared with the
archive read.

## 2026-10-18 - Tick maps read; Camelot tick-table fix (before the scan)

- The archive read took about 7 minutes for all 12 pools (history replay: days). Every set bit was an
  initialised tick, and in every pool the active liquidity from the map equals liquidity() at block
  489,802,913. Initialised ticks: ARB/USDC Uni 0.3% 309; ARB/WETH Uni 0.05% 2,416; WBTC/WETH Uni
  0.05% 1,300, Pancake 0.01% 2,621, Uni 0.3% 344; WETH/USDC Uni 0.05% 2,209, Uni 0.3% 505, Pancake
  0.05% 1,386, Camelot 619, Pancake 0.01% 11,285; WETH/USDT Uni 0.05% 1,860, Uni 0.3% 503.
- Cross-check: for ARB/USDC Uniswap V3 0.3%, the map built from full Mint/Burn history and the
  archive read are identical (309 ticks, same net and gross).
- Port bug found and fixed (expected risk named in the amendment entry): Camelot V3 (Algebra 1.9)
  indexes its tick table by the raw tick (row = tick >> 8), not by tick / spacing as Uniswap and
  PancakeSwap do. Its tick spacing is 10, so my port would have ended swap steps at the wrong row
  boundaries for Camelot, which changes rounding. The pool model now takes a bitmap unit (1 for
  Camelot, the tick spacing otherwise). Found on the archive read itself, before Check 2 ran.

## 2026-10-18 - Scan stopped: Check 2 failed as defined; diagnosis

Step 0 ran on August (scan_august.py check). No opportunity has been computed.

**Check 1 passed:** 12,804 of 12,804 pool-checkpoints (12 pools x 1,067 checkpoints) match the archive
exactly: active liquidity from the tick map, tracked liquidity and tick.

**Check 2 failed as written.** Replaying each swap as exact-input of the amount the pool received, with
no price limit, reproduced the event's sqrt price exactly for only 11% to 75% of swaps per pool,
against the 99.9% bar. All swaps in every pool were within 1e-9 (relative), except 24 of 4,727 in
WBTC/WETH Uniswap V3 0.3% (max 1.38e-9). Per pool (exact share): ARB/USDC 0.534, ARB/WETH 0.436,
WBTC/WETH Uni 0.05% 0.304, Pancake 0.01% 0.294, Uni 0.3% 0.305, WETH/USDC Uni 0.05% 0.152, Uni 0.3%
0.109, Pancake 0.05% 0.324, Camelot 0.550, Pancake 0.01% 0.750, WETH/USDT Uni 0.05% 0.157, Uni 0.3%
0.501. Full table: data/aug_checks.csv.

**Diagnosis (check2_diagnose.py).** When the free replay misses, it always ends beyond the event's
price and never short of it. That is what happens if the real swap stopped at a price limit (normal
for arbitrage bots) or was exact-output: given the same input with no limit, the replay keeps going.
The plan expected only exact-output swaps to differ and set the 99.9% bar on that assumption, which
was wrong. Replaying each swap a second way, with the event's own end price as the price limit, and
counting a swap as reproduced if either replay gives exactly the event's input, output and end price
(all three integers):
- 2,525,664 of 2,525,718 swaps (99.998%) reproduced exactly.
- 11 of 12 pools: 100.000%. Every pool in the 14 scanned pairs is among them.
- ARB/USDC Uniswap V3 0.3% (not in any scanned pair): 24,130 of 24,184 (99.777%). In the 54
  exceptions, input and end price match but the replay's output is 170 to 562 units higher. That
  fits exact-output swaps, where the pool delivers exactly the requested amount and the rounded-up
  input could have bought slightly more.
My reading is that the swap maths and tick maps are exact and the check was badly specified, not
that the port is wrong. Changing a check after seeing it fail is Harrison's decision, so the scan is
stopped here. Proposed revised Check 2: a swap counts as reproduced if either replay matches input,
output and end price exactly; the bar is 99.9% per pool for the pools in scanned pairs, with the two
ARB pools reported but not gating. This concerns the verification step only, not how opportunities
are found or sized, so I'd log it as a correction rather than a variant.

- Variants tested: 0 (the scan itself hasn't run).

## 2026-10-18 - Check 2 revised (after seeing it fail), approved by Harrison

**What happened, in order.** This revision was made after seeing the original check fail. It isn't a
pre-registered rule.
1. Tick maps: the plan said to build them by replaying every Mint and Burn since each pool's
   creation. That would have taken 1 to 3 more days on the public endpoint, so it was replaced by
   reading each pool's tick bitmap and ticks directly from the archive at block 489,802,913 (entry
   "Tick maps: read from the archive"). All 12 pools match liquidity() at that block. The one pool
   built both ways (ARB/USDC Uniswap V3 0.3%) is identical.
2. That read exposed a bug in my swap port: Camelot V3 (Algebra 1.9) indexes its tick table by the
   raw tick, not by tick / spacing. Its spacing is 10, so my code would have split Camelot swaps at
   the wrong boundaries. It was fixed before any check ran (entry "Tick maps read; Camelot
   tick-table fix").
3. Check 1 passed (12,804 of 12,804).
4. The original Check 2 (free exact-input replay must hit the event's sqrt price exactly for 99.9% of
   swaps per pool, and within 1e-9 for all) failed in all 12 pools: exact shares of 0.11 to 0.75
   (entry "Scan stopped: Check 2 failed as defined; diagnosis").
5. Diagnosis: the free replay only ever overshoots, because many real swaps stop at a price limit or
   are exact-output. Replaying with the event's own end price as the limit as well, 2,525,664 of
   2,525,718 swaps are reproduced exactly in input, output and end price. That's 100.000% in the 11
   non-ARB/USDC pools and 99.777% in ARB/USDC.

**Revised Check 2 (approved by Harrison).** A swap counts as reproduced if either replay (free, or
with the event's end price as the limit) gives exactly the event's input, output and end sqrt price.
The bar is at least 99.9% reproduced in each pool of the 14 scanned pairs. The two ARB pools aren't in
any scanned pair: they are reported but don't count towards pass/fail. The 1e-9 tolerance is dropped,
because the test is now exact on all three integers. Check 1 is unchanged.

This changes only how the swap maths is verified, not how opportunities are screened, sized or
counted, so it's a correction and not a variant.

- Variants tested: 0 so far. The main scan, when it runs, is variant 1.

## 2026-10-18 - August scan results (variant 1, calibration only)

Run: scan_august.py check aave scan capture, using the method in the entries "Opportunity scan:
method", "plan approved with two changes" and "Check 2 revised". September is untouched. Full printed
summary: data/aug_scan_summary.txt. Per-opportunity rows: data/raw/aug_opportunities.csv (not in git).

**Checks.** Check 1: 12,804 of 12,804 pool-checkpoints match. Revised Check 2: 100.000% of swaps
reproduced exactly in all 10 scanned pools. ARB/WETH is also 100%, and ARB/USDC is 99.777% (not
gating). Aave premium: 5 bps at all 1,067 checkpoints.

**Scale.** 14,197,262 pair-direction states evaluated (after every transaction touching a pool of a
pair), 205,088 passed the fee screen, and 17,661 opportunities had net profit > 0 (flash swap, gas at
350,000 units, L1 data fee excluded, so slightly overstated). Every opportunity closed within
August.

**Size (opening net profit, flash swap).**
- > $0: 17,661, total $6,012.51
- > $0.10: 2,249, total $5,731.95
- > $1: 371, total $5,234.34
- > $10: 53, total $4,344.12
- > $100: 8, total $3,058.99
- Median $0.0126, p90 $0.13, p99 $2.48, max $662.40. Summing the best state of each run instead of
  the opening state gives $7,004.30.
- Concentrated in time: all 8 opportunities above $100 come from three moments (around blocks
  496,292,234, 496,848,609 and 499,997,853), each opening several pool pairs at once.
- By pair: WETH/USDC 16,187 opportunities ($3,149), WBTC/WETH 1,372 ($2,817), WETH/USDT 102 ($47).
  The thin WBTC/WETH Uniswap 0.3% pool against the two deep WBTC/WETH pools gave $2,459 of the
  total from 407 opportunities. Camelot vs PancakeSwap 0.01% (WETH/USDC) is the most frequent pair
  (10,703) but small (median $0.009).
- Aave comparison: with a 5 bps loan, 1,702 of the 17,661 stay positive, total $4,777.40 against
  $6,012.51 for the flash swap.

**Duration.** 8,479 closed in the same block, 6,989 in the next block, 1,995 within 2-4 blocks, 175
within 5-20, and 23 lasted more than 20. Universe-pool transactions between opening and closing:
median 3, p90 21.

**Who closed it.** All 15,299 closing transactions fetched, all status 1.
- Atomic arbitrage (both legs of the pair, net gain): 363 (2.1%), $83 of opening profit (1.4%).
  Express lane: 2.8% of count, 2.7% of profit.
- One-sided swap (one pool of the pair): 15,639 (88.6%), $5,174 (86.1%). Express lane: 12.2% of
  count, 50.9% of profit.
- Other: 1,659 (9.4%), $755 (12.6%). Express lane: 13.3% of count, 2.4% of profit.
- Reading: gaps between these pools are almost never closed by a two-pool atomic arbitrage. They are
  closed by single-pool swaps. By profit, about half of those go through the express lane, which
  fits bots trading these pools against other venues (centralised exchanges or other pools) rather
  than against each other. Ordinary users can't be told apart from such bots with this data.
- Concentration by tx.to: the top 1, 3 and 10 take 47.6%, 61.2% and 85.8% of opening profit. One
  contract, 0x93c30e6e09f698cfea99b09b5166ed90cfaedd17, closed 2,444 opportunities worth $2,862. By
  tx.from: 21.0%, 46.1% and 64.7%. No address labels looked up yet.

**Left for a bot that's late (not in the express lane).** Still open after the last transaction of
block open+N, profit counted at that point:
- N=1: 2,193 (12.4%), $641.46 total; 69 above $1, 12 above $10
- N=2 (primary): 672 (3.8%), $407.96 total; 43 above $1, 8 above $10
- N=4: 198 (1.1%), $293.16 total; 18 above $1, 8 above $10
- N=8: 79 (0.4%), $223.14 total; 4 above $1, 4 above $10
- At N=2, 7 of the 8 opportunities above $10 come from the single moment at block 499,997,854.

**Interpretation (provisional, calibration month).** About $6,000 of gross-of-L1-fee two-pool
arbitrage appeared in August across 14 pool pairs, mostly in tiny amounts and closed within a block.
At the primary late-bot assumption, about $408 was still there for the month, before the L1 data fee,
failed-transaction gas, and competing with others for the same leftovers. More than half of that came
from one volatile moment. This is consistent with the starting expectation that very little is left
for a retail bot. Nothing has been tuned on these results.

- Variants tested: 1.

## 2026-10-18 - The 8 August opportunities over $100, and design freeze before September

**The 8 opportunities over $100** (August, flash swap; buy pool -> sell pool; closing tx):

| Open block | Pair | Buy -> sell | Net | Closing tx (block) | Closer (tx.to) | Express lane |
|---|---|---|---|---|---|---|
| 496,292,234 | WBTC/WETH | Uni 0.3% -> Uni 0.05% | $620.42 | 0xd98a9cae...3fda (496,292,235) | 0x93c3...dd17 | yes |
| 496,292,234 | WBTC/WETH | Uni 0.3% -> Pancake 0.01% | $560.19 | same | same | yes |
| 496,292,236 | WBTC/WETH | Uni 0.3% -> Uni 0.05% | $662.40 | 0x3838a538...b848 (496,292,236) | 0x93c3...dd17 | yes |
| 496,292,236 | WBTC/WETH | Uni 0.3% -> Pancake 0.01% | $597.36 | same | same | yes |
| 496,848,609 | WETH/USDC | Uni 0.05% -> Camelot | $173.77 | 0x2b705547...c3a5 (496,848,610) | 0x09ef...0e0c | no |
| 496,848,609 | WETH/USDC | Uni 0.3% -> Camelot | $145.16 | same | same | no |
| 499,997,853 | WETH/USDC | Uni 0.05% -> Pancake 0.05% | $157.48 | 0x9a28d60e...7216 (499,997,854) | 0x93c3...dd17 | no |
| 499,997,853 | WETH/USDC | Uni 0.05% -> Camelot | $142.20 | 0xe56f7f44...d977 (499,997,854) | 0xeccc...b7b | no |

**The WBTC/WETH 0.3% cases, checked by hand:**
- What opened them: two transactions two blocks apart (0x7ac980b5... and 0x51cdb53d...), from two
  different senders through the same unverified contract 0x3b994b48.... Each one takes about 8.7
  WETH from the 0.3% pool by flash swap, pays it to Compound III's WETH market (cWETHv3,
  0x6f7D514b..., name read on-chain), gets about 0.30 WBTC back, repays the pool about 0.296 WBTC,
  and keeps about 0.01 WBTC. That's the pattern of buying a liquidated borrower's WBTC collateral
  at a discount. These are liquidations routed through the thinnest WBTC/WETH pool. Each pushed its
  price down about 6% (30.76 to 28.83 and 28.78 WETH per WBTC; the deep pools stayed at about 30.74).
- Thin liquidity: active liquidity in the 0.3% pool was about 5.5e14 against 7.0e16 in the Uniswap
  0.05% pool, about 130 times thinner. That's why a $19k trade moved it 6%. The dislocation is real,
  not a data artefact.
- Price limits and rounding: Check 2 reproduced every swap in this pool exactly (input, output and
  price), including these. The opportunity profits come from the same exact maths.
- Fee-on-transfer: none. In the receipts, the WBTC and WETH Transfer amounts into and out of the pool
  equal the swap amounts exactly (for example 29,576,301 WBTC units in, 8,761,493,279,397,117,945
  WETH out).
- Who took them: both times, contract 0x93c3...dd17 bought the cheap WBTC back from the 0.3% pool in
  the next transaction slots, through the express lane, swapping in that one pool only (so
  classified as one-sided). At block 496,292,236 an atomic two-pool arbitrage (0xb49fb3f7...) also
  took part of the gap before 0x93c3 closed it. A rough check of 0x93c3's first trade: 0.28196 WBTC
  for 8.390 WETH, worth about 8.667 WETH in the deep pool, so about 0.28 WETH gross, which matches
  the $620 figure in size.

**What this means for the August figures (description only; nothing in the method changes):**
- Overlap: when one pool is knocked out of line, every pair that includes it opens at the same time,
  but the dislocation can only be taken once. The totals in the results entry add across pool
  pairs, so they double-count. 1,898 of the 14,837 opening transactions opened more than one
  opportunity. Keeping only the largest per opening transaction gives $3,274 instead of $6,013. The
  true extractable figure is somewhere between, probably nearer the lower one.
- Concentration: the 4 WBTC rows are $2,440 of the $2,459 earned on all WBTC/WETH 0.3% pairs, $2,440
  of the $2,634 of express-lane one-sided profit, and most of 0x93c3's $2,862. The 50.9%
  express-lane share of one-sided profit is essentially two liquidation backruns. Without them it is
  about 7%.

**Design freeze.** From here the design is frozen, unchanged from the entries "Opportunity scan:
method", "plan approved with two changes", "Tick maps: read from the archive", "Tick maps read;
Camelot tick-table fix" and "Check 2 revised":
- Universe: the same 12 pools (fixed at the 1 August snapshot); 14 pool pairs, both directions.
- Data: every event of the 12 pools from the public endpoint, reconciled against archive state every
  10,000 blocks (refetch on mismatch). Base fee at event blocks only, carried forward. L1 data fee
  excluded.
- Tick maps: read from the archive at the block before the period starts, with the same sanity
  checks.
- Checks: Check 1 at every checkpoint, revised Check 2 (at least 99.9% exact per scanned pool; ARB
  pools reported only). The scan doesn't run if either fails.
- Screen, exact sizing, flash swap on the buy-side pool, Aave V3 comparison (premium and balances
  read on-chain), 350,000 gas units, opportunity definition, $0/$0.10/$1/$10/$100 bins, the
  three-way capture classification with express-lane share, top-address concentration, durations,
  N = 1/2/4/8 (2 primary), and the 300,000 closing-transaction stop rule.
- Code: v3math.py, read_ticks.py, pull_august.py, fetch_gas_aug.py, scan_august.py at commit fb27a79.
  For September the only changes allowed are the block range and the file paths, through one
  setting.

**Proposed September run (not started):**
- Blocks 500,455,225 to 510,496,863 (2026-09-01 00:00 to 2026-09-30 23:59:59 UTC). That's 10,041,639
  blocks, starting right after August's last block, with 1,006 checkpoints (the start state at
  500,455,224 plus 1,005 windows of 10,000; the last is 1,639 blocks).
- Steps: (1) event pull with reconciliation, (2) base fee at event blocks, (3) tick maps from the
  archive at 500,455,224, (4) check, aave, scan, capture. Steps 1 and 2 are the slow ones (August's
  took several hours each on the free endpoints) and run in a separate window. Outputs go under
  data/raw/sep/ and data/sep_*, so August files are untouched.
- Report: the same summary as August, side by side. No threshold or setting is chosen from
  September. September is looked at once.

**Open question for Harrison (reporting only):** add two descriptive figures to both months'
summaries, computed from the same opportunity rows: (a) the total after keeping only the largest
opportunity per opening transaction, and (b) the totals with the top 3 opening transactions by
profit removed. They select nothing and change no opportunity. If approved, they'd be added and
recomputed for August before September is looked at.

- Variants tested: 1.

## 2026-10-18 - Reporting correction: overlap-free totals and top-3-removed figures (before September)

Approved by Harrison after the review of the 8 largest August opportunities, and recorded before any
September data has been pulled. This is a reporting correction: no opportunity is found, sized or
classified differently, and nothing is selected from the results. It applies to August (recomputed
now) and September alike.

**(a) Primary figure: largest opportunity per opening transaction.** One transaction that knocks a
pool out of line opens every pair containing that pool at once, but the gap can only be taken once.
So the headline totals and profit bins now keep, for each opening transaction, only the opportunity
with the largest opening net profit. For the left-for-a-late-bot table: for each opening
transaction, take the largest net profit at block open+N among its opportunities still open at that
point. The old per-pair sums are still shown, labelled "all pool pairs (overlapping)".

**(b) Reported alongside: top 3 events removed.** The same overlap-free totals and late-bot table,
with the 3 opening transactions that have the largest overlap-free opening profit removed. This
shows how much of the month comes from a handful of moments.

**Express-lane note (August).** The 50.9% express-lane share of one-sided-swap profit is dominated
by the two WBTC/WETH 0.3% liquidation events (blocks 496,292,234 and 496,292,236): those four rows are
$2,440 of the $2,634 express-lane one-sided profit. Without them the share is about 7% ($194 of
$2,734). The capture table itself is unchanged.

**Possible future project, not explored here:** trading behind liquidations. Liquidators that route
through thin pools leave large, short-lived dislocations, and in August an express-lane contract
took both large ones. Recorded as an idea only. It isn't part of this study and won't be looked at
in the September evaluation.

## 2026-10-18 - August recomputed with the reporting correction

Same opportunity rows as before; only the totals change (data/aug_scan_summary.txt).

**Opening net profit, flash swap:**

| Bin | Largest per opening tx (primary) | Primary, ex top 3 | All pool pairs (overlapping, old) |
|---|---|---|---|
| > $0 | 14,837, $3,274.11 | 14,834, $1,817.51 | 17,661, $6,012.51 |
| > $0.10 | 1,495, $3,045.58 | 1,492, $1,588.98 | 2,249, $5,731.95 |
| > $1 | 200, $2,707.57 | 197, $1,250.97 | 371, $5,234.34 |
| > $10 | 26, $2,213.52 | 23, $756.92 | 53, $4,344.12 |
| > $100 | 4, $1,614.08 | 1, $157.48 | 8, $3,058.99 |

- Top 3 opening transactions: 0x51cdb53d... (block 496,292,236, $662.40) and 0x7ac980b5...
  (496,292,234, $620.42), the two WBTC liquidations; and 0x652f60c6... (496,848,609, $173.77).
- Median opening net (primary) $0.0108, p90 $0.10, p99 $1.38.

**Left for a late bot (primary: largest net at open+N per opening transaction).** Ex top 3 is
identical, because all three top events closed within one block.
- N=1: 2,010 of 14,837 opening txs (13.5%), $539.73; 51 above $1, 10 above $10
- N=2 (primary): 633 (4.3%), $352.09; 34 above $1, 6 above $10
- N=4: 192 (1.3%), $253.36; 15 above $1, 6 above $10
- N=8: 76 (0.5%), $183.39; 3 above $1, 3 above $10
- Old overlapping figures for reference: N=2 672, $407.96.

**Code for September.** Block range and paths now come from one setting, period.py
(FLASH_ARB_PERIOD=sep). August outputs are unchanged by this: the recomputed August summary is
identical line for line before and after the change. No other code changed. The design freeze
otherwise stands.

- Variants tested: 1.

## 2026-10-19 - Implementation change: base fee fetched only where the fee screen passes (September)

**September data so far.** The event pull and reconciliation finished: 3,697,842 events, all 12,060
pool-windows (12 pools x 1,005 windows) match the archive, with no tick or Camelot fee mismatches.
The full base-fee fetch (1,244,245 event blocks) estimated 33 hours and could have exceeded the free
Alchemy monthly allowance, so Harrison stopped it after 9 of 125 parts. No September opportunity
data exists yet.

**Change (order of work only, not the method).** The tick read and checks run first, then a screen
pass lists the blocks where at least one pair-direction state passes the fee screen. The base fee is
fetched only at those blocks, and then the scan and capture finish as before. Headers from the 9
finished parts of the stopped fetch are reused where they fall on those blocks.

**Why results are identical to a full fetch.** In the scan, gas enters only through net profit =
gross - gas, and that's computed only for states that pass the screen. A state that fails the screen
has no net profit: it can't open an opportunity, and it closes an open one, whatever gas costs. The
Aave comparison uses gas only when an opportunity opens, which requires passing the screen. Capture
doesn't use gas. Every evaluated state is at an event block, so the base fee is the one fetched at
that exact block, and the carry-forward rule is never used. The screen itself uses only prices and
fees.

**Verified on August.** The screen pass gives 205,088 passing states in 96,083 distinct blocks (11% of
the 855,735 event blocks), all inside the full gas file. I reran the August scan with the gas file
cut down to those 96,083 blocks. The opportunity file is byte-identical to the run with the full gas
file, and the scan counts are identical. The full August gas file was restored afterwards. Along the
way I found that rows in the opportunity file came out in a varying order between runs, because
Python's set iteration order changes from process to process. Values never changed. The file is now
written sorted by opening transaction and pools. The August summary is unchanged by that, line for
line.

**Consequence for reporting.** September's base-fee statistics will describe the screened blocks
only, not all event blocks as in August. That's a description of the gas data, not an input to any
result.

- Variants tested: 1.

## 2026-10-19 - September results: the one-time evaluation (variant 1)

This is the evaluation run. September has now been looked at once, with the design frozen in the
entry "The 8 August opportunities over $100, and design freeze", the reporting rules in "Reporting
correction", and the gas-fetch order in "Implementation change" (identical results, verified on
August). Nothing was changed after seeing these numbers. The evaluation period is now spent.
Full printed summary: data/sep_scan_summary.txt. Per-opportunity rows: data/raw/sep_opportunities*.csv
(not in git). The label "Aave premium (bps) over August" in the printout is a fixed string. The
values are September's.

**Checks.** Tick maps read at block 500,455,224, and active liquidity matches liquidity() in all 12
pools. Check 1: 12,072 of 12,072 pool-checkpoints match. Revised Check 2: 100.000% exact in all 10
scanned pools. ARB/WETH is also 100%, and ARB/USDC is 99.926% (not gating). Aave premium: 5 bps at
all 1,006 checkpoints. Base fee fetched at the 104,755 screened blocks only: median 0.0200 gwei,
max 0.458 gwei. Every opportunity closed within September.

**Side by side (opening net profit, flash swap, gas at 350,000 units, L1 data fee excluded):**

| | August (calibration) | September (evaluation) |
|---|---|---|
| States evaluated / passed screen | 14,197,262 / 205,088 | 14,269,418 / 200,448 |
| Primary (largest per opening tx), > $0 | 14,837, $3,274.11 | 13,302, $35,317.82 |
| Primary, > $0.10 | 1,495, $3,045.58 | 1,582, $35,121.45 |
| Primary, > $1 | 200, $2,707.57 | 434, $34,775.20 |
| Primary, > $10 | 26, $2,213.52 | 140, $33,860.97 |
| Primary, > $100 | 4, $1,614.08 | 47, $30,879.08 |
| Primary ex top 3, > $0 | 14,834, $1,817.51 | 13,299, $23,160.01 |
| Primary ex top 3, > $1 | 197, $1,250.97 | 431, $22,617.39 |
| Primary ex top 3, > $10 | 23, $756.92 | 137, $21,703.16 |
| Primary ex top 3, > $100 | 1, $157.48 | 44, $18,721.27 |
| All pool pairs (overlapping), > $0 | 17,661, $6,012.51 | 16,435, $64,626.23 |
| Median / p90 / p99 (primary) | $0.0108 / $0.10 / $1.38 | $0.0109 / $0.13 / $11.01 |
| Largest | $662.40 | $5,111.18 |
| Aave 5 bps instead of flash swap (all pairs) | 1,702 positive, $4,777.40 | 2,421 positive, $60,360.58 |

**Left for a late bot (primary: largest net at block open+N per opening transaction):**

| N | August | September | September ex top 3 |
|---|---|---|---|
| 1 | 2,010, $539.73 | 1,520, $18,372.05 | 1,517, $9,259.83 |
| 2 (primary) | 633, $352.09 | 566, $7,161.43 | 564, $6,060.38 |
| 4 | 192, $253.36 | 202, $2,363.20 | 202, $2,363.20 |
| 8 | 76, $183.39 | 89, $204.27 | 89, $204.27 |

(August ex top 3 is the same as August primary.)

**Duration (September):** 6,638 closed in the same block, 8,068 in the next block, 1,501 within 2-4,
199 within 5-20, and 29 lasted more than 20 (August: 8,479 / 6,989 / 1,995 / 175 / 23).
Universe-pool transactions between opening and closing: median 3, p90 20.

**Who closed it (September).** All 14,058 closing transactions were fetched.
- Atomic arbitrage: 497 (3.0%), $1,638 (2.5%). Express lane: 0.4% of count, 0.0% of profit.
- One-sided swap: 13,873 (84.4%), $33,792 (52.3%). Express lane: 8.0% of count, 0.5% of profit.
- Other: 2,065 (12.6%), $29,196 (45.2%). Express lane: 9.8% of count, 0.1% of profit.
- Concentration by tx.to: the top 1, 3 and 10 take 21.5%, 51.2% and 86.2% of profit. By tx.from:
  9.5%, 24.2% and 47.3%. Contract 0x93c3...dd17 is again the most frequent large closer (1,739
  closes, $11,530).

**Concentration in one window (descriptive, not a pre-registered cut).** On 24 September between
19:17 and 21:02 UTC (blocks 508,535,000 to 508,560,000), the window holds 672 of 13,302 primary
opportunities but $33,488 of the $35,318 primary total (94.8%), and 45 of the 47 above $100. At N=2
it holds $7,114 of the $7,161. Outside this window, September's primary total is $1,829.44 (12,630
opportunities, 2 above $100), and the late-bot figures are N=1 $114.65, N=2 $47.72, N=4 $21.50 and
N=8 $0.19. The pre-registered ex top 3 rule removes only 3 of the window's events, so it doesn't
show this.

**The 10 largest opportunities, checked (correctness only, nothing changed).** All are WETH/USDC
and all are inside that window. Buy pool -> sell pool. None of the closing transactions went
through the express lane.

| # | Open block | Buy -> sell | Net | Closing tx (block) | Closer (tx.to), group |
|---|---|---|---|---|---|
| 1 | 508,540,760 | Uni 0.3% -> Uni 0.05% | $5,111.18 | [0x91027d38...0335](https://arbiscan.io/tx/0x91027d3836917bc5c4fe6ad81c76183933c41ccf30a8a132e2152bce5b760335) (508,540,762) | 0x089c...4a87, other |
| 2 | 508,540,895 | Uni 0.3% -> Uni 0.05% | $3,985.97 | [0x7a38a2fd...807a](https://arbiscan.io/tx/0x7a38a2fd4d1c4d6998d7c1d6ca23aa100d04ef4bc2e843330656372daf29807a) (508,540,897) | 0x089c...4a87, other |
| 3 | 508,554,119 | Uni 0.05% -> Uni 0.3% | $3,060.66 | [0x38d49ec3...6d45](https://arbiscan.io/tx/0x38d49ec334edef561868bf81a0ee1242fcb869a563a249cad4db3165d4516d45) (508,554,122) | 0xd681...6aef, other |
| 4 | 508,554,116 | Uni 0.05% -> Pancake 0.05% | $2,455.34 | [0x70991b44...dcde](https://arbiscan.io/tx/0x70991b44b1550e0a528e3dc733123580af12676eb579157b8806fca77137dcde) (508,554,119) | 0x93c3...dd17, one-sided |
| 5 | 508,553,007 | Uni 0.05% -> Uni 0.3% | $1,970.83 | [0x54b3cd9b...1994](https://arbiscan.io/tx/0x54b3cd9b566c4134879e6fccb1a9119ed44855bbe734904ead9058fbf3191994) (508,553,011) | 0x0a13...da04, other |
| 6 | 508,553,004 | Uni 0.3% -> Pancake 0.05% | $1,921.28 | [0x9f39d95d...a787](https://arbiscan.io/tx/0x9f39d95d8ac5d30b033f25f80e1268478a799214c434cbbb8125a02f6ceba787) (508,553,007) | 0x93c3...dd17, one-sided |
| 7 | 508,554,116 | Uni 0.05% -> Camelot | $1,538.17 | [0xaf29d879...093a](https://arbiscan.io/tx/0xaf29d8795b5d22e8c28f078eb4e005e25284ba4cff20fe2f7cc3bfde7bd1093a) (508,554,116) | 0x1efb...a7d, other |
| 8 | 508,553,004 | Uni 0.05% -> Pancake 0.05% | $1,479.18 | [0xd1594bb7...b437](https://arbiscan.io/tx/0xd1594bb733b7a0fdbbc2a2a8c0783142c8d44b60d4f16d3ca982e74a0711b437) (508,553,007) | 0x69bb...e4e3, atomic arbitrage |
| 9 | 508,553,004 | Uni 0.3% -> Camelot | $1,341.33 | [0xae20957a...a604](https://arbiscan.io/tx/0xae20957a05b145b8f36e8ee843bad45af3885cee8d95762df7dad0efe53ba604) (508,553,005) | 0x6367...519d, one-sided |
| 10 | 508,540,740 | Pancake 0.05% -> Uni 0.05% | $1,120.46 | [0xce3ce90f...f6ed](https://arbiscan.io/tx/0xce3ce90f2cd1721252a69d56149a8d4f18e21f7a4a0af2559d911570aa6af6ed) (508,540,741) | 0xd681...6aef, other |

What opened the gaps (seven opening transactions):
- Before and after the window, WETH/USDC on Arbitrum traded at about 2,670-2,700 USDC. Inside it,
  three very large trades pushed the deep Uniswap 0.05% pool about 6% away and back within minutes.
  They also moved the WETH/USDT 0.05% pool, so it was price impact on-chain, not a data error.
- Block 508,540,740 (19:41:45 UTC, [0x0aa9c5b9...](https://arbiscan.io/tx/0x0aa9c5b95facdd5f3ef9711b0207e9a86a26aea6620e41862501c679d6dce8b7)):
  a large WETH buy routed through several pools (contract 0x2d58...631a, with the 1inch router among
  the log emitters). About 755 WETH came out of Uni 0.05% for 2.12M USDC, plus legs in Uni 0.3%,
  WETH/USDT and WBTC/WETH. Uni 0.05% went to 2,870, against 2,757 on PancakeSwap 0.05% (#10).
- Blocks 508,540,760 and 508,540,895 ([0x5abf2af6...](https://arbiscan.io/tx/0x5abf2af6e4a9fda16b42b5e1d4e9ecc66e7b1d8386f73b9345a71ac8997d6c79),
  [0x818fd32e...](https://arbiscan.io/tx/0x818fd32e0adaec9186b9b45697982acd7a4735b05a757f4efa6f57c7c32a7a85)):
  contract 0x93c3...dd17 sold 119.8 and then 142.6 WETH into Uni 0.3% only, pushing it to 2,739 and
  2,702 while Uni 0.05% was still at 2,850 and 2,797 (#1, #2). This fits a bot trading that one pool
  back towards an outside price, which leaves the 0.05% pool out of line with it.
- Blocks 508,553,004 and 508,554,116 (20:32:38 and 20:37:14 UTC, [0xa1e7340f...](https://arbiscan.io/tx/0xa1e7340fafd5c99c236ccf560fef83ad4908b306cd4f7bb1a344bcea8602c42b),
  [0x66e4bfe2...](https://arbiscan.io/tx/0x66e4bfe281c7e4cf3990c2f6f10b8ae4f6785ec7ae15e2a8c5873cd7af19f531)):
  two large WETH sales by one sender (0x2bca...BeAE), through contract 0x2d01...Fe65 with the
  Universal Router execute selector (0x3593564c). They used round amounts split over Uni 0.05%, Uni
  0.3%, WETH/USDT and WBTC/WETH, about 1,998 WETH and 2,513 WETH in total. The largest leg was
  1,633 WETH into Uni 0.05% for 4.27M USDC. Uni 0.05% fell to 2,570 and then 2,535, while
  PancakeSwap 0.05% and Camelot stayed at about 2,686 (#4, #6, #7, #8, #9).
- Blocks 508,553,007 and 508,554,119 ([0x9f39d95d...](https://arbiscan.io/tx/0x9f39d95d8ac5d30b033f25f80e1268478a799214c434cbbb8125a02f6ceba787),
  [0xcfefc038...](https://arbiscan.io/tx/0xcfefc03807b2927830ed0c0abdefb0739914f5fee4160cd6e2f0ca0ca27d517c)):
  0x93c3 again bought 90.1 and then 129.1 WETH from Uni 0.3% only, lifting it to 2,679 while Uni
  0.05% was at 2,613 and 2,598 (#3, #5).

Correctness checks on these 10:
- Re-sizing from the replayed state right after each opening transaction gives the same trade size
  as the file and the same net profit to the cent (gross minus gas of $0.02-0.07).
- At the end of each opening block, the replayed state of both pools (sqrt price, tick, liquidity)
  equals the archive state, in all 10 cases.
- Independent maths check: for the 8 cases still open at the end of their opening block with no
  Camelot leg, I re-sized the trade at that state and quoted both legs on-chain with the official
  QuoterV2 contracts at that block (Uniswap 0x61fF...B21e, PancakeSwap 0xB048...5997). Both legs
  equal the model's outputs exactly, to the last unit, in all 8. Those end-of-block profits were
  $4,321, $3,973, $2,991, $1,476, $1,107, $677, $1,113 and $1,069. #7 closed inside its opening
  block, and #9 has a Camelot leg.
- A real trade matches the model: the closer of #1 put 274,313 USDC through Uni 0.3% and the WETH
  into Uni 0.05%, against the model's optimal 274,270 USDC at the opening state. It kept 1.2953 WETH.
- Units: profit is in USDC, so no price conversion is involved. Token transfers in the closing
  transactions equal the swap amounts (no fee-on-transfer), and Check 2 reproduced every swap in
  these pools exactly, including price-limited ones.
- Conclusion: the large September opportunities are real on-chain dislocations, priced correctly.
  None of them is an artefact.

**Reading of the capture labels (description only, the table is unchanged).** The rule for "atomic
arbitrage" needs a net token gain at tx.from or tx.to. The closers of #1, #2 and #3 do the whole
two-pool trade in one transaction but send the profit to a third address (0x3050... and 0x0084...),
so they are labelled "other". This is common. Of September's 2,065 "other" closes, 2,024 ($28,575
of $29,196) swapped in both pools of the pair in opposite directions. In August it was 1,631 of
1,659 ($751 of $755). So "atomic arbitrage" in both months' tables is a lower bound, and "other" is
mostly two-pool arbitrage that pays out elsewhere. Express-lane use is small in September: about
0.5% of profit, and none of the top 10.

**Interpretation (evaluation month).** September's totals are about ten times August's, but that
comes from one window of under two hours on 24 September. Three trades of $2-7M pushed the deepest
Arbitrum WETH/USDC pool about 6% out of line, and the gaps were taken within 0-4 blocks, mostly by
two-pool arbitrage contracts outside the express lane. For a bot that is two blocks late, September
left $7,161 (primary), $7,114 of it in that window, and $48 in the rest of the month. That is before
the L1 data fee, the gas of failed attempts and competition with other late bots for the same
leftovers. So the finding from August holds outside rare large dislocations: almost nothing is left
for a retail bot. Such events do leave $1,000-sized gaps open for a few blocks, but they are rare
(one in each month, of very different size) and can't be predicted from this data.

- Variants tested: 1.
- Evaluation period (September 2026): spent, looked at once on 2026-10-19.

## 2026-10-20 - Correction: two-pool arbitrage label in the capture table (both months)

The rule for "atomic arbitrage" was a classification bug, not a method choice (Harrison). It
required swaps in both pools of the pair in opposite directions and a net token gain at tx.from or
tx.to. Arbitrage contracts that pay their profit to a third address, which includes the closers of
the three largest September opportunities, failed the second condition and were labelled "other".
The corrected rule counts any closing transaction that swaps in both pools in opposite directions
as two-pool arbitrage, whoever receives the profit. The group is now called "two-pool arbitrage".

Only the capture table changes. Opportunities, profits, durations, closers, late-bot figures and the
Aave comparison are identical: the summary files differ only in those three lines. No receipts were
refetched.

**Who closed it, corrected:**

| Group | August | September |
|---|---|---|
| Two-pool arbitrage | 1,994 (11.3%), $833.96 (13.9%); express lane 11.5% of count, 2.4% of profit | 2,521 (15.3%), $30,213.20 (46.8%); express lane 8.1% of count, 0.1% of profit |
| One-sided swap (unchanged) | 15,639 (88.6%), $5,174.05 (86.1%); express lane 12.2%, 50.9% | 13,873 (84.4%), $33,792.46 (52.3%); express lane 8.0%, 0.5% |
| Other | 28 (0.2%), $4.51 (0.1%); express lane 3.6%, 0.1% | 41 (0.2%), $620.56 (1.0%); express lane 0.0%, 0.0% |

The old figures were: atomic arbitrage 363, $83.12 (Aug) and 497, $1,638.14 (Sep); other 1,659,
$755.35 and 2,065, $29,195.63. What remains in "other" is closes that swapped in both pools in the
same direction (28 in August, 40 in September), plus one September close with no swap in either pool.

**Reading.** In September, two-pool arbitrage closed about half the opening profit, and almost all
of the 24 September window's large gaps. In August, single-pool swaps dominate. The August
express-lane share of one-sided profit (50.9%) is still the two WBTC liquidation backruns. In
neither month does the express lane take a meaningful share of two-pool arbitrage profit.

- Variants tested: 1.
