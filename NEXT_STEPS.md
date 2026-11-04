# Where this left off (2026-11-03)

Goal: a tool that helps with better entries on **US stocks, day trading**, using
TradingView as the chart, Kronos forecasts and the user's own
**Willard 3.0 Hybrid Oscillator**. The user's chart is in **MST** (New York time
minus 2 hours; the open is 7:30 MST).

## What exists

- `vpa_trading/kronos_loader.py`: loads Kronos-small + tokenizer from Hugging Face.
- `vpa_trading/kronos_paths.py`: sample many Kronos paths, race them to stop/target,
  random-walk baseline, p10/p50/p90 cone.
- `vpa_trading/willard_osc.py`: Python port of the oscillator core (Pine `f_hybrid`).
- `vpa_trading/data.py`: Yahoo loader, session resampling (15m, 30m, 1h bins start 9:30).
- `scripts/kronos_backtest.py`: entry rules `time` (10:15), `rsi`, `osc`
  (`--osc-mode flip|touch`, `--trend-ema`), Kronos optional (`--paths 0` = rule only,
  runs in seconds). Resumable: finished decisions in the CSV are skipped.
- `scripts/kronos_report.py`: pools result CSVs across tickers.
- `results/`: CSVs from every run below.

## Findings so far (60 days of 5m bars, Aug-Nov 2026)

| Test | Result |
|---|---|
| Kronos, 5m bars, TSLA, 15 days | forecasts biased down; p10-p90 band held the real close only 33-40% of days; not better than a constant guess |
| Kronos, 15m bars, TSLA 10:15 rule, 50 days | band coverage 76% (much better), but hit-rate calls still worse than a constant guess (Brier 0.165 vs 0.120); filter -0.07R vs -0.10R, within noise |
| Oscillator 15m flip at 12/88, 7 tickers, no Kronos | 1,168 trades, 58% win, -0.03 +/- 0.04 R after 2 bps costs |
| Same, touch | -0.01 +/- 0.05 R |
| Same, with-trend only (EMA20/50) | -0.03 +/- 0.05 R |

Nothing so far shows an edge after costs. None of it is a verdict on the user's full
multi-timeframe setup, which has not been tested yet.

## Alpaca data and multi-timeframe rule (done 2026-11-03)

- Keys work (paper account ACTIVE, SIP history readable). `vpa_trading/alpaca.py` +
  `scripts/alpaca_pull.py` pull 1m SIP bars (split-adjusted, regular session, NY time) to
  `data/alpaca/<SYM>-1m.csv.gz` (gitignored, re-pull in ~1 min). Year pulled:
  2025-11-03..2026-11-02, 251 sessions, 7 tickers, ~97.8k bars each (390/day).
- Volume check vs Yahoo (TSLA 5m, 4,618 overlapping bars): identical on ~99% of bars; the
  differences are Yahoo's bogus prints (up to 100x). Alpaca volume is clean.
- `vpa_trading/mtf.py` + `scripts/mtf_backtest.py`: 1h (closed bars only) + 5m oscillator rule.
  Both low -> long, both high -> short; trigger `immediate` (first bar aligned) or `flip`
  (5m turns out of its zone while 1h is still extreme). ATR stop/target race (1.5 ATR, 2R) and
  oscillator-midline exit, 2 bps costs. `--grid` sweeps levels and shows first vs second half.

| Test (7 tickers, 1 year, 1h+5m) | Result |
|---|---|
| immediate, 1h <=20/>=80, 5m <=10/>=90, 3,549 trades | race -0.04 +/- 0.04 R; midline exit -0.08 +/- 0.03 R |
| flip, 1h 20, 5m 12, 3,834 trades | race -0.03 +/- 0.04 R; midline exit -0.09 +/- 0.03 R |
| 32-cell grid (trigger x 1h level x 5m level) | no cell positive in the second half; best first-half cell (+0.009 R) is -0.089 in the second |

No edge after costs. The 1h+5m agreement does not rescue the oscillator as an entry on its
own. Untested: the 3m/1m trigger, other timeframe pairs (15m+5m, 1h+15m), exits other than
ATR/midline, using the extreme as a *filter/avoid* signal, per-ticker results, time-of-day.

## Research grid, 5 years (done 2026-11-04) -> `reports/research.md`

