# Trade journal

Positions come from Alpaca's fills (half exits / thirds grouped, real P/L, same as the scorecard). Each is matched to the
scanner's own log (logs/live/<day>.jsonl) by symbol and fill time, which adds the plan: timeframe, candle type, gap,
key-level zone, planned entry / stop, and so slippage and the result in R. Market regime (vpa_trading/regime.py, known
before the session) and time of day are added for every position. Rebuilt in full each run.

105 positions, 2026-11-04 to 2026-11-24; 89 with a logged plan (R known). Total P/L +870. Small samples: read these as a running record, not conclusions, until each row has 30+ trades.


## By strategy

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| Alert mode | 13 | 54% | -117 | -0.16 |
| Banks level | 3 | 33% | +214 | -0.16 |
| Candle scanner | 76 | 61% | -1,396 | -0.02 |
| Trend-day breakout | 13 | 62% | +2,169 | - |

## By timeframe (scanner and alert trades)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| 15m | 18 | 61% | +603 | +0.03 |
| 2m | 4 | 100% | +907 | +0.93 |
| 5m | 14 | 43% | -2,286 | -0.34 |
| 9m | 53 | 60% | -562 | -0.07 |

## By candle type

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| ALERT_PIVOT_BOTTOM | 8 | 62% | +537 | +0.02 |
| ALERT_PIVOT_TOP | 5 | 40% | -654 | -0.46 |
| HAMMER | 10 | 60% | -669 | +0.06 |
| HANGING_MAN | 1 | 0% | -282 | -1.09 |
| PIVOT_WICK_BOTTOM | 8 | 62% | +123 | -0.08 |
| PIVOT_WICK_TOP | 39 | 67% | +1,121 | +0.05 |
| SHOOTING_STAR | 10 | 50% | -1,190 | -0.29 |
| SHOOTING_STAR_IN_DOWNTREND | 1 | 0% | -437 | -1.09 |
| STOPPING_VOLUME | 1 | 0% | -704 | -1.02 |
| single-bar climax bottom | 2 | 100% | +400 | +1.03 |
| single-bar climax top | 4 | 50% | +416 | -0.03 |

## By gap timeframe at entry

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| - | 9 | 56% | -351 | -0.23 |
| 1h | 31 | 71% | +602 | +0.11 |
| 4h | 22 | 68% | +1,833 | +0.16 |
| D | 24 | 42% | -3,636 | -0.36 |
| level | 3 | 33% | +214 | -0.16 |

## Key-level zone at entry

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| at a zone | 23 | 43% | -3,756 | -0.36 |
| no zone | 66 | 65% | +2,418 | +0.06 |

## Add to an open position?

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| False | 82 | 60% | -1,568 | -0.06 |
| True | 7 | 57% | +230 | +0.06 |

## Hour of entry (MST)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| 8 | 19 | 53% | +1,301 | -0.19 |
| 9 | 22 | 64% | +535 | -0.02 |
| 10 | 25 | 60% | -464 | +0.04 |
| 11 | 19 | 53% | -1,072 | -0.25 |
| 12 | 13 | 77% | +1,380 | +0.19 |
| 13 | 7 | 43% | -810 | -0.03 |

## Side

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| long | 35 | 63% | +245 | +0.04 |
| short | 70 | 57% | +625 | -0.09 |

## SPY vs its 200-day (as of the prior close)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| above | 73 | 56% | -127 | -0.06 |
| below | 24 | 67% | +1,398 | +0.02 |
| nan | 8 | 62% | -401 | -0.16 |

## SPY volatility

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| calm | 11 | 55% | -405 | +0.13 |
| normal | 5 | 20% | +61 | -1.15 |
| stressed | 81 | 62% | +1,615 | -0.03 |
| nan | 8 | 62% | -401 | -0.16 |

## Slippage (entry fill vs the planned entry, in R; negative = paid more than planned)

Average -0.062R, median -0.041R, worst -0.42R over 89 trades.
