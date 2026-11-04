"""Willard 3.0 MTF signals replayed as they behave on a 5-MINUTE chart, for windows that match a
TradingView scorecard (which only covers the history the chart has loaded).

  python scripts/willard_5m_chart.py [SYM ...]   -> results/willard5m/<SYM>.pkl, prints window tables
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import research as R, willard_signals as W  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
from research_run import DEFAULT  # noqa: E402

OUT = Path("results/willard5m")


def run_symbol(sym: str) -> str:
    m1 = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1)
    x, bars = W.inputs_5m_chart(s)
    tr, st = W.run(s, x, bars=bars, step=pd.Timedelta(minutes=5))
    tr["sym"], st["sym"] = sym, sym
    OUT.mkdir(parents=True, exist_ok=True)
    tr.to_pickle(OUT / f"{sym}.pkl")
    st.to_pickle(OUT / f"{sym}_setups.pkl")
    return f"{sym}: {len(st)} setups, {len(tr)} trades"


def card(t: pd.DataFrame) -> pd.DataFrame:
    def f(g):
        w, l = g.pnl[g.pnl > 0], g.pnl[g.pnl <= 0]
        return pd.Series({"Trades": len(g), "Win %": round(len(w) / len(g) * 100, 1) if len(g) else np.nan,
                          "PF": round(w.sum() / -l.sum(), 2) if len(l) and l.sum() < 0 else np.inf,
                          "Avg W / L %": f"+{w.mean():.2f} / {l.mean():.2f}" if len(w) and len(l) else "-",
                          "Net %": round(g.pnl.sum(), 2)})
    return t.groupby("rule").apply(f, include_groups=False).reindex(W.RULES)


if __name__ == "__main__":
    syms = sys.argv[1:] or DEFAULT
    with ProcessPoolExecutor(max_workers=3) as ex:
        for msg in ex.map(run_symbol, syms):
            print(msg, flush=True)
