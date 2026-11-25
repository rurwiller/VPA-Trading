"""A slower, second strategy: daily-timeframe trend rules on index and sector ETFs (step 3 of the overhaul).

Rules decided BEFORE looking at results (kept to four, to limit the number of tries):
  buy & hold       the benchmark
  200-day          hold while the close is above its 200-day average, else cash
  12-month         hold while the 252-day return is positive, else cash (time-series momentum)
  trend pullback   only while above the 200-day: buy at the close when the 2-day RSI is below 10, sell at the first
                   close above the 5-day average (short, in-trend dips)
Signals use the close of day t; the position earns the return from that close to the next (an end-of-day order).
Cost: 2 bps of the position each time it changes. Cash earns nothing. Prices are split-adjusted only (no dividends),
for every rule alike. Books: SPY alone, QQQ alone, and an equal-weight basket of 15 ETFs (each asset in or out on its own).
Discovery = before 2026-05-21; the holdout after it is shown once.

  python scripts/daily_trend_test.py   -> reports/daily_trend.md
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import pit  # noqa: E402
from osc_oversold_test import daily  # noqa: E402

BASKET = ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "TLT", "IEF", "GLD"]
COST = 0.0002


def load(sym):
    for a in range(4):
        try:
            return daily(sym).close
        except Exception as e:                                       # noqa: BLE001
            if "429" in str(e):
                time.sleep(20)
            else:
                raise
    raise RuntimeError(sym)


def rsi2(c):
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean(), (-d).clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def positions(c):
    sma200, sma5 = c.rolling(200).mean(), c.rolling(5).mean()
    pos = {"buy & hold": pd.Series(1.0, index=c.index),
           "200-day": (c > sma200).astype(float),
           "12-month": (c / c.shift(252) > 1).astype(float)}
    r, inpos, pb = rsi2(c), False, []
    for t in range(len(c)):
        if not inpos and c.iat[t] > sma200.iat[t] and r.iat[t] < 10:
            inpos = True
        elif inpos and (c.iat[t] > sma5.iat[t] or not c.iat[t] > sma200.iat[t]):
            inpos = False
        pb.append(1.0 if inpos else 0.0)
    pos["trend pullback"] = pd.Series(pb, index=c.index)
    valid = sma200.notna() & c.shift(252).notna()
    return {k: v.where(valid) for k, v in pos.items()}


def daily_ret(c, p):
    p = p.fillna(0.0)
    return p.shift(1) * c.pct_change() - COST * p.diff().abs().fillna(0)


def metrics(r):
    r = r.dropna()
    if len(r) < 20:
        return "- | - | - | -"
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    cagr = eq.iat[-1] ** (1 / yrs) - 1
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return f"{cagr * 100:+.1f}% | {sh:.2f} | {dd * 100:.1f}% | {r.std() * np.sqrt(252) * 100:.1f}%"


def main():
    closes = {s: load(s) for s in BASKET}
    rules = ["buy & hold", "200-day", "12-month", "trend pullback"]
    books = {}
    for s in ("SPY", "QQQ"):
        c = closes[s]
        p = positions(c)
        books[s] = {k: daily_ret(c, p[k]) for k in rules}
        books[s]["_exposure"] = {k: p[k].mean() for k in rules}
    per = {k: [] for k in rules}
    for s, c in closes.items():
        p = positions(c)
        for k in rules:
            per[k].append(daily_ret(c, p[k]).rename(s))
    books["15-ETF basket"] = {k: pd.concat(per[k], axis=1).mean(axis=1) for k in rules}
    start = max(c.index[252] for c in closes.values())          # after the 252-day warm-up of the slowest rule
    L = ["# Daily trend rules on ETFs\n", __doc__.split("\n\n")[1], "", __doc__.split("\n\n")[2], "",
         f"Measured from {start:%Y-%m-%d} (after the 252-day warm-up) to {max(c.index.max() for c in closes.values()):%Y-%m-%d}. "
         "Each cell: yearly growth | Sharpe | worst drop from a high | yearly volatility.\n"]
    for book, d in books.items():
        L += [f"\n## {book}\n", "| Rule | Whole period | Discovery (to May 2026) | Holdout (since May 21) | 2022 only |",
              "|---|---|---|---|---|"]
        for k in rules:
            r = d[k][d[k].index >= start]
            L.append(f"| {k} | {metrics(r)} | {metrics(r[r.index < pit.HOLDOUT_START])} | "
                     f"{metrics(r[r.index >= pit.HOLDOUT_START])} | {metrics(r[r.index.year == 2022])} |")
        if "_exposure" in d:
            L.append("\nTime in the market: " + ", ".join(f"{k} {v * 100:.0f}%" for k, v in d["_exposure"].items()))
    corr = []
    try:
        bo = pd.read_pickle("results/strategy_history.pkl")["breakout"]
        bo["day"] = pd.to_datetime(bo.day)
        bk = bo[bo.sym.isin(["TSLA", "QQQ"])].groupby("day").plain.sum()
        for k in rules:
            x = books["15-ETF basket"][k]
            j = pd.concat([x, bk], axis=1).dropna()
            corr.append(f"{k} {j.corr().iat[0, 1]:+.2f}")
        L.append("\nDaily correlation with the TSLA + QQQ breakout (basket book): " + ", ".join(corr)
                 + " (near 0 = the two add up without moving together).")
    except Exception as e:                                           # noqa: BLE001
        L.append(f"\n(correlation with the breakout not computed: {e})")
    pit.log_trial("daily_trend", "4 rules x 3 books", 0, float("nan"), float("nan"))
    Path("reports/daily_trend.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
