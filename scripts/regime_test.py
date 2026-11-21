"""Do the live strategies behave differently by market regime? (step 2 of the improvement plan)

Inputs: results/strategy_history.pkl (scripts/strategy_history.py) and the regime features in vpa_trading/regime.py,
all known before each session. Tuned on data before the holdout (vpa_trading/pit.HOLDOUT_START, 2026-05-21); the holdout
columns are shown once, for the final check, and are not used to pick anything.

  candle longs / shorts   average R per trade, live exit (half at +0.5R, rest breakeven / 1R), after cost
  breakout                average bps of notional per day the rule traded (live rules, thirds + breakeven), after cost

  python scripts/regime_test.py   -> reports/regime_test.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import pit, regime  # noqa: E402

BUCKETS = {
    "SPY vs 200-day": ("spy_above200", [("above", lambda x: x == 1), ("below", lambda x: x == 0)]),
    "SPY last 20 days": ("spy_20d", [("up", lambda x: x > 0), ("down", lambda x: x <= 0)]),
    "Breadth (S&P stocks above 50-day)": ("breadth50", [("under 40%", lambda x: x < 0.4), ("40-60%", lambda x: (x >= 0.4) & (x <= 0.6)),
                                                         ("over 60%", lambda x: x > 0.6)]),
    "SPY volatility (20-day)": ("vol20", [("calm, under 12%", lambda x: x < 0.12), ("normal, 12-20%", lambda x: (x >= 0.12) & (x <= 0.2)),
                                          ("stressed, over 20%", lambda x: x > 0.2)]),
    "QQQ vs 50-day": ("qqq_above50", [("above", lambda x: x == 1), ("below", lambda x: x == 0)]),
}


def stat(x, scale=1.0, unit="R"):
    x = pd.Series(x).dropna() * scale
    if len(x) < 10:
        return f"{len(x)} | -"
    return f"{len(x)} | {x.mean():+.3f}{unit} (t {pit.tstat(x):+.1f})" if unit == "R" else f"{len(x)} | {x.mean():+.1f} (t {pit.tstat(x):+.1f})"


def main():
    h = pd.read_pickle("results/strategy_history.pkl")
    f = regime.load()
    for c in ("spy_above200", "qqq_above50"):
        f[c] = f[c].map({True: 1, False: 0, "True": 1, "False": 0})
    f = f.astype(float)
    cd = h["candles"].copy()
    cd["day"] = pd.to_datetime(cd.time).dt.normalize()
    cd = cd.join(f, on="day")
    bo = h["breakout"].copy()
    bo["day"] = pd.to_datetime(bo.day)
    bo = bo[bo.plain.fillna(0) != 0].join(f, on="day")
    L = ["# Market regime vs the live strategies\n", __doc__.split("\n\n")[1], "", __doc__.split("\n\n")[2], "",
         f"Candle trades: {len(cd):,} ({cd.time.min():%Y-%m-%d} to {cd.time.max():%Y-%m-%d}), 9 symbols. "
         f"Breakout trading days: {len(bo):,}. Each cell: count | average (t; above about 2 is unlikely to be luck).\n"]
    trials = 0
    for split_name, fn in (("Discovery (before 2026-05-21)", lambda x, col: pit.holdout(x, col)),
                           ("Holdout (2026-05-21 on, looked at once)", lambda x, col: pit.holdout(x, col, final=True))):
        c, b = fn(cd, "day"), fn(bo, "day")
        L += [f"\n## {split_name}\n",
              "| Regime | Candle longs | Candle shorts | Breakout, all 9 (bps/day) | Breakout, TSLA only (bps/day) |",
              "|---|--:|--:|--:|--:|",
              f"| Everything | {stat(c[c.dir > 0]['half05_BE_1R'])} | {stat(c[c.dir < 0]['half05_BE_1R'])} | "
              f"{stat(b.plain, 1e4, 'bps')} | {stat(b[b.sym == 'TSLA'].plain, 1e4, 'bps')} |"]
        for title, (col, parts) in BUCKETS.items():
            for nm, cond in parts:
                cm, bm = cond(c[col]), cond(b[col])
                L.append(f"| {title}: {nm} | {stat(c[cm & (c.dir > 0)]['half05_BE_1R'])} | {stat(c[cm & (c.dir < 0)]['half05_BE_1R'])} | "
                         f"{stat(b[bm].plain, 1e4, 'bps')} | {stat(b[bm & (b.sym == 'TSLA')].plain, 1e4, 'bps')} |")
                trials += 4 if split_name.startswith("Disc") else 0
        L[-1 - sum(len(p) for _, p in BUCKETS.values())] += ""
    for tr in range(1):
        pit.log_trial("regime_test", "regime buckets x 4 strategy columns (discovery)", len(cd), float("nan"), float("nan"),
                      note=f"{trials} cells compared")
    n = pit.trials_so_far()
    L += [f"\nCells compared in discovery: {trials}. With {n} studies logged, a single cell needs |t| above "
          f"{pit.required_t(n + trials):.1f} to count as more than luck from all the slicing."]
    Path("reports/regime_test.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
