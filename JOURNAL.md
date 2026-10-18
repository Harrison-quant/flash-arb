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
