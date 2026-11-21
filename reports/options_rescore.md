# Paper trades re-scored as options

For every position (same entry and exit minutes as the stock trade, half exits included piece by piece):
long -> call, short -> put; three expiries (nearest, about a week, about a month) x two strikes (at the money,
one strike out of the money). Prices = Alpaca's historical 1-minute option trade bars (last trade at or before the
minute, at most 15 minutes old; otherwise that contract is skipped). Costs: Alpaca's bars are trades, not quotes,
so a round-trip spread is charged from today's quoted spreads (indicative feed) for the same symbol / expiry / strike
bucket, i.e. half the spread on the way in and half on the way out.
Result per trade: % return on the premium paid. "Equal risk" compares with the stock: if you spend the trade's
planned risk on premium (so the most you can lose matches the stock stop), option P/L in R = % return on premium.

86 positions, 2026-11-04 to 2026-11-20. Median holding time 16 minutes.

Today's quoted round-trip spread used as the cost (median of call and put, % of the option's mid):

| Stock | Nearest ATM | Nearest OTM | Week ATM | Week OTM | Month ATM | Month OTM |
|---|--:|--:|--:|--:|--:|--:|
| AAPL | 12.1% | 2.8% | 14.3% | 11.5% | nan% | 8.2% |
| AMZN | 11.3% | 6.9% | 10.7% | 7.5% | nan% | 4.5% |
| GOOGL | 9.7% | 7.4% | 14.4% | 15.1% | 8.3% | nan% |
| META | 7.4% | 1.6% | 0.8% | 1.8% | nan% | 2.3% |
| MSFT | 14.4% | 23.6% | 14.0% | 17.5% | 10.5% | nan% |
| NVDA | 0.2% | 0.2% | 2.8% | 3.4% | 2.3% | 0.5% |
| TSLA | 2.4% | 0.9% | 0.6% | 2.4% | 1.0% | nan% |

## Average result per trade

| Instrument | Trades priced | Avg % on premium (after spread) | Before spread | Won | Typical days to expiry |
|---|--:|--:|--:|--:|--:|
| Stock (what the account did), % of position | 86 | +0.05% | | 60% | |
| Nearest expiry, at the money | 62 | -7.5% | +0.2% | 35% | 0 |
| Nearest expiry, 1 strike out | 51 | +2.7% | +8.3% | 51% | 0 |
| About 1 week, at the money | 19 | -6.4% | +1.2% | 21% | 6 |
| About 1 week, 1 strike out | 22 | -5.3% | +2.0% | 18% | 5 |
| About 1 month, at the money | 5 | -4.1% | -1.1% | 20% | 28 |
| About 1 month, 1 strike out | 5 | -2.1% | -0.1% | 40% | 28 |

## Equal risk: spend the trade's planned risk on premium

Stock R = the account's P/L / planned risk ($1,000 scanner, $500 alert, $300 key level). Option R = % on premium / 100 (the premium is the most you can lose, like the stop). Breakout trades excluded (no fixed planned risk).

| Instrument | Trades | Average R | Total R |
|---|--:|--:|--:|
| Stock | 76 | +0.014 | +1.1 |
| nearest atm | 55 | -0.107 | -5.9 |
| nearest otm | 46 | +0.018 | +0.8 |
| week atm | 19 | -0.064 | -1.2 |
| week otm | 21 | -0.062 | -1.3 |
| month atm | 5 | -0.041 | -0.2 |
| month otm | 4 | -0.009 | -0.0 |

## By strategy (about 1 week, at the money, after spread)

| Strategy | Trades | Stock % | Option % on premium | Option won |
|---|--:|--:|--:|--:|
| Alert mode | 12 | +0.03% | -2.6% | 33% |
| Banks level | 3 | +0.07% | -0.9% | 50% |
| Candle scanner | 61 | +0.01% | -12.1% | 0% |
| TSLA breakout | 10 | +0.32% | +nan% | nan% |
