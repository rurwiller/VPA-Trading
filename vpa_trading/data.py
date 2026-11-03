"""US stock bars from Yahoo Finance's chart API (free, unofficial, can lag).

Timestamps come back as tz-naive New York time, regular session only.
"""
from __future__ import annotations

import gzip
import json
import urllib.request
from pathlib import Path

import pandas as pd

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={iv}&includePrePost=false"


def parse_yahoo_chart(payload: dict) -> pd.DataFrame:
    r = payload["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    tz = r["meta"].get("exchangeTimezoneName", "America/New_York")
    ts = pd.to_datetime(r["timestamp"], unit="s", utc=True).tz_convert(tz).tz_localize(None)
    df = pd.DataFrame({k: q[k] for k in ["open", "high", "low", "close", "volume"]}, index=ts)
    df.index.name = "timestamps"
    df = df.dropna()
    # Yahoo appends a live, still-forming tick whose time is not on the bar grid.
    step = df.index.to_series().diff().mode().iloc[0]
    on_grid = (df.index - df.index.normalize()) % step == pd.Timedelta(0)
    df = df[on_grid]
    t = df.index.time
    df = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
    return df[~df.index.duplicated(keep="last")].astype(float)


def load_yahoo_file(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt") as f:
        return parse_yahoo_chart(json.load(f))


def fetch_yahoo(symbol: str, interval: str = "5m", rng: str = "60d", timeout: float = 20) -> pd.DataFrame:
    """Yahoo serves 5m bars for the last 60 days, 1h for ~2 years, 1d for decades."""
    req = urllib.request.Request(YAHOO.format(sym=symbol, rng=rng, iv=interval),
                                 headers={"User-Agent": "Mozilla/5.0 (vpa-trading)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_yahoo_chart(json.load(resp))


def resample_bars(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Aggregate session bars to a coarser size (e.g. 5m -> 15m), one session at a time.

    Bins start at 9:30 as on a chart: 15m/30m bins at 9:30, 9:45 ...; 1h bins at 9:30, 10:30 ...
    A partial last bin (an incomplete or early-closed session) is kept.
    """
    rule = interval.replace("m", "min") if interval.endswith("m") else interval
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    # Hourly bins start at 9:30 like a TradingView chart (9:30, 10:30 ... 15:30 short bar).
    off = "30min" if pd.Timedelta(rule) >= pd.Timedelta("1h") else None
    out = df.groupby(df.index.date, group_keys=False).apply(lambda d: d.resample(rule, offset=off).agg(agg))
    out.index.name = "timestamps"
    return out.dropna()
