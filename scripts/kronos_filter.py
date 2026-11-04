"""Kronos as a filter on existing signals: does its forecast separate the winners from the losers?

For each sampled signal (pivot star-break entries, 2-candle price-pivot RSI divergences), Kronos-small reads the
last LOOKBACK 15-minute candles closed before the entry and samples PATHS futures of PRED 15-minute candles
(2 hours). We race those paths to the trade's own levels (stop just beyond the pivot extreme, 2R target) and
record p_target = share of resolved paths that hit the target first (a random walk gives 1/3), plus p_dir =
share of paths ending in the trade's favour. Only signals from SINCE onward are used, after Kronos's training data.
Resumable: decisions already in the CSV are skipped.

  python scripts/kronos_filter.py --n 300            -> results/kronos_filter.csv
  python scripts/kronos_filter.py --report           -> reports/kronos_filter.md
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import kronos_paths as kp  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
from vpa_trading.data import resample_bars  # noqa: E402
from midcap_test import MID, cost_bps  # noqa: E402

OUT = Path("results/kronos_filter.csv")
SINCE = pd.Timestamp("2025-11-01")
LOOKBACK, PRED, PATHS = 256, 8, 30


def signals(n: int, seed: int = 7) -> pd.DataFrame:
    rows = []
    for fam, d, cond, out in (("star_break", Path("results/pivots"), lambda e: e.event == "star_break", "st"),
                              ("rsi_div_k2", Path("results/rsi_div"), lambda e: e.event == "price_k2", "st60")):
        for p in sorted(d.glob("*.pkl")):
            e = pd.read_pickle(p)
            e = e[(e["mode"] == "with") & cond(e) & (e.time >= SINCE)]
            win = e["st_win"] if out == "st" else e["st60_win"]
            pct = e["st_gross_pct"] if out == "st" else e["st60_pct"]
            risk = e["st_risk_pct"] if out == "st" else e["risk_pct"]
            rows.append(pd.DataFrame({"family": fam, "sym": e.sym, "time": e.time, "tf": e.tf, "i": e.i,
                                      "dir": e.dir, "entry": e.entry, "ext": e.ext, "r60_net2": e.r60,
                                      "st_win": win, "st_pct": pct, "risk_pct": risk}))
    s = pd.concat(rows, ignore_index=True)
    # equal numbers per family, spread across tickers and time
    picks = [g.sample(min(n // 2, len(g)), random_state=seed) for _, g in s.groupby("family")]
    return pd.concat(picks).sort_values(["sym", "time"]).reset_index(drop=True)


def run(args) -> None:
    from vpa_trading.kronos_loader import load_kronos_small
    sig = signals(args.n)
    done = set()
    if OUT.exists():
        prev = pd.read_csv(OUT)
        done = set(zip(prev.family, prev.sym, prev.time.astype(str)))
    predictor = load_kronos_small(device="cpu", max_context=512)
    cache = {}
    t_all = time.time()
    for k, r in sig.iterrows():
        key = (r.family, r.sym, str(r.time))
        if key in done:
            continue
        if r.sym not in cache:
            cache.clear()
            m1 = load_bars_file(Path("data/alpaca") / f"{r.sym}-1m-ext.csv.gz")
            b = resample_bars(m1, "15m")
            cache[r.sym] = (m1, b)
        m1, b = cache[r.sym]
        clock = m1.index[int(r.i)] + pd.Timedelta(minutes=1)
        closed = b[b.index + pd.Timedelta(minutes=15) <= clock]
        x = closed.iloc[-LOOKBACK:]
        if len(x) < LOOKBACK:
            continue
        y_ts = kp.us_session_bars(x.index[-1], PRED, "15min")
        t0 = time.time()
        paths = kp.sample_paths(predictor, x[["open", "high", "low", "close", "volume"]], x.index.to_series(), y_ts,
                                n_paths=PATHS, T=1.0, top_p=0.9, batch_size=PATHS, seed=k)
        e = float(r.entry)
        risk = max(abs(r.ext - e) + 0.0002 * e, 0.0005 * e)
        stop, target = (e - risk, e + 2 * risk) if r.dir > 0 else (e + risk, e - 2 * risk)
        m = kp.race(paths, e, stop, target)
        fin = paths[:, -1, kp.C]
        mid = paths[:, min(3, PRED - 1), kp.C]
        row = dict(family=r.family, sym=r.sym, time=str(r.time), tf=r.tf, dir=int(r.dir), entry=e,
                   p_target=m.p_target_resolved, p_target_all=m.p_target, neither=m.neither / m.n,
                   p_dir_1h=float(((mid - e) * r.dir > 0).mean()), p_dir_2h=float(((fin - e) * r.dir > 0).mean()),
                   exp_move_2h_pct=float(np.median((fin - e) * r.dir) / e * 100),
                   r60_net2=r.r60_net2, st_win=bool(r.st_win), st_pct=r.st_pct, risk_pct=r.risk_pct,
                   secs=round(time.time() - t0, 1))
        pd.DataFrame([row]).to_csv(OUT, mode="a", header=not OUT.exists(), index=False)
        print(f"{r.family:10} {r.sym:5} {r.time}  p_t={row['p_target']:.2f} p_dir2h={row['p_dir_2h']:.2f} "
              f"real={'WIN ' if r.st_win else 'loss'}  {row['secs']}s", flush=True)
    print(f"done in {time.time() - t_all:.0f}s")


def report() -> None:
    t = pd.read_csv(OUT)
    t["cost"] = t.sym.map(cost_bps)
    t["r60"] = t.r60_net2 + 2 - t.cost                       # bps after each ticker's own cost
    t["R"] = (t.st_pct - t.cost / 100) / t.risk_pct          # structure race result in R after cost
    t["universe"] = np.where(t.sym.isin(MID), "mid-cap", "Mag7+")

    def summ(g):
        return pd.Series({"n": len(g), "win%": round(g.st_win.mean() * 100, 1), "R": round(g.R.mean(), 3),
                          "R_2se": round(2 * g.R.std() / np.sqrt(len(g)), 3) if len(g) > 1 else np.nan,
                          "r60 bps": round(g.r60.mean(), 1), "p_target": round(g.p_target.mean(), 3)})

    L = ["# Kronos as a filter on existing signals\n",
         f"{len(t)} signals since {SINCE:%Y-%m-%d} (after Kronos's training data), {', '.join(sorted(t.family.unique()))}. "
         f"Kronos-small, {PATHS} paths of {PRED} x 15-min candles from {LOOKBACK} candles of context. "
         "R = structure stop / 2R target result after each ticker's cost; win% = target before stop; "
         "p_target = Kronos's share of resolved paths hitting the target (random walk = 0.333).\n",
         "## All signals\n", t.groupby("family").apply(summ, include_groups=False).to_markdown()]
    for col, cuts in (("p_target", [0, 0.25, 0.333, 0.45, 1.0]), ("p_dir_2h", [0, 0.4, 0.5, 0.6, 1.0])):
        t[f"{col}_band"] = pd.cut(t[col], cuts, include_lowest=True).astype(str)
        L.append(f"\n## By Kronos {col}\n")
        L.append(t.groupby([f"{col}_band"]).apply(summ, include_groups=False).to_markdown())
        L.append(t.groupby(["family", f"{col}_band"]).apply(summ, include_groups=False).to_markdown())
    keep = t.p_target >= 1 / 3
    L.append("\n## Filter: keep only signals Kronos rates at least as well as a random walk (p_target >= 0.333)\n")
    L.append(pd.DataFrame({"kept": summ(t[keep]), "rejected": summ(t[~keep]), "all": summ(t)}).T.to_markdown())
    corr = t[["p_target", "p_dir_1h", "p_dir_2h", "exp_move_2h_pct"]].corrwith(t.R, method="spearman")
    L.append("\n## Rank correlation of each Kronos score with the real result (R)\n")
    L.append(corr.round(3).to_frame("spearman vs R").to_markdown())
    L.append(f"\nAverage {t.secs.mean():.1f} s per signal on this CPU.")
    Path("reports/kronos_filter.md").write_text("\n".join(L) + "\n")
    print("wrote reports/kronos_filter.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.report:
        report()
    else:
        run(a)
