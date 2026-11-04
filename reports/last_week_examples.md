# Last week's examples: gaps, fibs and premier candles

Data through Tue Nov 03, 2026 close. Gaps: 1h / 4h / daily, unfilled. Fib swings: 1h (3-candle pivots) and daily (2-day pivots). Premier candles: spec shapes on 9/15/29/60m, entries 10:00-15:30 ET (8:00-13:30 MST), result = +0.3% target / 0.5% stop race before costs.

## AAPL (last close 331.72)

**Unfilled fair value gaps at the close (nearest first)**

| tf   | kind              | zone            | formed           |   distance % |
|:-----|:------------------|:----------------|:-----------------|-------------:|
| 1h   | bear (resistance) | 331.14 - 337.57 | Tue Nov 03 09:30 |        -0.17 |
| 1h   | bear (resistance) | 334.50 - 336.50 | Tue Nov 03 08:30 |         0.84 |
| 4h   | bear (resistance) | 334.50 - 336.52 | Tue Nov 03 11:30 |         0.84 |
| D    | bull (support)    | 319.15 - 326.30 | Fri Sep 11 14:00 |        -1.63 |
| 1h   | bear (resistance) | 338.76 - 340.06 | Mon Nov 02 11:30 |         2.12 |
| 1h   | bear (resistance) | 342.32 - 343.14 | Mon Nov 02 09:30 |         3.2  |
| D    | bear (resistance) | 343.80 - 347.30 | Mon Nov 02 14:00 |         3.64 |
| 1h   | bear (resistance) | 343.86 - 346.25 | Fri Oct 30 13:30 |         3.66 |

**Fibonacci levels (last confirmed swing)**

| swing   | leg                                  |   high |    low |   r0.382 |   r0.5 |   GP 0.618 |   GP 0.65 |   r0.786 |
|:--------|:-------------------------------------|-------:|-------:|---------:|-------:|-----------:|----------:|---------:|
| 1h      | down leg (retracements = resistance) | 350.6  | 325.33 |   334.98 | 337.97 |     340.95 |    341.76 |   345.19 |
| D       | up leg (retracements = support)      | 351.43 | 341.03 |   347.46 | 346.23 |     345    |    344.67 |   343.26 |

**Premier candles (signal known at the candle close; MST)**

| close (MST)      | tf   | type                       | bias    |   entry | at gap   | +0.3% before -0.5%?   |   result % |
|:-----------------|:-----|:---------------------------|:--------|--------:|:---------|:----------------------|-----------:|
| Mon Oct 26 12:54 | 9m   | HAMMER                     | bullish |  342.92 | -        | yes                   |       0.3  |
| Mon Oct 26 13:30 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  343.55 | -        | neither               |      -0.13 |
| Tue Oct 27 10:45 | 15m  | SHOOTING_STAR              | bearish |  346.16 | -        | neither               |       0.1  |
| Wed Oct 28 09:36 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  345.37 | 1h       | neither               |       0.07 |
| Wed Oct 28 13:30 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  344.13 | -        | neither               |       0.08 |
| Thu Oct 29 09:09 | 9m   | SHOOTING_STAR              | bearish |  349.17 | -        | neither               |      -0.16 |
| Thu Oct 29 11:00 | 15m  | SHOOTING_STAR              | bearish |  349.77 | -        | neither               |      -0.09 |
| Thu Oct 29 12:36 | 9m   | HANGING_MAN                | bearish |  350.06 | -        | yes                   |       0.3  |
| Thu Oct 29 13:00 | 15m  | SHOOTING_STAR              | bearish |  350.1  | -        | yes                   |       0.3  |
| Fri Oct 30 10:15 | 15m  | HAMMER                     | bullish |  346.83 | -        | yes                   |       0.3  |
| Fri Oct 30 10:30 | 60m  | HANGING_MAN                | bearish |  347.5  | -        | yes                   |       0.3  |
| Fri Oct 30 12:27 | 9m   | HAMMER                     | bullish |  343.46 | -        | yes                   |       0.3  |
| Fri Oct 30 12:30 | 15m  | HAMMER                     | bullish |  343.13 | -        | yes                   |       0.3  |
| Fri Oct 30 12:30 | 60m  | HAMMER                     | bullish |  343.13 | -        | yes                   |       0.3  |
| Fri Oct 30 12:49 | 29m  | HAMMER                     | bullish |  343.12 | -        | yes                   |       0.3  |
| Fri Oct 30 13:00 | 15m  | HAMMER                     | bullish |  343.28 | -        | yes                   |       0.3  |
| Mon Nov 02 08:24 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  340.7  | -        | yes                   |       0.3  |
| Mon Nov 02 08:28 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  340.03 | -        | stopped               |      -0.5  |
| Mon Nov 02 08:33 | 9m   | HAMMER                     | bullish |  340.44 | -        | yes                   |       0.3  |
| Mon Nov 02 09:09 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  341    | -        | yes                   |       0.3  |
| Mon Nov 02 09:54 | 9m   | HAMMER                     | bullish |  339.74 | -        | stopped               |      -0.5  |
| Mon Nov 02 11:51 | 29m  | HAMMER                     | bullish |  337.15 | -        | yes                   |       0.3  |
| Mon Nov 02 12:20 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  336.92 | -        | stopped               |      -0.5  |
| Tue Nov 03 08:28 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  330.71 | -        | yes                   |       0.3  |
| Tue Nov 03 09:00 | 15m  | HAMMER                     | bullish |  329.12 | -        | yes                   |       0.3  |
| Tue Nov 03 09:30 | 60m  | HAMMER                     | bullish |  330.89 | -        | yes                   |       0.3  |
| Tue Nov 03 11:24 | 9m   | HANGING_MAN                | bearish |  332.32 | 1h       | yes                   |       0.3  |
| Tue Nov 03 11:33 | 9m   | HANGING_MAN                | bearish |  332.53 | 1h       | yes                   |       0.3  |
| Tue Nov 03 12:27 | 9m   | SHOOTING_STAR              | bearish |  332.12 | 1h       | yes                   |       0.3  |
| Tue Nov 03 13:18 | 29m  | HAMMER                     | bullish |  331.03 | -        | yes                   |       0.3  |
| Tue Nov 03 13:30 | 60m  | HAMMER                     | bullish |  331.29 | -        | neither               |       0.13 |

