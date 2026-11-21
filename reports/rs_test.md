# Relative strength vs QQQ and the scanner's candles

At each candle's signal minute (known then): the stock's move since the 9:30 open minus QQQ's move since the open
(relative strength, RS), and QQQ's own move since the open. Longs in stocks stronger than QQQ / shorts in stocks weaker
should do better if "trade with strength" holds. Trades = results/strategy_history.pkl candles (live exit, R after cost).
Discovery before the holdout (2026-05-21), holdout shown once.

Each cell: trades | average R after cost (t; above about 2 is unlikely to be luck).


## Discovery (before 2026-05-21)

| Filter | Longs | Shorts |
|---|--:|--:|
| All | 11764 | -0.070R (t -10.6) | 11906 | -0.085R (t -13.0) |
| Stock stronger than QQQ today | 3669 | -0.063R (t -5.4) | 8124 | -0.088R (t -11.0) |
| Stock weaker than QQQ today | 8095 | -0.073R (t -9.1) | 3782 | -0.080R (t -6.9) |
| Much stronger (RS above +0.5%) | 1908 | -0.048R (t -3.0) | 5523 | -0.071R (t -7.4) |
| Much weaker (RS below -0.5%) | 5610 | -0.063R (t -6.6) | 1896 | -0.084R (t -5.1) |
| QQQ up on the day so far | 3566 | -0.038R (t -3.2) | 8646 | -0.098R (t -12.7) |
| QQQ down on the day so far | 8193 | -0.084R (t -10.6) | 3250 | -0.053R (t -4.2) |
| With strength (long & RS>0, QQQ up / short & RS<0, QQQ down) | 1212 | -0.037R (t -1.9) | 1183 | -0.040R (t -1.9) |
| Fading (long & RS<0, QQQ down / short & RS>0, QQQ up) | 5739 | -0.088R (t -9.2) | 6049 | -0.098R (t -10.6) |

## Holdout (2026-05-21 on)

| Filter | Longs | Shorts |
|---|--:|--:|
| All | 1214 | -0.106R (t -5.2) | 1089 | -0.047R (t -2.1) |
| Stock stronger than QQQ today | 353 | -0.138R (t -3.6) | 742 | -0.056R (t -2.1) |
| Stock weaker than QQQ today | 861 | -0.093R (t -3.8) | 347 | -0.027R (t -0.7) |
| Much stronger (RS above +0.5%) | 230 | -0.118R (t -2.5) | 578 | -0.057R (t -1.9) |
| Much weaker (RS below -0.5%) | 667 | -0.082R (t -3.0) | 224 | -0.065R (t -1.4) |
| QQQ up on the day so far | 448 | -0.103R (t -3.1) | 675 | -0.024R (t -0.9) |
| QQQ down on the day so far | 766 | -0.108R (t -4.1) | 412 | -0.082R (t -2.3) |
| With strength (long & RS>0, QQQ up / short & RS<0, QQQ down) | 116 | -0.118R (t -1.8) | 104 | -0.093R (t -1.3) |
| Fading (long & RS<0, QQQ down / short & RS>0, QQQ up) | 529 | -0.090R (t -2.9) | 432 | -0.038R (t -1.1) |
