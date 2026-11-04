"""Our GEX levels (vpa_trading/gex.py, Alpaca options data) next to the ones you read off TerraShade.

  python scripts/gex_compare.py --now [SYM ...]     our levels right now (Mag 7 by default), to hold up against the site
  python scripts/gex_compare.py                     every row of data/terrashade_levels.csv vs our nearest snapshot

Enter what the TerraShade heatmap shows in data/terrashade_levels.csv (you read it; nothing is pulled from the site):
  date,time_mst,symbol,call_wall,put_wall,flip,note
  2026-11-05,07:45,TSLA,400,380,383,biggest yellow bar at 400
Leave a cell empty if the site does not show it. Our snapshots come from logs/gex/<date>.csv, which the live scanner
writes every 30 minutes; if there is none for that time the row is compared with our levels right now.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from vpa_trading import gex as GX  # noqa: E402

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


def ours_at(sym: str, t_et: pd.Timestamp) -> dict:
    p = ROOT / "logs/gex" / f"{t_et:%Y-%m-%d}.csv"
    if p.exists():
        g = pd.read_csv(p)
        g = g[g.sym == sym]
        if len(g):
            g["dt"] = (pd.to_datetime(g.time) - t_et).abs()
            r = g.sort_values("dt").iloc[0]
            if r.dt <= pd.Timedelta(hours=1):
                return r.to_dict() | {"src": f"snapshot {r.time[-5:]} ET"}
    return GX.levels(sym) | {"src": "now"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", nargs="*")
    a = ap.parse_args()
    if a.now is not None:
        rows = []
        for s in a.now or MAG7:
            lv = GX.levels(s)
            rows.append({"sym": s, "spot": lv["spot"], "call wall": lv["call_wall"], "put wall": lv["put_wall"],
                         "flip": lv["flip"], "net GEX $M/1%": lv["net_gex_musd"],
                         "next call walls": ", ".join(f"{x:g}" for x in lv["call_walls"][1:]),
                         "next put walls": ", ".join(f"{x:g}" for x in lv["put_walls"][1:])})
        print(pd.DataFrame(rows).to_string(index=False))
        return
    t = pd.read_csv(ROOT / "data/terrashade_levels.csv", dtype={"time_mst": str})
    if t.empty:
        print("data/terrashade_levels.csv has no rows yet")
        return
    out = []
    for _, r in t.iterrows():
        t_et = pd.Timestamp(f"{r.date} {r.time_mst}") + pd.Timedelta(hours=2)
        o = ours_at(r.symbol, t_et)
        row = {"date": r.date, "MST": r.time_mst, "sym": r.symbol, "spot": o.get("spot"), "ours from": o["src"]}
        for k in ("call_wall", "put_wall", "flip"):
            row[f"{k} TS"], row[f"{k} ours"] = r[k], o.get(k)
            row[f"{k} diff%"] = round((o.get(k) - r[k]) / r[k] * 100, 2) if pd.notna(r[k]) and pd.notna(o.get(k)) else None
        out.append(row)
    d = pd.DataFrame(out)
    print(d.to_string(index=False))
    for k in ("call_wall", "put_wall"):
        m = d[f"{k} TS"].notna() & d[f"{k} ours"].notna()
        if m.any():
            print(f"{k}: same strike {int((d[f'{k} TS'] == d[f'{k} ours'])[m].sum())} of {int(m.sum())}")


if __name__ == "__main__":
    main()