## MSFT (last close 520.77)

**Unfilled fair value gaps at the close (nearest first)**

| tf   | kind           | zone            | formed           |   distance % |
|:-----|:---------------|:----------------|:-----------------|-------------:|
| 1h   | bull (support) | 517.27 - 519.72 | Tue Nov 03 12:30 |        -0.2  |
| 1h   | bull (support) | 511.44 - 513.73 | Tue Nov 03 09:30 |        -1.35 |
| D    | bull (support) | 498.90 - 502.22 | Mon Sep 28 14:00 |        -3.56 |

**Fibonacci levels (last confirmed swing)**

| swing   | leg                                  |   high |    low |   r0.382 |   r0.5 |   GP 0.618 |   GP 0.65 |   r0.786 |
|:--------|:-------------------------------------|-------:|-------:|---------:|-------:|-----------:|----------:|---------:|
| 1h      | down leg (retracements = resistance) | 529.63 | 504.96 |   514.38 | 517.29 |     520.21 |    521    |   524.35 |
| D       | up leg (retracements = support)      | 541.29 | 515.7  |   531.51 | 528.5  |     525.48 |    524.66 |   521.18 |

**Premier candles (signal known at the candle close; MST)**

| close (MST)      | tf   | type                       | bias    |   entry | at gap   | +0.3% before -0.5%?   |   result % |
|:-----------------|:-----|:---------------------------|:--------|--------:|:---------|:----------------------|-----------:|
| Mon Oct 26 10:00 | 15m  | SHOOTING_STAR              | bearish |  529.68 | 4h       | neither               |      -0.15 |
| Mon Oct 26 10:12 | 9m   | SHOOTING_STAR              | bearish |  529.55 | 4h       | neither               |      -0.33 |
| Mon Oct 26 11:42 | 9m   | SHOOTING_STAR              | bearish |  530.1  | 4h       | stopped               |      -0.5  |
| Mon Oct 26 12:00 | 9m   | SHOOTING_STAR              | bearish |  530.48 | 4h       | stopped               |      -0.5  |
| Mon Oct 26 12:36 | 9m   | SHOOTING_STAR              | bearish |  532.14 | 4h       | neither               |      -0.11 |
| Mon Oct 26 13:21 | 9m   | SHOOTING_STAR              | bearish |  531.49 | 4h       | neither               |      -0.24 |
| Mon Oct 26 13:30 | 9m   | SHOOTING_STAR              | bearish |  531.3  | 4h       | neither               |      -0.27 |
| Tue Oct 27 09:26 | 29m  | SHOOTING_STAR              | bearish |  533.02 | 4h       | yes                   |       0.3  |
| Wed Oct 28 08:15 | 15m  | HAMMER                     | bullish |  530.01 | D        | stopped               |      -0.5  |
| Wed Oct 28 10:30 | 9m   | HAMMER                     | bullish |  528.16 | D        | neither               |      -0    |
| Wed Oct 28 11:45 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  527.18 | -        | stopped               |      -0.5  |
| Wed Oct 28 12:15 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  526.61 | -        | stopped               |      -0.5  |
| Thu Oct 29 08:30 | 15m  | HAMMER                     | bullish |  526.08 | -        | yes                   |       0.3  |
| Thu Oct 29 09:54 | 9m   | HAMMER                     | bullish |  522.77 | -        | yes                   |       0.3  |
| Thu Oct 29 11:30 | 60m  | HAMMER                     | bullish |  525.47 | -        | yes                   |       0.3  |
| Thu Oct 29 12:00 | 9m   | HANGING_MAN                | bearish |  526.27 | -        | stopped               |      -0.5  |
| Thu Oct 29 13:21 | 9m   | HANGING_MAN                | bearish |  528.84 | -        | yes                   |       0.3  |
| Fri Oct 30 09:45 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  521.94 | -        | yes                   |       0.3  |
| Fri Oct 30 11:42 | 9m   | HAMMER                     | bullish |  520.38 | -        | yes                   |       0.3  |
| Fri Oct 30 13:03 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  518.81 | -        | stopped               |      -0.5  |
| Mon Nov 02 08:45 | 15m  | HANGING_MAN                | bearish |  528.8  | -        | yes                   |       0.3  |
| Mon Nov 02 09:18 | 9m   | HANGING_MAN                | bearish |  524.24 | -        | yes                   |       0.3  |
| Mon Nov 02 10:39 | 9m   | HAMMER                     | bullish |  520    | -        | stopped               |      -0.5  |
| Mon Nov 02 10:57 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  520.19 | -        | yes                   |       0.3  |
| Mon Nov 02 11:24 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  519.71 | -        | yes                   |       0.3  |
| Mon Nov 02 12:30 | 15m  | HAMMER                     | bullish |  516.97 | -        | stopped               |      -0.5  |
| Mon Nov 02 12:36 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  515.82 | -        | yes                   |       0.3  |
| Mon Nov 02 12:54 | 9m   | HAMMER                     | bullish |  514.28 | -        | stopped               |      -0.5  |
| Mon Nov 02 13:00 | 15m  | HAMMER                     | bullish |  514.58 | -        | stopped               |      -0.5  |
| Tue Nov 03 09:27 | 9m   | HANGING_MAN                | bearish |  516.39 | -        | stopped               |      -0.5  |
| Tue Nov 03 13:15 | 15m  | SHOOTING_STAR              | bearish |  522.52 | -        | yes                   |       0.3  |
| Tue Nov 03 13:30 | 15m  | SHOOTING_STAR              | bearish |  522.34 | -        | yes                   |       0.3  |

