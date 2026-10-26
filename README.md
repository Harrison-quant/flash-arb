# How much DEX arbitrage is left for a retail bot on Arbitrum?

A measurement study of two-pool arbitrage between decentralised exchanges on Arbitrum One, over
August and September 2026. The goal was not to make money. It was to find out how much arbitrage
actually appears, who takes it, and how much would still be there for an ordinary bot that sees it a
fraction of a second late.

**Short answer:** very little, outside rare market shocks. In a normal month, a bot two blocks late
would have found a few hundred dollars in total, before costs I could not yet measure. Almost all the
real money appears in one or two short, unpredictable events per month.

Status: phase 1 (measurement) is complete. Phase 2 (a real contract replayed on a local copy of the
chain) is next.

## How this was built

I designed the study, set the rules and made the decisions; the code was written and run by an AI
coding assistant (Claude) working under my direction. My part was the research question, the
pre-commitments, checking that results made sense, and deciding what to do when something went wrong.
Every step, including mistakes, is in [JOURNAL.md](JOURNAL.md), which is written as it happened and
never edited after the fact.

## Background in plain terms

- **Arbitrage:** the same pair of tokens (say WETH and USDC) trades in several pools at once. If one
  pool's price drifts from another's by more than the fees, you can buy in the cheap pool and sell in
  the expensive one in a single transaction and keep the difference.
- **Flash swap / flash loan:** the trade borrows the tokens and repays them inside the same
  transaction, so it needs no capital. A failed attempt still costs gas.
- **Timeboost / express lane:** Arbitrum auctions an "express lane" every minute. The winner's
  transactions go through immediately; everyone else's are held back about 200 milliseconds. A 2026
  study found three entities win almost all auctions. My starting hypothesis was that the express-lane
  holders take almost all arbitrage and a bot without it is always too late.

## Setup and pre-commitments

Fixed in the journal before any trading data was pulled:

- **Pairs:** WETH/USDC, WETH/USDT, WBTC/WETH, ARB/WETH, ARB/USDC.
- **Exchanges:** Uniswap V3, Camelot, SushiSwap, PancakeSwap V3.
- **Pools:** every pool for those pairs on those exchanges with more than $250k locked on 1 August
  2026. That rule gave 12 pools and 14 same-pair pool combinations to compare (the two ARB pools had
  no partner above the threshold, and I did not lower it to bring more in).
- **Periods:** August 2026 for calibration, September 2026 for evaluation. The method was frozen
  after August, and September was run once.
- **Costs:** pool fees, financing cost and gas at each block's actual price.
- **Variants:** every version of the method tried is counted. The final count is 1.

How an opportunity is measured:

1. Rebuild every pool's exact state after every transaction from the on-chain event log.
2. Flag moments where a profitable trade is possible at all after both pools' fees.
3. For those, find the best trade size with exact pool maths and subtract gas. Financing is a flash
   swap from the cheaper pool (no extra fee); an Aave flash loan at 0.05% is reported for comparison.
4. An opportunity runs from the transaction that opens a gap to the one that closes it. For each, I
   recorded who closed it and whether that transaction used the express lane.
5. "Left for a late bot": opportunities still open two blocks after they appeared (about half a
   second), valued at that later point. One, four and eight blocks are shown alongside.

## Data checks

The results are only as good as the replay of the pools, so this was checked hard:

- **Completeness:** every event of the 12 pools was pulled, and the rebuilt state was compared with
  the chain's own recorded state every 10,000 blocks. 12,792 of 12,792 checks matched exactly in
  August, and 12,060 of 12,060 in September.
- **Swap maths:** every real swap in each month (2.5 million in August) was replayed through my model
  of the pools. Every swap in the scanned pools was reproduced exactly: same amounts in and out, same
  final price, to the last unit.
- **Spot checks:** the ten largest September opportunities were re-priced with the exchanges' own
  on-chain quote contracts at those blocks. The model matched to the last unit. In one case a real
  bot made almost exactly the trade the model said was optimal (274,313 USDC against the model's
  274,270).
- **By hand:** the largest cases in both months were traced transaction by transaction to confirm
  they were real price dislocations and not data errors.

## Results

All figures are net of pool fees and gas, but **exclude the Arbitrum L1 data fee** (see limitations),
so they overstate profit somewhat. When one trade knocks a pool out of line, it opens gaps against
several other pools at once, but only one can really be taken, so the totals count only the largest
opportunity per triggering transaction.

| | August (calibration) | September (evaluation) |
|---|---:|---:|
| Opportunities found | 14,837 | 13,302 |
| Total opening profit | $3,274 | $35,318 |
| Same, with the 3 biggest events removed | $1,818 | $23,160 |
| Median opportunity | $0.011 | $0.011 |
| Opportunities over $100 | 4 | 47 |
| Largest single opportunity | $662 | $5,111 |
| Closed in the same or next block | 88% | 89% |
| **Left for a bot 2 blocks late** | **633, $352** | **566, $7,161** |
| Left for a bot 1 / 4 / 8 blocks late | $540 / $253 / $183 | $18,372 / $2,363 / $204 |

