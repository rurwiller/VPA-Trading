# Trading overhaul, Nov 25 2026

## Why

Three weeks of paper trading and five years of backtests point the same way:

- **The candle scanner has no edge after costs.**
  - Backtest: about 29,000 pivot-candle trades lost 0.07 to 0.10R each after costs, in every market regime (reports/regime_test.md, reports/rs_test.md, reports/events_test.md).
  - Live: it lost money, about -$3,000 on Nov 25 alone.
  - Slippage is about -0.07R a trade (reports/journal.md).
- **The trend-day breakout is the only strategy that survived** the backtest, the six-month holdout and live trading (reports/breakout_symbols.md).

## What runs from Nov 27 (paper)

| Part | Setting | Evidence |
|---|---|---|
| Candle scanner | off, alerts off too (`--no-candles --alert-risk 0`) | no edge after costs |
| Trend-day breakout | TSLA + QQQ | backtest and holdout positive (reports/breakout_symbols.md) |
| Breakout sizing | by volatility: $1,700 of a typical day's move per trade, at most $150k (`--breakout-vol-budget 1700`) | TSLA + QQQ Sharpe 1.29 -> 1.51, worst day -$3,855 -> -$2,350 (reports/breakout_sizing.md) |
| Breakout exits | wait for Alpaca to confirm the cancels before exiting | Nov 25 QQQ exit rejected, short left with no stop |
| Daily loss stop | -$3,000 (the trend sleeve's daily swing is not counted) | fired correctly on Nov 25 |
| QQQ 200-day trend sleeve | $50,000 of QQQM held while QQQ closes above its 200-day average; checked 15 min before the close, market-on-close order, kept overnight (`--trend-qqq 50000`); added Nov 25 at the user's request | reports/daily_trend.md |

## Tested and not adopted

**Breakout as options** (reports/breakout_options.md; 1,344 trades since Feb 2024, priced with Alpaca option prices):

| Instrument | Result |
|---|---|
| Stock (equal risk) | +$19 a trade |
| Nearest expiry, at the money | -$21 a trade |
| ~1 week, in the money | -$26 a trade |
| ~2 weeks, at the money | -$27 a trade |

- In the holdout, nearest-expiry options made +$181 a trade over 201 trades. Before it, they lost $57 a trade over 1,123 trades. That's a few big days, not an edge.
- Verdict: stay with stock. If you trade the breakout in options yourself, use the nearest QQQ expiry. It came closest to breaking even.

**Daily trend rules on ETFs** (reports/daily_trend.md, 2017 to 2026):

- **QQQ above its 200-day average, otherwise cash:** Sharpe 0.96 against 0.85 for buy & hold, worst drop -22% against -36%, growth 16.1% a year against 18.5%. In 2022 it lost 17.8% against 33.2%.
- **The 15-ETF basket with the same rule:** worst drop -12% against -29%, but half the growth.
- **Correlation with the breakout:** about 0, so the two would not move together.
- **Recommendation:** a QQQ 200-day sleeve for money you would otherwise just hold. It is mainly a drawdown cutter, not a return booster. QQQ is below its 200-day now, so it would be in cash today.
- **Switched on (paper) on Nov 25** at your request; see the table above. It is judged on its own over months, not 60 days: it trades rarely.

## How it gets judged (fixed now, before the results)

- **The breakout runs unchanged for 60 trading days** (to about Feb 24, 2027). No mid-run tweaks; new ideas go to a list and are tested against the holdout once.
- **Expected:** the backtest says vol-sized TSLA + QQQ makes about +$80 a day on average, with swings of a few thousand dollars.
- **Kill rules:**
  - stop early if the drawdown from the high passes -$20,000 (1.5x the backtest's worst, -$13,169);
  - after 60 days, stop if the average day is below zero and more than 2 standard errors under the backtest average.
- **If it passes:** consider real money at a quarter of this size, with the same rules.
- **Daily report:** the end-of-day report, scorecard and journal keep running, so the record builds itself.

## Honest expectations

- The breakout's edge is modest: about a 1.5 Sharpe in backtests, which usually shrinks in live trading.
- If it fails its kill rules, the money is better in an index fund (or the QQQ 200-day sleeve).