## GOOGL (last close 279.92)

**Unfilled fair value gaps at the close (nearest first)**

| tf   | kind              | zone            | formed           |   distance % |
|:-----|:------------------|:----------------|:-----------------|-------------:|
| D    | bear (resistance) | 283.14 - 322.65 | Fri Oct 30 14:00 |         1.15 |
| 4h   | bear (resistance) | 284.04 - 322.65 | Thu Oct 29 14:00 |         1.47 |
| 1h   | bear (resistance) | 287.31 - 323.48 | Thu Oct 29 09:30 |         2.64 |
| 1h   | bear (resistance) | 288.20 - 322.84 | Thu Oct 29 08:30 |         2.96 |
| 4h   | bear (resistance) | 288.33 - 323.00 | Thu Oct 29 11:30 |         3    |
| D    | bear (resistance) | 288.33 - 316.86 | Thu Oct 29 14:00 |         3    |
| D    | bear (resistance) | 324.53 - 330.38 | Fri Oct 23 14:00 |        15.94 |
| 4h   | bear (resistance) | 326.49 - 332.80 | Thu Oct 22 14:00 |        16.64 |

**Fibonacci levels (last confirmed swing)**

| swing   | leg                                  |   high |    low |   r0.382 |   r0.5 |   GP 0.618 |   GP 0.65 |   r0.786 |
|:--------|:-------------------------------------|-------:|-------:|---------:|-------:|-----------:|----------:|---------:|
| 1h      | up leg (retracements = support)      |  281.6 | 277.2  |   279.92 | 279.4  |     278.88 |    278.74 |   278.14 |
| D       | down leg (retracements = resistance) |  326.4 | 276.92 |   295.82 | 301.66 |     307.5  |    309.09 |   315.82 |

**Premier candles (signal known at the candle close; MST)**

