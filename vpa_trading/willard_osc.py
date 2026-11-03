"""Willard 3.0 Hybrid Oscillator: Python port of the core oscillator (f_hybrid).

Ported from the user's Pine Script v6 indicator "Willard 3.0 Hybrid Oscillator"
(lines 1-130: MACD + RSI + ROC + VWAP z-score, stochastic blend, 20-bar
normalisation, Ehlers super smoother, clamped to 0-100). Defaults are the
indicator's defaults at Sensitivity "Medium" with Source "Close".

Pine built-ins are reproduced as Pine computes them (EMA/RMA seeded with an SMA,
na propagation, nz() in the smoother), so values should match TradingView on the
same bars once enough history has passed for the seeds to wash out.

Not ported: the multi-timeframe setup/trigger system, PSAR, VPA candles,
Fire & Ice and the scorecard (lines 131+).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

SENSITIVITY = {"Low": 1.5, "Medium": 1.0, "High": 0.5}


def _pine_ema(x: pd.Series, n: int, alpha: float | None = None) -> pd.Series:
    """ta.ema (alpha=2/(n+1)) or ta.rma (alpha=1/n): SMA seed over the first n valid values."""
    a = 2 / (n + 1) if alpha is None else alpha
    v = x.to_numpy(float)
    out = np.full(len(v), np.nan)
    prev, seed = np.nan, []
    for i, xi in enumerate(v):
        if np.isnan(xi):
            continue  # Pine keeps the previous state across na inputs
        if np.isnan(prev):
            seed.append(xi)
            if len(seed) == n:
                prev = sum(seed) / n
                out[i] = prev
            continue
        prev = a * xi + (1 - a) * prev
        out[i] = prev
    return pd.Series(out, index=x.index)


def _rma(x: pd.Series, n: int) -> pd.Series:
    return _pine_ema(x, n, alpha=1 / n)


def _rsi(x: pd.Series, n: int) -> pd.Series:
    d = x.diff()
    up, dn = _rma(d.clip(lower=0), n), _rma((-d).clip(lower=0), n)
    r = 100 - 100 / (1 + up / dn)
    r[(dn == 0) & up.notna()] = 100.0  # Pine: down == 0 ? 100 : up == 0 ? 0 : ...
    return r


def _sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def _lowest(x, n):
    return x.rolling(n, min_periods=n).min()


def _highest(x, n):
    return x.rolling(n, min_periods=n).max()


def _stoch_self(x: pd.Series, n: int) -> pd.Series:
    """ta.stoch(x, x, x, n); na when the range is zero (Pine divides by zero -> na)."""
    lo, hi = _lowest(x, n), _highest(x, n)
    rng = (hi - lo).replace(0, np.nan)
    return 100 * (x - lo) / rng


def _normalise(x: pd.Series, n: int) -> pd.Series:
    """(x - lowest) / (highest - lowest) * 100, or 50 when the range is flat.

    Pine's ternary: a na comparison is false, so na highest/lowest -> 50 as well.
    """
    lo, hi = _lowest(x, n), _highest(x, n)
    flat = ~(hi != lo) | hi.isna() | lo.isna()
    out = (x - lo) / (hi - lo) * 100
    return out.where(~flat, 50.0)


def _ehlers(x: pd.Series, length: int) -> pd.Series:
    a1 = math.exp(-math.pi * math.sqrt(2) / length)
    c2 = 2 * a1 * math.cos(math.sqrt(2) * math.pi / length)
    c3 = -a1 * a1
    c1 = (1 - c2 - c3) / 2
    v = x.to_numpy(float)
    f = np.full(len(v), np.nan)
    nz = lambda z: 0.0 if np.isnan(z) else z  # noqa: E731
    for i in range(len(v)):
        f[i] = c1 * (v[i] + nz(v[i - 1] if i else np.nan)) + c2 * nz(f[i - 1] if i else np.nan) \
            + c3 * nz(f[i - 2] if i > 1 else np.nan)
    return pd.Series(f, index=x.index)


def willard_osc(df: pd.DataFrame, sensitivity: str = "Medium", fast=12, slow=26, rsi_len=6,
                stoch_len=6, smooth_k=2, ehlers_len=2, roc_len=6, vwapz_len=9,
                w_macd=3.0, w_rsi=0.5, w_vwapz=6.0) -> pd.DataFrame:
    """Return columns osc (0-100, the plotted value) and roc, indexed like df."""
    m = SENSITIVITY[sensitivity]
    fast, slow, rsi_len, stoch_len, smooth_k, ehlers_len, roc_len, vwapz_len = (
        int(round(v * m)) for v in (fast, slow, rsi_len, stoch_len, smooth_k, ehlers_len, roc_len, vwapz_len))
    src, vol = df["close"].astype(float), df["volume"].astype(float)

    macd = _pine_ema(src, fast) - _pine_ema(src, slow)
    rsi = _rsi(src, rsi_len)
    roc = 100 * (src - src.shift(roc_len)) / src.shift(roc_len)
    s_macd = (macd + roc) / 2
    s_rsi = (rsi + roc) / 2

    vw_mean = (vol * src).rolling(vwapz_len, min_periods=vwapz_len).sum() / \
        vol.rolling(vwapz_len, min_periods=vwapz_len).sum()
    vw_sd = np.sqrt(_sma((src - vw_mean) ** 2, vwapz_len))
    vwapz = ((src - vw_mean) / vw_sd).where(vw_sd != 0, 0.0)
    vwapz[vw_sd.isna()] = np.nan
    n_vwapz = _normalise(vwapz, vwapz_len)

    st = lambda x: _sma(_stoch_self(x, stoch_len), smooth_k) * 0.3 + x * 0.7  # noqa: E731
    hybrid = (st(s_macd) * w_macd + st(s_rsi) * w_rsi + st(n_vwapz) * w_vwapz) / (w_macd + w_rsi + w_vwapz)
    osc = _ehlers(_normalise(hybrid, 20), ehlers_len).clip(0, 100)
    return pd.DataFrame({"osc": osc, "roc": roc}, index=df.index)
