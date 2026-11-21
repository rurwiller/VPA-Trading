# Risk rules replayed on the paper account's real trades

Each rule decides, at a trade's entry time, whether the trade would have been allowed, using only what was known then
(trades already closed, positions already open). A blocked trade's P/L is removed. Simplifications, stated plainly:
- the replay cannot invent trades a rule would have freed room for (e.g. buying power used elsewhere), so it can only
  remove trades; their knock-on effects are ignored;
- the daily loss stop uses realized P/L only (closed trades), not open losses.
Positions = the pieces of one entry (half exits, the breakout's thirds) grouped together, as on the scorecard.

86 positions over 13 trading days (2026-11-04 to 2026-11-20). Total P/L +3,554.

| Rule | Trades kept | Blocked | P/L of the blocked trades | Total P/L | Win rate | Worst day | Worst drawdown |
|---|--:|--:|--:|--:|--:|--:|--:|
| No rule (what happened) | 86 | 0 | +0 | +3,554 | 60% | -1,603 | -5,281 |
| After a loss on a stock: no more trades in it that day | 65 | 21 | -711 | +4,266 | 63% | -1,025 | -4,175 |
| After a loss on a stock: none in the same direction that day | 69 | 17 | +7 | +3,547 | 61% | -1,794 | -5,134 |
| After a loss on a stock: 60-minute cooldown | 79 | 7 | +708 | +2,846 | 58% | -1,794 | -5,718 |
| After a loss on a stock: 30-minute cooldown | 81 | 5 | +401 | +3,154 | 59% | -1,794 | -5,652 |
| At most 2 losses per stock per day | 83 | 3 | +370 | +3,184 | 59% | -1,794 | -5,652 |
| No adds: one open position per stock | 79 | 7 | +2,351 | +1,203 | 59% | -1,603 | -4,976 |
| Daily loss stop $1,000 (realized) | 72 | 14 | +210 | +3,344 | 61% | -1,650 | -4,864 |
| Daily loss stop $2,000 (realized) | 86 | 0 | +0 | +3,554 | 60% | -1,603 | -5,281 |
| Daily loss stop $3,000 (realized) | 86 | 0 | +0 | +3,554 | 60% | -1,603 | -5,281 |
| At most 2 open positions in the same direction | 83 | 3 | +1,027 | +2,527 | 59% | -1,603 | -5,550 |
| At most 3 open positions in the same direction | 86 | 0 | +0 | +3,554 | 60% | -1,603 | -5,281 |
| Combined: same-direction no-repeat after a loss + no adds + $2,000 daily stop | 64 | 22 | +1,859 | +1,696 | 61% | -1,505 | -4,329 |

## P/L by strategy

| Strategy | Positions | Won | P/L | Average |
|---|--:|--:|--:|--:|
| Alert mode | 12 | 58% | +218 | +18 |
| Banks level | 3 | 33% | +214 | +71 |
| Candle scanner | 61 | 62% | +405 | +7 |
| TSLA breakout | 10 | 60% | +2,717 | +272 |

## Repeat trades in the same stock on the same day

| Trade # in that stock that day | Positions | Won | P/L |
|---|--:|--:|--:|
| 1 | 49 | 59% | +1,242 |
| 2 | 22 | 59% | +1,608 |
| 3 | 10 | 60% | +38 |
| 4+ | 5 | 80% | +666 |

## By day

| Day | Positions | P/L |
|---|--:|--:|
| 2026-11-04 | 11 | -405 |
| 2026-11-05 | 5 | +61 |
| 2026-11-06 | 5 | +1,984 |
| 2026-11-09 | 3 | +293 |
| 2026-11-10 | 11 | +3,221 |
| 2026-11-11 | 5 | -1,603 |
| 2026-11-12 | 9 | -80 |
| 2026-11-13 | 9 | -664 |
| 2026-11-16 | 5 | -973 |
| 2026-11-17 | 6 | -1,489 |
| 2026-11-18 | 4 | -472 |
| 2026-11-19 | 7 | +2,048 |
| 2026-11-20 | 6 | +1,634 |
