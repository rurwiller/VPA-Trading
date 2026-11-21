# Market regime vs the live strategies

Inputs: results/strategy_history.pkl (scripts/strategy_history.py) and the regime features in vpa_trading/regime.py,
all known before each session. Tuned on data before the holdout (vpa_trading/pit.HOLDOUT_START, 2026-05-21); the holdout
columns are shown once, for the final check, and are not used to pick anything.

  candle longs / shorts   average R per trade, live exit (half at +0.5R, rest breakeven / 1R), after cost
  breakout                average bps of notional per day the rule traded (live rules, thirds + breakeven), after cost

Candle trades: 29,441 (2021-11-05 to 2026-11-03), 9 symbols. Breakout trading days: 6,644. Each cell: count | average (t; above about 2 is unlikely to be luck).


## Discovery (before 2026-05-21)

| Regime | Candle longs | Candle shorts | Breakout, all 9 (bps/day) | Breakout, TSLA only (bps/day) |
|---|--:|--:|--:|--:|
| Everything | 13272 | -0.073R (t -11.7) | 13568 | -0.095R (t -15.3) | 6056 | +2.9 (t +2.2) | 697 | +10.8 (t +2.1) |
| SPY vs 200-day: above | 9778 | -0.077R (t -10.7) | 9792 | -0.090R (t -12.4) | 4387 | +1.2 (t +0.8) | 501 | +8.1 (t +1.4) |
| SPY vs 200-day: below | 3494 | -0.060R (t -4.9) | 3776 | -0.108R (t -9.1) | 1669 | +7.4 (t +2.3) | 196 | +17.8 (t +1.6) |
| SPY last 20 days: up | 8443 | -0.064R (t -8.3) | 8418 | -0.094R (t -12.0) | 3722 | +4.5 (t +2.9) | 427 | +12.4 (t +2.1) |
| SPY last 20 days: down | 4829 | -0.087R (t -8.4) | 5150 | -0.096R (t -9.5) | 2334 | +0.3 (t +0.1) | 270 | +8.3 (t +0.9) |
| Breadth (S&P stocks above 50-day): under 40% | 3213 | -0.063R (t -5.0) | 3508 | -0.108R (t -8.7) | 1590 | +0.8 (t +0.2) | 174 | +19.4 (t +1.7) |
| Breadth (S&P stocks above 50-day): 40-60% | 4283 | -0.073R (t -6.7) | 4485 | -0.107R (t -9.9) | 2043 | +6.0 (t +2.7) | 245 | +8.8 (t +1.0) |
| Breadth (S&P stocks above 50-day): over 60% | 5776 | -0.077R (t -8.3) | 5575 | -0.077R (t -8.1) | 2423 | +1.7 (t +0.9) | 278 | +7.2 (t +1.0) |
| SPY volatility (20-day): calm, under 12% | 4716 | -0.083R (t -8.0) | 4723 | -0.101R (t -9.7) | 2166 | +2.3 (t +1.2) | 243 | +2.1 (t +0.3) |
| SPY volatility (20-day): normal, 12-20% | 5761 | -0.070R (t -7.4) | 5854 | -0.094R (t -10.0) | 2606 | +1.3 (t +0.6) | 302 | +3.6 (t +0.5) |
| SPY volatility (20-day): stressed, over 20% | 2795 | -0.061R (t -4.5) | 2991 | -0.087R (t -6.5) | 1284 | +7.2 (t +2.0) | 152 | +39.1 (t +3.2) |
| QQQ vs 50-day: above | 8735 | -0.070R (t -9.1) | 8705 | -0.098R (t -12.8) | 3871 | +2.2 (t +1.5) | 444 | +9.0 (t +1.6) |
| QQQ vs 50-day: below | 4537 | -0.078R (t -7.3) | 4863 | -0.088R (t -8.5) | 2185 | +4.1 (t +1.6) | 253 | +14.0 (t +1.4) |

## Holdout (2026-05-21 on, looked at once)

| Regime | Candle longs | Candle shorts | Breakout, all 9 (bps/day) | Breakout, TSLA only (bps/day) |
|---|--:|--:|--:|--:|
| Everything | 1373 | -0.113R (t -5.8) | 1228 | -0.062R (t -3.0) | 588 | +1.9 (t +0.5) | 69 | +13.8 (t +1.0) |
| SPY vs 200-day: above | 1373 | -0.113R (t -5.8) | 1228 | -0.062R (t -3.0) | 588 | +1.9 (t +0.5) | 69 | +13.8 (t +1.0) |
| SPY vs 200-day: below | 0 | - | 0 | - | 0 | - | 0 | - |
| SPY last 20 days: up | 979 | -0.135R (t -5.8) | 742 | -0.035R (t -1.4) | 367 | +11.1 (t +2.2) | 40 | +22.5 (t +1.4) |
| SPY last 20 days: down | 394 | -0.057R (t -1.6) | 486 | -0.102R (t -3.1) | 221 | -13.3 (t -2.0) | 29 | +1.7 (t +0.1) |
| Breadth (S&P stocks above 50-day): under 40% | 263 | -0.048R (t -1.1) | 284 | -0.162R (t -3.6) | 118 | -4.0 (t -0.5) | 13 | -34.4 (t -1.3) |
| Breadth (S&P stocks above 50-day): 40-60% | 580 | -0.112R (t -3.8) | 477 | +0.024R (t +0.8) | 252 | +2.9 (t +0.5) | 31 | +40.2 (t +2.3) |
| Breadth (S&P stocks above 50-day): over 60% | 530 | -0.146R (t -4.7) | 467 | -0.088R (t -2.6) | 218 | +3.9 (t +0.6) | 25 | +6.1 (t +0.2) |
| SPY volatility (20-day): calm, under 12% | 832 | -0.128R (t -5.1) | 701 | -0.069R (t -2.6) | 358 | +3.1 (t +0.6) | 41 | +10.5 (t +0.7) |
| SPY volatility (20-day): normal, 12-20% | 541 | -0.090R (t -3.0) | 527 | -0.052R (t -1.7) | 230 | -0.0 (t -0.0) | 28 | +18.6 (t +0.8) |
| SPY volatility (20-day): stressed, over 20% | 0 | - | 0 | - | 0 | - | 0 | - |
| QQQ vs 50-day: above | 921 | -0.114R (t -4.8) | 765 | -0.055R (t -2.1) | 381 | +5.2 (t +1.0) | 43 | +18.8 (t +1.0) |
| QQQ vs 50-day: below | 452 | -0.110R (t -3.3) | 463 | -0.072R (t -2.2) | 207 | -4.2 (t -0.7) | 26 | +5.5 (t +0.3) |

Cells compared in discovery: 48. With 13 studies logged, a single cell needs |t| above 3.3 to count as more than luck from all the slicing.
