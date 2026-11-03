"""Multi-timeframe oscillator rule: a slow and a fast Willard oscillator at an extreme together.

Slow timeframe values are used only once their bar has CLOSED (the indicator's "Confirmed"
mode), so nothing leaks from the future. All timestamps are bar *start* times, New York.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import resample_bars
from .willard_osc import willard_osc

SESSION_END = pd.Timedelta(hours=16)


def osc_on(bars1m: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Session bars of `interval` built from 1m bars, with the oscillator and bar close time."""
    b = bars1m if interval == "1m" else resample_bars(bars1m[["open", "high", "low", "close", "volume"]], interval)
    b = b.copy()
    b["osc"] = willard_osc(b).osc
    step = pd.Timedelta(interval.replace("m", "min")) if interval.endswith("m") else pd.Timedelta(interval)
    day = b.index.normalize()
    b["closes_at"] = np.minimum((b.index + step).values, (day + SESSION_END).values)
    return b


def closed_value(slow: pd.DataFrame, at: pd.DatetimeIndex, col: str = "osc") -> pd.Series:
    """Latest slow-bar value whose bar has closed by each time in `at` (backward as-of join)."""
    s = slow[["closes_at", col]].dropna().sort_values("closes_at")
    left = pd.DataFrame({"t": at}).sort_values("t")
    m = pd.merge_asof(left, s, left_on="t", right_on="closes_at", direction="backward")
    return pd.Series(m[col].to_numpy(), index=pd.DatetimeIndex(m["t"]), name=col).reindex(at)


def signals(fast: pd.DataFrame, slow_osc: pd.Series, lvl_slow: float, lvl_fast: float,
            trigger: str = "immediate", within: int = 3) -> tuple[pd.Series, pd.Series]:
    """Boolean (long, short) series on fast-bar close.

    Both oscillators low  (slow <= lvl_slow and fast <= lvl_fast) -> long;
    both high (>= 100 - level) -> short. trigger:
      immediate: the first fast bar at which the alignment becomes true;
      flip:      slow still extreme and the fast osc turns back out of its zone
                 (up for long, down for short) within `within` bars of being in it.
    """
    o = fast["osc"]
    lo_s, hi_s = slow_osc <= lvl_slow, slow_osc >= 100 - lvl_slow
    if trigger == "immediate":
        lo, hi = lo_s & (o <= lvl_fast), hi_s & (o >= 100 - lvl_fast)
        return lo & ~lo.shift(fill_value=False), hi & ~hi.shift(fill_value=False)
    p = o.shift()
    long_ = lo_s & (o > p) & (p <= o.shift(2)) & (p.rolling(within).min() <= lvl_fast)
    short = hi_s & (o < p) & (p >= o.shift(2)) & (p.rolling(within).max() >= 100 - lvl_fast)
    return long_, short


def atr_series(b: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = b["close"].shift()
    tr = pd.concat([b["high"] - b["low"], (b["high"] - pc).abs(), (b["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def backtest(fast: pd.DataFrame, long_sig: pd.Series, short_sig: pd.Series, k: float = 1.5, rr: float = 2.0,
             cost_bps: float = 2.0, cooldown: int = 4, window=("09:45", "15:30"),
             exit_level: float = 50.0) -> pd.DataFrame:
    """Enter at the close of the signal bar; race stop/target on later bars of the same day.

    One row per trade: real_r (stop/target race, same-bar touch = stop, flat at close otherwise),
    rule_r (exit when the fast osc crosses back through the midline, else at the close), costs in R.
    """
    step = fast.index.to_series().diff().mode().iloc[0]
    atr = atr_series(fast)
    lo_t, hi_t = (pd.Timestamp(w).time() for w in window)
    hi_a, lo_a, cl, osc = (fast[c].to_numpy() for c in ("high", "low", "close", "osc"))
    pos = {t: i for i, t in enumerate(fast.index)}
    day_end = fast.groupby(fast.index.date).cumcount(ascending=False).to_numpy()  # bars left in session
    last = {"long": -10**9, "short": -10**9}
    rows = []
    for side, sig in (("long", long_sig), ("short", short_sig)):
        sgn = 1 if side == "long" else -1
        for t in sig.index[sig.fillna(False).to_numpy(bool)]:
            i = pos[t]
            if not (lo_t <= (t + step).time() <= hi_t) or i - last[side] < cooldown or not day_end[i] or np.isnan(atr.iloc[i]):
                continue
            last[side] = i
            entry, risk = cl[i], k * atr.iloc[i]
            stop, target = entry - sgn * risk, entry + sgn * rr * risk
            j = slice(i + 1, i + 1 + day_end[i])
            hit_s = lo_a[j] <= stop if sgn > 0 else hi_a[j] >= stop
            hit_t = hi_a[j] >= target if sgn > 0 else lo_a[j] <= target
            fs, ft = (np.argmax(h) if h.any() else 10**9 for h in (hit_s, hit_t))
            if fs <= ft and fs < 10**9:
                out, r = "stop", -1.0
            elif ft < 10**9:
                out, r = "target", rr
            else:
                out, r = "neither", sgn * (cl[j][-1] - entry) / risk
            back = osc[j] >= exit_level if sgn > 0 else osc[j] <= 100 - exit_level
            px = cl[j][np.argmax(back)] if back.any() else cl[j][-1]
            rows.append(dict(time=t + step, side=side, entry=entry, real_outcome=out, real_r=r,
                             rule_r=sgn * (px - entry) / risk, cost_r=cost_bps / 1e4 * entry / risk))
    return pd.DataFrame(rows)