September looks ten times better than August, but that is one event. On 24 September, between 19:17
and 21:02 UTC, a few trades worth $2-7 million each pushed the deepest WETH/USDC pool about 6% away
from the others and back. That window holds 94.8% of September's total. **Outside it, September left
$48 for a bot two blocks late, for the whole month.**

### Who took the profit

Share of opening profit by the kind of transaction that closed the gap (all pool combinations
counted):

| Closed by | August | September |
|---|---:|---:|
| Two-pool arbitrage (trades both pools in one transaction) | 13.9% | 46.8% |
| A trade in only one of the two pools | 86.1% | 52.3% |
| Other | 0.1% | 1.0% |
| Express-lane share of two-pool arbitrage profit | 2.4% | 0.1% |

The top 10 closing contracts took 86% of the profit in both months. One contract was the most active
large closer in both.

## What surprised me

- **The express lane barely mattered.** I expected express-lane holders to take nearly everything.
  In September, express-lane transactions closed about 0.5% of the profit or less in every group, and
  none of the ten largest opportunities. In August, half of the single-pool profit went through the
  express lane, but that is two events (below); without them it is about 7%. Whatever decided who won
  these gaps, in these two months it was mostly not the auction.
- **Profit is concentrated in rare shocks.** The median opportunity is about one cent in both months.
  August's largest came from two loan liquidations routed through a thin WBTC/WETH pool, which moved
  it 6% for a moment. September's came from one two-hour window. These events are real and leave
  $1,000-sized gaps open for a few blocks, but there was one per month, of very different size, and
  nothing in the data says when the next one comes.
- **Two-pool arbitrage takes about half, not all.** In September, bots trading both pools at once
  closed about half of the profit, and almost all of the big gaps. The rest, and most of August, was
  closed by trades in a single pool. Those are likely bots pricing against other venues, such as
  centralised exchanges, though ordinary users cannot be told apart from them with this data.

## Limitations

- **L1 data fee not counted.** Every Arbitrum transaction also pays to post its data to Ethereum.
  That is not in the block data I used, so all profit figures are too high. Phase 2 measures it.
- **Gas is an estimate.** 350,000 gas units per trade, to be replaced by the real figure from phase 2.
  At August's typical gas price this cost about a cent, so it matters for small opportunities only.
- **Failed attempts not counted.** A real bot pays gas on every attempt that arrives too late and
  reverts. With most gaps gone within a block, that could be most attempts.
- **Competition for the leftovers not modelled.** "Left for a late bot" assumes I am the only late
  bot. Any other bot with the same delay competes for the same few hundred dollars.
- **Only two months,** each dominated by a single event. Totals from months like these are mostly
  luck about when the next shock comes.
- **Scope.** Only same-pair, two-pool trades in the 12 fixed pools. Uniswap V4 (3-12% of liquidity
  for these pairs), smaller pools and multi-hop routes are not measured, so some gaps may be closed
  by routes I do not see.
- **Labels are approximate.** "One-sided" closers could be bots or ordinary users; the data does not
  separate them.

## Corrections log

Each is a separate journal entry, written when it happened.

1. **Camelot tick-indexing bug (18 Oct).** My model of Camelot pools indexed its price table the wrong
   way. Found and fixed before any check ran.
2. **Faster tick-map source (18 Oct).** Rebuilding pool history from scratch would have taken days, so
   starting pool states were read directly from an archive node instead. Verified identical on the
   one pool built both ways.
3. **Swap-replay check revised after it failed (18 Oct).** The check as written assumed real swaps
   run to completion, but many stop at a price limit, so it failed. The revised check (every swap
   reproduced exactly) was approved and logged as a change made after seeing the failure, not as a
   pre-registered rule.
4. **Overlap in totals (18 Oct, before September).** Totals first added gaps across pool combinations
   that one trade had opened at the same time, double-counting. Primary totals now keep the largest
   per triggering transaction; the old figures are still reported.
5. **Gas fetch order (19 Oct).** To stay within free data limits, gas prices were fetched only where
   needed. Results verified byte-identical on August.
6. **Two-pool arbitrage label (20 Oct, after September).** Arbitrage contracts that sent their
   profit to a third address were wrongly labelled "other". Fixing this moved two-pool arbitrage
   from 2.5% to 46.8% of September's profit. Only the "who took it" table changed.

## What's next

- **Phase 2:** a real arbitrage contract on a local copy of the chain, replaying historical
  opportunities at their original blocks, to measure real gas and the L1 fee and check the phase 1
  numbers.
- **Phase 3:** a live listener that records what it would have done, without trading.
- **Phase 4:** a tiny live test, only if phase 3 is net positive after the cost of failed attempts.
- Later: the same measurement on Base, which has no express lane.

## Files

- [JOURNAL.md](JOURNAL.md): the full research log.
- `data/pools.csv`: the 12 pools. `data/aug_scan_summary.txt`, `data/sep_scan_summary.txt`: full
  results. Raw chain data is not committed and can be re-created with the scripts.
- Scripts: `pool_list.py` (pool universe), `v4_tvl.py` (Uniswap V4 context), `pull_august.py`
  (events and reconciliation), `fetch_gas_aug.py` (gas), `read_ticks.py` and `v3math.py` (pool
  state and swap maths), `scan_august.py` (checks, scan, capture). `period.py` selects the month.
  An archive RPC key goes in `.env` (see `.env.example`).