| close (MST)      | tf   | type                       | bias    |   entry | at gap   | +0.3% before -0.5%?   |   result % |
|:-----------------|:-----|:---------------------------|:--------|--------:|:---------|:----------------------|-----------:|
| Mon Oct 26 08:00 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  318.03 | -        | stopped               |      -0.5  |
| Mon Oct 26 08:06 | 9m   | HAMMER                     | bullish |  318.22 | -        | yes                   |       0.3  |
| Mon Oct 26 08:30 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  319.89 | -        | neither               |       0.21 |
| Mon Oct 26 12:20 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  317.94 | -        | yes                   |       0.3  |
| Mon Oct 26 13:18 | 29m  | HAMMER                     | bullish |  317.14 | -        | neither               |      -0.08 |
| Tue Oct 27 10:00 | 15m  | HANGING_MAN                | bearish |  320.54 | -        | stopped               |      -0.5  |
| Tue Oct 27 10:03 | 9m   | SHOOTING_STAR              | bearish |  320.98 | -        | neither               |      -0.29 |
| Tue Oct 27 10:21 | 9m   | HANGING_MAN                | bearish |  322.07 | -        | yes                   |       0.3  |
| Wed Oct 28 08:00 | 15m  | HANGING_MAN                | bearish |  324.24 | D        | yes                   |       0.3  |
| Wed Oct 28 08:30 | 15m  | HANGING_MAN                | bearish |  324.64 | D        | yes                   |       0.3  |
| Wed Oct 28 11:15 | 15m  | SHOOTING_STAR              | bearish |  324.52 | D        | yes                   |       0.3  |
| Wed Oct 28 12:30 | 15m  | HAMMER                     | bullish |  323.64 | -        | yes                   |       0.3  |
| Wed Oct 28 13:18 | 29m  | SHOOTING_STAR              | bearish |  324.85 | D        | yes                   |       0.3  |
| Thu Oct 29 09:18 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  285.95 | -        | stopped               |      -0.5  |
| Thu Oct 29 12:30 | 15m  | HAMMER                     | bullish |  281.91 | -        | yes                   |       0.3  |
| Thu Oct 29 13:03 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  283.04 | -        | yes                   |       0.3  |
| Fri Oct 30 13:00 | 15m  | HAMMER                     | bullish |  277.6  | -        | yes                   |       0.3  |
| Fri Oct 30 13:03 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  277.17 | -        | stopped               |      -0.5  |
| Mon Nov 02 12:54 | 9m   | HAMMER                     | bullish |  282.09 | 1h       | yes                   |       0.3  |
| Tue Nov 03 10:00 | 15m  | HAMMER                     | bullish |  279.08 | -        | yes                   |       0.3  |
| Tue Nov 03 11:22 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  280.42 | -        | yes                   |       0.3  |

## AMZN (last close 250.74)

**Unfilled fair value gaps at the close (nearest first)**

| tf   | kind              | zone            | formed           |   distance % |
|:-----|:------------------|:----------------|:-----------------|-------------:|
| 4h   | bear (resistance) | 251.05 - 261.20 | Thu Oct 22 14:00 |         0.12 |
| 1h   | bull (support)    | 241.00 - 251.47 | Mon Nov 02 09:30 |         0.29 |
| D    | bear (resistance) | 250.01 - 259.29 | Fri Oct 23 14:00 |        -0.29 |
| 1h   | bear (resistance) | 248.39 - 254.08 | Thu Oct 29 09:30 |        -0.94 |
| 4h   | bull (support)    | 241.00 - 244.90 | Mon Nov 02 14:00 |        -2.33 |
| 4h   | bear (resistance) | 258.41 - 259.29 | Thu Oct 22 11:30 |         3.06 |
| D    | bear (resistance) | 258.41 - 260.42 | Thu Oct 22 14:00 |         3.06 |
| 1h   | bull (support)    | 239.66 - 242.28 | Mon Nov 02 08:30 |        -3.37 |

**Fibonacci levels (last confirmed swing)**

| swing   | leg                                  |   high |    low |   r0.382 |   r0.5 |   GP 0.618 |   GP 0.65 |   r0.786 |
|:--------|:-------------------------------------|-------:|-------:|---------:|-------:|-----------:|----------:|---------:|
| 1h      | down leg (retracements = resistance) | 253.81 | 244.9  |   248.3  | 249.36 |     250.41 |    250.69 |    251.9 |
| D       | down leg (retracements = resistance) | 255.36 | 229.36 |   239.29 | 242.36 |     245.43 |    246.26 |    249.8 |

**Premier candles (signal known at the candle close; MST)**

