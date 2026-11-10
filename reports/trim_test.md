# Profit trimming test

5 years of 1m bars. Before = before 2024-11-01, after = from 2024-11-01. Costs = spread + 1 bp.

## A. Trend-day breakout, average per day in bps (Sharpe), per ticker


**TSLA**

| Variant | Before | After | Sharpe before | Sharpe after | Worst day | Winning days |
|---|--:|--:|--:|--:|--:|--:|
| live: thirds at 1% / 2%, breakeven after the first | +9.1 | +3.5 | 1.33 | 0.56 | -462 | 48% |
| + auto-trim a third when the 15m osc crosses 80 against | +8.9 | +3.8 | 1.34 | 0.63 | -441 | 48% |
| + auto-trim a third at 90 | +7.8 | +3.0 | 1.19 | 0.49 | -441 | 48% |
| + auto-trim half at 80 | +8.5 | +4.1 | 1.31 | 0.67 | -441 | 49% |
| auto-trim at 80 instead of the +1% third | +12.6 | +4.4 | 1.61 | 0.61 | -545 | 46% |
| no trimming at all (hold to the rule) | +15.6 | +4.1 | 1.74 | 0.50 | -555 | 42% |

**AMD**

| Variant | Before | After | Sharpe before | Sharpe after | Worst day | Winning days |
|---|--:|--:|--:|--:|--:|--:|
| live: thirds at 1% / 2%, breakeven after the first | +8.7 | +1.2 | 1.31 | 0.19 | -542 | 48% |
| + auto-trim a third when the 15m osc crosses 80 against | +8.1 | -0.7 | 1.26 | -0.11 | -542 | 48% |
| + auto-trim a third at 90 | +8.8 | -0.2 | 1.34 | -0.04 | -542 | 48% |
| + auto-trim half at 80 | +7.8 | -0.7 | 1.22 | -0.11 | -542 | 49% |
| auto-trim at 80 instead of the +1% third | +8.7 | +1.9 | 1.14 | 0.26 | -542 | 44% |
| no trimming at all (hold to the rule) | +10.2 | +4.8 | 1.15 | 0.53 | -542 | 41% |

**QQQ**

| Variant | Before | After | Sharpe before | Sharpe after | Worst day | Winning days |
|---|--:|--:|--:|--:|--:|--:|
| live: thirds at 1% / 2%, breakeven after the first | +5.1 | +1.7 | 1.54 | 0.65 | -216 | 46% |
| + auto-trim a third when the 15m osc crosses 80 against | +4.8 | +1.5 | 1.48 | 0.58 | -216 | 48% |
| + auto-trim a third at 90 | +4.4 | +1.4 | 1.37 | 0.55 | -216 | 47% |
| + auto-trim half at 80 | +4.6 | +1.5 | 1.44 | 0.57 | -216 | 48% |
| auto-trim at 80 instead of the +1% third | +4.8 | +2.6 | 1.42 | 0.83 | -216 | 47% |
| no trimming at all (hold to the rule) | +5.0 | +3.2 | 1.43 | 0.87 | -216 | 45% |

**NVDA**

| Variant | Before | After | Sharpe before | Sharpe after | Worst day | Winning days |
|---|--:|--:|--:|--:|--:|--:|
| live: thirds at 1% / 2%, breakeven after the first | +6.2 | -1.6 | 0.92 | -0.30 | -513 | 46% |
| + auto-trim a third when the 15m osc crosses 80 against | +5.6 | -0.8 | 0.87 | -0.15 | -513 | 47% |
| + auto-trim a third at 90 | +5.2 | -1.3 | 0.79 | -0.24 | -513 | 47% |
| + auto-trim half at 80 | +5.5 | -0.6 | 0.85 | -0.12 | -513 | 47% |
| auto-trim at 80 instead of the +1% third | +6.8 | -1.9 | 0.91 | -0.31 | -599 | 44% |
| no trimming at all (hold to the rule) | +8.3 | -2.2 | 0.98 | -0.34 | -599 | 41% |

**META**

| Variant | Before | After | Sharpe before | Sharpe after | Worst day | Winning days |
|---|--:|--:|--:|--:|--:|--:|
| live: thirds at 1% / 2%, breakeven after the first | +0.0 | -2.0 | 0.01 | -0.44 | -457 | 41% |
| + auto-trim a third when the 15m osc crosses 80 against | -0.3 | -2.4 | -0.07 | -0.52 | -457 | 42% |
| + auto-trim a third at 90 | +0.1 | -2.8 | 0.02 | -0.62 | -457 | 42% |
| + auto-trim half at 80 | -0.6 | -2.4 | -0.11 | -0.54 | -457 | 43% |
| auto-trim at 80 instead of the +1% third | +0.8 | -3.6 | 0.13 | -0.69 | -457 | 41% |
| no trimming at all (hold to the rule) | +0.8 | -2.5 | 0.12 | -0.43 | -457 | 38% |

## B. Candle trades (pivot-wick candles, 9m and 15m, 9 tickers), average R per trade after costs

| Exit | Before | After | Share of trades that made money (after) |
|---|--:|--:|--:|
| all at 1R (live) | -0.090 | -0.077 | 49% |
| half at +0.5R, rest to breakeven stop / 1R | -0.091 | -0.073 | 65% |
| half at +0.5R, rest to breakeven stop / 2R | -0.091 | -0.072 | 65% |
| half when the 15m osc turns against (80/20), then breakeven / 1R | -0.095 | -0.077 | 51% |
| half when the 15m osc turns against, then breakeven / 2R | -0.094 | -0.066 | 46% |

29,441 trades that filled.
