"""Indicators computed on one timeframe's session bars (index = bar start, New York time).

ADX/DI and ATR follow TradingView's ta.dmi / ta.atr (Wilder RMA, length 14). Candle and
VPA features follow Anna Coulling's vocabulary: spread = bar range, effort = volume
(relative to the same time of day, so the opening bars are not always "ultra high").
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .willard_osc import _rma


def atr(b: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = b.close.shift()
    tr = pd.concat([b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = b.high.iloc[0] - b.low.iloc[0]
    return _rma(tr, n)


def dmi(b: pd.DataFrame, di_len: int = 14, adx_len: int = 14) -> pd.DataFrame:
    """TradingView ta.dmi: +DI, -DI, ADX."""
    up, dn = b.high.diff(), -b.low.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=b.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=b.index)
    tr = atr(b, di_len)
    pdi, mdi = 100 * _rma(pdm, di_len) / tr, 100 * _rma(mdm, di_len) / tr
    dx = (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pd.DataFrame({"pdi": pdi, "mdi": mdi, "adx": 100 * _rma(dx, adx_len)})


def rvol(b: pd.DataFrame, days: int = 20) -> pd.Series:
    """Volume / average volume of the same time-of-day slot over the previous `days` sessions."""
    slot = b.index.time
    prior = b.volume.groupby(slot).transform(lambda v: v.shift().rolling(days, min_periods=5).mean())
    return b.volume / prior


def candles(b: pd.DataFrame, a: pd.Series) -> pd.DataFrame:
    rng = (b.high - b.low).replace(0, np.nan)
    top, bot = np.maximum(b.open, b.close), np.minimum(b.open, b.close)
    f = pd.DataFrame({
        "upper_frac": (b.high - top) / rng, "lower_frac": (bot - b.low) / rng,
        "body_frac": (top - bot) / rng, "close_pos": (b.close - b.low) / rng,
        "spread_atr": (b.high - b.low) / a, "up_bar": (b.close > b.open).astype(float)}, index=b.index)
    # Inverted hammer / shooting star shape: long upper wick, small body near the low.
    f["inv_hammer"] = ((f.upper_frac >= 0.5) & (f.body_frac <= 0.35) & (f.lower_frac <= 0.2)).astype(float)
    f["hammer"] = ((f.lower_frac >= 0.5) & (f.body_frac <= 0.35) & (f.upper_frac <= 0.2)).astype(float)
    return f


def climaxes(b: pd.DataFrame, f: pd.DataFrame, rv: pd.Series, lookback: int = 20,
             min_rvol: float = 2.0, min_wick: float = 0.4) -> pd.DataFrame:
    """VPA climax bars (Coulling): ultra-high effort at a fresh extreme with the close pushed back.

    buying climax : new `lookback`-bar high, rvol >= min_rvol, upper wick >= min_wick of range
    selling climax: new `lookback`-bar low,  rvol >= min_rvol, lower wick >= min_wick of range
    """
    new_hi = b.high >= b.high.rolling(lookback, min_periods=lookback).max()
    new_lo = b.low <= b.low.rolling(lookback, min_periods=lookback).min()
    return pd.DataFrame({"buy_climax": new_hi & (rv >= min_rvol) & (f.upper_frac >= min_wick),
                         "sell_climax": new_lo & (rv >= min_rvol) & (f.lower_frac >= min_wick)})


def fvgs(b: pd.DataFrame, a: pd.Series, rv: pd.Series, closes_at: pd.Series, min_atr: float = 0.1,
         intraday_only: bool = True) -> pd.DataFrame:
    """Three-bar fair value gaps, known at the close of the third bar.

    bull: low[i] > high[i-2] -> zone [high[i-2], low[i]] (support below price)
    bear: high[i] < low[i-2] -> zone [high[i], low[i-2]] (resistance above price)
    Only gaps of at least `min_atr` x ATR. `disp_rvol` is the middle (displacement) bar's
    relative volume: in VPA terms, how much effort made the gap.
    With intraday_only (default) the three bars must be from the same day; 4h / daily gaps span days.
    """
    h2, l2 = b.high.shift(2), b.low.shift(2)
    same_day = b.index.normalize() == pd.Series(b.index, index=b.index).shift(2).dt.normalize()
    if not intraday_only:
        same_day = pd.Series(True, index=b.index)
    bull = (b.low > h2) & same_day
    bear = (b.high < l2) & same_day
    rows = []
    for d, m, lo_z, hi_z in ((1, bull, h2, b.low), (-1, bear, b.high, l2)):
        g = pd.DataFrame({"dir": d, "bottom": lo_z[m], "top": hi_z[m], "atr": a[m],
                          "disp_rvol": rv.shift()[m], "formed_at": closes_at[m]})
        rows.append(g)
    g = pd.concat(rows).sort_values("formed_at")
    g["size_atr"] = (g.top - g.bottom) / g.atr
    return g[g.size_atr >= min_atr]


def session_vwap(m1: pd.DataFrame) -> pd.Series:
    """Session VWAP from 1m bars (uses each bar's own VWAP when present), value at the bar close."""
    px = m1["vwap"] if "vwap" in m1 else (m1.high + m1.low + m1.close) / 3
    day = m1.index.normalize()
    pv = (px * m1.volume).groupby(day).cumsum()
    return pv / m1.volume.groupby(day).cumsum()
