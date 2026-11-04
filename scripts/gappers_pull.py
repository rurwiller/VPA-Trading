"""Build a "stocks in play" data set: each day's biggest opening gappers among liquid US stocks, with 1m bars.

1. Universe: active, tradable US stocks on NASDAQ / NYSE / AMEX (ETFs and funds dropped by name).
2. Daily bars for 5 years (SIP, split-adjusted). Screen: prior close >= $5 and prior 20-day average volume >= 1M.
3. Each day, the TOP_N largest |gap| = open / prior close - 1 with |gap| >= MIN_GAP (known at 9:30: no lookahead).
4. 1-minute regular-session bars for those stock-days only.
Note: today's listed stocks only (delisted names missing = survivorship bias, which flatters long trades a little).

  python scripts/gappers_pull.py   -> data/gappers/{universe.csv, daily.csv.gz, events.csv, m1.csv.gz}
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading.alpaca import to_session_frame  # noqa: E402

D = Path("data/gappers")
H = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]}
URL = "https://data.alpaca.markets/v2/stocks/bars"
FUND_WORDS = ("ETF", " FUND", "TRUST", "ETN", "PROSHARES", "DIREXION", "ISHARES", "SPDR", "INVESCO", "VANGUARD",
              "LEVERAGED", "2X", "3X", "-1X", "INVERSE", "ACQUISITION", "WARRANT", " UNITS", "RIGHTS", "NOTES", "DEPOSITARY SHARES REPRESENTING")
MIN_GAP, TOP_N = 0.04, 5
S = requests.Session()


def get(params: dict) -> dict:
    for k in range(8):
        r = S.get(URL, headers=H, params=params, timeout=90)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 + 2 ** k)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def bars(symbols: list[str], start: str, end: str, tf: str) -> list[dict]:
    out, params = [], {"symbols": ",".join(symbols), "timeframe": tf, "start": start, "end": end, "feed": "sip",
                       "adjustment": "split", "limit": 10000}
    while True:
        j = get(params)
        for sym, bs in (j.get("bars") or {}).items():
            for b in bs:
                b["sym"] = sym
                out.append(b)
        if not j.get("next_page_token"):
            return out
        params["page_token"] = j["next_page_token"]


def main() -> None:
    D.mkdir(parents=True, exist_ok=True)
    a = requests.get("https://paper-api.alpaca.markets/v2/assets", headers=H,
                     params={"status": "active", "asset_class": "us_equity"}, timeout=60).json()
    u = pd.DataFrame(a)
    u = u[u.tradable & u.exchange.isin(["NASDAQ", "NYSE", "AMEX"]) & ~u.symbol.str.contains(r"[./ ]", regex=True)]
    u = u[~u.name.str.upper().str.contains("|".join(FUND_WORDS), regex=False)] if False else \
        u[~u.name.str.upper().apply(lambda n: any(w in n for w in FUND_WORDS))]
    u[["symbol", "name", "exchange", "shortable", "easy_to_borrow"]].to_csv(D / "universe.csv", index=False)
    syms = u.symbol.tolist()
    print(f"universe: {len(syms)} stocks", flush=True)
    end = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=20)).floor("D")
    start = end - pd.Timedelta(days=5 * 365 + 40)
    if not (D / "daily.csv.gz").exists():
        rows = []
        for k in range(0, len(syms), 100):
            rows += bars(syms[k:k + 100], start.isoformat(), end.isoformat(), "1Day")
            print(f"daily bars: {k + 100}/{len(syms)} symbols, {len(rows)} bars", flush=True)
        dd = pd.DataFrame(rows).rename(columns={"t": "date", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        dd["date"] = pd.to_datetime(dd.date, utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
        dd[["sym", "date", "open", "high", "low", "close", "volume"]].to_csv(D / "daily.csv.gz", index=False)
    dd = pd.read_csv(D / "daily.csv.gz", parse_dates=["date"]).sort_values(["sym", "date"])
    g = dd.groupby("sym")
    dd["prev_close"] = g.close.shift()
    dd["avg_vol20"] = g.volume.transform(lambda v: v.shift().rolling(20, min_periods=15).mean())
    tr = pd.concat([dd.high - dd.low, (dd.high - dd.prev_close).abs(), (dd.low - dd.prev_close).abs()], axis=1).max(axis=1)
    dd["atr14_prev"] = tr.groupby(dd.sym).transform(lambda x: x.shift().rolling(14, min_periods=10).mean())
    dd["gap"] = dd.open / dd.prev_close - 1
    ok = (dd.prev_close >= 5) & (dd.avg_vol20 >= 1e6) & (dd.gap.abs() >= MIN_GAP)
    ev = dd[ok].copy()
    ev["rank"] = ev.groupby("date").gap.transform(lambda x: x.abs().rank(ascending=False, method="first"))
    ev = ev[ev["rank"] <= TOP_N].sort_values(["date", "rank"])
    ev = ev[ev.date >= start.tz_localize(None).normalize() + pd.Timedelta(days=40)]
    ev.to_csv(D / "events.csv", index=False)
    print(f"events: {len(ev)} stock-days on {ev.date.nunique()} days", flush=True)
    done = set()
    m1p = D / "m1.csv.gz"
    if m1p.exists():
        done = set(pd.read_csv(m1p, usecols=["date"]).date.unique())
    for n, (day, grp) in enumerate(ev.groupby("date")):
        ds = day.strftime("%Y-%m-%d")
        if ds in done:
            continue
        rows = bars(grp.sym.tolist(), f"{ds}T13:00:00Z", f"{ds}T21:30:00Z", "1Min")
        if not rows:
            continue
        f = pd.DataFrame(rows)
        parts = []
        for sym, x in f.groupby("sym"):
            sf = to_session_frame(x.drop(columns="sym").to_dict("records"))
            sf["sym"], sf["date"] = sym, ds
            parts.append(sf)
        pd.concat(parts).to_csv(m1p, mode="a", header=not m1p.exists())
        if n % 50 == 0:
            print(f"1m bars: day {n}/{ev.date.nunique()}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
