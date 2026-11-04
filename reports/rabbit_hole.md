# Where an edge could still be: the rabbit hole (2026-11-04)

## What 30 tests say

Every candle / oscillator / level / gap / pivot / Fibonacci / divergence / zone rule on the Mag 7 intraday is
within about 1-3 bps of zero **before costs**, and the sign flips between 2021-24 and 2024-26. Flipping a rule
gives the mirror image (also ~0). So the problem is not the cost model or the exit: there is no directional
information in these patterns on the most liquid stocks in the world at the 2-15 minute scale. Adding more rules
of the same kind will keep finding things that look good on one period and fail on the next.

So the search moved to ideas where (a) the move per trade is large next to costs (fewer, bigger trades) and
(b) there is a published, economic reason for the effect.

## Test 1: market intraday momentum (Gao, Han, Li, Zhou 2018; Baltussen et al. 2021)

Trade 15:30 -> 16:00 in the direction of the day so far. The mechanism offered in the papers is dealer
gamma hedging and late-day rebalancing.

| Mag7+ (10 tickers) | before Nov 2024 | after |
|---|---|---|
| day so far -> last 30 min, gross | +1.3 bps/day | -1.8 |
| net of costs | -0.7 | -3.9 |
| only the biggest third of days | +1.0 | -5.4 |

Dead on these tickers since 2023 (by year: +5.2, +0.9, -1.8, -1.7, -4.8, -4.1 bps).

## Test 2: noise-area breakout (Zarattini, Aziz, Barbon 2024, "Beat the market")

Band = average absolute move from the open at that minute over the last 14 days; long above it, short
below, checked every 30 minutes, exit at band / VWAP or the close. About one trade on 60% of days.

| Mag7+ | before Nov 2024 | after |
|---|---|---|
| every day, net | +4.3 bps/day (Sharpe 0.70) | -0.3 (Sharpe -0.05) |
| by year | 2021 +21, 2022 +8.6, 2023 +2.4 | 2024 -0.7, 2025 -1.2, 2026 +1.2 |

Parameter sweep (72 settings: lookback 7/14/28, band 0.75-1.5x, checks every 15/30/60 min, with/without VWAP
stop), averaged over the 10 tickers: 100% of settings positive before Nov 2024, 25% after, and the correlation
between a setting's early and late result is **-0.41** (the settings that looked best early did worst later).
Splitting by volatility regime (own or SPY 20-day range vs its 1-year median) does not rescue the late period.
Classic decay after publication / crowding.

The one exception is **TSLA** (also AMD): positive in both periods for 94% of the 72 settings; TSLA averages
+13 bps/day before and +4.6 after, Sharpe 1.7 then 0.5. The noise band on that holdout is about +-12 bps/day,
so it is not proven; it is the only mechanical result in this whole project that kept the same sign.

## What this means for how to do it

1. **Stop adding candle rules.** The evidence is consistent and large-sample: no edge on Mag 7 intraday patterns.
2. **The live candidate worth paper trading is TSLA (and AMD, QQQ) trend-day breakout**: one trade a day at most,
   big average move, cheap to monitor. Treat it as an experiment, not a strategy.
3. **Costs decide everything at these edge sizes, and options are the expensive way to trade them.** A TSLA
   weekly near the money costs ~16 cents a round trip at ~0.5 delta, about 8 bps of the stock, three times the
   stock's spread. An edge of +4 bps/day in the stock is negative in options at market. If trading options: limit
   orders at the mid, the tightest strikes, or SPY / QQQ, where spreads are a penny.
4. **The most likely real edge is the user's own selection**: context we cannot code (what the tape looks like,
   when to sit out). `data/my_calls.csv` + `scripts/compare_calls.py` measure it. ~50-100 calls are needed
   before a win rate means anything.
5. **Dealer gamma is the published explanation for intraday momentum** (Baltussen et al.): momentum into the close
   should exist when dealers are short gamma and vanish when they are long. That could explain why it died in a
   high-gamma market. We have no gamma history to test it, but the scanner now logs our GEX levels every 30 min,
   so in a few months this can be checked going forward.

Scripts: `scripts/intraday_momentum_test.py` (both tests, `reports/intraday_momentum.md`).
