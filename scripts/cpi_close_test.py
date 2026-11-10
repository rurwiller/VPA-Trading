"""The "close location into CPI" rule from X, tested on SPY / QQQ / the Mag 7.

Rule as posted: if the day before CPI closes in the top half of its range, short at that close and cover at the CPI-day
close; bottom half, go long. Claim: 2025 to now, 81% win rate, profit factor 3.9.

CPI dates: BLS blocks automated requests, so they come from memory, checked against the 8:30 ET premarket volume burst in
SPY's 1m data (every date below lines up with a burst; 2022 matched 12 of 12 blind). Two 2026 dates are uncertain (Mar 11
or 18, Oct 14 or 15); both versions are run. Regular-session daily bars built from 1m data (Nov 2021 on). Costs 2 bps.
The same rule on every non-CPI day is the baseline: is anything special about CPI?

  python scripts/cpi_close_test.py   -> reports/cpi_close_test.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading.alpaca import load_bars_file  # noqa: E402

CPI = """2021-12-10 2022-01-12 2022-02-10 2022-03-10 2022-04-12 2022-05-11 2022-06-10 2022-07-13 2022-08-10 2022-09-13
2022-10-13 2022-11-10 2022-12-13 2023-01-12 2023-02-14 2023-03-14 2023-04-12 2023-05-10 2023-06-13 2023-07-12 2023-08-10
2023-09-13 2023-10-12 2023-11-14 2023-12-12 2024-01-11 2024-02-13 2024-03-12 2024-04-10 2024-05-15 2024-06-12 2024-07-11
2024-08-14 2024-09-11 2024-10-10 2024-11-13 2024-12-11 2025-01-15 2025-02-12 2025-03-12 2025-04-10 2025-05-13 2025-06-11
2025-07-15 2025-08-12 2025-09-11 2025-10-24 2025-12-18 2026-01-13 2026-02-13 2026-03-11 2026-04-10 2026-05-13 2026-06-10
2026-07-14 2026-08-12 2026-09-11 2026-10-15""".split()
ALT = {"2026-03-11": "2026-03-18", "2026-10-15": "2026-10-14"}
SYMS = ["SPY", "QQQ", "TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]
COST = 2.0


def daily(sym: str) -> pd.DataFrame:
    m = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=True)
    d = m.groupby(m.index.normalize()).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    d["loc"] = ((d.close - d.low) / (d.high - d.low)).shift(1)       # prior day's close location in its range
    d["ret"] = d.close / d.close.shift(1) - 1                         # prior close -> this close
    d["pnl"] = np.where(d["loc"] > 0.5, -1, 1) * d.ret * 1e4 - COST
    return d.dropna()


def stats(x: pd.Series) -> str:
    if not len(x):
        return "-"
    pf = x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
    return f"{len(x)} | {(x > 0).mean():.0%} | {pf:.1f} | {x.mean():+.0f}"


def main() -> None:
    out = ["# Close location into CPI (rule from X)\n", __doc__.split("\n\n")[1], "",
           "Trades | win % | profit factor | average bps per trade after costs.\n",
           "| Ticker | CPI 2025-now | CPI 2025-now (alt 2026 dates) | CPI 2022-2024 | All CPI | Every other day (baseline) |",
           "|---|---|---|---|---|---|"]
    cpi = pd.DatetimeIndex(CPI)
    alt = pd.DatetimeIndex([ALT.get(x, x) for x in CPI])
    for sym in SYMS:
        d = daily(sym)
        a, b = d[d.index.isin(cpi)].pnl, d[d.index.isin(alt)].pnl
        out.append(f"| {sym} | {stats(a[a.index >= '2025-01-01'])} | {stats(b[b.index >= '2025-01-01'])} | "
                   f"{stats(a[a.index < '2025-01-01'])} | {stats(a)} | {stats(d[~d.index.isin(cpi)].pnl)} |")
    spy = daily("SPY")
    rows = spy[spy.index.isin(cpi) & (spy.index >= "2025-01-01")]
    out.append("\n## SPY trade by trade, 2025 on\n\n| CPI day | Prior close location | Side | SPY prior close -> CPI close | Result bps |\n|---|--:|---|--:|--:|")
    for t, r in rows.iterrows():
        out.append(f"| {t:%Y-%m-%d} | {r['loc']:.2f} | {'short' if r['loc'] > 0.5 else 'long'} | {r.ret:+.2%} | {r.pnl:+.0f} |")
    Path("reports/cpi_close_test.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
