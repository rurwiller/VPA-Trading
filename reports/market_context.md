# Weekly video call (Nov 8, 2026) against the charts

Source: the transcript of the Sunday Nov 8 weekly call. Prices are Alpaca daily bars (SIP), checked after Monday Nov 9's close.
The daily table for any day comes from `python scripts/market_context.py`.

## His thesis for the week

- The market broke structure on Thursday Nov 5 (QQQ -6.5%, SPY -4.4%). Friday's bounce was a dead-cat bounce.
- Expect a relief rally early in the week, possibly a walk back up toward the 200-day SMA and the July lows, then a roll-over.
  Rallies stay suspect through year end. A weak, low-volume walk back up into the July lows is "not it".
- "Monday probably gaps up, pushes a little and fades."
- CPI Tuesday, PPI Friday. Chop for the rest of the year, volatility back January to March.
- Levels: QQQ first target around 630, put wall 600. TSLA: sell covered calls and buy puts at 370-380 (200-day), target 300-320.
  AMD: puts near 480. AAPL: needs to hold above 344, weak under 330. NVDA: oversold, wait for a bear-flag walk up to the 200-day.
  META rejected at the 200-day and daily 9 EMA. IWM a weak double bottom, RSP to flush below 215 toward its 200-day. Oil a double top.

## Monday Nov 9 against those calls

| Call | What happened | Verdict |
|---|---|---|
| Relief rally early in the week | QQQ +3.5%, SPY +2.4%, IWM +3.2%, almost everything up | Right |
| Monday gaps up and fades | Gapped up (QQQ +1.0%) and closed near the high (+2.5% from the open). Only GOOGL and AMZN faded | Wrong on the fade |
| QQQ walks up toward the 200-day / July lows | Back above the July low (661.14) and tagged the 200-day (681.17), closed just under it at 679.35, on 1.13x volume | Reached in one day, not a weak walk-up |
| TSLA up into 370-380 / the 200-day, then sell it | Closed 378.05, 200-day 383.51, volume 0.91x, +10% in two days | In his zone |
| NVDA "probably green" (contrarian) | -4.3% (gapped -7.3%, rallied +3.2% from the open), volume 3.9x, RSI 27 | Wrong |
| AMD back toward 480 to buy puts | +13.3% to 508.58 (high 515), volume 1.86x | Went through it |
| AAPL needs to get back over 344 | Closed 350.69 | Above it |
| META rejected at its 200-day | Reclaimed it (641.37 vs 631.85) on light volume (0.76x) | Not yet |
| GOOGL bear flag / dead cat | Gapped up and faded, rejected at the daily 9 EMA, below a falling 200-day | Consistent |
| IWM / RSP lower | IWM +3.2% and back above its 200-day, RSP 220.95 | Not yet |
| Oil double top | USO -3.9% | Consistent |

One day says little either way; his setups play out over weeks.

## What 10 years of daily data say about his main ideas

18 tickers (the Mag 7, QQQ, SPY, IWM, RSP, SMH, MAGS, AMD, MU, PLTR, HOOD, USO), Nov 2016 to Nov 2026. Returns are the stock's,
so a negative number is what a short would have made.

**After a big index down day (QQQ -4% or worse), does price make a lower low within 20 trading days?** 15 of 16 completed cases
did (2018-2026). The bounces were often large (average next-day +0.6%), but the low rarely held. That supports "dead-cat bounce,
then a retest", without saying when.

**Selling a rally into a falling 200-day.**

| Situation | Count | Next day | 5 days | 20 days |
|---|--:|--:|--:|--:|
| Any day under a falling 200-day (baseline) | 7,899 | | +0.65% (44% down) | +2.53% (42% down) |
| A rally tags the 200-day from below | 222 | | +0.42% (49% down) | +1.61% (45% down) |
| Rallied 6%+ off its 5-day low into the 200-day | 147 | -0.34% (53% down) | -0.07% (48% down) | +1.71% (48% down) |
| ... on below-average volume | 52 | +0.09% | +0.82% (37% down) | +1.34% |
| ... on above-average volume | 95 | -0.58% | -0.56% (54% down) | +1.91% |

- The 200-day does act as resistance: stocks that tag it from below do worse afterward than the baseline.
- But they still rose on average, so shorting there was close to a coin flip. A sharp rally into it fades a little the next day
  (about -0.3%) and nothing after a week.
- A light-volume walk-up was **not** weaker afterward. It did slightly better than a high-volume rally. The volume tell he uses
  doesn't show up in these daily numbers.
- His monthly trendline since 2009 can't be checked here: Alpaca's history starts in 2016.

## How we use it

- `scripts/market_context.py` prints the table and plain-English flags for the watchlist: trend vs the 200-day, tests and
  rejections of the 200-day, the July lows, light- or heavy-volume days, gap-and-fade, rejections at the daily 9 EMA, RSI.
- These are context for your own calls and the call log, not a filter. The tests above say none of them would improve the
  scanner on their own.
