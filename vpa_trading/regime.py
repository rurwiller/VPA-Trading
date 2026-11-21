"""Daily market-regime features, each known BEFORE the trading day starts (computed from the prior session's close).

  spy_above200  SPY closed above its 200-day average
  spy_20d       SPY's return over the prior 20 sessions
  breadth50     share of today's S&P 500 members (data/daily) that closed above their own 50-day average
                (survivorship caveat: today's members only)
  vol20         SPY's 20-day realized volatility, annualized
  qqq_above50   QQQ closed above its 50-day average
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DAILY = Path("data/daily")
OUT = Path("results/regime_daily.csv")


def _close(sym):
    return pd.read_csv(DAILY / f"{sym}.csv.gz", index_col=0, parse_dates=True).close


def build(members: list[str] | None = None) -> pd.DataFrame:
    if members is None:
        members = pd.read_csv("data/sp500/constituents.csv").Symbol.tolist()
    spy, qqq = _close("SPY"), _close("QQQ")
    above = []
    for s in members:
        p = DAILY / f"{s}.csv.gz"
        if p.exists():
            c = _close(s)
            above.append((c > c.rolling(50).mean()).where(c.rolling(50).count() >= 50).rename(s))
    br = pd.concat(above, axis=1).reindex(spy.index).mean(axis=1)
    f = pd.DataFrame({
        "spy_above200": spy > spy.rolling(200).mean(),
        "spy_20d": spy / spy.shift(20) - 1,
        "breadth50": br,
        "vol20": np.log(spy).diff().rolling(20).std() * np.sqrt(252),
        "qqq_above50": qqq > qqq.rolling(50).mean(),
    })
    f = f.shift(1)                       # known before the session: yesterday's close
    OUT.parent.mkdir(exist_ok=True)
    f.to_csv(OUT)
    return f


def load() -> pd.DataFrame:
    return pd.read_csv(OUT, index_col=0, parse_dates=True) if OUT.exists() else build()