| close (MST)      | tf   | type                       | bias    |   entry | at gap   | +0.3% before -0.5%?   |   result % |
|:-----------------|:-----|:---------------------------|:--------|--------:|:---------|:----------------------|-----------:|
| Mon Oct 26 13:30 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  248.42 | -        | neither               |      -0.25 |
| Tue Oct 27 11:00 | 15m  | SHOOTING_STAR              | bearish |  253.65 | D        | neither               |      -0.35 |
| Tue Oct 27 12:09 | 9m   | LL_DOJI_AT_HIGH            | bearish |  253.84 | D        | yes                   |       0.3  |
| Wed Oct 28 08:28 | 29m  | SHOOTING_STAR              | bearish |  253.32 | D        | yes                   |       0.3  |
| Wed Oct 28 09:45 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  252.39 | D        | neither               |      -0.09 |
| Wed Oct 28 12:45 | 9m   | LL_DOJI_AT_HIGH            | bearish |  253.53 | D        | stopped               |      -0.5  |
| Thu Oct 29 09:00 | 9m   | HAMMER                     | bullish |  245.97 | -        | yes                   |       0.3  |
| Thu Oct 29 09:45 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  248.38 | 1h       | yes                   |       0.3  |
| Thu Oct 29 12:45 | 15m  | HAMMER                     | bullish |  244.91 | -        | yes                   |       0.3  |
| Fri Oct 30 09:09 | 9m   | HAMMER                     | bullish |  240.02 | -        | yes                   |       0.3  |
| Fri Oct 30 09:30 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  239.81 | 1h       | yes                   |       0.3  |
| Fri Oct 30 10:15 | 15m  | HAMMER                     | bullish |  239.27 | -        | yes                   |       0.3  |
| Fri Oct 30 10:30 | 15m  | HAMMER                     | bullish |  239.31 | -        | yes                   |       0.3  |
| Fri Oct 30 10:53 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  237.97 | 1h       | stopped               |      -0.5  |
| Mon Nov 02 08:51 | 9m   | SHOOTING_STAR              | bearish |  252.94 | D        | yes                   |       0.3  |
| Mon Nov 02 09:45 | 9m   | HANGING_MAN                | bearish |  251.58 | D        | yes                   |       0.3  |
| Mon Nov 02 12:54 | 9m   | HAMMER                     | bullish |  247.87 | 1h       | yes                   |       0.3  |
| Mon Nov 02 13:12 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  248.36 | 1h       | yes                   |       0.3  |
| Tue Nov 03 08:15 | 15m  | HAMMER                     | bullish |  247.12 | 1h       | yes                   |       0.3  |
| Tue Nov 03 11:33 | 9m   | HANGING_MAN                | bearish |  250.92 | D        | yes                   |       0.3  |
| Tue Nov 03 12:00 | 9m   | HANGING_MAN                | bearish |  251.39 | D        | yes                   |       0.3  |
| Tue Nov 03 12:00 | 15m  | HANGING_MAN                | bearish |  251.39 | D        | yes                   |       0.3  |
| Tue Nov 03 12:18 | 9m   | HANGING_MAN                | bearish |  251.06 | D        | stopped               |      -0.5  |
| Tue Nov 03 12:20 | 29m  | HANGING_MAN                | bearish |  251.28 | D        | neither               |       0.21 |
| Tue Nov 03 12:30 | 60m  | HANGING_MAN                | bearish |  251.71 | D        | yes                   |       0.3  |
| Tue Nov 03 13:12 | 9m   | HANGING_MAN                | bearish |  251.54 | D        | yes                   |       0.3  |

## NVDA (last close 206.56)

**Unfilled fair value gaps at the close (nearest first)**

| tf   | kind              | zone            | formed           |   distance % |
|:-----|:------------------|:----------------|:-----------------|-------------:|
| 1h   | bull (support)    | 203.47 - 207.16 | Tue Nov 03 09:30 |         0.29 |
| 1h   | bull (support)    | 204.66 - 205.93 | Tue Nov 03 08:30 |        -0.3  |
| 1h   | bear (resistance) | 207.17 - 207.71 | Tue Nov 03 13:30 |         0.3  |
| 1h   | bear (resistance) | 207.57 - 212.81 | Fri Oct 30 09:30 |         0.49 |
| 4h   | bear (resistance) | 205.42 - 212.21 | Fri Oct 30 14:00 |        -0.55 |
| 1h   | bear (resistance) | 209.06 - 212.21 | Fri Oct 30 08:30 |         1.21 |
| 4h   | bear (resistance) | 209.06 - 212.08 | Fri Oct 30 11:30 |         1.21 |
| D    | bear (resistance) | 209.06 - 214.47 | Fri Oct 30 14:00 |         1.21 |

