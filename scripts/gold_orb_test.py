"""Micro Gold opening-range breakdown, as posted (tested on GLD 1m bars: Alpaca has no futures).

Rules as posted:
  - trade only on days gold opens below the prior close
  - mark the low of the first 30 minutes
  - short when a 30-minute block closes below it (entry at that block's close)
  - stop 20 points, target 15 points, else out at the 4 PM close; one trade a day
GLD stands in for gold futures: 1 futures point = 1/10.86 of a GLD dollar (GLD holds ~0.092 oz). Session = 9:30-16:00 ET
(the post's "4 PM close"), 30-minute blocks from 9:30. Same 1m bar touching stop and target = stop. Cost 0.4 futures points
per round trip (about a tick each way plus micro fees). 1 point = $10 on one Micro Gold contract.
Variants: the same stop/target as a share of price (20 and 15 points were sized for ~$1,800 gold in 2021), the mirrored
long on gap-up days, and the short on days that did NOT gap down (does the gap filter matter?).

  python scripts/gold_orb_test.py   -> reports/gold_orb.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading.alpaca import load_bars_file  # noqa: E402

R = 10.86            # gold futures price / GLD price
COST = 0.4           # futures points per round trip
SPLIT = pd.Timestamp("2024-11-01")


def run(m: pd.DataFrame, side: int, gap: str, stop_pts=20.0, tgt_pts=15.0, pct=False) -> pd.DataFrame:
    rows, prev = [], None
    for d, g in m.groupby(m.index.normalize()):
        if len(g) < 380:
            prev = None if len(g) < 200 else float(g.close.iat[-1])
            continue
        o, c_last = float(g.open.iat[0]), float(g.close.iat[-1])
        if prev is not None:
            gapped_down = o < prev
            ok = {"down": gapped_down, "up": not gapped_down and o > prev, "notdown": not gapped_down}[gap]
            if ok:
                mi = ((g.index - d) / pd.Timedelta(minutes=1)).astype(int) - 570
                first = g[mi < 30]
                lvl = float(first.low.min()) if side < 0 else float(first.high.max())
                H, L, C = g.high.to_numpy(), g.low.to_numpy(), g.close.to_numpy()
                gc = o * R
                s_pts = stop_pts * (gc / 1800.0 if pct else 1.0)      # pct: scale to today's gold price like 2021's ~$1,800
                t_pts = tgt_pts * (gc / 1800.0 if pct else 1.0)
                for b in range(60, 390, 30):                          # block 10:00-10:30 closes at index 59
                    j = b - 1
                    if j >= len(C):
                        break
                    if (side < 0 and C[j] < lvl) or (side > 0 and C[j] > lvl):
                        e = C[j] * R
                        stop, tgt = e - side * s_pts, e + side * t_pts
                        out, why = C[-1] * R, "4 PM close"
                        for k in range(j + 1, len(C)):
                            if (side < 0 and H[k] * R >= stop) or (side > 0 and L[k] * R <= stop):
                                out, why = stop, "stop"
                                break
                            if (side < 0 and L[k] * R <= tgt) or (side > 0 and H[k] * R >= tgt):
                                out, why = tgt, "target"
                                break
                        rows.append({"day": d, "pts": side * (out - e) - COST, "why": why, "gold": e, "risk_pts": s_pts})
                        break
        prev = c_last
    return pd.DataFrame(rows)


def stats(t: pd.DataFrame) -> str:
    if not len(t):
        return "| - | - | - | - | - |"
    p = t.pts
    tt = p.mean() / (p.std() / np.sqrt(len(p))) if len(p) > 2 else np.nan
    return f"| {len(p)} | {(p > 0).mean():.0%} | {p.mean():+.2f} | {p.sum() * 10:+,.0f} | {tt:+.1f} |"


def main() -> None:
    m = load_bars_file(Path("data/alpaca") / "GLD-1m-ext.csv.gz")
    variants = [("As posted: short, gap-down days, 20 / 15 points", dict(side=-1, gap="down")),
                ("Short, gap-down days, stop/target scaled to the gold price", dict(side=-1, gap="down", pct=True)),
                ("Short on days that did NOT gap down (gap filter off)", dict(side=-1, gap="notdown")),
                ("Mirror: long on gap-up days above the first-30-min high", dict(side=1, gap="up")),
                ("Short, gap-down days, 15 / 15 points", dict(side=-1, gap="down", stop_pts=15.0)),
                ("Short, gap-down days, 20 / 30 points", dict(side=-1, gap="down", tgt_pts=30.0))]
    L = ["# Micro Gold opening-range breakdown (tested on GLD, 5 years of 1m bars)\n", __doc__.split("\n\n")[1], "",
         f"Data {m.index[0]:%Y-%m-%d} to {m.index[-1]:%Y-%m-%d}. Points are gold-futures points after costs; $ is for one "
         "Micro Gold contract ($10 a point). t = mean / standard error.\n"]
    for name, kw in variants:
        t = run(m, **kw)
        L += [f"\n## {name}\n", "| Period | Trades | Won | Avg points | $ total (1 MGC) | t |", "|---|--:|--:|--:|--:|--:|"]
        for lab, x in (("All", t), ("Before Nov 2024", t[t.day < SPLIT] if len(t) else t), ("Since Nov 2024", t[t.day >= SPLIT] if len(t) else t)):
            L.append(f"| {lab} " + stats(x))
        if len(t):
            yr = t.groupby(t.day.dt.year).pts.agg(["count", "mean"])
            L.append("\nBy year (trades, avg points): " + ", ".join(f"{y} {int(r['count'])} / {r['mean']:+.1f}" for y, r in yr.iterrows()))
            L.append("How trades ended: " + ", ".join(f"{k} {v:.0%}" for k, v in t.why.value_counts(normalize=True).items())
                     + f". Gold price at entry {t.gold.min():,.0f}-{t.gold.max():,.0f}; 20 points was "
                     f"{20 / t.gold.iloc[0]:.2%} of price at the start and {20 / t.gold.iloc[-1]:.2%} at the end.")
    Path("reports/gold_orb.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
