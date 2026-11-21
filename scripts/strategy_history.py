"""Build one reusable history of the live strategies over 5 years of 1m bars (inputs for the regime, breakout and
relative-strength studies).

- breakout: the live TSLA trend-day rules (checks every 30 min, thirds at +1% / +2%, breakeven after the first; plus the
  live 15m-oscillator trim of half at 80/20) run on every symbol, one return per day (fraction of notional, after cost).
- candles: the scanner's pivot-wick candles on 9m / 15m (stop-entry through the candle, stop beyond the wick), scored with
  the live exit (half at +0.5R, rest breakeven / 1R), in R after cost. Uses trim_test.run_symbol unchanged.

  python scripts/strategy_history.py   -> results/strategy_history.pkl
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import trim_test as T  # noqa: E402
from vpa_trading import research as R  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402

SYMS = ["TSLA", "NVDA", "META", "AAPL", "MSFT", "GOOGL", "AMZN", "QQQ", "AMD"]


def one(sym):
    out = T.run_symbol(sym)
    if "breakout" not in out:
        s = R.prepare(sym, load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False))
        mats = T.matrices(s)
        out["breakout"] = {"live: thirds at 1% / 2%, breakeven after the first": T.breakout(sym, mats),
                           "+ auto-trim half at 80": T.breakout(sym, mats, osc_trim=(80, 0.5))}
    b = pd.DataFrame({"plain": out["breakout"]["live: thirds at 1% / 2%, breakeven after the first"],
                      "osc_trim": out["breakout"]["+ auto-trim half at 80"]})
    b["sym"] = sym
    print(sym, "done", flush=True)
    return b.reset_index(names="day"), out["candles"]


def main():
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(one, SYMS))
    pd.to_pickle({"breakout": pd.concat([r[0] for r in res], ignore_index=True),
                  "candles": pd.concat([r[1] for r in res], ignore_index=True)}, "results/strategy_history.pkl")


if __name__ == "__main__":
    main()
