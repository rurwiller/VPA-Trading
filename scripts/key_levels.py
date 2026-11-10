"""Morning key-levels sheet: the strongest zones above and below each stock, ranked, before the open.

  python scripts/key_levels.py                 # Mag 7 + QQQ + SPY, today
  python scripts/key_levels.py --symbols TSLA NVDA --top 5

Levels come from vpa_trading/keylevels.py on full-tape (SIP) history: 1m bars with premarket for about 150 days (cached in
logs/keylevels/cache/, only new days are downloaded) and 2 years of daily bars. Our gamma walls and any hand-entered levels
(data/levels/, e.g. Banks) are added as their own families. Written to logs/keylevels/<date>.csv (every raw level; the
scanner reads it to tag signals) and <date>.md (the sheet), plus one line to paste into the TradingView script
pine/key_levels.pine. Run it after 07:15 MST so the premarket high / low are in.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import gex as GX, keylevels as K, levels as LVL, live as LV  # noqa: E402
from vpa_trading.alpaca import to_session_frame  # noqa: E402

UNIVERSE = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "QQQ", "SPY"]
DIR = K.SHEET_DIR
KEEP_DAYS = 150


def minute_history(syms: list[str], now: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """1m bars 04:00-20:00 ET for the last KEEP_DAYS days, from the cache plus whatever is new (SIP, 15 minutes delayed)."""
    cache = DIR / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    end = now - pd.Timedelta(minutes=16)
    old, start = {}, {}
    for s in syms:
        f = cache / f"{s}.csv.gz"
        old[s] = pd.read_csv(f, index_col=0, parse_dates=True) if f.exists() else None
        start[s] = old[s].index[-1].normalize() if old[s] is not None and len(old[s]) else now.normalize() - pd.Timedelta(days=KEEP_DAYS)
    out = {}
    for t0 in sorted(set(start.values())):
        group = [s for s in syms if start[s] == t0]
        params = {"symbols": ",".join(group), "timeframe": "1Min", "start": t0.tz_localize("America/New_York").isoformat(),
                  "end": end.tz_localize("America/New_York").isoformat(), "feed": "sip", "adjustment": "split", "limit": 10000}
        rows: dict[str, list] = {s: [] for s in group}
        while True:
            j = LV._get(LV.DATA, params)
            for s, bs in (j.get("bars") or {}).items():
                rows[s] += bs
            if not j.get("next_page_token"):
                break
            params["page_token"] = j["next_page_token"]
        for s in group:
            new = to_session_frame(rows[s], regular_only=False)
            m = new if old[s] is None else pd.concat([old[s][old[s].index < t0], new])
            m = m[~m.index.duplicated(keep="last")].sort_index()
            m = m[m.index >= now.normalize() - pd.Timedelta(days=KEEP_DAYS)]
            m.to_csv(cache / f"{s}.csv.gz")
            out[s] = m
    return out


def extras(sym: str, now: pd.Timestamp, posted: pd.DataFrame) -> list[tuple[float, str]]:
    ex: list[tuple[float, str]] = []
    try:
        g = GX.levels(sym, now)
        for key, kind in (("call_wall", "call_wall"), ("put_wall", "put_wall"), ("flip", "gamma_flip")):
            v = g.get(key)
            if v is not None and v == v:
                ex.append((float(v), kind))
    except Exception as e:      # options data is optional
        print(f"  (no gamma levels for {sym}: {str(e)[:60]})", file=sys.stderr)
    for r in posted[posted.sym == sym].itertuples():
        ex += [(float(r.lo), "posted")] + ([(float(r.hi), "posted")] if r.hi != r.lo else [])
    return ex


def build(syms: list[str], now: pd.Timestamp | None = None, top: int = 4) -> tuple[pd.DataFrame, str, str]:
    """(raw levels table, the sheet as markdown, the TradingView paste line)."""
    now = now or pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    m1 = minute_history(syms, now)
    daily = LV.fetch_bars(syms, now - pd.Timedelta(days=760), now - pd.Timedelta(minutes=16), tf="1Day", feed="sip")
    posted = LVL.load(now)
    raw_rows, md, paste = [], [f"# Key levels, {now:%a %b %d %Y} (made {now - pd.Timedelta(hours=2):%H:%M} MST)\n"], []
    for s in syms:
        d = daily[s]
        d = d[d.index < now.normalize()]                       # completed sessions only
        ctx = K.Context(m1[s], d, today=now)
        i = ctx.index_of(now)
        spot, adr, tol = float(m1[s].close.iloc[-1]), float(ctx.adr[i]), ctx.tol(i)      # latest print (premarket before the open)
        raw = ctx.raw(i) + extras(s, now, posted)
        zones = K.cluster(raw, tol)
        up, dn = K.select(zones, spot, adr, n=top)
        raw_rows += [dict(sym=s, price=round(p, 2), kind=k, tol=round(tol, 3), adr=round(adr, 2), spot=round(spot, 2)) for p, k in raw]
        md.append(f"\n## {s}  {spot:.2f}  (average day's range ${adr:.2f})\n")
        md.append("| Zone | Score | From price | What is there |\n|---|--:|--:|---|")
        for z in list(reversed(up)) + ["px"] + dn:
            if z == "px":
                md.append(f"| **price {spot:.2f}** | | | |")
                continue
            md.append(f"| {z.price()} | {z.score:g} | {(z.mid / spot - 1) * 100:+.1f}% | {z.label(4)} |")
            paste.append(f"{s}|{z.lo:.2f}|{z.hi:.2f}|{z.score:g}|{z.label(2)}")
    return pd.DataFrame(raw_rows), "\n".join(md) + "\n", ";".join(paste)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=UNIVERSE)
    ap.add_argument("--top", type=int, default=4, help="zones kept above and below the price")
    a = ap.parse_args()
    now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    raw, md, paste = build([s.upper() for s in a.symbols], now, a.top)
    DIR.mkdir(parents=True, exist_ok=True)
    raw.to_csv(DIR / f"{now:%Y-%m-%d}.csv", index=False)
    (DIR / f"{now:%Y-%m-%d}.md").write_text(md)
    (DIR / f"{now:%Y-%m-%d}_tradingview.txt").write_text(paste + "\n")
    print(md)
    print(f"TradingView paste line saved to {DIR}/{now:%Y-%m-%d}_tradingview.txt ({len(paste)} characters)")


if __name__ == "__main__":
    main()
