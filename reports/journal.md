# Trade journal

Positions come from Alpaca's fills (half exits / thirds grouped, real P/L, same as the scorecard). Each is matched to the
scanner's own log (logs/live/<day>.jsonl) by symbol and fill time, which adds the plan: timeframe, candle type, gap,
key-level zone, planned entry / stop, and so slippage and the result in R. Market regime (vpa_trading/regime.py, known
before the session) and time of day are added for every position. Rebuilt in full each run.

115 positions, 2026-11-04 to 2026-11-25; 98 with a logged plan (R known). Total P/L -2,245. Small samples: read these as a running record, not conclusions, until each row has 30+ trades.


## By strategy

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| Alert mode | 13 | 54% | -117 | -0.16 |
| Banks level | 3 | 33% | +214 | -0.16 |
| Candle scanner | 85 | 55% | -4,397 | -0.11 |
| Trend-day breakout | 14 | 57% | +2,055 | - |

## By timeframe (scanner and alert trades)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| 15m | 23 | 48% | -1,370 | -0.19 |
| 2m | 4 | 100% | +907 | +0.93 |
| 5m | 14 | 43% | -2,286 | -0.34 |
| 9m | 57 | 58% | -1,590 | -0.11 |

## By candle type

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| ALERT_PIVOT_BOTTOM | 8 | 62% | +537 | +0.02 |
| ALERT_PIVOT_TOP | 5 | 40% | -654 | -0.46 |
| HAMMER | 10 | 60% | -669 | +0.06 |
| HANGING_MAN | 1 | 0% | -282 | -1.09 |
| PIVOT_WICK_BOTTOM | 8 | 62% | +123 | -0.08 |
| PIVOT_WICK_TOP | 47 | 57% | -1,398 | -0.09 |
| SHOOTING_STAR | 11 | 45% | -1,672 | -0.37 |
| SHOOTING_STAR_IN_DOWNTREND | 1 | 0% | -437 | -1.09 |
| STOPPING_VOLUME | 1 | 0% | -704 | -1.02 |
| single-bar climax bottom | 2 | 100% | +400 | +1.03 |
| single-bar climax top | 4 | 50% | +416 | -0.03 |

## By gap timeframe at entry

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| - | 9 | 56% | -351 | -0.23 |
| 1h | 37 | 62% | -1,466 | -0.04 |
| 4h | 23 | 65% | +1,440 | +0.11 |
| D | 26 | 38% | -4,176 | -0.40 |
| level | 3 | 33% | +214 | -0.16 |

## Key-level zone at entry

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| at a zone | 26 | 42% | -4,581 | -0.39 |
| no zone | 72 | 60% | +242 | -0.02 |

## Add to an open position?

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| False | 91 | 55% | -4,570 | -0.13 |
| True | 7 | 57% | +230 | +0.06 |

## Hour of entry (MST)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| 8 | 20 | 50% | +1,187 | -0.19 |
| 9 | 22 | 64% | +535 | -0.02 |
| 10 | 26 | 62% | -320 | +0.05 |
| 11 | 24 | 42% | -3,524 | -0.44 |
| 12 | 16 | 62% | +687 | -0.01 |
| 13 | 7 | 43% | -810 | -0.03 |

## Side

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| long | 35 | 63% | +245 | +0.04 |
| short | 80 | 51% | -2,490 | -0.19 |

## SPY vs its 200-day (as of the prior close)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| above | 73 | 56% | -127 | -0.06 |
| below | 42 | 52% | -2,118 | -0.23 |

## SPY volatility

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| calm | 11 | 55% | -405 | +0.13 |
| normal | 5 | 20% | +61 | -1.15 |
| stressed | 99 | 57% | -1,901 | -0.13 |

## Slippage (entry fill vs the planned entry, in R; negative = paid more than planned)

Average -0.067R, median -0.042R, worst -0.42R over 98 trades.
