# Higher-timeframe candles and the oversold setup: all S&P 500 stocks

PART 1. The oversold setup in 2026: daily AND live weekly Willard oscillator below 10 (first day of each run),
        with and without the daily-gap filter, compared with the years before.

PART 2. Pivot candles (the scanner's hammer / shooting star: rejection wick >= 40% of the range and >= the body,
        opposite wick <= 30%) on the DAILY and WEEKLY charts, alone and when the oscillator is at an extreme:
          long:  hammer (wick at the bottom)      with the oscillator below 10 (oversold)
          short: shooting star (wick at the top)  with the oscillator above 90 (overbought)
        Weekly candles are finished weeks; their oscillator is the weekly value at that week's close.
        Daily candles use the live weekly value that day (the week so far), so nothing looks ahead.
        "High volume" = the candle's volume at least 1.5x its 20-bar average.
  Two ways to score each candle:
    drift  return from the candle's close to 5 / 10 / 20 trading days later, in the trade's direction, minus that
           stock's average move over the same days (so "short" is not penalised just for the bull market... it is:
           a short has to beat minus the usual move).
    trade  how the scanner trades it: buy a break of the candle's high (short: break of the low) during the next bar
           (next day for daily candles, next week for weekly), stop at the other end of the candle, target 1R,
           otherwise out at the close 20 trading days after entry. Result in R (risk units) before costs; a day
           that touches both stop and target counts as a stop.

Drift cells: average return in the trade's direction beyond the stock's usual move (t; above about 2 is unlikely to be luck). Trade result: average R per triggered trade (share that made money).

## Part 1: daily + weekly oscillator below 10, 2026 vs before

| Setups | Count | +5 days | +10 days | +20 days |
|---|--:|--:|--:|--:|
| 2016-2025, all | 14969 | +0.04% (t +1.1) | +0.24% (t +4.4) | +0.28% (t +3.6) |
| 2026, all | 1549 | +0.22% (t +1.3) | +0.04% (t +0.2) | +0.09% (t +0.3) |
| 2016-2025, at a daily gap | 6023 | +0.09% (t +1.4) | +0.35% (t +3.9) | +0.33% (t +2.6) |
| 2026, at a daily gap | 629 | +0.57% (t +2.1) | +0.35% (t +0.9) | +0.06% (t +0.1) |
| 2026, no gap | 920 | -0.02% (t -0.1) | -0.16% (t -0.6) | +0.11% (t +0.3) |

2026 by month (all setups):

| Month | Setups | +5 days | +10 days | +20 days |
|---|--:|--:|--:|--:|
| 2026-01 | 142 | +1.02% (t +2.2) | -0.08% (t -0.1) | +1.24% (t +1.1) |
| 2026-02 | 106 | -0.43% (t -0.8) | -2.63% (t -3.5) | -4.57% (t -4.7) |
| 2026-03 | 260 | -0.20% (t -0.6) | +2.06% (t +2.9) | +3.41% (t +3.8) |
| 2026-04 | 77 | -1.68% (t -4.0) | -2.63% (t -4.1) | -2.93% (t -3.9) |
| 2026-05 | 51 | +1.15% (t +1.7) | +2.03% (t +1.9) | +0.09% (t +0.1) |
| 2026-06 | 194 | +1.00% (t +2.3) | +2.48% (t +4.7) | +0.90% (t +1.2) |
| 2026-07 | 138 | +2.75% (t +3.8) | +1.83% (t +2.1) | +1.39% (t +1.3) |
| 2026-08 | 162 | -0.17% (t -0.5) | -1.46% (t -3.5) | -4.09% (t -6.7) |
| 2026-09 | 277 | -1.18% (t -5.0) | -1.64% (t -5.7) | +0.40% (t +0.7) |
| 2026-10 | 67 | -0.44% (t -0.3) | +0.78% (t +0.4) | -0.69% (t -0.3) |
| 2026-11 | 75 | +3.42% (t +2.0) | -3.74% (t -2.1) | - |

## Part 2: pivot candles, 2016-2026


### Daily candles