**Fibonacci levels (last confirmed swing)**

| swing   | leg                                  |   high |    low |   r0.382 |   r0.5 |   GP 0.618 |   GP 0.65 |   r0.786 |
|:--------|:-------------------------------------|-------:|-------:|---------:|-------:|-----------:|----------:|---------:|
| 1h      | up leg (retracements = support)      | 209.14 | 201.66 |   206.28 | 205.4  |     204.52 |    204.28 |   203.26 |
| D       | down leg (retracements = resistance) | 219.99 | 200.92 |   208.2  | 210.45 |     212.71 |    213.32 |   215.91 |

**Premier candles (signal known at the candle close; MST)**

| close (MST)      | tf   | type                       | bias    |   entry | at gap   | +0.3% before -0.5%?   |   result % |
|:-----------------|:-----|:---------------------------|:--------|--------:|:---------|:----------------------|-----------:|
| Tue Oct 27 08:06 | 9m   | HAMMER                     | bullish |  216.22 | 4h       | yes                   |       0.3  |
| Tue Oct 27 10:24 | 29m  | HANGING_MAN                | bearish |  219.04 | D        | yes                   |       0.3  |
| Tue Oct 27 10:30 | 15m  | SHOOTING_STAR              | bearish |  218.66 | D        | yes                   |       0.3  |
| Tue Oct 27 12:30 | 60m  | SHOOTING_STAR              | bearish |  217.52 | 4h       | neither               |      -0.18 |
| Tue Oct 27 13:30 | 60m  | SHOOTING_STAR              | bearish |  217.37 | 4h       | stopped               |      -0.5  |
| Wed Oct 28 11:33 | 9m   | HAMMER                     | bullish |  216.97 | -        | yes                   |       0.3  |
| Wed Oct 28 12:45 | 15m  | LL_DOJI_AT_LOW             | bullish |  217.05 | -        | stopped               |      -0.5  |
| Wed Oct 28 13:21 | 9m   | LL_DOJI_AT_LOW             | bullish |  215.44 | D        | neither               |      -0.02 |
| Thu Oct 29 08:33 | 9m   | HAMMER                     | bullish |  213.76 | 1h       | yes                   |       0.3  |
| Thu Oct 29 08:42 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  213.77 | 4h       | yes                   |       0.3  |
| Thu Oct 29 09:00 | 15m  | HAMMER                     | bullish |  213.92 | 1h       | neither               |      -0.12 |
| Thu Oct 29 09:26 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  213.7  | 4h       | yes                   |       0.3  |
| Thu Oct 29 12:45 | 15m  | HAMMER                     | bullish |  212.6  | 1h       | yes                   |       0.3  |
| Thu Oct 29 13:00 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  212.58 | -        | stopped               |      -0.5  |
| Thu Oct 29 13:15 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  212.6  | -        | stopped               |      -0.5  |
| Thu Oct 29 13:30 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  212.84 | -        | neither               |      -0.42 |
| Fri Oct 30 09:30 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  206.16 | -        | yes                   |       0.3  |
| Mon Nov 02 08:33 | 9m   | SHOOTING_STAR              | bearish |  209.08 | D        | yes                   |       0.3  |
| Mon Nov 02 12:18 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  204.9  | 4h       | yes                   |       0.3  |
| Mon Nov 02 12:36 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  203.94 | -        | yes                   |       0.3  |
| Mon Nov 02 13:12 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  203.96 | -        | yes                   |       0.3  |
| Tue Nov 03 11:51 | 29m  | SHOOTING_STAR              | bearish |  207.85 | 4h       | yes                   |       0.3  |
| Tue Nov 03 12:00 | 9m   | HAMMER                     | bullish |  207.79 | -        | stopped               |      -0.5  |
| Tue Nov 03 12:18 | 9m   | HAMMER                     | bullish |  207.27 | 1h       | neither               |      -0.34 |

## META (last close 621.13)

**Unfilled fair value gaps at the close (nearest first)**

