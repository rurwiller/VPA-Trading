"""Kronos filter on premier candles / climaxes at 1h-4h-D fair value gaps (scripts/fvg_candle_test.py).

Only signals from 2025-11-01 (after Kronos's training data), traded with Coulling's bias. Kronos-small reads the last
256 fifteen-minute candles closed before the entry and samples 30 paths of 8 candles (2 h). p_target = share of
resolved paths reaching +0.3% before -0.5% (a random walk: 62.5%); p_dir = share of paths up (in the trade's
direction) after 1 h. Real outcome = the same +0.3% / -0.5% race on 1m bars. Resumable.

  python scripts/kronos_fvg.py --n 600       -> results/kronos_fvg.csv
  python scripts/kronos_fvg.py --report      -> reports/kronos_fvg.md
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

OUT = Path("results/kronos_fvg.csv")
SINCE = pd.Timestamp("2025-11-01")
LOOKBACK, PRED, PATHS = 256, 8, 30


def signals(n: int) -> pd.DataFrame:
    rows = []
    for p in sorted(Path("results/fvg_candles").glob("*.pkl")):
        e = pd.read_pickle(p)
        rows.append(e[e.at_gap & (e.side == "with") & (e.time >= SINCE)][
            ["family", "type", "tf", "gap_tf", "sym", "time", "i", "dir", "entry", "out_T0.3_S0.5", "pct_T0.3_S0.5"]])
    s = pd.concat(rows, ignore_index=True)
    picks = [g.sample(min(n // 2, len(g)), random_state=5) for _, g in s.groupby("family")]
    return pd.concat(picks).sort_values(["sym", "time"]).reset_index(drop=True)


def run(n: int) -> None:
    from vpa_trading.kronos_loader import load_kronos_small
    sig = signals(n)
    done = set()
    if OUT.exists():
        prev = pd.read_csv(OUT)
        done = set(zip(prev.family, prev.sym, prev.time.astype(str), prev.tf))
    pred = load_kronos_small(device="cpu", max_context=512)
    cache = {}
    for k, r in sig.iterrows():
        if (r.family, r.sym, str(r.time), r.tf) in done:
            continue
        if r.sym not in cache:
            cache.clear()
            m1 = load_bars_file(Path("data/alpaca") / f"{r.sym}-1m-ext.csv.gz")
            cache[r.sym] = (m1, resample_bars(m1, "15m"))
        m1, b = cache[r.sym]
        clock = m1.index[int(r.i)] + pd.Timedelta(minutes=1)
        x = b[b.index + pd.Timedelta(minutes=15) <= clock].iloc[-LOOKBACK:]
        if len(x) < LOOKBACK:
            continue
        t0 = time.time()
        paths = kp.sample_paths(pred, x[["open", "high", "low", "close", "volume"]], x.index.to_series(),
                                kp.us_session_bars(x.index[-1], PRED, "15min"), n_paths=PATHS, batch_size=PATHS, seed=k)
        e, d = float(r.entry), int(r.dir)
        stop, tgt = (e * 0.995, e * 1.003) if d > 0 else (e * 1.005, e * 0.997)
        m = kp.race(paths, e, stop, tgt)
        row = dict(family=r.family, type=r.type, tf=r.tf, gap_tf=r.gap_tf, sym=r.sym, time=str(r.time), dir=d,
                   p_target=m.p_target_resolved, p_dir_1h=float(((paths[:, 3, kp.C] - e) * d > 0).mean()),
                   real_hit=int(r["out_T0.3_S0.5"] == 1), real_pct=r["pct_T0.3_S0.5"], secs=round(time.time() - t0, 1))
        pd.DataFrame([row]).to_csv(OUT, mode="a", header=not OUT.exists(), index=False)
        print(f"{r.family:7} {r.sym:5} {r.time} p_t={row['p_target']:.2f} real={'HIT' if row['real_hit'] else 'miss'}", flush=True)
    print("done")


def report() -> None:
    t = pd.read_csv(OUT)
    t["net"] = t.real_pct - t.sym.map(cost_bps) / 100

    def summ(g):
        return pd.Series({"n": len(g), "hit +0.3% %": round(g.real_hit.mean() * 100, 1), "avg % after cost": round(g.net.mean(), 3),
                          "2se": round(2 * g.net.std() / np.sqrt(len(g)), 3) if len(g) > 1 else np.nan,
                          "Kronos p_target": round(g.p_target.mean(), 3)})

    t["band"] = pd.cut(t.p_target, [0, 0.5, 0.625, 0.75, 1.0], include_lowest=True).astype(str)
    keep = t.p_target >= 0.625
    ranks = t[["p_target", "p_dir_1h", "net"]].rank()
    L = ["# Kronos filter: premier candles and climaxes at 1h / 4h / D fair value gaps\n",
         f"{len(t)} signals since {SINCE:%Y-%m-%d}, traded with Coulling's bias; exit +0.3% target / 0.5% stop. "
         "Kronos p_target = share of its paths hitting +0.3% first (random walk 62.5%).\n",
         "## All\n", t.groupby("family").apply(summ, include_groups=False).to_markdown(),
         "\n## By Kronos p_target\n", t.groupby(["family", "band"]).apply(summ, include_groups=False).to_markdown(),
         "\n## Keep only p_target >= 0.625 (better than a random walk)\n",
         pd.DataFrame({"kept": summ(t[keep]), "rejected": summ(t[~keep])}).T.to_markdown(),
         "\n## Rank correlation with the real result\n",
         ranks.drop(columns="net").corrwith(ranks.net).round(3).to_frame("spearman").to_markdown()]
    Path("reports/kronos_fvg.md").write_text("\n".join(L) + "\n")
    print("wrote reports/kronos_fvg.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    report() if a.report else run(a.n)
