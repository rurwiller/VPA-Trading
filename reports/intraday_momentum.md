# Intraday momentum (lower-frequency) on 5 years of 1m bars

2021-11-05 to 2026-11-03, 20 tickers. One row = one ticker-day. `_d` before 2024-11-01, `_h` after. avg / 2se in bps of the position per day (net of each ticker's spread + 1 bp per round trip unless marked gross). ann. Sharpe = per ticker-day mean / std x sqrt(252) (one ticker traded alone).


## Mag7+

| strategy                                    |   n_d |   avg bps_d |   2se bps_d |   win%_d |   ann. Sharpe_d |   n_h |   avg bps_h |   2se bps_h |   win%_h |   ann. Sharpe_h |
|:--------------------------------------------|------:|------------:|------------:|---------:|----------------:|------:|------------:|------------:|---------:|----------------:|
| always long 15:30-16:00 (baseline)          |  7494 |       -2.12 |        1.08 |     47.3 |           -0.72 |  5012 |       -0.25 |        1.31 |     49.3 |           -0.09 |
| momentum: day so far -> last 30 min (gross) |  7484 |        1.32 |        1.08 |     51.3 |            0.45 |  5012 |       -1.82 |        1.31 |     47.6 |           -0.63 |
| momentum: day so far -> last 30 min         |  7484 |       -0.73 |        1.08 |     48.9 |           -0.25 |  5012 |       -3.87 |        1.31 |     44.9 |           -1.33 |
| momentum, only top third of day moves       |  2395 |        0.95 |        2.11 |     49.7 |            0.29 |  1737 |       -5.42 |        2.4  |     44.2 |           -1.72 |
| momentum: first 30 min -> last 30 min       |  7484 |       -2.82 |        1.08 |     47   |           -0.96 |  5012 |       -2.98 |        1.31 |     46.3 |           -1.02 |
| noise-band breakout, every day (gross)      |  7354 |        6.08 |        2.28 |     26.8 |            0.99 |  5012 |        1.35 |        2.56 |     23.2 |            0.24 |
| noise-band breakout, every day              |  7354 |        4.31 |        2.28 |     26   |            0.7  |  5012 |       -0.31 |        2.57 |     22.5 |           -0.05 |
| noise-band breakout, days with a trade      |  4495 |        7.06 |        3.73 |     42.6 |            0.9  |  2919 |       -0.54 |        4.41 |     38.6 |           -0.07 |

### Mag7+ by ticker (avg bps per day, net)

| sym   |   mom bps_d |   mom bps_h |   noise bps_d |   noise bps_h |
|:------|------------:|------------:|--------------:|--------------:|
| AAPL  |       -2.43 |       -6.68 |         -0.61 |          1.16 |
| AMD   |       -5.62 |       -4.8  |         10.16 |          4.83 |
| AMZN  |       -1.99 |       -2.33 |          0.84 |         -6.44 |
| GOOGL |       -1.46 |       -3.21 |         -0.96 |         -1.86 |
| META  |        2.58 |       -1.02 |          0.77 |         -2.47 |
| MSFT  |       -1.55 |       -5.91 |          0.61 |         -1.49 |
| NVDA  |        2.09 |       -4.13 |          8.29 |         -2.23 |
| QQQ   |       -0.69 |       -4.11 |          5.01 |          3.21 |
| SPY   |       -1.58 |       -3.58 |          3.34 |         -2.01 |
| TSLA  |        3.31 |       -2.96 |         15.64 |          4.15 |

### Mag7+ by year (avg bps per ticker-day, net)

|   year |   mom_full |   nb_ret |
|-------:|-----------:|---------:|
|   2021 |       5.24 |    21.15 |
|   2022 |       0.93 |     8.55 |
|   2023 |      -1.84 |     2.35 |
|   2024 |      -1.65 |    -0.69 |
|   2025 |      -4.78 |    -1.22 |
|   2026 |      -4.05 |     1.15 |

## mid-cap

| strategy                                    |   n_d |   avg bps_d |   2se bps_d |   win%_d |   ann. Sharpe_d |   n_h |   avg bps_h |   2se bps_h |   win%_h |   ann. Sharpe_h |
|:--------------------------------------------|------:|------------:|------------:|---------:|----------------:|------:|------------:|------------:|---------:|----------------:|
| always long 15:30-16:00 (baseline)          |  7479 |       -8.88 |        2.04 |     44.9 |           -1.6  |  4994 |       -7.13 |        2.42 |     46.8 |           -1.33 |
| momentum: day so far -> last 30 min (gross) |  7469 |        3.92 |        2.04 |     51.3 |            0.71 |  4994 |       -2.67 |        2.41 |     48.7 |           -0.5  |
| momentum: day so far -> last 30 min         |  7469 |       -3.91 |        2.04 |     47.7 |           -0.7  |  4994 |      -10.5  |        2.42 |     44.7 |           -1.95 |
| momentum, only top third of day moves       |  2354 |       -3.23 |        4.02 |     48.2 |           -0.53 |  1688 |      -12.71 |        4.77 |     44.5 |           -2.06 |
| momentum: first 30 min -> last 30 min       |  7469 |       -8.65 |        2.04 |     45.5 |           -1.56 |  4994 |       -9.56 |        2.42 |     45.8 |           -1.78 |
| noise-band breakout, every day (gross)      |  7338 |        6.85 |        5.62 |     25.3 |            0.45 |  4994 |       -2.75 |        5.1  |     22.6 |           -0.24 |
| noise-band breakout, every day              |  7338 |        0.08 |        5.65 |     24.3 |            0    |  4994 |       -9.43 |        5.14 |     21.4 |           -0.82 |
| noise-band breakout, days with a trade      |  4562 |        0.12 |        9.08 |     39.1 |            0.01 |  2989 |      -15.76 |        8.59 |     35.8 |           -1.07 |

### mid-cap by ticker (avg bps per day, net)

| sym   |   mom bps_d |   mom bps_h |   noise bps_d |   noise bps_h |
|:------|------------:|------------:|--------------:|--------------:|
| AFRM  |      -14.46 |      -13.72 |         -1.77 |         -4.92 |
| CVNA  |       -7.23 |       -6.68 |         13.3  |        -11.79 |
| DKNG  |        1.31 |       -6.7  |         -2.65 |         -7.27 |
| HOOD  |       -0.28 |       -4.54 |        -10.27 |         -3.61 |
| MARA  |       -4.39 |      -24.62 |          9.93 |        -23.7  |
| RIOT  |        2.83 |      -12.37 |          0.75 |         -3.06 |
| RIVN  |       -9.22 |      -22.39 |        -12.4  |        -26.72 |
| ROKU  |        2.06 |       -7.84 |          6.1  |         -7.16 |
| SMCI  |       -6.82 |       -0.4  |          2.86 |          7.49 |
| SOFI  |       -2.97 |       -5.71 |         -5.05 |        -13.53 |

### mid-cap by year (avg bps per ticker-day, net)

|   year |   mom_full |   nb_ret |
|-------:|-----------:|---------:|
|   2021 |      -5.88 |    22.25 |
|   2022 |       0.12 |    -2.49 |
|   2023 |      -6.3  |     2.88 |
|   2024 |      -4.48 |    -1.29 |
|   2025 |     -12.08 |    -6.35 |
|   2026 |     -10.84 |   -16.01 |
