# Event days vs the live strategies

Events (all known in advance, except the gap day, which is known at the 9:30 open, before any signal):
  CPI release days      list from scripts/cpi_close_test.py (from memory, checked against the 8:30 volume burst)
  FOMC decision days    Fed statement days, from memory (2026 dates = the Fed's published schedule as I recall it)
  Monthly opex          third Friday of the month
  Stock-specific gap    the stock opened 3%+ away from its prior close and at least 2% more than QQQ did
                        (earnings and big news days; no earnings calendar is available here)
Trades = results/strategy_history.pkl (candles: live exit, R after cost; breakout: bps per traded day after cost).

Each cell: count | average (t; above about 2 is unlikely to be luck). Whole 5 years (event days are too few to split off a holdout).

| Day type | Candle longs | Candle shorts | Breakout, all 9 (bps/day) | Breakout, TSLA (bps/day) |
|---|--:|--:|--:|--:|
| No event | 12325 | -0.081R (t -12.5) | 12458 | -0.101R (t -15.7) | 5626 | +2.2 (t +1.6) | 619 | +13.6 (t +2.6) |
| CPI day | 622 | -0.061R (t -2.1) | 703 | -0.053R (t -2.0) | 312 | +10.3 (t +1.8) | 38 | +10.3 (t +0.5) |
| FOMC day | 488 | +0.004R (t +0.1) | 556 | -0.058R (t -1.9) | 228 | +7.4 (t +1.0) | 23 | -34.8 (t -1.7) |
| Monthly opex | 751 | -0.052R (t -2.0) | 671 | -0.016R (t -0.6) | 307 | +4.1 (t +0.8) | 36 | -12.8 (t -0.6) |
| Stock-specific gap (earnings / news) | 510 | -0.094R (t -2.9) | 487 | -0.048R (t -1.5) | 200 | +4.9 (t +0.5) | 51 | +21.8 (t +0.9) |

FOMC: candles before vs after the 14:00 ET statement

| Time | Candle trades | Average R |
|---|--:|--:|
| before 13:30 | 567 | -0.031R |
| 13:30 to 14:00 | 88 | +0.059R |
| after 14:00 | 389 | -0.045R |
