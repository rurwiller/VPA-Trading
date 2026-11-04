"""Our own gamma exposure (GEX) levels from Alpaca options data (open interest + implied volatility).

Standard dealer convention: customers are assumed net long calls and net short puts, so dealers are short calls
(positive gamma to them is counted +) and long puts (counted -). Per contract:
    GEX ($ per 1% move) = gamma x open interest x 100 x spot^2 x 0.01, calls +, puts -
Levels:
    call wall   strike with the largest call GEX (resistance)
    put wall    strike with the largest put GEX (support)
    gamma flip  spot price where total GEX crosses zero (gamma re-computed with Black-Scholes at each test price);
                above it dealers are long gamma (moves get damped), below it short gamma (moves get amplified)
    net GEX     total at the current price, in $ millions per 1% move
Open interest is the previous session's (OCC publishes it once a day); gamma moves with price all day.
Other sites estimate this differently (expirations included, dealer side assumptions), so walls usually land on the
same strikes but the numbers will not match exactly.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import requests

from .live import TRADE, headers

OPT = "https://data.alpaca.markets/v1beta1/options/snapshots/"
LATEST = "https://data.alpaca.markets/v2/stocks/{}/trades/latest"
RATE = 0.04


def _pages(url: str, params: dict, key: str) -> list:
    out, tok = [], None
    for _ in range(100):
        p = dict(params, **({"page_token": tok} if tok else {}))
        r = requests.get(url, headers=headers(), params=p, timeout=30)
        r.raise_for_status()
        j = r.json()
        part = j.get(key) or ([] if key != "snapshots" else {})
        out.extend(part.items() if isinstance(part, dict) else part)
        tok = j.get("next_page_token")
        if not tok:
            break
    return out


def spot(sym: str) -> float:
    r = requests.get(LATEST.format(sym), headers=headers(), params={"feed": "iex"}, timeout=30)
    r.raise_for_status()
    return float(r.json()["trade"]["p"])


def chain(sym: str, now: pd.Timestamp, max_days: int = 30, band: float = 0.25) -> pd.DataFrame:
    """Contracts expiring within max_days with strikes within +-band of spot: type, strike, expiry, OI, IV."""
    s = spot(sym)
    lo, hi = round(s * (1 - band), 2), round(s * (1 + band), 2)
    last = (now + pd.Timedelta(days=max_days)).strftime("%Y-%m-%d")
    first = (now if now.hour < 16 else now + pd.Timedelta(days=1)).strftime("%Y-%m-%d")   # skip expired same-day options
    con = _pages(TRADE + "/options/contracts", {"underlying_symbols": sym, "expiration_date_gte": first,
                                                "expiration_date_lte": last, "strike_price_gte": lo,
                                                "strike_price_lte": hi, "limit": 10000}, "option_contracts")
    c = pd.DataFrame([{"symbol": x["symbol"], "type": x["type"], "strike": float(x["strike_price"]),
                       "expiry": pd.Timestamp(x["expiration_date"]), "oi": float(x.get("open_interest") or 0)} for x in con])
    if c.empty:
        return c.assign(iv=np.nan, spot=s)
    snaps = _pages(OPT + sym, {"feed": "indicative", "limit": 1000, "expiration_date_gte": first,
                               "expiration_date_lte": last, "strike_price_gte": lo, "strike_price_lte": hi}, "snapshots")
    iv = {k: v.get("impliedVolatility") for k, v in snaps}
    c["iv"] = c.symbol.map(iv).astype(float)
    # fill missing IVs (deep in/out of the money) from the nearest strike of the same expiry and type
    c = c.sort_values(["expiry", "type", "strike"])
    c["iv"] = c.groupby(["expiry", "type"]).iv.transform(lambda v: v.interpolate(limit_direction="both"))
    c["spot"] = s
    return c.dropna(subset=["iv"]).reset_index(drop=True)


def bs_gamma(S: np.ndarray | float, K: np.ndarray, T: np.ndarray, iv: np.ndarray) -> np.ndarray:
    S = np.asarray(S, float)
    d1 = (np.log(S / K) + (RATE + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
    return np.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi) / (S * iv * np.sqrt(T))


def gex_at(c: pd.DataFrame, S: float, now: pd.Timestamp) -> np.ndarray:
    """GEX per contract at test price S ($ per 1% move)."""
    T = np.maximum(((c.expiry + pd.Timedelta(hours=16)) - now).dt.total_seconds().to_numpy() / (365 * 86400), 1 / (365 * 24))
    g = bs_gamma(S, c.strike.to_numpy(), T, c.iv.to_numpy())
    sign = np.where(c.type.to_numpy() == "call", 1.0, -1.0)
    return sign * g * c.oi.to_numpy() * 100 * S * S * 0.01


def levels(sym: str, now: pd.Timestamp | None = None, max_days: int = 30) -> dict:
    now = now or pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    c = chain(sym, now, max_days)
    if c.empty:
        return {"sym": sym}
    S = float(c.spot.iat[0])
    c["gex"] = gex_at(c, S, now)
    by = c.groupby(["strike", "type"]).gex.sum().unstack(fill_value=0.0)
    calls = by.get("call", pd.Series(dtype=float))
    puts = by.get("put", pd.Series(dtype=float))
    net = by.sum(axis=1)
    grid = np.linspace(S * 0.9, S * 1.1, 81)
    tot = np.array([gex_at(c, x, now).sum() for x in grid])
    cross = np.flatnonzero(np.sign(tot[:-1]) != np.sign(tot[1:]))
    flip = np.nan
    if len(cross):
        k = cross[np.argmin(np.abs(grid[cross] - S))]
        flip = float(grid[k] - tot[k] * (grid[k + 1] - grid[k]) / (tot[k + 1] - tot[k]))
    top = lambda s, n=3: [float(x) for x in s.abs().sort_values(ascending=False).index[:n]]  # noqa: E731
    return {"sym": sym, "time": now.strftime("%Y-%m-%d %H:%M"), "spot": round(S, 2),
            "call_wall": top(calls, 1)[0] if len(calls) else np.nan,
            "put_wall": top(puts, 1)[0] if len(puts) else np.nan,
            "flip": round(flip, 2) if flip == flip else np.nan,
            "net_gex_musd": round(float(net.sum()) / 1e6, 1),
            "call_walls": top(calls), "put_walls": top(puts),
            "abs_gex_strikes": top(net, 5), "contracts": len(c), "max_days": max_days}


def near(lv: dict, px: float, a5: float) -> str:
    """Which level (if any) price is at, within 0.5 ATR(5m): 'call wall 400', 'put wall 380', 'flip 388.2' or ''."""
    hits = []
    for name, key in (("call wall", "call_wall"), ("put wall", "put_wall"), ("flip", "flip")):
        v = lv.get(key)
        if v is not None and v == v and abs(px - v) <= 0.5 * a5:
            hits.append(f"{name} {v:g}")
    return ", ".join(hits)
