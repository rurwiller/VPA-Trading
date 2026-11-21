"""The live trend-day breakout rules (TSLA's) on 9 symbols, and the scanner's raw pivot-candle trades per symbol
(step 4 of the improvement plan). Reads results/strategy_history.pkl. Discovery = before the holdout (2026-05-21).

  python scripts/breakout_symbols.py   -> reports/breakout_symbols.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import pit  # noqa: E402


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")


def main():
    h = pd.read_pickle("results/strategy_history.pkl")
    b = h["breakout"].copy()
    b["day"] = pd.to_datetime(b.day)
    L = ["# Trend-day breakout on more symbols\n", __doc__.split("\n\n")[0], "",
         "Per day, after cost, in basis points of the position (1 bp = 0.01%; on $75,000 that is $7.50). "
         "Sharpe = per-day mean / std x sqrt(252), the symbol traded alone. t above about 2 is unlikely to be luck; "
         "9 symbols were tried, so the bar for any one of them is higher (about 2.8).\n",
         "| Symbol | Discovery bps/day | t | Sharpe | Holdout bps/day | t | Holdout days | Trades on % of days | Same with the osc trim (disc / hold) |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    rows = []
    for s, g in b.groupby("sym"):
        g = g.dropna(subset=["plain"])
        d, o = pit.holdout(g, "day"), pit.holdout(g, "day", final=True)
        rows.append((sharpe(d.plain), f"| {s} | {d.plain.mean() * 1e4:+.1f} | {pit.tstat(d.plain):+.1f} | {sharpe(d.plain):+.2f} | "
                     f"{o.plain.mean() * 1e4:+.1f} | {pit.tstat(o.plain):+.1f} | {len(o)} | {(g.plain != 0).mean():.0%} | "
                     f"{d.osc_trim.mean() * 1e4:+.1f} / {o.osc_trim.mean() * 1e4:+.1f} |"))
        pit.log_trial("breakout_symbols", s, len(d), d.plain.mean() * 1e4, pit.tstat(d.plain), "bps/day")
    L += [r for _, r in sorted(rows, reverse=True)]
    top = ["TSLA", "QQQ", "NVDA"]
    port = b[b.sym.isin(top)].pivot(index="day", columns="sym", values="plain").fillna(0)
    for name, cols in (("TSLA alone", ["TSLA"]), ("TSLA + QQQ", ["TSLA", "QQQ"]), ("TSLA + QQQ + NVDA", top)):
        x = port[cols].mean(axis=1) * len(cols)          # each symbol at full size, summed
        d, o = x[x.index < pit.HOLDOUT_START], x[x.index >= pit.HOLDOUT_START]
        L.append(f"\n{name}, each at $75,000: discovery {d.mean() * 7.5e4:+.0f} $/day (Sharpe {sharpe(d):.2f}, worst day "
                 f"{d.min() * 7.5e4:+,.0f}), holdout {o.mean() * 7.5e4:+.0f} $/day (Sharpe {sharpe(o):.2f})")
    c = h["candles"]
    L += ["\n## The scanner's raw pivot candles, by symbol (no live filters)\n",
          "Pivot-wick candles on 9m / 15m with the live exit (half at +0.5R, rest breakeven / 1R), average R after cost. "
          "The live scanner adds filters (a gap, extreme volume for longs, the premier-candle list), so this is the raw "
          "material, not the exact live strategy.\n", "| Symbol | Trades | Discovery R | Holdout R |", "|---|--:|--:|--:|"]
    c = c.assign(day=pd.to_datetime(c.time))
    for s, g in c.groupby("sym"):
        d, o = pit.holdout(g, "day"), pit.holdout(g, "day", final=True)
        L.append(f"| {s} | {len(g)} | {d.half05_BE_1R.mean():+.3f} | {o.half05_BE_1R.mean():+.3f} |")
    Path("reports/breakout_symbols.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
