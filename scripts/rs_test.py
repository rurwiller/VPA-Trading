"""Relative strength vs QQQ for the scanner's pivot-candle trades (step 6).

At each candle's signal minute (known then): the stock's move since the 9:30 open minus QQQ's move since the open
(relative strength, RS), and QQQ's own move since the open. Longs in stocks stronger than QQQ / shorts in stocks weaker
should do better if "trade with strength" holds. Trades = results/strategy_history.pkl candles (live exit, R after cost).
Discovery before the holdout (2026-05-21), holdout shown once.

  python scripts/rs_test.py   -> reports/rs_test.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import pit  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402


def day_move(sym):
    m = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz")
    o = m.groupby(m.index.normalize()).open.transform("first")
    return (m.close / o - 1).rename(sym)


def at(series, times):
    s = series.sort_index()
    idx = s.index.searchsorted(times, side="right") - 1
    v = s.to_numpy()[np.clip(idx, 0, None)]
    same_day = s.index[np.clip(idx, 0, None)].normalize() == pd.DatetimeIndex(times).normalize()
    return np.where((idx >= 0) & same_day, v, np.nan)


def cell(x):
    x = pd.Series(x).dropna()
    return f"{len(x)} | {x.mean():+.3f}R (t {pit.tstat(x):+.1f})" if len(x) >= 10 else f"{len(x)} | -"


def main():
    c = pd.read_pickle("results/strategy_history.pkl")["candles"].copy()
    c["time"] = pd.to_datetime(c.time)
    q = day_move("QQQ")
    c["qqq"] = at(q, c.time)
    c["own"] = np.nan
    for s, g in c.groupby("sym"):
        c.loc[g.index, "own"] = at(day_move(s) if s != "QQQ" else q, g.time)
    c["rs"] = c.own - c.qqq
    c = c[c.sym != "QQQ"]
    c["R"] = c.half05_BE_1R
    L = ["# Relative strength vs QQQ and the scanner's candles\n", __doc__.split("\n\n")[1], "",
         "Each cell: trades | average R after cost (t; above about 2 is unlikely to be luck).\n"]
    for nm, fn in (("Discovery (before 2026-05-21)", lambda x: pit.holdout(x, "time")),
                   ("Holdout (2026-05-21 on)", lambda x: pit.holdout(x, "time", final=True))):
        d = fn(c)
        lg, sh = d[d.dir > 0], d[d.dir < 0]
        L += [f"\n## {nm}\n", "| Filter | Longs | Shorts |", "|---|--:|--:|",
              f"| All | {cell(lg.R)} | {cell(sh.R)} |",
              f"| Stock stronger than QQQ today | {cell(lg[lg.rs > 0].R)} | {cell(sh[sh.rs > 0].R)} |",
              f"| Stock weaker than QQQ today | {cell(lg[lg.rs < 0].R)} | {cell(sh[sh.rs < 0].R)} |",
              f"| Much stronger (RS above +0.5%) | {cell(lg[lg.rs > 0.005].R)} | {cell(sh[sh.rs > 0.005].R)} |",
              f"| Much weaker (RS below -0.5%) | {cell(lg[lg.rs < -0.005].R)} | {cell(sh[sh.rs < -0.005].R)} |",
              f"| QQQ up on the day so far | {cell(lg[lg.qqq > 0].R)} | {cell(sh[sh.qqq > 0].R)} |",
              f"| QQQ down on the day so far | {cell(lg[lg.qqq < 0].R)} | {cell(sh[sh.qqq < 0].R)} |",
              f"| With strength (long & RS>0, QQQ up / short & RS<0, QQQ down) | "
              f"{cell(lg[(lg.rs > 0) & (lg.qqq > 0)].R)} | {cell(sh[(sh.rs < 0) & (sh.qqq < 0)].R)} |",
              f"| Fading (long & RS<0, QQQ down / short & RS>0, QQQ up) | "
              f"{cell(lg[(lg.rs < 0) & (lg.qqq < 0)].R)} | {cell(sh[(sh.rs > 0) & (sh.qqq > 0)].R)} |"]
    pit.log_trial("rs_test", "9 RS filters x long/short (discovery)", len(c), float("nan"), float("nan"))
    Path("reports/rs_test.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
