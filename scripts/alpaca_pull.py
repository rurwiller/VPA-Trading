"""Pull 1-minute SIP bars from Alpaca into data/alpaca/<SYM>-1m.csv.gz.

Usage: python scripts/alpaca_pull.py [--years 1] [SYM ...]
Needs ALPACA_API_KEY / ALPACA_SECRET_KEY. Prints a data-quality summary per symbol.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import alpaca  # noqa: E402

DEFAULT = ["TSLA", "SPY", "QQQ", "AAPL", "NVDA", "AMD", "META"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=DEFAULT)
    ap.add_argument("--years", type=float, default=1.0)
    ap.add_argument("--out-dir", default="data/alpaca")
    args = ap.parse_args()

    acct = alpaca.check_keys()
    print(f"paper account status: {acct['status']}")
    end = pd.Timestamp.now(tz="UTC").floor("D") + pd.Timedelta(hours=0)
    start = end - pd.Timedelta(days=round(365 * args.years))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for sym in args.symbols:
        df = alpaca.fetch_bars(sym, start.isoformat(), end.isoformat())
        path = out_dir / f"{sym}-1m.csv.gz"
        df.to_csv(path)
        days = df.index.normalize().nunique()
        per_day = df.groupby(df.index.date).size()
        med = df.volume.rolling(25, center=True, min_periods=5).median()
        spikes = int((df.volume > 8 * med).sum())
        print(f"{sym:5} {len(df):7} bars  {days} sessions  {df.index[0]:%Y-%m-%d}..{df.index[-1]:%Y-%m-%d}  "
              f"median {int(per_day.median())} bars/day (390 = full)  vol>8x median: {spikes}  -> {path}")


if __name__ == "__main__":
    main()
