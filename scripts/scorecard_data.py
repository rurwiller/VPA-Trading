"""Data files for the paper-trading scorecard (the claude.ai dashboard), rebuilt from Alpaca after the close.

  python scripts/scorecard_data.py            -> logs/scorecard/trades.json, logs/scorecard/equity.json

trades.json: one row per position opened since Nov 4 (pieces of a position, e.g. the breakout's thirds or the half exits,
count as one), with day, time (MST), stock, strategy, side, shares, entry, P/L and how it ended (the last piece's way out).
equity.json: the account's value at each close (Alpaca's portfolio history; today = the account's equity now).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import live as LV  # noqa: E402
import eod_report as E  # noqa: E402

START = pd.Timestamp("2026-11-04")
OUT = Path("logs/scorecard")


def main() -> None:
    now = pd.Timestamp.now(tz="America/New_York")
    cal = requests.get(LV.TRADE + "/calendar", headers=LV.headers(), timeout=30,
                       params={"start": f"{START:%Y-%m-%d}", "end": f"{now:%Y-%m-%d}"}).json()
    days = [c["date"] for c in cal if c["date"] < f"{now:%Y-%m-%d}" or now.strftime("%H:%M") >= "15:51"]
    rows = []
    for d in days:
        pieces, _ = E.get_pieces(pd.Timestamp(d))
        df = pd.DataFrame(pieces)
        if not len(df):
            continue
        for (strat, sym, t_in), g in df.groupby(["strat", "sym", "t_in"]):
            g = g.sort_values("t_out")
            rows.append({"day": d, "time": t_in.tz_convert("America/Denver").strftime("%H:%M"), "stock": sym, "strategy": strat,
                         "side": g.side.iat[0], "shares": int(g.q.sum()), "entry": round(float(g.entry.iat[0]), 2),
                         "pnl": round(float(g.pnl.sum()), 2), "how": g.how.iat[-1]})
    rows.sort(key=lambda x: (x["day"], x["time"], x["stock"]))
    h = requests.get(LV.TRADE + "/account/portfolio/history", headers=LV.headers(), timeout=30,
                     params={"period": "3M", "timeframe": "1D"}).json()
    eq = {}
    for t, e in zip(h["timestamp"], h["equity"]):
        d = pd.Timestamp(t, unit="s", tz="UTC").tz_convert("America/New_York").strftime("%Y-%m-%d")
        if e and d >= "2026-11-03":
            eq[d] = float(e)
    a = requests.get(LV.TRADE + "/account", headers=LV.headers(), timeout=30).json()
    if days and days[-1] == f"{now:%Y-%m-%d}":
        eq[days[-1]] = float(a["equity"])
    eq = [{"day": d, "equity": v} for d, v in sorted(eq.items()) if d == "2026-11-03" or d in days]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "trades.json").write_text(json.dumps(rows))
    (OUT / "equity.json").write_text(json.dumps(eq))
    last = rows[-1]["day"] if rows else "-"
    print(f"{len(rows)} trades over {len(days)} days (last {last}); account {eq[0]['equity']:,.2f} -> {eq[-1]['equity']:,.2f}")


if __name__ == "__main__":
    main()
