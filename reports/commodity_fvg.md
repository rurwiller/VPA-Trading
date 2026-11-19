# Commodities: the fair-value-gap candles, and the gaps combined with the opening-range breakdown

A. The fair-value-gap candle study (scripts/fvg_candle_test.py, run per fund into results/fvg_candles/): premier candles
   and climaxes, traded in their own direction (Coulling's bias), at an unfilled 1h / 4h / daily gap vs away from any gap.
   Exit as the live scanner does it: stop just beyond the candle's extreme (+0.02%), entry at the candle's close.
   The study's own exit is a 2R target or 120 minutes; results in R (multiples of the risk) after each fund's cost.
B. Combined with the opening-range breakdown (scripts/commodity_orb_test.py: gap-down day, short when a 30-minute block
   closes below the first 30 minutes' low):
   B1  breakdown trades split by whether a bearish premier / climax AT A GAP printed earlier that day (from 10:00 to entry)
   B2  bearish gap signals split by whether they came on a gap-down day after the opening range broke down
Before / after = before Nov 2024 / since. t = mean / standard error.

Cells: trades | average after costs | t.


## A. Gap candles (premier + climax, own direction), structure stop, 2R target, average R

| Fund | Market | At a 1h/4h/D gap, all | before | since Nov 2024 | Away from gaps, all | 9m/15m at a gap (the live scanner's) |
|---|---|---|---|---|---|---|
| GLD | gold | 5963 | -0.146 | -8.7 | 3443 | -0.203 | -9.4 | 2520 | -0.067 | -2.5 | 5111 | -0.211 | -11.6 | 2483 | -0.168 | -6.6 |
| SLV | silver | 6514 | -0.198 | -12.1 | 3853 | -0.232 | -11.1 | 2661 | -0.149 | -5.8 | 5028 | -0.334 | -18.0 | 2630 | -0.181 | -7.3 |
| USO | crude oil | 6383 | -0.173 | -10.6 | 3706 | -0.177 | -8.1 | 2677 | -0.168 | -6.7 | 4946 | -0.173 | -9.2 | 2685 | -0.180 | -7.3 |
| UNG | natural gas | 7246 | -0.132 | -8.4 | 4111 | -0.095 | -4.6 | 3135 | -0.180 | -7.5 | 6111 | -0.166 | -9.8 | 2745 | -0.114 | -4.5 |
| CPER | copper | 3662 | -1.031 | -44.7 | 1234 | -0.963 | -25.4 | 2428 | -1.066 | -36.8 | 1812 | -1.110 | -33.8 | 1886 | -1.023 | -32.4 |
| PPLT | platinum | 4355 | -0.644 | -30.8 | 1884 | -0.710 | -22.6 | 2471 | -0.594 | -21.2 | 3002 | -0.762 | -30.6 | 2102 | -0.624 | -20.9 |
| DBA | agriculture | 5353 | -0.819 | -45.9 | 3204 | -0.764 | -32.9 | 2149 | -0.900 | -32.5 | 4483 | -0.894 | -47.1 | 2603 | -0.787 | -31.1 |
| **All 7** | | 39476 | -0.385 | -55.8 | 21435 | -0.355 | -38.6 | 18041 | -0.420 | -40.5 | 30493 | -0.424 | -54.5 | 17134 | -0.407 | -39.6 |

## B1. Opening-range breakdown shorts, split by a gap signal earlier that day (bps per trade)

| Fund | Market | All breakdown shorts | After a bearish gap signal | After a bullish gap signal | No gap signal |
|---|---|---|---|---|---|
| GLD | gold | 271 | +5.2 | +2.0 | 35 | +5.0 | +1.0 | 139 | +5.7 | +1.4 | 97 | +4.5 | +1.2 |
| SLV | silver | 268 | -6.1 | -1.0 | 30 | -4.7 | -0.4 | 127 | -14.4 | -1.6 | 111 | +3.0 | +0.3 |
| USO | crude oil | 329 | -12.8 | -2.1 | 53 | -11.2 | -0.8 | 136 | -13.3 | -1.5 | 140 | -13.0 | -1.3 |
| UNG | natural gas | 392 | +5.1 | +0.6 | 63 | +13.2 | +0.8 | 138 | +7.0 | +0.5 | 191 | +0.9 | +0.1 |
| CPER | copper | 258 | -12.2 | -3.1 | 29 | -11.5 | -1.1 | 101 | -19.0 | -3.0 | 128 | -7.0 | -1.2 |
| PPLT | platinum | 302 | -14.5 | -3.3 | 32 | -13.1 | -1.0 | 116 | -19.0 | -2.3 | 154 | -11.4 | -2.1 |
| DBA | agriculture | 301 | -3.4 | -1.4 | 48 | -11.3 | -2.5 | 109 | -4.4 | -1.0 | 144 | -0.0 | -0.0 |
| **All 7** | | 2121 | -5.2 | -2.4 | 290 | -3.5 | -0.7 | 866 | -7.5 | -2.3 | 965 | -3.7 | -1.1 |

## B2. Bearish gap signals (own direction = short), split by the day (average R)

| Fund | Market | After an opening-range breakdown on a gap-down day | Any other time |
|---|---|---|---|
| GLD | gold | 292 | -0.071 | -0.9 | 2457 | -0.146 | -5.5 |
| SLV | silver | 382 | -0.282 | -4.2 | 2669 | -0.268 | -10.6 |
| USO | crude oil | 496 | -0.315 | -5.5 | 2711 | -0.244 | -9.8 |
| UNG | natural gas | 547 | -0.127 | -2.3 | 3413 | -0.163 | -7.1 |
| CPER | copper | 193 | -1.204 | -11.9 | 1718 | -1.090 | -32.7 |
| PPLT | platinum | 219 | -0.661 | -7.7 | 2009 | -0.758 | -24.4 |
| DBA | agriculture | 337 | -0.954 | -14.3 | 2633 | -0.881 | -35.1 |
| **All 7** | | 2466 | -0.427 | -15.7 | 17610 | -0.455 | -44.0 |
