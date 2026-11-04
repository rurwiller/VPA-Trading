"""Fibonacci retracements / extensions from higher-timeframe swings (1h and daily).

The swing ("top to bottom") is the latest confirmed pivot high and pivot low on that timeframe
(pivot = highest/lowest of k bars each side, known k bars later - no lookahead).
  up leg   (low came first, then the high): retracements H - r*R are SUPPORT below price,
           extensions L + e*R above the high are where an up move may exhaust.
  down leg (high first, then the low): retracements L + r*R are RESISTANCE above price,
           extensions H - e*R below the low.
Golden pocket = the 0.618-0.65 retracement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .research import asof

RETR = [0.382, 0.5, 0.618, 0.65, 0.786]
EXT = [1.272, 1.618]


def daily_bars(m1: pd.DataFrame) -> pd.DataFrame:
    d = m1.groupby(m1.index.normalize()).agg(open=("open", "first"), high=("high", "max"),
                                             low=("low", "min"), close=("close", "last"))
    d["closes_at"] = d.index + pd.Timedelta(hours=16)
    return d


def legs(b: pd.DataFrame, k: int) -> pd.DataFrame:
    """Confirmed pivots of frame `b` (needs closes_at): one row per pivot, time it became known."""
    h, l = b.high, b.low
    ph = h == h.rolling(2 * k + 1, center=True).max()
    pl = l == l.rolling(2 * k + 1, center=True).min()
    known = b.closes_at.shift(-k)              # pivot at j is known when bar j+k closes
    rows = [pd.DataFrame({"kind": "H", "price": h[ph], "pivot_time": b.index[ph], "closes_at": known[ph]}),
            pd.DataFrame({"kind": "L", "price": l[pl], "pivot_time": b.index[pl], "closes_at": known[pl]})]
    return pd.concat(rows).dropna(subset=["closes_at"]).sort_values("closes_at")


def state(piv: pd.DataFrame, times: np.ndarray) -> pd.DataFrame:
    """Latest confirmed pivot high and low (with their bar times) at each time."""
    out = {}
    for kind in ("H", "L"):
        p = piv[piv.kind == kind][["closes_at", "price", "pivot_time"]].copy()
        p["pt"] = p.pivot_time.astype("int64")
        v = asof(p, times, ["price", "pt"])
        out[kind], out[kind + "t"] = v.price.to_numpy(), v.pt.to_numpy()
    H, L = out["H"], out["L"]
    up = out["Ht"] > out["Lt"]                 # most recent extreme is the high -> up leg (L -> H)
    R = H - L
    return pd.DataFrame({"H": H, "L": L, "R": R, "up": up, "leg_id": np.where(up, out["Ht"], out["Lt"])})


def levels(st: pd.DataFrame) -> dict:
    H, L, R, up = st.H.to_numpy(), st.L.to_numpy(), st.R.to_numpy(), st.up.to_numpy()
    lv = {}
    for r in RETR:
        lv[f"r{r}"] = np.where(up, H - r * R, L + r * R)
    for e in EXT:
        lv[f"e{e}"] = np.where(up, L + e * R, H - e * R)
    return lv


def features(st: pd.DataFrame, px: np.ndarray, atr: np.ndarray, d: np.ndarray, tag: str, near: float = 0.25) -> pd.DataFrame:
    """For a trade in direction d at price px: is it at a fib level that fits the trade?
    fits a long: up-leg retracement (support) or down-leg extension (exhaustion below)."""
    lv = levels(st)
    up = st.up.to_numpy()
    ok = (st.R.to_numpy() > 0)
    retr_fit = np.where(d > 0, up, ~up)          # long at support of an up leg / short at resistance of a down leg
    ext_fit = np.where(d > 0, ~up, up)
    dist_r = np.min(np.column_stack([np.abs(px - lv[f"r{r}"]) for r in RETR]), axis=1) / atr
    dist_e = np.min(np.column_stack([np.abs(px - lv[f"e{e}"]) for e in EXT]), axis=1) / atr
    gp_lo = np.minimum(lv["r0.618"], lv["r0.65"]) - 0.1 * atr
    gp_hi = np.maximum(lv["r0.618"], lv["r0.65"]) + 0.1 * atr
    in_gp = (px >= gp_lo) & (px <= gp_hi)
    return pd.DataFrame({
        f"fib{tag}_retr": ok & retr_fit & (dist_r <= near),
        f"fib{tag}_gp": ok & retr_fit & in_gp,
        f"fib{tag}_ext": ok & ext_fit & (dist_e <= near),
        f"fib{tag}_any": ok & (((dist_r <= near) & retr_fit) | ((dist_e <= near) & ext_fit)),
        f"fib{tag}_range_atr": st.R.to_numpy() / atr,
    })


def gp_touch_events(s, st: pd.DataFrame, tag: str) -> pd.DataFrame:
    """First touch of each leg's golden pocket from the right side (1m bars, entry window)."""
    from .research import _in_window
    lv = levels(st)
    up = st.up.to_numpy()
    edge = np.where(up, np.maximum(lv["r0.618"], lv["r0.65"]), np.minimum(lv["r0.618"], lv["r0.65"]))
    lo, hi, c = (s.m1[k].to_numpy() for k in ("low", "high", "close"))
    prev_c = np.r_[c[0], c[:-1]]
    touch = np.where(up, (prev_c > edge) & (lo <= edge), (prev_c < edge) & (hi >= edge)) & (st.R.to_numpy() > 0)
    idx = np.flatnonzero(touch)
    leg = st.leg_id.to_numpy()
    first = pd.Series(idx).groupby(leg[idx]).head(1).to_numpy()   # one touch per leg
    first = first[_in_window(s, first)]
    stretch = np.where(up[first], -1, 1)                           # up leg: price fell into support
    rows = []
    for mode in ("fade", "cont"):
        rows.append(pd.DataFrame({"sym": s.name, "i": first, "stretch": stretch,
                                  "dir": -stretch if mode == "fade" else stretch, "family": "fib_gp",
                                  "variant": tag, "mode": mode}))
    return pd.concat(rows, ignore_index=True)
