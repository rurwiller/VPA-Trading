"""Do the live strategies behave differently on event days? (step 7)

Events (all known in advance, except the gap day, which is known at the 9:30 open, before any signal):
  CPI release days      list from scripts/cpi_close_test.py (from memory, checked against the 8:30 volume burst)
  FOMC decision days    Fed statement days, from memory (2026 dates = the Fed's published schedule as I recall it)
  Monthly opex          third Friday of the month
  Stock-specific gap    the stock opened 3%+ away from its prior close and at least 2% more than QQQ did
                        (earnings and big news days; no earnings calendar is available here)
Trades = results/strategy_history.pkl (candles: live exit, R after cost; breakout: bps per traded day after cost).

  python scripts/events_test.py   -> reports/events_test.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import pit  # noqa: E402
from cpi_close_test import CPI  # noqa: E402

FOMC = """2021-11-03 2021-12-15 2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13 2024-01-31 2024-03-20 2024-05-01
2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18 2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17
2025-10-29 2025-12-10 2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28""".split()


def gaps():
    out = {}
    q = pd.read_csv("data/daily/QQQ.csv.gz", index_col=0, parse_dates=True)
    qg = q.open / q.close.shift() - 1
    for s in ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD"]:
        d = pd.read_csv(f"data/daily/{s}.csv.gz", index_col=0, parse_dates=True)
        g = d.open / d.close.shift() - 1
        out[s] = set(d.index[(g.abs() >= 0.03) & ((g - qg).abs() >= 0.02)])
    return out


def cell(x, scale=1.0, unit="R"):
    x = pd.Series(x).dropna() * scale
    if len(x) < 10:
        return f"{len(x)} | -"
    return f"{len(x)} | {x.mean():+.3f}R (t {pit.tstat(x):+.1f})" if unit == "R" else f"{len(x)} | {x.mean():+.1f} (t {pit.tstat(x):+.1f})"


def main():
    h = pd.read_pickle("results/strategy_history.pkl")
    c = h["candles"].copy()
    c["day"] = pd.to_datetime(c.time).dt.normalize()
    b = h["breakout"].copy()
    b["day"] = pd.to_datetime(b.day)
    b = b[b.plain.fillna(0) != 0]
    cpi, fomc = set(pd.to_datetime(CPI)), set(pd.to_datetime(FOMC))
    gp = gaps()
    for df in (c, b):
        df["cpi"] = df.day.isin(cpi)
        df["fomc"] = df.day.isin(fomc)
        df["opex"] = (df.day.dt.weekday == 4) & (df.day.dt.day.between(15, 21))
        df["gap"] = [d in gp.get(s, set()) for s, d in zip(df.sym, df.day)]
        df["none"] = ~(df.cpi | df.fomc | df.opex | df.gap)
    L = ["# Event days vs the live strategies\n", __doc__.split("\n\n")[1], "",
         "Each cell: count | average (t; above about 2 is unlikely to be luck). Whole 5 years (event days are too few "
         "to split off a holdout).\n",
         "| Day type | Candle longs | Candle shorts | Breakout, all 9 (bps/day) | Breakout, TSLA (bps/day) |", "|---|--:|--:|--:|--:|"]
    for nm, col in (("No event", "none"), ("CPI day", "cpi"), ("FOMC day", "fomc"), ("Monthly opex", "opex"),
                    ("Stock-specific gap (earnings / news)", "gap")):
        cc, bb = c[c[col]], b[b[col]]
        L.append(f"| {nm} | {cell(cc[cc.dir > 0].half05_BE_1R)} | {cell(cc[cc.dir < 0].half05_BE_1R)} | "
                 f"{cell(bb.plain, 1e4, 'bps')} | {cell(bb[bb.sym == 'TSLA'].plain, 1e4, 'bps')} |")
    L += ["\nFOMC: candles before vs after the 14:00 ET statement\n", "| Time | Candle trades | Average R |", "|---|--:|--:|"]
    f = c[c.fomc].copy()
    t = pd.to_datetime(f.time)
    for nm, m in (("before 13:30", t.dt.hour * 60 + t.dt.minute < 810), ("13:30 to 14:00", (t.dt.hour * 60 + t.dt.minute).between(810, 839)),
                  ("after 14:00", t.dt.hour * 60 + t.dt.minute >= 840)):
        x = f[m].half05_BE_1R
        L.append(f"| {nm} | {len(x)} | {x.mean():+.3f}R |")
    pit.log_trial("events_test", "5 day types x 4 columns", len(c), float("nan"), float("nan"))
    Path("reports/events_test.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