| tf   | kind              | zone            | formed           |   distance % |
|:-----|:------------------|:----------------|:-----------------|-------------:|
| 1h   | bull (support)    | 610.19 - 616.15 | Tue Nov 03 09:30 |        -0.8  |
| D    | bull (support)    | 600.38 - 605.27 | Fri Sep 04 14:00 |        -2.55 |
| D    | bull (support)    | 584.95 - 604.35 | Thu Sep 03 14:00 |        -2.7  |
| D    | bear (resistance) | 648.04 - 689.68 | Fri Oct 23 14:00 |         4.33 |
| 4h   | bear (resistance) | 650.22 - 689.68 | Thu Oct 22 14:00 |         4.68 |
| D    | bull (support)    | 553.87 - 561.40 | Tue Aug 25 14:00 |        -9.62 |
| 4h   | bear (resistance) | 681.07 - 692.38 | Thu Oct 22 11:30 |         9.65 |
| D    | bear (resistance) | 708.83 - 715.58 | Mon Oct 19 14:00 |        14.12 |

**Fibonacci levels (last confirmed swing)**

| swing   | leg                             |   high |    low |   r0.382 |   r0.5 |   GP 0.618 |   GP 0.65 |   r0.786 |
|:--------|:--------------------------------|-------:|-------:|---------:|-------:|-----------:|----------:|---------:|
| 1h      | up leg (retracements = support) | 624.84 | 606.41 |   617.8  | 615.62 |     613.45 |    612.86 |   610.35 |
| D       | up leg (retracements = support) | 634.68 | 609    |   624.87 | 621.84 |     618.81 |    617.99 |   614.5  |

**Premier candles (signal known at the candle close; MST)**

| close (MST)      | tf   | type                       | bias    |   entry | at gap   | +0.3% before -0.5%?   |   result % |
|:-----------------|:-----|:---------------------------|:--------|--------:|:---------|:----------------------|-----------:|
| Mon Oct 26 09:00 | 15m  | SHOOTING_STAR              | bearish |  644.63 | D        | yes                   |       0.3  |
| Mon Oct 26 12:36 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  632.72 | -        | yes                   |       0.3  |
| Tue Oct 27 08:00 | 15m  | HAMMER                     | bullish |  624.23 | D        | yes                   |       0.3  |
| Tue Oct 27 08:28 | 29m  | HAMMER                     | bullish |  624.8  | D        | yes                   |       0.3  |
| Tue Oct 27 09:45 | 15m  | HAMMER                     | bullish |  625.52 | D        | stopped               |      -0.5  |
| Tue Oct 27 12:36 | 9m   | HAMMER                     | bullish |  622.68 | D        | stopped               |      -0.5  |
| Wed Oct 28 08:28 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  614.89 | -        | yes                   |       0.3  |
| Wed Oct 28 09:00 | 9m   | HAMMER                     | bullish |  612.28 | -        | yes                   |       0.3  |
| Wed Oct 28 09:09 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  612.58 | -        | neither               |       0.08 |
| Wed Oct 28 09:30 | 15m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  612.44 | -        | neither               |      -0.07 |
| Wed Oct 28 11:15 | 9m   | HAMMER                     | bullish |  612.67 | -        | stopped               |      -0.5  |
| Wed Oct 28 12:18 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  610.07 | -        | stopped               |      -0.5  |
| Wed Oct 28 12:30 | 15m  | HAMMER                     | bullish |  610.17 | -        | yes                   |       0.3  |
| Wed Oct 28 12:54 | 9m   | LL_DOJI_AT_LOW             | bullish |  612.81 | -        | neither               |      -0.07 |
| Thu Oct 29 11:30 | 60m  | SHOOTING_STAR              | bearish |  629.33 | 1h       | yes                   |       0.3  |
| Thu Oct 29 12:49 | 29m  | HANGING_MAN                | bearish |  627.39 | -        | yes                   |       0.3  |
| Thu Oct 29 13:12 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  628.04 | -        | yes                   |       0.3  |
| Fri Oct 30 08:24 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  617.04 | -        | stopped               |      -0.5  |
| Fri Oct 30 09:00 | 9m   | HAMMER                     | bullish |  625.18 | -        | stopped               |      -0.5  |
| Fri Oct 30 10:48 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  620.66 | -        | yes                   |       0.3  |
| Fri Oct 30 11:42 | 9m   | HAMMER                     | bullish |  618.73 | -        | stopped               |      -0.5  |
| Fri Oct 30 12:45 | 15m  | HAMMER                     | bullish |  613.66 | -        | yes                   |       0.3  |
| Fri Oct 30 13:00 | 15m  | HAMMER                     | bullish |  612.98 | -        | yes                   |       0.3  |
| Mon Nov 02 09:55 | 29m  | SHOOTING_STAR_IN_DOWNTREND | bearish |  611.7  | -        | yes                   |       0.3  |
| Mon Nov 02 12:30 | 15m  | HAMMER                     | bullish |  611.57 | -        | yes                   |       0.3  |
| Mon Nov 02 12:45 | 9m   | HAMMER                     | bullish |  610.28 | -        | yes                   |       0.3  |
| Tue Nov 03 08:33 | 9m   | SHOOTING_STAR              | bearish |  616.58 | -        | stopped               |      -0.5  |
| Tue Nov 03 08:45 | 15m  | LL_DOJI_AT_HIGH            | bearish |  618.12 | 4h       | stopped               |      -0.5  |
| Tue Nov 03 11:51 | 9m   | SHOOTING_STAR              | bearish |  622.95 | -        | yes                   |       0.3  |

