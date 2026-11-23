# Trade journal

Positions come from Alpaca's fills (half exits / thirds grouped, real P/L, same as the scorecard). Each is matched to the
scanner's own log (logs/live/<day>.jsonl) by symbol and fill time, which adds the plan: timeframe, candle type, gap,
key-level zone, planned entry / stop, and so slippage and the result in R. Market regime (vpa_trading/regime.py, known
before the session) and time of day are added for every position. Rebuilt in full each run.

97 positions, 2026-11-04 to 2026-11-23; 82 with a logged plan (R known). Total P/L +1,271. Small samples: read these as a running record, not conclusions, until each row has 30+ trades.


## By strategy

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| Alert mode | 12 | 58% | +218 | -0.08 |
| Banks level | 3 | 33% | +214 | -0.16 |
| Candle scanner | 70 | 60% | -1,327 | -0.03 |
| Trend-day breakout | 12 | 58% | +2,166 | - |

## By timeframe (scanner and alert trades)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| 15m | 16 | 56% | +68 | -0.03 |
| 2m | 4 | 100% | +907 | +0.93 |
| 5m | 14 | 43% | -2,286 | -0.34 |
| 9m | 48 | 62% | +377 | -0.03 |

## By candle type

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| ALERT_PIVOT_BOTTOM | 8 | 62% | +537 | +0.02 |
| ALERT_PIVOT_TOP | 4 | 50% | -319 | -0.30 |
| HAMMER | 10 | 60% | -669 | +0.06 |
| HANGING_MAN | 1 | 0% | -282 | -1.09 |
| PIVOT_WICK_BOTTOM | 6 | 67% | +248 | -0.07 |
| PIVOT_WICK_TOP | 35 | 66% | +1,064 | +0.05 |
| SHOOTING_STAR | 10 | 50% | -1,190 | -0.29 |
| SHOOTING_STAR_IN_DOWNTREND | 1 | 0% | -437 | -1.09 |
| STOPPING_VOLUME | 1 | 0% | -704 | -1.02 |
| single-bar climax bottom | 2 | 100% | +400 | +1.03 |
| single-bar climax top | 4 | 50% | +416 | -0.03 |

## By gap timeframe at entry

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| - | 8 | 62% | -15 | -0.12 |
| 1h | 29 | 69% | +335 | +0.10 |
| 4h | 20 | 70% | +1,958 | +0.19 |
| D | 22 | 41% | -3,426 | -0.38 |
| level | 3 | 33% | +214 | -0.16 |

## Key-level zone at entry

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| at a zone | 21 | 43% | -3,630 | -0.38 |
| no zone | 61 | 66% | +2,696 | +0.08 |

## Add to an open position?

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| False | 75 | 60% | -1,165 | -0.05 |
| True | 7 | 57% | +230 | +0.06 |

## Hour of entry (MST)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| 8 | 19 | 53% | +1,301 | -0.19 |
| 9 | 18 | 67% | +993 | +0.06 |
| 10 | 23 | 61% | -93 | +0.08 |
| 11 | 17 | 47% | -1,500 | -0.34 |
| 12 | 13 | 77% | +1,380 | +0.19 |
| 13 | 7 | 43% | -810 | -0.03 |

## Side

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| long | 33 | 64% | +371 | +0.05 |
| short | 64 | 56% | +900 | -0.08 |

## SPY vs its 200-day (as of the prior close)

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| above | 73 | 56% | -127 | -0.06 |
| below | 13 | 85% | +3,681 | +0.38 |
| nan | 11 | 45% | -2,283 | -0.52 |

## SPY volatility

| Group | Trades | Won | P/L | Average R |
|---|--:|--:|--:|--:|
| calm | 11 | 55% | -405 | +0.13 |
| normal | 5 | 20% | +61 | -1.15 |
| stressed | 70 | 64% | +3,898 | +0.03 |
| nan | 11 | 45% | -2,283 | -0.52 |

## Slippage (entry fill vs the planned entry, in R; negative = paid more than planned)

Average -0.066R, median -0.042R, worst -0.42R over 82 trades.