| Candle | Count | +5 days | +10 days | +20 days | Triggered | Trade result |
|---|--:|--:|--:|--:|--:|--:|
| Hammer, any | 228690 | -0.07% (t -6.7) | -0.11% (t -7.8) | -0.17% (t -8.9) | 153724 | -0.01R (49% won) |
| Hammer, weekly osc below 10 | 37959 | -0.10% (t -3.4) | -0.11% (t -2.9) | +0.19% (t +3.9) | 25143 | -0.00R (50% won) |
| Hammer, daily AND weekly osc below 10 | 5053 | -0.17% (t -2.4) | -0.03% (t -0.3) | +0.11% (t +0.9) | 3221 | -0.03R (48% won) |
| Hammer, weekly osc below 10, high volume | 4760 | -0.43% (t -3.9) | -0.71% (t -5.4) | -0.11% (t -0.6) | 2956 | +0.02R (51% won) |
| Hammer, weekly below 10, SPY above 200-day | 30903 | -0.01% (t -0.5) | -0.05% (t -1.5) | +0.14% (t +2.9) | 20743 | -0.01R (50% won) |
| Hammer, weekly below 10, SPY below 200-day | 7056 | -0.46% (t -4.5) | -0.33% (t -2.9) | +0.39% (t +2.7) | 4400 | +0.02R (51% won) |
| Shooting star, any | 205598 | -0.04% (t -3.7) | -0.03% (t -2.0) | -0.04% (t -2.0) | 129652 | -0.13R (43% won) |
| Shooting star, weekly osc above 90 | 32101 | -0.10% (t -3.8) | -0.20% (t -5.4) | -0.18% (t -3.5) | 20022 | -0.15R (43% won) |
| Shooting star, daily AND weekly above 90 | 4153 | +0.19% (t +2.7) | +0.06% (t +0.6) | -0.07% (t -0.5) | 2464 | -0.09R (46% won) |
| Shooting star, weekly above 90, high volume | 2966 | +0.02% (t +0.2) | -0.07% (t -0.6) | +0.10% (t +0.6) | 1666 | -0.14R (43% won) |
| Shooting star, weekly above 90, SPY below 200-day | 6407 | -0.66% (t -9.3) | -1.21% (t -13.1) | -1.90% (t -14.3) | 3852 | -0.24R (38% won) |

### Weekly candles

| Candle | Count | +5 days | +10 days | +20 days | Triggered | Trade result |
|---|--:|--:|--:|--:|--:|--:|
| Hammer, any | 42426 | +0.04% (t +1.8) | +0.10% (t +3.1) | +0.10% (t +2.2) | 30036 | +0.08R (55% won) |
| Hammer, weekly osc below 10 | 7455 | +0.05% (t +0.9) | +0.26% (t +3.6) | +0.60% (t +5.8) | 5107 | +0.08R (54% won) |
| Hammer, daily AND weekly osc below 10 | 67 | -0.37% (t -0.7) | -0.09% (t -0.1) | -0.57% (t -0.6) | 32 | -0.06R (47% won) |
| Hammer, weekly osc below 10, high volume | 954 | -0.63% (t -2.4) | -0.43% (t -1.8) | +1.16% (t +3.2) | 555 | +0.04R (54% won) |
| Hammer, weekly below 10, SPY above 200-day | 6003 | +0.07% (t +1.3) | +0.11% (t +1.5) | +0.38% (t +3.7) | 4109 | +0.07R (54% won) |
| Hammer, weekly below 10, SPY below 200-day | 1452 | -0.03% (t -0.1) | +0.87% (t +4.2) | +1.50% (t +4.9) | 998 | +0.10R (55% won) |
| Shooting star, any | 35080 | +0.12% (t +4.3) | +0.19% (t +4.8) | +0.29% (t +4.9) | 22942 | -0.08R (46% won) |
| Shooting star, weekly osc above 90 | 5510 | -0.10% (t -1.5) | +0.28% (t +3.1) | +0.12% (t +0.9) | 3326 | -0.07R (47% won) |
| Shooting star, daily AND weekly above 90 | 29 | -1.51% (t -1.5) | -1.50% (t -1.1) | -0.09% (t -0.0) | 8 | -0.25R (38% won) |
| Shooting star, weekly above 90, high volume | 433 | -0.45% (t -1.5) | +0.22% (t +0.6) | -0.41% (t -0.8) | 193 | -0.10R (46% won) |
| Shooting star, weekly above 90, SPY below 200-day | 962 | -0.93% (t -4.6) | +0.44% (t +1.6) | -2.32% (t -6.0) | 581 | -0.10R (44% won) |

## Part 2: pivot candles, 2026 only


### Daily candles

