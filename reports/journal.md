# Trade journal

Positions come from Alpaca's fills (half exits / thirds grouped, real P/L, same as the scorecard). Each is matched to the
scanner's own log (logs/live/<day>.jsonl) by symbol and fill time, which adds the plan: timeframe, candle type, gap,
key-level zone, planned entry / stop, and so slippage and the result in R. Market regime (vpa_trading/regime.py, known
before the session) and time of day are added for every position. Rebuilt in full each run.

86 positions, 2026-11-04 to 2026-11-20; 74 with a logged plan (R known). Total P/L +3,554. Small samples: read these as a running record, not conclusions, until each row has 30+ trades.


## By strategy

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| Alert mode | 12 | 58% | +218 | -0.08 |
| Banks level | 3 | 33% | +214 | -0.16 |
| Candle scanner | 61 | 62% | +405 | +0.04 |
| TSLA breakout | 10 | 60% | +2,717 | - |

## By timeframe (scanner and alert trades)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| 15m | 14 | 64% | +1,112 | +0.11 |
| 2m | 4 | 100% | +907 | +0.93 |
| 5m | 14 | 43% | -2,286 | -0.34 |
| 9m | 42 | 64% | +1,234 | +0.01 |

## By candle type

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| ALERT_PIVOT_BOTTOM | 8 | 62% | +537 | +0.02 |
| ALERT_PIVOT_TOP | 4 | 50% | -319 | -0.30 |
| HAMMER | 10 | 60% | -669 | +0.06 |
| HANGING_MAN | 1 | 0% | -282 | -1.09 |
| PIVOT_WICK_BOTTOM | 4 | 75% | +618 | +0.09 |
| PIVOT_WICK_TOP | 32 | 72% | +2,493 | +0.16 |
| SHOOTING_STAR | 7 | 43% | -1,088 | -0.42 |
| SHOOTING_STAR_IN_DOWNTREND | 1 | 0% | -437 | -1.09 |
| STOPPING_VOLUME | 1 | 0% | -704 | -1.02 |
| single-bar climax bottom | 2 | 100% | +400 | +1.03 |
| single-bar climax top | 4 | 50% | +416 | -0.03 |

## By gap timeframe at entry

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| - | 8 | 62% | -15 | -0.12 |
| 1h | 27 | 70% | +705 | +0.13 |
| 4h | 18 | 72% | +2,347 | +0.26 |
| D | 18 | 44% | -2,283 | -0.32 |
| level | 3 | 33% | +214 | -0.16 |

## Key-level zone at entry

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| at a zone | 18 | 44% | -2,673 | -0.34 |
| no zone | 56 | 68% | +3,640 | +0.13 |

## Add to an open position?

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| False | 68 | 62% | +240 | -0.01 |
| True | 6 | 67% | +728 | +0.23 |

## Hour of entry (MST)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| 8 | 16 | 50% | +1,443 | -0.15 |
| 9 | 16 | 69% | +1,413 | +0.13 |
| 10 | 19 | 68% | +1,300 | +0.18 |
| 11 | 15 | 47% | -1,172 | -0.30 |
| 12 | 13 | 77% | +1,380 | +0.19 |
| 13 | 7 | 43% | -810 | -0.03 |

## Side

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| long | 29 | 66% | +1,292 | +0.09 |
| short | 57 | 58% | +2,263 | -0.02 |

## SPY vs its 200-day (as of the prior close)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| above | 73 | 56% | -127 | -0.06 |
| below | 13 | 85% | +3,681 | +0.38 |

## SPY volatility

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| calm | 11 | 55% | -405 | +0.13 |
| normal | 5 | 20% | +61 | -1.15 |
| stressed | 70 | 64% | +3,898 | +0.03 |

## Slippage (entry fill vs the planned entry, in R; negative = paid more than planned)

Average -0.066R, median -0.042R, worst -0.42R over 74 trades.
