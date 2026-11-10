# Key levels: do they hold, and do pivot candles at them work better?

2022-05-13 to 2026-11-03, 9 tickers. A. First touch of a level in the session (9:45-15:30 ET; opening-range levels from 10:00), coming from one side:      held    price moves a quarter of the average daily range away again before a 1m close an eighth of it through      broke   the close through comes first            (60 minutes, else neither)    Every level is compared with two CONTROL prices 0.3-0.7 daily ranges away from it (not within reach of a real level),    scored the same way: "held" has to beat that, or the level is just a price. B. Pivot-wick candles (9m / 15m, the scanner's shape and pivot rule, scanner order mechanics, half at +0.5R then breakeven /    1R, costs = spread + 1 bp) with the wick at a zone vs away from every zone, by zone score, family and volume. Before = before 2024-11-01, after = from then (the check on unseen data).

## A. First touch: held / broke, level vs control prices

Edge = held% of the level minus held% of its control prices, in points. An edge near zero means the level holds no better than a random nearby price.

| Level | Touches | Held | Broke | Control held | Edge before | Edge after |
|---|--:|--:|--:|--:|--:|--:|
| VWAP from the low | 1,155 | 31% | 42% | 21% | +8.3 | +10.7 |
| gap edge | 1,073 | 32% | 44% | 26% | +10.3 | +1.9 |
| prior month low | 593 | 34% | 42% | 29% | +2.4 | +9.0 |
| gap fill | 638 | 34% | 40% | 29% | +7.6 | +1.6 |
| daily EMA 9 | 2,350 | 31% | 43% | 28% | +3.7 | +2.1 |
| daily EMA 21 | 1,635 | 30% | 44% | 27% | +1.2 | +4.2 |
| prior week low | 1,412 | 32% | 45% | 29% | +2.8 | +2.0 |
| 200-day average | 267 | 33% | 42% | 30% | -4.0 | +8.7 |
| prior month high | 944 | 31% | 46% | 30% | -1.1 | +5.3 |
| prior week close | 2,971 | 29% | 45% | 27% | +2.5 | +1.6 |
| prior day high | 3,683 | 28% | 44% | 26% | +3.0 | +0.9 |
| yesterday's volume peak | 4,667 | 30% | 44% | 28% | +4.0 | -0.3 |
| 20-day value high | 1,620 | 28% | 44% | 27% | -0.6 | +3.9 |
| VWAP from the gap day | 1,065 | 30% | 44% | 28% | +1.5 | +1.5 |
| swing low | 4,345 | 30% | 44% | 28% | +3.8 | -1.3 |
| half round number | 2,223 | 31% | 43% | 30% | -0.7 | +2.8 |
| prior close | 5,039 | 29% | 45% | 27% | +4.9 | -3.1 |
| swing high | 4,947 | 31% | 43% | 30% | +1.8 | -0.2 |
| 52-week high | 614 | 27% | 45% | 26% | +7.7 | -6.9 |
| premarket low | 5,119 | 30% | 44% | 29% | +1.7 | -1.3 |
| VWAP from the high | 1,755 | 28% | 45% | 28% | -0.7 | +0.8 |
| opening range high | 5,723 | 26% | 43% | 26% | +1.9 | -2.5 |
| prior week high | 1,883 | 28% | 45% | 28% | +2.1 | -3.1 |
| daily EMA 50 | 1,006 | 29% | 45% | 29% | +7.8 | -9.1 |
| prior day low | 3,300 | 30% | 47% | 30% | +3.1 | -5.3 |
| opening range low | 5,701 | 27% | 45% | 29% | -1.3 | -2.0 |
| premarket high | 5,205 | 28% | 45% | 30% | -2.7 | -0.7 |
| 20-day value low | 1,191 | 30% | 44% | 32% | -5.9 | +2.4 |
| round number | 2,434 | 29% | 45% | 31% | -1.3 | -2.6 |
| 20-day volume peak | 1,647 | 31% | 43% | 33% | -1.8 | -2.6 |
| 52-week low | 121 | 22% | 59% | 32% | -8.3 | -25.7 |
| **All levels** | 76,326 | 29% | 44% | 29% | +1.6 | -0.5 |

### By how many kinds of level stack in the zone

| Families in the zone | Touches | Held | Broke | Edge vs control |
|---|--:|--:|--:|--:|
| 1 | 26,931 | 29% | 46% | +0.2 |
| 2 | 21,961 | 30% | 44% | +1.2 |
| 3 | 14,258 | 31% | 42% | +2.1 |
| 4 or more | 13,176 | 28% | 42% | -0.6 |

### By zone score

| Zone score | Touches | Held | Broke | Edge vs control |
|---|--:|--:|--:|--:|
| under 4 | 26,139 | 29% | 46% | +0.2 |
| 4 to 7 | 20,860 | 30% | 44% | +1.4 |
| 7 to 10 | 14,514 | 30% | 43% | +1.4 |
| 10 or more | 14,813 | 28% | 43% | -0.1 |

## B. Pivot-wick candles: at a key zone vs not

Average R per trade after costs, half at +0.5R then breakeven / 1R.

| Group | Trades | Avg R before | Avg R after | t after | Won (after) | 2R runner after |
|---|--:|--:|--:|--:|--:|--:|
| All candles | 26,407 | -0.099 | -0.094 | -14.2 | 64% | -0.094 |
| Wick away from every zone | 16,849 | -0.097 | -0.096 | -11.5 | 64% | -0.095 |
| Wick at a zone | 9,558 | -0.101 | -0.091 | -8.3 | 64% | -0.093 |
| zone score under 4 | 4,681 | -0.108 | -0.099 | -6.3 | 63% | -0.103 |
| zone score 4 to 7 | 2,475 | -0.105 | -0.078 | -3.5 | 65% | -0.079 |
| zone score 7 to 10 | 1,310 | -0.063 | -0.098 | -3.3 | 65% | -0.099 |
| zone score 10 or more | 1,092 | -0.109 | -0.080 | -2.6 | 66% | -0.073 |

### Only candles on volume 2x usual or more

| Group | Trades | Avg R before | Avg R after | t after | Won (after) | 2R runner after |
|---|--:|--:|--:|--:|--:|--:|
| Away from every zone | 2,699 | -0.106 | -0.089 | -4.7 | 63% | -0.085 |
| At a zone | 980 | -0.093 | -0.048 | -1.5 | 64% | -0.056 |
| At a zone scoring 7 or more | 207 | -0.051 | +0.112 | +1.8 | 78% | +0.070 |

### By family in the zone the wick is at (a candle counts once per family)

| Group | Trades | Avg R before | Avg R after | t after | Won (after) | 2R runner after |
|---|--:|--:|--:|--:|--:|--:|
| month | 419 | -0.108 | +0.002 | +0.0 | 71% | -0.018 |
| round | 1,101 | -0.124 | -0.068 | -2.1 | 65% | -0.069 |
| or | 2,532 | -0.125 | -0.072 | -3.4 | 67% | -0.060 |
| ma | 1,417 | -0.048 | -0.080 | -2.9 | 64% | -0.083 |
| swing | 2,427 | -0.079 | -0.082 | -3.9 | 64% | -0.070 |
| gap | 430 | -0.134 | -0.086 | -1.6 | 65% | -0.077 |
| session | 2,458 | -0.107 | -0.086 | -4.1 | 65% | -0.091 |
| profile | 2,096 | -0.113 | -0.090 | -3.9 | 65% | -0.087 |
| premkt | 2,386 | -0.085 | -0.091 | -4.1 | 65% | -0.085 |
| avwap | 923 | -0.106 | -0.100 | -2.8 | 65% | -0.113 |
| week | 1,448 | -0.043 | -0.141 | -5.0 | 62% | -0.134 |
| year | 187 | -0.164 | -0.323 | -4.5 | 46% | -0.358 |

### Oscillator at the extreme when the candle prints

15m oscillator 80+ at a top / 20 or less at a bottom; "all three" = the 5m, 9m and 15m oscillators all past 75 / 25 (the alert mode's rule).

| Group | Trades | Avg R before | Avg R after | t after | Won (after) | 2R runner after |
|---|--:|--:|--:|--:|--:|--:|
| 15m oscillator NOT at the extreme | 13,212 | -0.098 | -0.086 | -9.2 | 64% | -0.087 |
| 15m oscillator at the extreme | 13,195 | -0.099 | -0.103 | -10.8 | 63% | -0.101 |
| all three at the extreme | 2,062 | -0.139 | -0.088 | -3.6 | 64% | -0.094 |
| at a zone, 15m oscillator not extreme | 4,430 | -0.114 | -0.083 | -5.3 | 65% | -0.085 |
| at a zone + 15m oscillator extreme | 5,128 | -0.091 | -0.099 | -6.4 | 64% | -0.100 |
| at a zone + all three extreme | 857 | -0.143 | -0.065 | -1.7 | 67% | -0.068 |
| zone 7+ and 15m oscillator extreme | 1,348 | -0.064 | -0.132 | -4.5 | 63% | -0.121 |
| volume 2x + 15m oscillator extreme, away from zones | 1,162 | -0.147 | -0.128 | -4.3 | 60% | -0.115 |
| volume 2x + zone + 15m oscillator extreme | 492 | -0.057 | -0.089 | -1.9 | 61% | -0.106 |
| volume 2x + zone 7+ + 15m oscillator extreme | 110 | +0.021 | +0.022 | +0.2 | 75% | +0.000 |
| volume 2x + zone 7+, oscillator NOT extreme | 97 | -0.161 | +0.188 | +2.4 | 81% | +0.129 |

### Longs and shorts at a zone

| Group | Trades | Avg R before | Avg R after | t after | Won (after) | 2R runner after |
|---|--:|--:|--:|--:|--:|--:|
| longs at a zone (bottom wick) | 4,677 | -0.077 | -0.076 | -4.8 | 65% | -0.076 |
| shorts at a zone (top wick) | 4,881 | -0.125 | -0.105 | -6.8 | 63% | -0.108 |
