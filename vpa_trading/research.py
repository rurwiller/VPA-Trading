"""Event study engine on a 1-minute master clock.

Every timeframe (3m ... 1h) is built from 1m bars anchored at 9:30, and its values are
used only once the bar has CLOSED. An *event* is a moment (a 1m close) when a setup
appears; each event is scored twice:
  fade = trade against the stretch (reversal), cont = trade with it (continuation).
For FVG touches, fade = bounce off the gap, cont = break through it.

Outcomes (all after a round-trip cost, per trade, entry at the event minute's close):
  r5/r15/r60  return after 5/15/60 minutes, bps (flat at 16:00 if sooner)
  pct_*       race to +0.5% target / -0.3% stop within 60 min (same bar = stop)
  atr_*       race to 2R target / 1.5 x ATR(5m) stop within 60 min
  mfe/mae     best/worst excursion within 60 min, in ATR(5m) units (for stop research)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind
from .data import resample_bars
from .willard_osc import willard_osc

TFS = ["3m", "5m", "9m", "15m", "30m", "1h"]
STEP = {tf: pd.Timedelta(tf.replace("m", "min")) if tf.endswith("m") else pd.Timedelta(tf) for tf in TFS}
COST_BPS = 2.0
HORIZON = 60
WINDOW = ("09:35", "15:00")   # entry window (clock time = 1m close), so the 60-minute horizon fits


@dataclass
class Sym:
    name: str
    m1: pd.DataFrame
    tf: dict = field(default_factory=dict)
    osc_clock: dict = field(default_factory=dict)  # tf -> np.array of closed osc at each 1m close
    gaps: dict = field(default_factory=dict)       # tf -> FVG frame with first touch / fill indices


def build_tf(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    b = resample_bars(m1, tf)
    day_close = b.index.normalize() + pd.Timedelta(hours=16)
    b["closes_at"] = np.minimum((b.index + STEP[tf]).values, day_close.values)
    b["osc"] = willard_osc(b).osc
    b["atr"] = ind.atr(b)
    b = b.join(ind.dmi(b))
    b["adx_slope"] = b.adx - b.adx.shift(3)
    b["ema9"] = b.close.ewm(span=9, adjust=False).mean()
    b["ema21"] = b.close.ewm(span=21, adjust=False).mean()
    b["rvol"] = ind.rvol(b)
    b = b.join(ind.candles(b, b.atr))
    return b


def asof(frame: pd.DataFrame, times: np.ndarray, cols: list[str]) -> pd.DataFrame:
    """Values of the latest bar of `frame` that has closed by each time (order of `times` kept)."""
    right = frame[["closes_at"] + cols].sort_values("closes_at")
    left = pd.DataFrame({"t": pd.to_datetime(times), "k": np.arange(len(times))}).sort_values("t")
    m = pd.merge_asof(left, right, left_on="t", right_on="closes_at", direction="backward")
    return m.sort_values("k")[cols].reset_index(drop=True)


def prepare(name: str, m1: pd.DataFrame) -> Sym:
    s = Sym(name, m1)
    s.clock = (m1.index + pd.Timedelta(minutes=1)).values
    day = m1.index.normalize()
    pos = np.arange(len(m1))
    s.day_last = pd.Series(pos, index=m1.index).groupby(day).transform("max").to_numpy()
    s.minute = ((m1.index - day) / pd.Timedelta(minutes=1)).to_numpy().astype(int) - 570 + 1  # minutes since 9:30 at close
    s.vwap = ind.session_vwap(m1).to_numpy()
    for tf in TFS:
        s.tf[tf] = build_tf(m1, tf)
        s.osc_clock[tf] = asof(s.tf[tf], s.clock, ["osc"]).osc.to_numpy()
    s.atr5_clock = asof(s.tf["5m"], s.clock, ["atr"]).atr.to_numpy()
    for tf in ("5m", "15m", "1h"):
        s.gaps[tf] = locate_gaps(s, tf)
    return s


def locate_gaps(s: Sym, tf: str, max_sessions: int = 3) -> pd.DataFrame:
    """FVGs of `tf` with the 1m index they form at, first touch and full fill (or -1)."""
    b = s.tf[tf]
    g = ind.fvgs(b, b.atr, b.rvol, b.closes_at).reset_index(drop=True)
    lo, hi = s.m1.low.to_numpy(), s.m1.high.to_numpy()
    start = np.searchsorted(s.clock, g.formed_at.values)  # first 1m bar closing at/after formation
    start = start + 1                                     # the next 1m bar is the first that can touch
    span = 390 * max_sessions
    touch, fill = np.full(len(g), -1), np.full(len(g), -1)
    for k, (d, top, bot, st) in enumerate(zip(g.dir.to_numpy(), g.top.to_numpy(), g.bottom.to_numpy(), start)):
        en = min(st + span, len(lo))
        if st >= en:
            continue
        if d > 0:   # bull gap below price: touched when low <= top, filled when low <= bottom
            t_hit, f_hit = lo[st:en] <= top, lo[st:en] <= bot
        else:
            t_hit, f_hit = hi[st:en] >= bot, hi[st:en] >= top
        if t_hit.any():
            touch[k] = st + int(np.argmax(t_hit))
        if f_hit.any():
            fill[k] = st + int(np.argmax(f_hit))
    g["start"], g["touch"], g["fill"] = start, touch, fill
    g["expire"] = np.minimum(start + span, len(lo))
    return g


# ------------------------------------------------------------------ events

def _in_window(s: Sym, idx: np.ndarray) -> np.ndarray:
    lo, hi = (int((pd.Timedelta(w + ":00") - pd.Timedelta("09:30:00")) / pd.Timedelta(minutes=1)) for w in WINDOW)
    return (s.minute[idx] >= lo) & (s.minute[idx] <= hi)


def _cooldown(idx: np.ndarray, minutes: int) -> np.ndarray:
    keep, last = [], -10**9
    for i in idx:
        if i - last >= minutes:
            keep.append(i)
            last = i
    return np.array(keep, dtype=int)


def _rows(s, idx, stretch, family, variant, modes=("fade", "cont")) -> pd.DataFrame:
    out = []
    for mode in modes:
        d = -stretch if mode == "fade" else stretch
        out.append(pd.DataFrame({"sym": s.name, "i": idx, "stretch": stretch, "dir": d,
                                 "family": family, "variant": variant, "mode": mode}))
    return pd.concat(out, ignore_index=True)


def stack_events(s: Sym, tfs: list[str], level: float, trigger: str | None = None,
                 cooldown: int = 15, trigger_within: int = 15) -> pd.DataFrame:
    """All oscillators in `tfs` at an extreme together (closed bars). Rising edge only."""
    O = np.column_stack([s.osc_clock[tf] for tf in tfs])
    variant = "+".join(tfs) + f" L{level:g}" + (f" trig{trigger}" if trigger else "")
    frames = []
    for st, aligned in ((1, (O >= 100 - level).all(1)), (-1, (O <= level).all(1))):
        edge = aligned & ~np.r_[False, aligned[:-1]]
        idx = np.flatnonzero(edge)
        idx = _cooldown(idx[_in_window(s, idx)], cooldown)
        if not len(idx):
            continue
        if trigger is None:
            frames.append(_rows(s, idx, np.full(len(idx), st), "stack", variant))
            continue
        # Trigger: the first close of a `trigger` bar within N minutes whose oscillator
        # moves in the trade's direction (e.g. the 3m turns down for a fade short).
        o = s.osc_clock[trigger]
        chg = np.r_[0.0, np.diff(o)]
        for mode in ("fade", "cont"):
            d = -st if mode == "fade" else st
            ent = []
            for i in idx:
                j_end = min(i + trigger_within, s.day_last[i])
                w = np.flatnonzero(np.sign(chg[i + 1:j_end + 1]) == d)
                if len(w):
                    ent.append(i + 1 + w[0])
            ent = np.array(ent, dtype=int)
            ent = ent[_in_window(s, ent)] if len(ent) else ent
            frames.append(_rows(s, ent, np.full(len(ent), st), "stack", variant, modes=(mode,)))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _bar_close_index(s: Sym, closes_at: pd.Series) -> np.ndarray:
    j = np.searchsorted(s.clock, closes_at.values)
    ok = (j < len(s.clock)) & (s.clock[np.minimum(j, len(s.clock) - 1)] == closes_at.values)
    return np.where(ok, j, -1)


def candle_events(s: Sym, tf: str, level: float) -> pd.DataFrame:
    """Rejection candle at an oscillator extreme on one timeframe:
    inverted hammer / shooting star with osc >= 100-L (stretch up), hammer with osc <= L."""
    b = s.tf[tf]
    j = _bar_close_index(s, b.closes_at)
    frames = []
    for st, m in ((1, (b.inv_hammer == 1) & (b.osc >= 100 - level)), (-1, (b.hammer == 1) & (b.osc <= level))):
        idx = j[m.to_numpy() & (j >= 0)]
        idx = idx[_in_window(s, idx)]
        frames.append(_rows(s, idx, np.full(len(idx), st), "candle", f"{tf} L{level:g}"))
    return pd.concat(frames, ignore_index=True)


def climax_events(s: Sym, tf: str, min_rvol: float, min_wick: float) -> pd.DataFrame:
    b = s.tf[tf]
    c = ind.climaxes(b, b, b.rvol, min_rvol=min_rvol, min_wick=min_wick)
    j = _bar_close_index(s, b.closes_at)
    frames = []
    for st, m in ((1, c.buy_climax), (-1, c.sell_climax)):
        idx = j[m.to_numpy() & (j >= 0)]
        idx = idx[_in_window(s, idx)]
        frames.append(_rows(s, idx, np.full(len(idx), st), "climax", f"{tf} rvol{min_rvol:g} wick{min_wick:g}"))
    return pd.concat(frames, ignore_index=True)


def fvg_events(s: Sym, tf: str) -> pd.DataFrame:
    """First touch of an unfilled FVG. Bull gap (support) touched from above = stretch down."""
    g = s.gaps[tf]
    g = g[g.touch >= 0]
    idx = g.touch.to_numpy()
    ok = _in_window(s, idx)
    g, idx = g[ok], idx[ok]
    ev = _rows(s, idx, -g.dir.to_numpy(), "fvg", f"{tf}")
    ev["gap_size_atr"] = np.tile(g.size_atr.to_numpy(), 2)
    ev["gap_disp_rvol"] = np.tile(g.disp_rvol.to_numpy(), 2)
    ev["gap_age_min"] = np.tile(idx - g.start.to_numpy(), 2)
    ev["gap_same_day"] = np.tile((s.day_last[idx] == s.day_last[g.start.to_numpy()]).astype(float), 2)
    return ev


# ------------------------------------------------------------------ outcomes and features

def outcomes(s: Sym, ev: pd.DataFrame) -> pd.DataFrame:
    i, d = ev.i.to_numpy(), ev.dir.to_numpy().astype(float)
    C, H, L = (s.m1[c].to_numpy() for c in ("close", "high", "low"))
    e = C[i]
    last = s.day_last[i]
    out = {}
    for h in (5, 15, 60):
        x = np.minimum(i + h, last)
        out[f"r{h}"] = d * (C[x] - e) / e * 1e4 - COST_BPS
    J = i[:, None] + np.arange(1, HORIZON + 1)
    valid = J <= last[:, None]
    Jc = np.minimum(J, last[:, None])
    fav = np.where(d[:, None] > 0, H[Jc] - e[:, None], e[:, None] - L[Jc])
    adv = np.where(d[:, None] > 0, e[:, None] - L[Jc], H[Jc] - e[:, None])
    fav, adv = np.where(valid, fav, -np.inf), np.where(valid, adv, -np.inf)
    a5 = s.atr5_clock[i]
    out["mfe_atr"] = fav.max(1) / a5
    out["mae_atr"] = adv.max(1) / a5
    end_ret = d * (C[np.minimum(i + HORIZON, last)] - e)

    def race(stop, target):
        hs, ht = adv >= stop[:, None], fav >= target[:, None]
        fs = np.where(hs.any(1), hs.argmax(1), 10**6)
        ft = np.where(ht.any(1), ht.argmax(1), 10**6)
        stop_first = (fs <= ft) & (fs < 10**6)
        tgt_first = (ft < fs)
        res = np.where(stop_first, -stop, np.where(tgt_first, target, end_ret))
        return np.where(stop_first, 0, np.where(tgt_first, 1, 2)), res

    o, res = race(0.003 * e, 0.005 * e)
    out["pct_out"], out["pct_ret"] = o, res / e * 100 - COST_BPS / 100      # in % of price
    o, res = race(1.5 * a5, 3.0 * a5)
    out["atr_out"], out["atr_r"] = o, res / (1.5 * a5) - COST_BPS / 1e4 * e / (1.5 * a5)
    return pd.DataFrame(out, index=ev.index)


def features(s: Sym, ev: pd.DataFrame) -> pd.DataFrame:
    i = ev.i.to_numpy()
    t = s.clock[i]
    f = {"time": pd.to_datetime(t), "tod": s.minute[i]}
    for tf in TFS:
        f[f"osc_{tf}"] = s.osc_clock[tf][i]
    for tf in ("5m", "15m", "1h"):
        v = asof(s.tf[tf], t, ["adx", "adx_slope", "pdi", "mdi"])
        for c in v:
            f[f"{c}_{tf}"] = v[c].to_numpy()
    for tf in ("5m", "15m"):
        v = asof(s.tf[tf], t, ["ema9", "ema21", "close", "inv_hammer", "hammer", "upper_frac",
                               "lower_frac", "rvol", "spread_atr", "up_bar"])
        for c in v:
            f[f"{c}_{tf}"] = v[c].to_numpy()
    a5 = s.atr5_clock[i]
    px = s.m1.close.to_numpy()[i]
    f["atr5_pct"] = a5 / px * 100
    f["vwap_dist_atr"] = (px - s.vwap[i]) / a5
    # Unfilled fair value gaps near price (inside the zone or within 0.25 ATR of it).
    for tf, g in s.gaps.items():
        for d, name in ((1, "bull"), (-1, "bear")):
            gg = g[g.dir == d]
            st, fi, ex = gg.start.to_numpy(), gg.fill.to_numpy(), gg.expire.to_numpy()
            top, bot, ga = gg.top.to_numpy(), gg.bottom.to_numpy(), gg.atr.to_numpy()
            near = np.zeros(len(i))
            lo_k = np.searchsorted(st, i - 390 * 3)
            hi_k = np.searchsorted(st, i, side="right")
            for n, (ii, a, b_) in enumerate(zip(i, lo_k, hi_k)):
                if a >= b_:
                    continue
                sl = slice(a, b_)
                active = ((fi[sl] < 0) | (fi[sl] > ii)) & (ex[sl] > ii)
                if not active.any():
                    continue
                p, buf = px[n], 0.25 * ga[sl]
                close_ = (p >= bot[sl] - buf) & (p <= top[sl] + buf) & active
                near[n] = float(close_.any())
            f[f"near_{name}_fvg_{tf}"] = near
    return pd.DataFrame(f, index=ev.index)


def score(s: Sym, ev: pd.DataFrame) -> pd.DataFrame:
    if ev is None or not len(ev):
        return pd.DataFrame()
    ev = ev.reset_index(drop=True)
    return pd.concat([ev, outcomes(s, ev), features(s, ev)], axis=1)