| Candle | Count | +5 days | +10 days | +20 days | Triggered | Trade result |
|---|--:|--:|--:|--:|--:|--:|
| Hammer, any | 18248 | -0.18% (t -4.1) | -0.13% (t -2.2) | -0.26% (t -2.8) | 11930 | -0.08R (46% won) |
| Hammer, weekly osc below 10 | 3244 | -0.53% (t -5.6) | -0.68% (t -4.8) | -0.52% (t -2.7) | 2060 | -0.14R (43% won) |
| Hammer, daily AND weekly osc below 10 | 426 | -0.47% (t -1.9) | -0.76% (t -2.3) | -0.61% (t -1.2) | 264 | -0.19R (40% won) |
| Hammer, weekly osc below 10, high volume | 376 | -0.33% (t -1.1) | -0.67% (t -1.7) | -0.27% (t -0.5) | 241 | -0.11R (44% won) |
| Hammer, weekly below 10, SPY above 200-day | 3002 | -0.61% (t -6.1) | -0.86% (t -5.7) | -0.74% (t -3.6) | 1898 | -0.16R (42% won) |
| Hammer, weekly below 10, SPY below 200-day | 242 | +0.52% (t +2.4) | +1.56% (t +5.4) | +2.21% (t +4.1) | 162 | +0.09R (54% won) |
| Shooting star, any | 18881 | +0.18% (t +4.3) | +0.21% (t +3.7) | +0.24% (t +2.8) | 12082 | -0.08R (46% won) |
| Shooting star, weekly osc above 90 | 3054 | -0.03% (t -0.3) | -0.36% (t -2.4) | -0.26% (t -1.1) | 1888 | -0.12R (44% won) |
| Shooting star, daily AND weekly above 90 | 396 | -0.26% (t -0.8) | -0.70% (t -1.5) | -1.27% (t -1.9) | 252 | -0.18R (40% won) |
| Shooting star, weekly above 90, high volume | 296 | -0.46% (t -1.1) | -0.92% (t -1.8) | -0.55% (t -0.7) | 163 | -0.26R (37% won) |
| Shooting star, weekly above 90, SPY below 200-day | 91 | +0.23% (t +0.4) | -2.71% (t -2.5) | -5.64% (t -4.3) | 62 | -0.01R (50% won) |

### Weekly candles

| Candle | Count | +5 days | +10 days | +20 days | Triggered | Trade result |
|---|--:|--:|--:|--:|--:|--:|
| Hammer, any | 3580 | +0.12% (t +1.2) | +0.23% (t +1.6) | -0.39% (t -2.0) | 2561 | +0.05R (52% won) |
| Hammer, weekly osc below 10 | 644 | -0.28% (t -1.3) | -0.19% (t -0.6) | -0.62% (t -1.5) | 426 | +0.02R (50% won) |
| Hammer, daily AND weekly osc below 10 | 7 | +1.24% (t +0.8) | +1.86% (t +0.9) | +0.35% (t +0.1) | 6 | -0.25R (33% won) |
| Hammer, weekly osc below 10, high volume | 51 | +0.65% (t +0.6) | +0.80% (t +0.6) | -0.15% (t -0.1) | 36 | -0.13R (39% won) |
| Hammer, weekly below 10, SPY above 200-day | 596 | -0.53% (t -2.4) | -0.55% (t -1.8) | -1.14% (t -3.0) | 383 | -0.02R (48% won) |
| Hammer, weekly below 10, SPY below 200-day | 48 | +2.79% (t +3.9) | +4.29% (t +3.4) | +5.84% (t +2.1) | 43 | +0.34R (67% won) |
| Shooting star, any | 3832 | +0.34% (t +3.6) | +0.19% (t +1.5) | +0.04% (t +0.2) | 2490 | -0.06R (47% won) |
| Shooting star, weekly osc above 90 | 677 | -0.18% (t -0.9) | -0.04% (t -0.1) | -0.21% (t -0.5) | 372 | -0.05R (49% won) |
| Shooting star, daily AND weekly above 90 | 7 | -1.18% (t -0.7) | -1.08% (t -0.4) | +0.75% (t +0.1) | - | - |
| Shooting star, weekly above 90, high volume | 54 | -0.92% (t -1.0) | +0.73% (t +0.8) | +1.21% (t +0.7) | 19 | +0.11R (63% won) |
| Shooting star, weekly above 90, SPY below 200-day | 15 | +0.84% (t +0.3) | -3.73% (t -1.3) | -6.00% (t -2.5) | - | - |
