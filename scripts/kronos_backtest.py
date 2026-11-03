"""Does Kronos know anything? Score its path race against what really happened.

For each trading day, at a fixed decision time (default 10:15 New York):
  entry  = last closed bar's close
  long:  stop = entry - k*ATR, target = entry + rr*k*ATR   (short mirrored)
  horizon = every remaining bar of the session (flat at the close)
Kronos samples N paths from the prior `lookback` bars only (no peeking), and we
race them to the levels. Then the real bars are raced the same way.

Writes one CSV row per decision (resumable: finished decisions are skipped),
then prints:
  * calibration: predicted target-first share vs the real hit rate
  * a filter test: realized R of all trades vs only the ones Kronos favoured
  * cone coverage: how often the real close at the horizon fell inside p10-p90

Usage:
  python scripts/kronos_backtest.py data/TSLA-60d5m.json.gz --paths 30
  python scripts/kronos_backtest.py --symbol AAPL --paths 30      # needs Yahoo access
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import kronos_paths as kp  # noqa: E402
from vpa_trading.data import fetch_yahoo, load_yahoo_file, resample_bars  # noqa: E402


def real_outcome(bars: pd.DataFrame, entry: float, stop: float, target: float) -> tuple[str, float]:
    """Race the real bars; return (outcome, realized R). Same-bar touch = stop."""
    r = abs(entry - stop)
    long = target > entry
    for _, b in bars.iterrows():
        hit_s = b.low <= stop if long else b.high >= stop
        hit_t = b.high >= target if long else b.low <= target
        if hit_s:
            return "stop", -1.0
        if hit_t:
            return "target", abs(target - entry) / r
    last = bars.close.iloc[-1]
    return "neither", ((last - entry) if long else (entry - last)) / r


def run(df: pd.DataFrame, args) -> pd.DataFrame:
    from vpa_trading.kronos_loader import load_kronos_small

    out = Path(args.out)
    done = set(pd.read_csv(out)["decision_time"]) if out.exists() else set()
    predictor = None
    rsi_s = rsi(df.close, args.rsi_len)
    bar = df.index.to_series().diff().mode().iloc[0]
    n_run = 0
    for t_dec, sides in decisions(df, rsi_s, bar, args):
        day = t_dec.date()
        hist = df[df.index < t_dec]           # bars that started before the decision
        fut = df[(df.index >= t_dec) & (df.index.date == day)]
        if len(hist) < args.lookback or len(fut) < 2 or str(t_dec) in done:
            continue
        if hist.index[-1].date() != day:      # no bars yet today (late/missing data)
            continue
        x = hist.iloc[-args.lookback:]
        entry, a = float(x.close.iloc[-1]), kp.atr(x)
        if args.limit and n_run >= args.limit:
            break
        n_run += 1
        if predictor is None:
            predictor = load_kronos_small(device=args.device, max_context=args.lookback)
        t0 = time.time()
        paths = kp.sample_paths(predictor, x, x.index.to_series(), fut.index.to_series(),
                                n_paths=args.paths, T=args.temperature, top_p=args.top_p, seed=args.seed)
        secs = time.time() - t0
        cone = kp.cone(paths, fut.index.to_series())
        real_close = float(fut.close.iloc[-1])
        rows = []
        for side in sides:
            sgn = 1 if side == "long" else -1
            stop = entry - sgn * args.k * a
            target = entry + sgn * args.rr * args.k * a
            m = kp.race(paths, entry, stop, target)
            outcome, r = real_outcome(fut, entry, stop, target)
            # The RSI strategy's own exit (RSI back above exit level, else the close), no stop.
            rule_r = float("nan")
            if args.entry == "rsi":
                ex = rsi_s.reindex(fut.index) > args.rsi_exit
                px = fut.close[ex].iloc[0] if ex.any() else fut.close.iloc[-1]
                rule_r = (px - entry) / abs(entry - stop)
            cost_r = (args.cost_bps / 1e4 * entry) / abs(entry - stop)
            rows.append(dict(
                decision_time=str(t_dec), side=side, entry=entry, stop=stop, target=target,
                atr=a, bars_ahead=len(fut), paths=m.n, p_target=m.p_target,
                p_stop=m.stop_first / m.n, p_neither=m.neither / m.n,
                p_target_resolved=m.p_target_resolved, random_walk=m.random_walk_target_first,
                model_exp_r=m.expected_r(), real_outcome=outcome, real_r=r, rule_r=rule_r,
                rsi=float(rsi_s.loc[x.index[-1]]), cost_r=cost_r,
                p10=cone.p10.iloc[-1], p50=cone.p50.iloc[-1], p90=cone.p90.iloc[-1],
                real_close=real_close, secs=secs))
        pd.DataFrame(rows).to_csv(out, mode="a", header=not out.exists(), index=False)
        print(f"{t_dec}  {secs:5.0f}s  " + "  ".join(
            f"{w['side']} p_t={w['p_target']:.2f} real={w['real_outcome']:7}" for w in rows), flush=True)
    return pd.read_csv(out)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI on the continuous bar series (carries across sessions)."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn)


def decisions(df: pd.DataFrame, rsi_s: pd.Series, bar: pd.Timedelta, args):
    """Yield (decision_time, sides). A decision is made when a bar has closed."""
    days = sorted(set(df.index.date))
    if args.entry == "time":
        for day in days:
            yield pd.Timestamp.combine(day, pd.Timestamp(args.at).time()), ("long", "short")
        return
    # rsi: first close of the day that crosses below the entry level, long only,
    # inside the entry window. One trade per day, flat at the close.
    lo, hi = pd.Timestamp(args.window[0]).time(), pd.Timestamp(args.window[1]).time()
    cross = (rsi_s < args.rsi_entry) & (rsi_s.shift() >= args.rsi_entry)
    for day in days:
        for t in cross[cross & (cross.index.date == day)].index:
            t_dec = t + bar
            if lo <= t_dec.time() <= hi:
                yield t_dec, ("long",)
                break


def report(res: pd.DataFrame, threshold: float) -> None:
    n_dec = res.decision_time.nunique()
    print(f"\n=== {n_dec} decisions, {len(res)} trades ({', '.join(sorted(res.side.unique()))}) ===")
    res = res.assign(hit=(res.real_outcome == "target").astype(float),
                     net_r=res.real_r - res.cost_r)

    print("\nCalibration (Kronos share of paths hitting target first vs reality):")
    bins = pd.cut(res.p_target, [0, .2, .35, .5, .65, 1.0], include_lowest=True)
    cal = res.groupby(bins, observed=True).agg(trades=("hit", "size"), predicted=("p_target", "mean"),
                                              real_hit_rate=("hit", "mean"))
    print(cal.round(3).to_string())
    brier_k = ((res.p_target - res.hit) ** 2).mean()
    base = res.hit.mean()  # in-sample base rate: a generous baseline for the comparison
    brier_b = ((base - res.hit) ** 2).mean()
    print(f"Brier score: Kronos {brier_k:.4f}  vs constant base rate {brier_b:.4f}"
          f"  ({'Kronos better' if brier_k < brier_b else 'Kronos NOT better'}; lower is better)")

    print(f"\nFilter test (take a side only if Kronos p_target_resolved >= {threshold:.0%}):")
    sel = res[res.p_target_resolved >= threshold]
    for name, s in (("all trades", res), ("Kronos-filtered", sel), ("rejected", res.drop(sel.index))):
        if len(s):
            print(f"  {name:16} n={len(s):3}  hit {s.hit.mean():5.1%}  avg R {s.real_r.mean():+.3f}"
                  f"  after costs {s.net_r.mean():+.3f}")
    if "rule_r" in res and res.rule_r.notna().any():
        print("  RSI rule's own exit (RSI > exit level, else the close; no stop), before costs:")
        for name, s in (("all trades", res), ("Kronos-filtered", sel), ("rejected", res.drop(sel.index))):
            if len(s):
                print(f"  {name:16} n={len(s):3}  win {(s.rule_r > 0).mean():5.1%}  avg R {s.rule_r.mean():+.3f}")
    if 0 < len(sel) < 30:
        print("  (fewer than 30 filtered trades: too few to conclude anything)")

    d = res.drop_duplicates("decision_time")
    cov = ((d.real_close >= d.p10) & (d.real_close <= d.p90)).mean()
    print(f"\nCone coverage: real close inside p10-p90 on {cov:.0%} of decisions (well calibrated ~80%)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="saved Yahoo chart JSON (.json or .json.gz)")
    ap.add_argument("--symbol")
    ap.add_argument("--interval", default="5m", help="bar size: 5m, 15m, 30m, 1h (resampled from the file)")
    ap.add_argument("--entry", choices=["time", "rsi"], default="time",
                    help="time: both sides at --at each day; rsi: long on RSI crossing below --rsi-entry")
    ap.add_argument("--at", default="10:15", help="decision time, New York (entry=time)")
    ap.add_argument("--rsi-len", type=int, default=14)
    ap.add_argument("--rsi-entry", type=float, default=35)
    ap.add_argument("--rsi-exit", type=float, default=55)
    ap.add_argument("--window", nargs=2, default=["09:45", "15:30"], help="entry window (entry=rsi)")
    ap.add_argument("--lookback", type=int, default=256, help="bars of context (<=512)")
    ap.add_argument("--paths", type=int, default=30)
    ap.add_argument("--k", type=float, default=1.5, help="stop distance in ATRs")
    ap.add_argument("--rr", type=float, default=2.0, help="target as a multiple of risk")
    ap.add_argument("--cost-bps", type=float, default=2.0, help="round-trip fees+slippage, bps of price")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--top-p", type=float, default=0.9, help="nucleus sampling; <1 trims tail moves")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--device")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", help="results CSV (default results/<name>.csv)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N new decisions (0 = all)")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    name = args.symbol or Path(args.file).name.split(".")[0]
    samp = "" if (args.top_p, args.temperature) == (0.9, 1.0) else f"_p{args.top_p}_T{args.temperature}"
    rule = args.at.replace(":", "") if args.entry == "time" else f"rsi{args.rsi_len}-{args.rsi_entry:g}-{args.rsi_exit:g}"
    iv = "" if args.interval == "5m" else f"_{args.interval}"
    args.out = args.out or f"results/{name}{iv}_{rule}_k{args.k}_rr{args.rr}{samp}.csv"
    Path(args.out).parent.mkdir(exist_ok=True)
    if args.report_only:
        report(pd.read_csv(args.out), args.threshold)
        return
    df = load_yahoo_file(args.file) if args.file else fetch_yahoo(args.symbol)
    if args.interval != "5m":
        df = resample_bars(df, args.interval)
    report(run(df, args), args.threshold)


if __name__ == "__main__":
    main()
