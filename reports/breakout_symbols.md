# Trend-day breakout on more symbols

The live trend-day breakout rules (TSLA's) on 9 symbols, and the scanner's raw pivot-candle trades per symbol
(step 4 of the improvement plan). Reads results/strategy_history.pkl. Discovery = before the holdout (2026-05-21).

Per day, after cost, in basis points of the position (1 bp = 0.01%; on $75,000 that is $7.50). Sharpe = per-day mean / std x sqrt(252), the symbol traded alone. t above about 2 is unlikely to be luck; 9 symbols were tried, so the bar for any one of them is higher (about 2.8).

| Symbol | Discovery bps/day | t | Sharpe | Holdout bps/day | t | Holdout days | Trades on % of days | Same with the osc trim (disc / hold) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| QQQ | +3.8 | +2.6 | +1.24 | +3.1 | +0.7 | 115 | 59% | +3.4 / +3.1 |
| AMD | +6.9 | +2.2 | +1.04 | -6.9 | -0.7 | 115 | 58% | +5.7 / -8.7 |
| TSLA | +6.7 | +2.1 | +1.00 | +8.3 | +1.0 | 115 | 62% | +6.7 / +6.9 |
| NVDA | +2.6 | +0.9 | +0.41 | +5.9 | +0.8 | 115 | 60% | +2.5 / +6.7 |
| META | -0.9 | -0.4 | -0.18 | +0.4 | +0.1 | 115 | 59% | -1.3 / -1.1 |
| AMZN | -0.9 | -0.4 | -0.20 | -5.1 | -0.8 | 115 | 61% | -1.3 / -3.7 |
| GOOGL | -0.8 | -0.4 | -0.20 | -3.0 | -0.5 | 115 | 59% | -1.0 / -4.0 |
| AAPL | -0.9 | -0.5 | -0.23 | +4.5 | +0.9 | 115 | 60% | -1.0 / +4.2 |
| MSFT | -0.9 | -0.5 | -0.23 | +2.6 | +0.5 | 115 | 59% | -1.5 / +1.7 |

TSLA alone, each at $75,000: discovery +50 $/day (Sharpe 0.99, worst day -3,468), holdout +62 $/day (Sharpe 1.54)

TSLA + QQQ, each at $75,000: discovery +78 $/day (Sharpe 1.29, worst day -3,855), holdout +85 $/day (Sharpe 1.72)

TSLA + QQQ + NVDA, each at $75,000: discovery +97 $/day (Sharpe 1.11, worst day -7,210), holdout +129 $/day (Sharpe 2.00)

## The scanner's raw pivot candles, by symbol (no live filters)

Pivot-wick candles on 9m / 15m with the live exit (half at +0.5R, rest breakeven / 1R), average R after cost. The live scanner adds filters (a gap, extreme volume for longs, the premier-candle list), so this is the raw material, not the exact live strategy.

| Symbol | Trades | Discovery R | Holdout R |
|---|--:|--:|--:|
| AAPL | 3262 | -0.119 | -0.053 |
| AMD | 3260 | -0.059 | -0.025 |
| AMZN | 3182 | -0.090 | -0.090 |
| GOOGL | 3109 | -0.079 | -0.093 |
| META | 3263 | -0.068 | -0.130 |
| MSFT | 3305 | -0.103 | -0.121 |
| NVDA | 3320 | -0.060 | -0.041 |
| QQQ | 3468 | -0.128 | -0.172 |
| TSLA | 3272 | -0.044 | -0.069 |
