# The 15m EMA 20 idea (@piru4o), 5 years of 1m bars

Rules as posted (mirrored for shorts):
  1. a 15m candle crosses the EMA 20 from below and CLOSES above it -> longs are armed
  2. while candles stay above the EMA 20, buy when price comes back and touches the EMA 20
The post gives no stop or exit, so three common ones are tested:
  1R / 2R   stop 1 ATR(15m) beyond the entry, target 1R or 2R
  ema       hold until a 15m candle closes back on the other side of the EMA 20 (stop 1 ATR as a guard)
Entry: a limit at the EMA 20 of the last closed 15m candle, filled when a 1m bar touches it (10:00-15:30 ET), first touch
after each cross only ("first") or every touch while armed ("every", one trade at a time). Flat at 15:50 ET. Regular
hours only, EMA carried across days like a chart. Costs: ticker spread + 1 bp per round trip.

Average result per trade in basis points (1 bp = 0.01%) after costs; win % in brackets. Before / after Nov 2024 (the later part is the out-of-sample check).


## Entry on the first touch after each cross

| Ticker | Trades | 1R before | 1R after | 2R before | 2R after | ema before | ema after |
|---|--:|--:|--:|--:|--:|--:|--:|
| GLD | 1316 | -1.6 (49%) | -0.8 (48%) | -1.0 (41%) | -1.4 (39%) | -0.2 (37%) | -0.3 (37%) |
| SLV | 1341 | -3.5 (49%) | -1.2 (50%) | -4.3 (40%) | -4.7 (38%) | -2.9 (37%) | -6.4 (35%) |
| SPY | 1589 | -2.5 (50%) | -2.0 (50%) | -2.5 (37%) | -1.9 (39%) | -1.5 (34%) | -1.8 (35%) |
| QQQ | 1552 | -3.1 (48%) | -2.2 (48%) | -2.8 (37%) | -2.2 (38%) | -2.8 (32%) | -2.8 (34%) |
| TSLA | 1429 | -3.7 (49%) | -0.2 (52%) | -4.7 (40%) | -4.6 (40%) | -3.2 (37%) | +6.2 (39%) |
| NVDA | 1467 | +0.8 (51%) | -3.2 (51%) | +1.9 (40%) | -0.5 (43%) | +4.2 (37%) | +0.6 (41%) |
| AAPL | 1489 | -2.1 (48%) | -1.7 (50%) | -1.1 (38%) | -0.4 (41%) | -0.8 (35%) | -1.6 (37%) |
| MSFT | 1501 | -0.9 (50%) | -2.2 (47%) | -2.7 (38%) | -1.8 (37%) | -1.1 (36%) | -1.7 (35%) |
| AMZN | 1444 | +1.2 (53%) | +0.2 (53%) | +0.6 (41%) | +1.8 (45%) | +2.1 (39%) | -0.6 (42%) |
| META | 1499 | -3.1 (49%) | -0.7 (50%) | -3.5 (38%) | -2.6 (39%) | -2.0 (36%) | -1.1 (37%) |
| GOOGL | 1454 | -1.5 (50%) | -0.3 (50%) | -2.2 (39%) | -1.5 (41%) | -0.5 (36%) | -0.5 (39%) |
| AMD | 1444 | +0.3 (50%) | -5.1 (48%) | +2.8 (41%) | -3.7 (40%) | +2.5 (39%) | -2.8 (38%) |
| **All** | 17525 | -1.7 (50%) | -1.6 (50%) | -1.6 (39%) | -1.9 (40%) | -0.5 (36%) | -1.1 (37%) |

longs: 1R -2.4 bps, 2R -2.1 bps, ema -0.6 bps

shorts: 1R -0.9 bps, 2R -1.4 bps, ema -0.9 bps

## Entry on the every touch while above / below

| Ticker | Trades | 1R before | 1R after | 2R before | 2R after | ema before | ema after |
|---|--:|--:|--:|--:|--:|--:|--:|
| GLD | 1363 | -1.5 (49%) | -1.2 (48%) | -0.8 (41%) | -2.2 (38%) | +0.2 (37%) | -1.3 (36%) |
| SLV | 1382 | -4.0 (49%) | -1.2 (50%) | -4.8 (39%) | -5.2 (38%) | -3.2 (37%) | -6.7 (35%) |
| SPY | 1673 | -2.9 (49%) | -1.7 (51%) | -3.0 (37%) | -1.6 (40%) | -2.1 (33%) | -1.5 (35%) |
| QQQ | 1602 | -2.8 (49%) | -2.1 (49%) | -2.5 (37%) | -2.5 (38%) | -2.7 (32%) | -3.4 (34%) |
| TSLA | 1490 | -4.4 (48%) | -2.7 (50%) | -5.9 (39%) | -7.2 (39%) | -4.3 (37%) | +3.4 (38%) |
| NVDA | 1511 | -1.2 (50%) | -2.2 (52%) | -0.2 (39%) | +0.4 (44%) | +2.5 (37%) | +2.0 (41%) |
| AAPL | 1532 | -2.2 (48%) | -0.9 (51%) | -1.1 (38%) | -0.4 (41%) | -1.3 (35%) | -1.5 (38%) |
| MSFT | 1538 | -1.0 (50%) | -3.0 (46%) | -2.5 (38%) | -2.4 (37%) | -1.1 (36%) | -1.7 (35%) |
| AMZN | 1489 | +0.9 (52%) | +0.6 (54%) | +0.0 (41%) | +2.4 (45%) | +1.2 (39%) | +0.4 (42%) |
| META | 1548 | -3.7 (48%) | -1.4 (49%) | -3.2 (38%) | -4.3 (38%) | -2.2 (36%) | -4.8 (36%) |
| GOOGL | 1484 | -1.3 (50%) | -0.9 (50%) | -1.9 (39%) | -1.9 (41%) | -0.2 (36%) | -0.9 (39%) |
| AMD | 1475 | -1.6 (49%) | -4.1 (48%) | +0.1 (40%) | -2.8 (40%) | -0.3 (37%) | -2.0 (38%) |
| **All** | 18087 | -2.1 (49%) | -1.8 (50%) | -2.1 (39%) | -2.3 (40%) | -1.1 (36%) | -1.5 (37%) |

longs: 1R -2.9 bps, 2R -2.6 bps, ema -1.2 bps

shorts: 1R -1.0 bps, 2R -1.8 bps, ema -1.3 bps
