"""Pool backtest CSVs from several tickers into one report.

Usage: python scripts/kronos_report.py results/*_1015_k1.5_rr2.0.csv [--threshold 0.5]
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kronos_backtest import report  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("csv", nargs="+")
ap.add_argument("--threshold", type=float, default=0.5)
a = ap.parse_args()
frames = [pd.read_csv(p).assign(ticker=Path(p).name.split("-")[0]) for p in a.csv]
res = pd.concat(frames, ignore_index=True)
res["decision_time"] = res.ticker + " " + res.decision_time
print("tickers:", ", ".join(f"{t} ({n // 2} days)" for t, n in res.ticker.value_counts().sort_index().items()))
report(res, a.threshold)
