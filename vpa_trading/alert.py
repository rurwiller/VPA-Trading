"""Candle alert mode: the setups the user trades by eye, alerted (and paper-traded at half the usual risk).

A candle on 5m, 9m or 15m qualifies when ALL of these hold at its close:
  - pivot wick: upper (top) or lower (bottom) wick >= 40% of the range and >= the body, the other wick <= 30%, and the
    wick is the highest / lowest of the last 12 candles
  - volume surge: the candle's volume >= 2x the usual for that time of day
  - stretch: the wick is >= 0.5 ATR(5m) beyond the 15m EMA 9 (as drawn on the chart, including the current price)
  - oscillators: the 5m, 9m and 15m oscillators all >= 75 (top / short) or all <= 25 (bottom / long)
No 1h/4h/D gap is needed. Orders (entry stop beyond the candle, stop beyond the wick, 1R target) use the same mechanics as
the regular scanner with the alert risk; their client_order_id prefix is "alert-". Backtest note: over 5 years this
combination did not beat costs (reports/osc_pivot.md); this mode exists to measure the user's own picks.
"""
from __future__ import annotations

import pandas as pd

from . import vpa
from .live import Engine, Plan, frame
from .willard_osc import willard_osc


def pivot_wick(done: pd.DataFrame, n: int = 12) -> int:
    """-1 if the last closed candle is a pivot-wick TOP, +1 if a pivot-wick BOTTOM, else 0 (the alert mode's candle rule)."""
    if len(done) < n + 2:
        return 0
    o, h, l, c = (float(done[k].iat[-1]) for k in ("open", "high", "low", "close"))
    rng = h - l
    if rng <= 0:
        return 0
    up, dn, body = h - max(o, c), min(o, c) - l, abs(c - o)
    if up >= 0.4 * rng and up >= body and dn <= 0.3 * rng and h >= float(done.high.iloc[-n:].max()):
        return -1
    if dn >= 0.4 * rng and dn >= body and up <= 0.3 * rng and l <= float(done.low.iloc[-n:].min()):
        return 1
    return 0


class AlertMode:
    def __init__(self, eng: Engine, level: float = 75.0, min_rvol: float = 2.0, min_stretch: float = 0.5,
                 tfs: tuple = ("15m", "9m", "5m"), pivot_bars: int = 12):
        self.eng, self.level, self.min_rvol, self.min_stretch = eng, level, min_rvol, min_stretch
        self.tfs, self.pivot_bars = tfs, pivot_bars

    def signals(self, sym: str, m1: pd.DataFrame, now: pd.Timestamp) -> list[Plan]:
        minute = (now - now.normalize()) / pd.Timedelta(minutes=1) - 570
        if not 30 <= minute <= self.eng.cfg.close_min - 30:
            return []
        b5 = frame(m1, "5m")
        a5 = float(b5[b5.closes_at <= now].atr.iloc[-1])
        for tf in self.tfs:
            b = frame(m1, tf)
            done = b[b.closes_at <= now]
            if len(done) < self.pivot_bars + 2 or done.closes_at.iloc[-1] != now:
                continue
            t = done.index[-1]
            key = ("alert", sym, tf, t)
            if key in self.eng.seen:
                continue
            o, h, l, c = (float(done[k].iat[-1]) for k in ("open", "high", "low", "close"))
            rng = h - l
            if rng <= 0:
                continue
            up, dn, body = h - max(o, c), min(o, c) - l, abs(c - o)
            n = self.pivot_bars
            if up >= 0.4 * rng and up >= body and dn <= 0.3 * rng and h >= float(done.high.iloc[-n:].max()):
                bias, wick = -1, h
            elif dn >= 0.4 * rng and dn >= body and up <= 0.3 * rng and l <= float(done.low.iloc[-n:].min()):
                bias, wick = 1, l
            else:
                continue
            self.eng.seen.add(key)
            rv = float(vpa.relvol_tod(done).iat[-1])
            if not rv >= self.min_rvol:
                continue
            b15 = frame(m1, "15m")
            c15 = b15[b15.closes_at <= now]
            e9 = float(c15.close.ewm(span=9, adjust=False).mean().iloc[-1])
            ema15 = e9 if c15.closes_at.iloc[-1] == now else 0.2 * float(m1.close.iloc[-1]) + 0.8 * e9
            stretch = ((wick - ema15) if bias < 0 else (ema15 - wick)) / a5
            if stretch < self.min_stretch:
                continue
            osc = {}
            for tt in ("5m", "9m", "15m"):
                bt = frame(m1, tt)
                osc[tt] = round(float(willard_osc(bt[bt.closes_at <= now]).osc.iat[-1]), 1)
            vals = list(osc.values())
            if not (min(vals) >= self.level if bias < 0 else max(vals) <= 100 - self.level):
                continue
            gaps = self.eng._gaps(sym, m1, now)
            gap = self.eng._at_gap(gaps, wick, bias, a5)
            p = self.eng._plan(sym, tf, "alert", "ALERT_PIVOT_TOP" if bias < 0 else "ALERT_PIVOT_BOTTOM", bias, now, h, l,
                               wick, gap, risk_usd=self.eng.cfg.risk_usd)
            if p is None:
                continue
            p.tags = self.eng._tags(sym, m1, now, wick, bias, a5, gaps)
            p.tags.update({"alert": True, "rvol": round(rv, 1), "osc": osc, "stretch_atr": round(stretch, 2),
                           "ema15_9": round(ema15, 2)})
            p.extra["prefix"] = "alert"
            return [p]
        return []