## TSLA (last close 398.21)

**Unfilled fair value gaps at the close (nearest first)**

| tf   | kind              | zone            | formed           |   distance % |
|:-----|:------------------|:----------------|:-----------------|-------------:|
| 1h   | bear (resistance) | 399.79 - 400.91 | Tue Nov 03 10:30 |         0.4  |
| D    | bull (support)    | 377.32 - 395.25 | Tue Oct 27 14:00 |        -0.74 |
| 1h   | bear (resistance) | 405.53 - 407.20 | Mon Nov 02 13:30 |         1.84 |
| 4h   | bull (support)    | 373.64 - 390.50 | Mon Oct 26 14:00 |        -1.94 |
| 1h   | bear (resistance) | 408.17 - 409.32 | Mon Nov 02 12:30 |         2.5  |
| 4h   | bull (support)    | 377.32 - 383.73 | Mon Oct 26 11:30 |        -3.64 |
| 4h   | bull (support)    | 355.42 - 366.24 | Mon Oct 19 14:00 |        -8.03 |
| D    | bull (support)    | 323.00 - 326.15 | Mon Aug 10 14:00 |       -18.1  |

**Fibonacci levels (last confirmed swing)**

| swing   | leg                                  |   high |    low |   r0.382 |   r0.5 |   GP 0.618 |   GP 0.65 |   r0.786 |
|:--------|:-------------------------------------|-------:|-------:|---------:|-------:|-----------:|----------:|---------:|
| 1h      | up leg (retracements = support)      | 414.23 | 393.83 |   406.44 | 404.03 |     401.62 |    400.97 |   398.2  |
| D       | down leg (retracements = resistance) | 410.85 | 387.52 |   396.43 | 399.19 |     401.94 |    402.68 |   405.86 |

**Premier candles (signal known at the candle close; MST)**

| close (MST)      | tf   | type                       | bias    |   entry | at gap   | +0.3% before -0.5%?   |   result % |
|:-----------------|:-----|:---------------------------|:--------|--------:|:---------|:----------------------|-----------:|
| Mon Oct 26 08:00 | 15m  | LL_DOJI_AT_HIGH            | bearish |  392.79 | -        | stopped               |       -0.5 |
| Mon Oct 26 09:15 | 15m  | HANGING_MAN                | bearish |  395.77 | -        | yes                   |        0.3 |
| Mon Oct 26 13:03 | 9m   | HAMMER                     | bullish |  394.4  | -        | stopped               |       -0.5 |
| Tue Oct 27 09:09 | 9m   | SHOOTING_STAR              | bearish |  402.35 | -        | stopped               |       -0.5 |
| Tue Oct 27 11:15 | 15m  | SHOOTING_STAR              | bearish |  406.47 | -        | yes                   |        0.3 |
| Tue Oct 27 11:51 | 29m  | SHOOTING_STAR              | bearish |  405.78 | -        | stopped               |       -0.5 |
| Tue Oct 27 13:30 | 15m  | SHOOTING_STAR              | bearish |  407.55 | -        | yes                   |        0.3 |
| Wed Oct 28 10:30 | 15m  | HAMMER                     | bullish |  401.3  | 4h       | yes                   |        0.3 |
| Wed Oct 28 13:03 | 9m   | LL_DOJI_AT_HIGH            | bearish |  403.25 | 1h       | yes                   |        0.3 |
| Thu Oct 29 09:27 | 9m   | SHOOTING_STAR              | bearish |  405.69 | -        | yes                   |        0.3 |
| Mon Nov 02 09:30 | 60m  | LL_DOJI_AT_HIGH            | bearish |  410.86 | -        | yes                   |        0.3 |
| Mon Nov 02 13:12 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  403.92 | -        | yes                   |        0.3 |
| Tue Nov 03 10:30 | 9m   | HAMMER                     | bullish |  397.32 | -        | yes                   |        0.3 |
| Tue Nov 03 10:57 | 9m   | SHOOTING_STAR_IN_DOWNTREND | bearish |  397.58 | -        | stopped               |       -0.5 |
