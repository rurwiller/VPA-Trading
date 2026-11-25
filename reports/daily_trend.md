# Daily trend rules on ETFs

Rules decided BEFORE looking at results (kept to four, to limit the number of tries):
  buy & hold       the benchmark
  200-day          hold while the close is above its 200-day average, else cash
  12-month         hold while the 252-day return is positive, else cash (time-series momentum)
  trend pullback   only while above the 200-day: buy at the close when the 2-day RSI is below 10, sell at the first
                   close above the 5-day average (short, in-trend dips)
Signals use the close of day t; the position earns the return from that close to the next (an end-of-day order).
Cost: 2 bps of the position each time it changes. Cash earns nothing. Prices are split-adjusted only (no dividends),
for every rule alike. Books: SPY alone, QQQ alone, and an equal-weight basket of 15 ETFs (each asset in or out on its own).
Discovery = before 2026-05-21; the holdout after it is shown once.

  python scripts/daily_trend_test.py   -> reports/daily_trend.md


Measured from 2017-01-03 (after the 252-day warm-up) to 2026-11-24. Each cell: yearly growth | Sharpe | worst drop from a high | yearly volatility.


## SPY

| Rule | Whole period | Discovery (to May 2026) | Holdout (since May 21) | 2022 only |
|---|---|---|---|---|
| buy & hold | +12.5% | 0.74 | -34.2% | 18.0% | +13.6% | 0.79 | -34.2% | 18.1% | -5.8% | -0.28 | -11.5% | 16.6% | -19.6% | -0.78 | -25.4% | 24.3% |
| 200-day | +7.9% | 0.70 | -21.2% | 11.9% | +8.5% | 0.75 | -21.2% | 11.8% | -2.9% | -0.14 | -6.3% | 14.1% | -15.7% | -2.35 | -16.1% | 7.2% |
| 12-month | +8.9% | 0.68 | -22.8% | 13.9% | +9.8% | 0.75 | -22.8% | 13.7% | -5.8% | -0.28 | -11.5% | 16.6% | -16.3% | -1.26 | -16.7% | 13.4% |
| trend pullback | +2.8% | 0.50 | -22.0% | 5.8% | +2.3% | 0.42 | -22.0% | 5.8% | +12.7% | 2.01 | -1.9% | 6.1% | -3.9% | -1.46 | -4.1% | 2.7% |

Time in the market: buy & hold 100%, 200-day 82%, 12-month 86%, trend pullback 10%

## QQQ

| Rule | Whole period | Discovery (to May 2026) | Holdout (since May 21) | 2022 only |
|---|---|---|---|---|
| buy & hold | +18.5% | 0.85 | -35.6% | 23.1% | +21.0% | 0.95 | -35.6% | 22.8% | -19.4% | -0.64 | -19.9% | 27.7% | -33.2% | -1.09 | -35.2% | 32.1% |
| 200-day | +16.1% | 0.96 | -21.9% | 17.0% | +18.5% | 1.10 | -21.9% | 16.6% | -19.7% | -0.83 | -16.2% | 23.2% | -17.8% | -2.52 | -18.5% | 7.7% |
| 12-month | +12.7% | 0.70 | -32.4% | 19.9% | +14.8% | 0.81 | -32.4% | 19.4% | -19.4% | -0.64 | -19.9% | 27.7% | -24.6% | -1.57 | -25.2% | 17.1% |
| trend pullback | +4.2% | 0.54 | -13.2% | 8.1% | +4.8% | 0.65 | -13.2% | 7.6% | -6.5% | -0.41 | -6.8% | 13.9% | -1.0% | -0.43 | -1.3% | 2.3% |

Time in the market: buy & hold 100%, 200-day 83%, 12-month 88%, trend pullback 12%

## 15-ETF basket

| Rule | Whole period | Discovery (to May 2026) | Holdout (since May 21) | 2022 only |
|---|---|---|---|---|
| buy & hold | +9.7% | 0.72 | -29.4% | 14.1% | +10.4% | 0.76 | -29.4% | 14.3% | -2.4% | -0.16 | -7.9% | 11.2% | -12.7% | -0.63 | -19.1% | 18.6% |
| 200-day | +5.3% | 0.71 | -11.6% | 7.7% | +5.7% | 0.76 | -11.6% | 7.8% | -2.1% | -0.26 | -5.2% | 7.2% | -8.9% | -1.68 | -9.7% | 5.5% |
| 12-month | +5.2% | 0.63 | -16.1% | 8.7% | +5.8% | 0.70 | -16.1% | 8.6% | -4.3% | -0.39 | -8.2% | 10.1% | -8.8% | -1.07 | -10.2% | 8.3% |
| trend pullback | +1.3% | 0.43 | -9.6% | 3.1% | +1.2% | 0.39 | -9.6% | 3.1% | +3.5% | 1.12 | -2.1% | 3.1% | -1.6% | -0.87 | -2.3% | 1.8% |

Daily correlation with the TSLA + QQQ breakout (basket book): buy & hold -0.03, 200-day -0.06, 12-month -0.09, trend pullback +0.02 (near 0 = the two add up without moving together).