Data: 1m SIP bars incl. extended hours, 2021-11-05..2026-11-03, 1,253 sessions x 7 tickers
(`data/alpaca/<SYM>-1m-ext.csv.gz`, `python scripts/alpaca_pull.py --years 5 --extended`).
Run: `python scripts/research_run.py` (~1 min) then `python scripts/research_report.py`.
Discovery = before 2024-11-01, holdout = after. 1.6M scored trades, 4,885 discovery cells.

Families: osc stacks (1h+30m+15m+5m, 1h+15m+9m+5m, 15m+9m+5m, 1h+15m+5m, 1h+5m; levels
10-30; with/without 3m trigger), rejection candle at osc extreme, VPA climaxes, FVG touches;
each as fade and continuation, split by ADX(14) band/slope, DI, time of day, VWAP distance,
9/21 EMA, RVOL, nearby FVG, ticker. Exits 5/15/60 min, +0.5%/-0.3%, 2R/1.5 ATR(5m), 2 bps cost.

Findings:
- No setup is positive after costs in both periods. The 25 best discovery cells all fall to
  ~0 or below on the holdout (classic selection luck).
- Osc stacks: continuation beat fade in discovery, fade beat continuation in holdout: no
  stable direction. "ADX decides" (fade < X, ride >= X with DI) did not help at any X.
- Inverted hammer / hammer at an osc extreme (5m, 15m): no edge either way.
- FVG: bounce beats break-through in both periods on 5m/15m/1h (1h bounce up after 15 min
  51-54% of the time) but only ~1-3 bps gross, less than costs with a market entry at the touch.
- 15m climax (rvol >= 3, wick >= 0.4) *continuation* (trade in the climax bar's direction):
  positive in both halves (n=201 each, +0.04/+0.09 R, 15-min win 57%/53%), but within noise
  and r60 flips sign. Watch-list only.
- Stops: trades that are up after 60 min rarely went more than ~1.5 ATR(5m) against first
  (median 0.6, 80th pct ~1.2, 90th pct ~1.5-1.6); losers' median is ~2 ATR. A ~1.5 ATR(5m)
  stop keeps ~90% of eventual winners.

Ideas not yet tested: limit entries at the FVG edge (instead of market at the touch);
targets scaled per ticker (0.5% is far for SPY/QQQ in an hour); Coulling rules from the
user's notes (no demand / no supply, stopping volume, tests, upthrusts); levels (prior-day
H/L, premarket H/L, opening range) as event families; the levels / FVG Pine indicator.

## Known data problem: Yahoo volume spikes

Yahoo's 5m bars contain bogus volume prints (23 of 4,680 TSLA bars at 8-110x the
local median; e.g. 20M shares at 15:35 ET on 2026-11-03). They distort the
oscillator's VWAP z-score (weight 6 of 9.5). Capping volume at 8x the 25-bar median
made the port match the user's TradingView value on that bar (43.1 vs chart 44.49;
uncapped 65.8). The oscillator results above used **uncapped** Yahoo volume, so they
should be re-run on clean data.

## Next steps (items 1-2 and the 1h+5m part of 4 are done)

1. Check `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` against the paper account.
2. Add an Alpaca bars loader (`/v2/stocks/{sym}/bars`, `feed=sip`; the free plan can
   read SIP history older than 15 minutes). Pull at least a year of **1-minute** bars
   for TSLA, SPY, QQQ, AAPL, NVDA, AMD, META. Compare volume with Yahoo's.
3. Re-run the single-timeframe 15m oscillator rules on Alpaca data (clean volume, 1 year).
4. Build the **multi-timeframe oscillator rule** the user asked for: enter when the
   oscillator on several timeframes is at an extreme together, e.g. 1h and 5m both
   elevated -> short, both low -> long. Higher timeframes must use **closed** bars only
   (the indicator's "Confirmed" mode). Options: timeframes and touch levels
   (indicator defaults: 5m 5, 9m 10, 15m 12, 1m 3), alignment window, trigger =
   immediate or a flip on the fastest timeframe. Then add the 3m/1m trigger.
5. Run Kronos as a filter only on whatever rule shows a real edge (Kronos is slow:
   about 25-70 s per decision on this CPU).
6. Then build the entry screen: chart with the cone and race, paper orders on Alpaca
   with protective orders that do not expire.

Ask the user for: their indicator settings if changed from defaults, and a few
oscillator values from the TradingView Data Window to keep checking the port.
