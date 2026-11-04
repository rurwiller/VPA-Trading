"""Live supply/demand zones for a stock, ranked by strength (same rules as scripts/sd_zone_test.py).

Pulls recent bars from Alpaca (1-minute for the last ~90 sessions -> 1h and 4h candles; daily candles for ~2 years),
finds base-then-impulse zones on 1h / 4h / daily, drops zones a later close has broken, and ranks the rest.

  strength = impulse size (candle range / ATR) x timeframe weight (1h 1, 4h 2, D 4) / (1 + 0.5 x retests)
  retests  = separate visits back into the zone after it formed

  python scripts/zones_now.py TSLA [NVDA ...] [--top 6]     -> prints a table, writes results/zones_now/<SYM>.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import alpaca, fib, indicators as ind  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402
from sd_zone_test import zones  # noqa: E402

WEIGHT = {"1h": 1.0, "4h": 2.0, "D": 4.0}


def fetch(sym: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    now = pd.Timestamp.now(tz="UTC")
    end = (now - pd.Timedelta(minutes=20)).floor("min")      # free plan: no SIP data from the last 15 minutes
    m1 = alpaca.fetch_bars(sym, (end - pd.Timedelta(days=130)).isoformat(), end.isoformat())
    d = alpaca.fetch_bars(sym, (end - pd.Timedelta(days=730)).isoformat(), end.isoformat(), timeframe="1Day",
                          regular_only=False)
    d.index = d.index.normalize()
    return m1, d


def live_zones(sym: str) -> tuple[pd.DataFrame, float]:
    m1, d = fetch(sym)
    frames = {"1h": V.frame(m1, "60m"), "4h": V.frame(m1, "4h")}
    d = d[["open", "high", "low", "close", "volume"]].copy()
    d["closes_at"] = d.index + pd.Timedelta(hours=16)
    d["atr"] = ind.atr(d)
    frames["D"] = d
    price = float(m1.close.iloc[-1])
    rows = []
    for tf, b in frames.items():
        z = zones(b)
        if not len(z):
            continue
        z = z[z.broken_at == pd.Timestamp.max]                        # still unbroken at the last close
        for _, r in z.iterrows():
            i = int(r.made)
            imp = (b.high.iat[i] - b.low.iat[i]) / b.atr.iat[i]
            hh, ll = b.high.to_numpy()[i + 1:], b.low.to_numpy()[i + 1:]
            touching = (ll <= r.top) & (hh >= r.bottom)
            retests = int((touching & ~np.r_[False, touching[:-1]]).sum())   # separate visits, not candles
            rows.append(dict(sym=sym, tf=tf, type="demand" if r.kind > 0 else "supply",
                             bottom=round(r.bottom, 2), top=round(r.top, 2), formed=b.index[i],
                             impulse_atr=round(imp, 2), retests=retests,
                             strength=round(imp * WEIGHT[tf] / (1 + 0.5 * retests), 2)))
    zt = pd.DataFrame(rows)
    if len(zt):
        zt["distance_%"] = np.where(zt.type == "demand", (zt.top - price) / price * 100, (zt.bottom - price) / price * 100).round(2)
        # a demand zone above price (or supply below) has been traded through without a close beyond it: keep, but flag
        zt["side"] = np.where(((zt.type == "demand") & (zt.top < price)) | ((zt.type == "supply") & (zt.bottom > price)),
                              "ok", "price inside / beyond")
    return zt, price


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--top", type=int, default=6)
    a = ap.parse_args()
    Path("results/zones_now").mkdir(parents=True, exist_ok=True)
    for sym in a.symbols:
        zt, price = live_zones(sym.upper())
        zt.to_csv(f"results/zones_now/{sym.upper()}.csv", index=False)
        print(f"\n{sym.upper()}  last price {price:.2f}  ({len(zt)} live zones)")
        cols = ["tf", "bottom", "top", "distance_%", "impulse_atr", "retests", "strength", "formed"]
        for typ, label in (("supply", "SUPPLY above (strongest first)"), ("demand", "DEMAND below (strongest first)")):
            t = zt[zt.type == typ].sort_values("strength", ascending=False).head(a.top)
            print(f"  {label}")
            print(t[cols].to_string(index=False) if len(t) else "  (none)")


if __name__ == "__main__":
    main()
