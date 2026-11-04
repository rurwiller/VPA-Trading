"""US stock bars from Alpaca's market-data API (SIP feed, split-adjusted).

Keys come from ALPACA_API_KEY / ALPACA_SECRET_KEY. Output matches data.py: tz-naive
New York time, regular session only (09:30 <= t < 16:00), columns open..volume
(plus trade_count and vwap), so the rest of the code can use it unchanged.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

DATA_URL = "https://data.alpaca.markets/v2/stocks/{sym}/bars"
PAPER_URL = "https://paper-api.alpaca.markets/v2/account"


def _headers() -> dict:
    try:
        return {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]}
    except KeyError as e:
        raise SystemExit(f"missing environment variable {e}") from None


def check_keys() -> dict:
    """Return the paper account record (raises on bad keys)."""
    r = requests.get(PAPER_URL, headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_bars(symbol: str, start: str, end: str, timeframe: str = "1Min", feed: str = "sip",
               session: requests.Session | None = None, regular_only: bool = True) -> pd.DataFrame:
    """Download bars for [start, end) (ISO dates/times, UTC), following pagination."""
    s = session or requests.Session()
    params = {"timeframe": timeframe, "start": start, "end": end, "feed": feed,
              "adjustment": "split", "limit": 10000}
    rows: list[dict] = []
    while True:
        for attempt in range(5):
            r = s.get(DATA_URL.format(sym=symbol), headers=_headers(), params=params, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            break
        else:
            r.raise_for_status()
        j = r.json()
        rows += j.get("bars") or []
        if not j.get("next_page_token"):
            break
        params["page_token"] = j["next_page_token"]
    return to_session_frame(rows, regular_only)


def to_session_frame(rows: list[dict], regular_only: bool = True) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "trade_count", "vwap"])
    df = pd.DataFrame(rows).rename(columns={"t": "timestamps", "o": "open", "h": "high", "l": "low",
                                            "c": "close", "v": "volume", "n": "trade_count", "vw": "vwap"})
    ts = pd.to_datetime(df.pop("timestamps"), utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    df.index = pd.DatetimeIndex(ts, name="timestamps")
    if regular_only:
        df = regular_session(df)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[["open", "high", "low", "close", "volume", "trade_count", "vwap"]].astype(float)


def regular_session(df: pd.DataFrame) -> pd.DataFrame:
    t = df.index.time
    return df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]


def load_bars_file(path: str | Path, regular_only: bool = True) -> pd.DataFrame:
    """Load a saved bar file; files ending -ext hold extended hours (04:00-20:00 NY)."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "timestamps"
    return regular_session(df) if regular_only else df
