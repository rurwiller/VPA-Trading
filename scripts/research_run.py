"""Run every event family on every ticker and save the scored events.

  python scripts/research_run.py [SYM ...]       -> results/events/<SYM>.pkl

Families (each scored as fade and as continuation):
  stack  : all oscillators of a timeframe stack at an extreme (closed bars), optional 3m trigger
  candle : inverted hammer / hammer at an oscillator extreme on one timeframe
  climax : VPA buying / selling climax (fresh 20-bar extreme, high relative volume, wick)
  fvg    : first touch of an unfilled fair value gap (5m, 15m, 1h), market and limit entry
  level  : first touch per day of prior-day H/L/C, premarket H/L, 15/30-min opening range
  vpa    : Coulling detections from docs/vpa-detection-spec.md on 2m, 5m, 15m (with / against)
Then run scripts/research_report.py.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import research as R  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
DEFAULT = MAG7 + ["SPY", "QQQ", "AMD"]
STACKS = [["1h", "30m", "15m", "5m"], ["1h", "15m", "9m", "5m"], ["15m", "9m", "5m"],
          ["1h", "15m", "5m"], ["1h", "5m"]]
LEVELS = [10, 15, 20, 25, 30]


def run_symbol(sym: str, data_dir: str = "data/alpaca", out_dir: str = "results/events") -> str:
    t0 = time.time()
    p = Path(data_dir) / f"{sym}-1m-ext.csv.gz"
    m1 = load_bars_file(p, regular_only=False)
    s = R.prepare(sym, m1)
    ev = []
    for tfs in STACKS:
        for lv in LEVELS:
            for trig in (None, "3m"):
                ev.append(R.stack_events(s, tfs, lv, trig))
    for tf in ("5m", "15m"):
        for lv in (15, 20, 30, 50):
            ev.append(R.candle_events(s, tf, lv))
        for rv in (1.5, 2.0, 3.0):
            for wick in (0.0, 0.4):
                ev.append(R.climax_events(s, tf, rv, wick))
    for tf in ("5m", "15m", "1h"):
        ev.append(R.fvg_events(s, tf))
    for tf in R.VPA_TFS:
        ev.append(R.vpa_events(s, tf))
    ev.append(R.level_events(s))
    for rv in (2.0, 3.0):
        ev.append(R.climax_events(s, "2m", rv, 0.4))
    ev = pd.concat([e for e in ev if len(e)], ignore_index=True)
    sc = R.score(s, ev)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    sc.to_pickle(Path(out_dir) / f"{sym}.pkl")
    return f"{sym}: {len(m1)} 1m bars, {len(sc)} scored trades, {time.time() - t0:.0f}s"


if __name__ == "__main__":
    syms = sys.argv[1:] or DEFAULT
    with ProcessPoolExecutor(max_workers=min(3, len(syms))) as ex:
        for msg in ex.map(run_symbol, syms):  # ~2-3 GB RAM per worker
            print(msg, flush=True)
