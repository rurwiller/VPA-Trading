"""Coulling VPA detectors, implemented from docs/vpa-detection-spec.md.

NAMING (Coulling, NOT Wyckoff/VSA - do not "fix" this):
    top of an uptrend, insiders selling      -> SELLING_CLIMAX  (bearish)
    bottom of a downtrend, insiders buying   -> BUYING_CLIMAX   (bullish)
SHOOTING_STAR is a candle shape; UPTHRUST is a false break above a ceiling (spec 3.6).

Every detection at bar i uses bars <= i only and is known at bar i's close.
Thresholds are the spec's [Interp] defaults (Coulling gives no numbers).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BEAR, BULL = -1, 1
VOL_CLASSES = [0, 0.7, 1.3, 2.0, np.inf]
VOL_NAMES = ["LOW", "AVERAGE", "HIGH", "ULTRA_HIGH"]


def relvol_tod(b: pd.DataFrame, days: int = 20) -> pd.Series:
    """Volume / median volume of the same time slot over the prior `days` sessions (spec 1)."""
    prior = b.volume.groupby(b.index.time).transform(lambda v: v.shift().rolling(days, min_periods=5).median())
    return b.volume / prior


def _slope(x: pd.Series, n: int) -> pd.Series:
    t = pd.Series(np.arange(len(x), dtype=float), index=x.index)
    cov = (x * t).rolling(n).mean() - x.rolling(n).mean() * t.rolling(n).mean()
    return cov / t.rolling(n).var(ddof=0)


def _count_true(m: pd.Series, n: int) -> pd.Series:
    return m.astype(float).rolling(n, min_periods=n).sum()


def context(b: pd.DataFrame, atr: pd.Series, lookback: int = 15) -> pd.DataFrame:
    """Trend state (spec 1, pivots omitted), maturity, and position vs recent highs/lows."""
    ema21 = b.close.ewm(span=21, adjust=False).mean()
    slope = _slope(b.close, lookback) / atr
    above = (b.close > ema21).astype(float).rolling(lookback).mean()
    trend = pd.Series(np.where((slope > 0.08) & (above >= 0.6), 1, np.where((slope < -0.08) & (above <= 0.4), -1, 0)),
                      index=b.index)
    run = trend.groupby((trend != trend.shift()).cumsum()).cumcount() + 1
    hi20, lo20 = b.high.rolling(20).max(), b.low.rolling(20).min()
    return pd.DataFrame({"trend": trend, "maturity": run.where(trend != 0, 0),
                         "near_high": b.high >= hi20 - 0.25 * atr, "near_low": b.low <= lo20 + 0.25 * atr,
                         "ceiling": b.high.shift().rolling(20).max(), "floor": b.low.shift().rolling(20).min()})


def detect(b: pd.DataFrame, atr: pd.Series) -> pd.DataFrame:
    """Return one row per detection: index = bar start, columns type, bias, vol_class, repeat."""
    rng = (b.high - b.low).replace(0, np.nan)
    body = (b.close - b.open).abs()
    top, bot = np.maximum(b.open, b.close), np.minimum(b.open, b.close)
    up_w, lo_w = b.high - top, bot - b.low
    close_loc = ((b.close - b.low) / rng).fillna(0.5)
    rv = relvol_tod(b)
    rel_range = (b.high - b.low) / atr
    vol_up = _slope(b.volume, 3) > 0
    c = context(b, atr)
    hi_vol, ultra, low_vol = rv >= 1.3, rv >= 2.0, rv < 0.7
    mature_up, mature_dn = (c.trend == 1) & (c.maturity >= 10), (c.trend == -1) & (c.maturity >= 10)

    # 3.1 premier candle shapes
    star = (up_w >= 2 * body) & (up_w >= 0.5 * rng) & (lo_w <= 0.15 * rng) & (top <= b.low + rng / 3)
    hammer = (lo_w >= 2 * body) & (lo_w >= 0.5 * rng) & (up_w <= 0.15 * rng) & (bot >= b.high - rng / 3)
    ll_doji = (body <= 0.1 * rng) & (up_w >= 0.3 * rng) & (lo_w >= 0.3 * rng) & (rel_range >= 1.0)

    d = {}
    # 3.2 / 3.3: shooting star after a rise or at highs (bearish); hammer after a fall or at lows (bullish)
    d["SHOOTING_STAR"] = (star & ((c.trend == 1) | c.near_high), BEAR)
    d["SHOOTING_STAR_IN_DOWNTREND"] = (star & (c.trend == -1) & ~c.near_high, BEAR)
    d["HAMMER"] = (hammer & ((c.trend == -1) | c.near_low), BULL)
    # 3.4 hanging man: hammer shape at the top on at least average volume
    hm = hammer & ((c.trend == 1) | c.near_high) & (rv >= 1.0)
    d["HANGING_MAN"] = (hm, BEAR)
    hm_recent = hm.shift().rolling(3, min_periods=1).max().fillna(0).astype(bool)
    hm_high = b.high.where(hm).shift().ffill(limit=3)
    d["HANGING_MAN_SHOOTING_STAR"] = (d["SHOOTING_STAR"][0] & hm_recent & ((b.high - hm_high).abs() <= 0.5 * atr), BEAR)
    # 3.5 long-legged doji on high volume at an extreme: WAIT, scored both ways by the caller
    d["LL_DOJI_HIGH_VOL_AT_HIGH"] = (ll_doji & hi_vol & c.near_high, BEAR)
    d["LL_DOJI_HIGH_VOL_AT_LOW"] = (ll_doji & hi_vol & c.near_low, BULL)

    # 5.1 stopping volume (3-bar window inside a mature downtrend)
    sv = mature_dn.shift(2, fill_value=False) & (_count_true(hi_vol, 3) >= 3) & \
        (_count_true(lo_w >= 0.3 * rng, 3) >= 2) & (_count_true(close_loc >= 0.35, 3) >= 2)
    d["STOPPING_VOLUME"] = (sv & ~sv.shift(fill_value=False), BULL)
    # 5.2 topping out volume (4-bar window inside a mature uptrend, arcing over)
    flat = b.high.rolling(2).max() - b.high.shift(2).rolling(2).max() < 0.25 * atr
    to = mature_up.shift(3, fill_value=False) & (_count_true(hi_vol, 4) >= 3) & vol_up & \
        (_count_true(up_w >= 0.3 * rng, 4) >= 3) & (_count_true(close_loc <= 0.5, 4) >= 3) & flat
    d["TOPPING_OUT_VOLUME"] = (to & ~to.shift(fill_value=False), BEAR)
    # 5.3 / 5.4 climaxes as 3-bar processes after an extended trend
    win_rng = (b.high.rolling(3).max() - b.low.rolling(3).min())
    net = b.close - b.open.shift(2)
    climax_vol = (_count_true(hi_vol, 3) >= 2) & (ultra.rolling(3).max() > 0)
    sc = mature_up.shift(2, fill_value=False) & climax_vol & (_count_true(up_w >= 0.4 * rng, 3) >= 2) & \
        (win_rng >= 2.0 * atr) & (net <= 0.5 * atr) & (c.near_high.rolling(3).max() > 0)
    bc = mature_dn.shift(2, fill_value=False) & climax_vol & (_count_true(lo_w >= 0.4 * rng, 3) >= 2) & \
        (win_rng >= 2.0 * atr) & (net >= -0.5 * atr) & (c.near_low.rolling(3).max() > 0)
    d["SELLING_CLIMAX"] = (sc & ~sc.shift(fill_value=False), BEAR)
    d["BUYING_CLIMAX"] = (bc & ~bc.shift(fill_value=False), BULL)

    # 6. tests within 30 bars after a climax / stopping volume / topping out
    def _after(ev: pd.Series, n: int = 30) -> pd.Series:
        return ev.astype(float).shift().rolling(n, min_periods=1).max().fillna(0).astype(bool)

    bc_low = b.low.where(d["BUYING_CLIMAX"][0] | d["STOPPING_VOLUME"][0]).ffill()
    sc_high = b.high.where(d["SELLING_CLIMAX"][0] | d["TOPPING_OUT_VOLUME"][0]).ffill()
    tos = _after(d["BUYING_CLIMAX"][0] | d["STOPPING_VOLUME"][0]) & (b.low <= bc_low + 0.5 * atr) & \
        (close_loc >= 0.5) & (lo_w >= 0.3 * rng)
    tod = _after(d["SELLING_CLIMAX"][0] | d["TOPPING_OUT_VOLUME"][0]) & (b.high >= sc_high - 0.5 * atr) & \
        (close_loc <= 0.5) & (up_w >= 0.3 * rng)
    d["TEST_OF_SUPPLY_PASSED"] = (tos & low_vol, BULL)
    d["TEST_OF_DEMAND_PASSED"] = (tod & low_vol, BEAR)

    # Appendix A: no demand / no supply
    narrow = rel_range < 0.7
    d["NO_DEMAND"] = ((b.close > b.open) & narrow & low_vol & (c.trend == 1), BEAR)
    d["NO_SUPPLY"] = ((b.close < b.open) & narrow & low_vol & (c.trend == -1), BULL)

    # 8.4-8.7 against a 20-bar congestion zone (range <= 3 ATR)
    congest = (c.ceiling - c.floor) <= 3.0 * atr
    d["UPTHRUST"] = (congest & (b.high > c.ceiling) & (b.close < c.ceiling) & (up_w >= 0.4 * rng), BEAR)
    d["SPRING"] = (congest & (b.low < c.floor) & (b.close > c.floor) & (lo_w >= 0.4 * rng), BULL)
    d["VALID_BREAKOUT_UP"] = (congest & (b.close > c.ceiling + 0.25 * atr) & (rv >= 1.5) & vol_up, BULL)
    d["VALID_BREAKOUT_DOWN"] = (congest & (b.close < c.floor - 0.25 * atr) & (rv >= 1.5) & vol_up, BEAR)
    d["FALSE_BREAKOUT_UP"] = (congest & (b.close > c.ceiling) & (rv < 1.0), BEAR)
    d["FALSE_BREAKOUT_DOWN"] = (congest & (b.close < c.floor) & (rv < 1.0), BULL)

    vc = pd.cut(rv, VOL_CLASSES, labels=VOL_NAMES, right=False).astype(str)
    rows = []
    for name, (m, bias) in d.items():
        m = m.fillna(False).astype(bool)
        if not m.any():
            continue
        r = pd.DataFrame({"type": name, "bias": bias, "vol_class": vc[m], "relvol": rv[m],
                          "trend": c.trend[m]}, index=b.index[m])
        if name in ("SHOOTING_STAR", "HAMMER"):  # spec 4: repeats in the same price area
            px = b.high if name == "SHOOTING_STAR" else b.low
            idx = np.flatnonzero(m.to_numpy())
            pv, av = px.to_numpy(), atr.to_numpy()
            r["repeat"] = [1 + sum(1 for j in idx if i - 10 <= j < i and abs(pv[j] - pv[i]) <= 0.5 * av[i]) for i in idx]
        rows.append(r)
    out = pd.concat(rows).sort_index()
    out.index.name = "timestamps"
    return out


def signal_flags(det: pd.DataFrame, index: pd.Index, within: int = 3) -> pd.DataFrame:
    """Per bar: was there any bullish / bearish detection in the last `within` bars (incl. this one)?"""
    out = pd.DataFrame(index=index)
    for bias, name in ((BULL, "vpa_bull"), (BEAR, "vpa_bear")):
        hit = pd.Series(0.0, index=index)
        hit.loc[det.index[det.bias == bias].unique()] = 1.0
        out[name] = hit.rolling(within, min_periods=1).max()
    ss = pd.Series(0.0, index=index)
    ss.loc[det.index[det.type.isin(["SHOOTING_STAR", "HANGING_MAN_SHOOTING_STAR"])].unique()] = 1.0
    hm = pd.Series(0.0, index=index)
    hm.loc[det.index[det.type == "HAMMER"].unique()] = 1.0
    out["star_recent"], out["hammer_recent"] = ss.rolling(within, min_periods=1).max(), hm.rolling(within, min_periods=1).max()
    return out
