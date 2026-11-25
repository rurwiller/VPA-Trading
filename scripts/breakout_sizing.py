"""Fixed notional vs volatility-based sizing for the trend-day breakout (TSLA, QQQ, NVDA).

Fixed: $75,000 of stock every trade (live until Nov 2026).
Vol-sized: notional = budget / (the stock's 20-day realized daily volatility, known at the prior close), so a typical
day's move is worth the same dollars on every symbol and in every market; capped at $150,000.
The budget is set so the average notional on TSLA + QQQ over the discovery period is about $75,000 (same capital use).
Daily breakout returns from results/strategy_history.pkl (live rules, after cost). Discovery before 2026-05-21, holdout
after, shown once.

  python scripts/breakout_sizing.py   -> reports/breakout_sizing.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import pit  # noqa: E402
from osc_oversold_test import daily  # noqa: E402

SYMS = ["TSLA", "QQQ", "NVDA"]
CAP = 150_000.0


def vol20(sym):
    c = daily(sym).close
    return np.log(c).diff().rolling(20).std().shift(1)


def stats(x):
    x = x.dropna()
    sh = x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")
    eq = x.cumsum()
    return f"{x.mean():+.0f} | {sh:.2f} | {x.min():+,.0f} | {(eq - eq.cummax()).min():+,.0f}"


def main():
    b = pd.read_pickle("results/strategy_history.pkl")["breakout"]
    b["day"] = pd.to_datetime(b.day)
    rows = {}
    for s in SYMS:
        g = b[b.sym == s].set_index("day").plain.fillna(0.0)
        v = vol20(s).reindex(g.index)
        rows[s] = pd.DataFrame({"ret": g, "vol": v})
    disc = pd.concat([pit.holdout(rows[s][["vol"]]).assign(sym=s) for s in ("TSLA", "QQQ")])
    budget = 75_000.0 * disc.vol.median()
    L = ["# Breakout sizing: fixed $75k vs volatility-based\n", __doc__.split("\n\n")[1], "",
         f"Budget = ${budget:,.0f} of one day's typical move per trade (so a stock moving 2% a day gets "
         f"${min(budget / 0.02, CAP):,.0f}, one moving 4% gets ${min(budget / 0.04, CAP):,.0f}).\n",
         "Per symbol and portfolio, in dollars per day: average | Sharpe | worst day | worst drawdown.\n",
         "| Book | Sizing | Discovery | Holdout |", "|---|---|---|---|"]
    port = {"fixed": [], "vol": []}
    for s in SYMS:
        r = rows[s]
        fixed = r.ret * 75_000
        vs = r.ret * np.minimum(budget / r.vol, CAP)
        for nm, x in (("fixed $75k", fixed), ("vol-sized", vs)):
            L.append(f"| {s} | {nm} | {stats(pit.holdout(x.to_frame('x')).x)} | {stats(pit.holdout(x.to_frame('x'), final=True).x)} |")
        if s in ("TSLA", "QQQ"):
            port["fixed"].append(fixed)
            port["vol"].append(vs)
        n = r.vol.dropna()
        L.append(f"| {s} | vol-sized notional | median ${np.minimum(budget / n, CAP).median():,.0f}, "
                 f"range ${np.minimum(budget / n, CAP).quantile(.05):,.0f} to ${np.minimum(budget / n, CAP).quantile(.95):,.0f} | |")
    for nm, k in (("fixed $75k", "fixed"), ("vol-sized", "vol")):
        x = pd.concat(port[k], axis=1).fillna(0).sum(axis=1)
        L.append(f"| TSLA + QQQ | {nm} | {stats(pit.holdout(x.to_frame('x')).x)} | {stats(pit.holdout(x.to_frame('x'), final=True).x)} |")
    pit.log_trial("breakout_sizing", "vol-sized vs fixed, TSLA/QQQ/NVDA", len(b), float("nan"), float("nan"))
    Path("reports/breakout_sizing.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
