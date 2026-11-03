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
from vpa_trading.data import fetch_yahoo, load_yahoo_file  # noqa: E402


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
    days = sorted(set(df.index.date))
    n_run = 0
    for day in days:
        t_dec = pd.Timestamp.combine(day, pd.Timestamp(args.at).time())
        hist = df[df.index < t_dec]           # bars that started before the decision
        fut = df[(df.index >= t_dec) & (df.index.date == day)]
        if len(hist) < args.lookback or len(fut) < 6 or str(t_dec) in done:
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
                                n_paths=args.paths, seed=args.seed)
        secs = time.time() - t0
        cone = kp.cone(paths, fut.index.to_series())
        real_close = float(fut.close.iloc[-1])
        rows = []
        for side, sgn in (("long", 1), ("short", -1)):
            stop = entry - sgn * args.k * a
            target = entry + sgn * args.rr * args.k * a
            m = kp.race(paths, entry, stop, target)
            outcome, r = real_outcome(fut, entry, stop, target)
            cost_r = (args.cost_bps / 1e4 * entry) / abs(entry - stop)
            rows.append(dict(
                decision_time=str(t_dec), side=side, entry=entry, stop=stop, target=target,
                atr=a, bars_ahead=len(fut), paths=m.n, p_target=m.p_target,
                p_stop=m.stop_first / m.n, p_neither=m.neither / m.n,
                p_target_resolved=m.p_target_resolved, random_walk=m.random_walk_target_first,
                model_exp_r=m.expected_r(), real_outcome=outcome, real_r=r, cost_r=cost_r,
                p10=cone.p10.iloc[-1], p50=cone.p50.iloc[-1], p90=cone.p90.iloc[-1],
                real_close=real_close, secs=secs))
        pd.DataFrame(rows).to_csv(out, mode="a", header=not out.exists(), index=False)
        print(f"{t_dec}  {secs:5.0f}s  long p_t={rows[0]['p_target']:.2f} real={rows[0]['real_outcome']:7}"
              f"  short p_t={rows[1]['p_target']:.2f} real={rows[1]['real_outcome']}", flush=True)
    return pd.read_csv(out)


def report(res: pd.DataFrame, threshold: float) -> None:
    n_dec = res.decision_time.nunique()
    print(f"\n=== {n_dec} decisions x 2 sides = {len(res)} trades ===")
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
    if 0 < len(sel) < 30:
        print("  (fewer than 30 filtered trades: too few to conclude anything)")

    cov = ((res.real_close >= res.p10) & (res.real_close <= res.p90))[res.side == "long"].mean()
    print(f"\nCone coverage: real close inside p10-p90 on {cov:.0%} of days (well calibrated ~80%)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="saved Yahoo chart JSON (.json or .json.gz)")
    ap.add_argument("--symbol")
    ap.add_argument("--at", default="10:15", help="decision time, New York")
    ap.add_argument("--lookback", type=int, default=256, help="bars of context (<=512)")
    ap.add_argument("--paths", type=int, default=30)
    ap.add_argument("--k", type=float, default=1.5, help="stop distance in ATRs")
    ap.add_argument("--rr", type=float, default=2.0, help="target as a multiple of risk")
    ap.add_argument("--cost-bps", type=float, default=2.0, help="round-trip fees+slippage, bps of price")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--device")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", help="results CSV (default results/<name>.csv)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N new decisions (0 = all)")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    name = args.symbol or Path(args.file).name.split(".")[0]
    args.out = args.out or f"results/{name}_{args.at.replace(':', '')}_k{args.k}_rr{args.rr}.csv"
    Path(args.out).parent.mkdir(exist_ok=True)
    if args.report_only:
        report(pd.read_csv(args.out), args.threshold)
        return
    df = load_yahoo_file(args.file) if args.file else fetch_yahoo(args.symbol)
    report(run(df, args), args.threshold)


if __name__ == "__main__":
    main()
