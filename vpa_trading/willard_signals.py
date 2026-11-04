"""Replay of the Willard 3.0 "MTF Signals" system (Ready Call / Ready Put -> CALL / PUT) on a
1-minute chart, with the indicator's default settings. Source: the user's Pine v6 script.

What is reproduced (defaults):
  Setup  : 5m <= 5, 9m <= 10, 15m <= 12 and 1m <= 3 all touched within 16 one-minute bars
           (tops: >= 100 - level) -> Ready Call (Ready Put). Live mode on history = the higher
           timeframe value as of its bar close. Regular hours, not in the first 15 min, not in
           the last 30 min, cooldown 10 bars per side, expires after 30 bars.
  Trigger rules (each fires at most once per setup), trigger TFs 3m (closed bars) and 1m, zone 10:
           0 Exit Extreme, 1 Color Flip, 2 PSAR Cross, 3 Sequential, 4 Fire/Ice,
           5 Immediate (no 3m/1m), 6 1m ADX Primed.
  Factors: star stretch (1m Bollinger/ADX/DI, 2 of 3), EMA (price near 15m EMA9 within 0.05 ATR),
           spread (15m oscillator candle >= 2.5x average, pointing into the extreme),
           hammer = VPA (the script's 5m VPA engine, any strength).
           Labels need >= 1 factor (min_stars = 1); the scorecard counts every trigger.
  Exits  : stop 2 x ATR(5m), trail from +2.25 ATR at 1.1 ATR; take profit when the 5m oscillator
           reaches the other extreme (>= 95 / <= 5); momentum exit (5m osc turns + 1m close beyond
           the prior candle); opposite signal; flat 30 min before the close. Relative volatility
           filter (ATR >= 0.7 x this symbol's typical for the time of day). Costs 0.02% round trip.
P&L is the stock's % move, like the indicator's scorecard (not option P&L).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import indicators as ind
from .research import STEP, asof
from .willard_osc import willard_osc

RULES = ["Exit Extreme", "Color Flip", "PSAR Cross", "Sequential", "Fire/Ice", "Immediate", "1m ADX Primed"]
BIG = 10**9
SETUP = {"5m": 5.0, "9m": 10.0, "15m": 12.0}
TOUCH_1M, ZONE_A, ZONE_B = 3.0, 10.0, 10.0
ALIGN, EXPIRY, COOLDOWN = 16, 30, 10
COST_PCT = 0.02


def psar(base: np.ndarray, start=0.06, inc=0.24, mx=2.4) -> np.ndarray:
    """The script's f_psar on oscillator values (PSAR Sensitivity High = 6x), clamped 0-100."""
    n = len(base)
    out = np.full(n, np.nan)
    val = ep = np.nan
    af, trend = start, True
    for i in range(n):
        b = base[i]
        if i == 0:
            ep = val = b
        else:
            pv = val if not math.isnan(val) else b
            pe = ep if not math.isnan(ep) else b
            pa = af
            new = pv + pa * (pe - pv)
            if (trend and b < new) or (not trend and b > new):
                trend = not trend
                val, ep, af = pe, b, start
            else:
                val = new
                if trend and b > pe:
                    ep, af = b, min(pa + inc, mx)
                elif not trend and b < pe:
                    ep, af = b, min(pa + inc, mx)
                else:
                    ep, af = pe, pa
        if not math.isnan(val):
            val = min(max(val, 0.0), 100.0)
        out[i] = val
    return out


def barssince(cond: np.ndarray) -> np.ndarray:
    idx = np.arange(len(cond), dtype=float)
    last = pd.Series(np.where(cond, idx, np.nan)).ffill().to_numpy()
    return np.where(np.isnan(last), BIG, idx - last)


def osc_candle(b: pd.DataFrame, osc: pd.Series, roc: pd.Series) -> pd.DataFrame:
    """The script's f_osc_candle: oscillator candle size (wick to wick) and body, VPA multipliers."""
    rel = b.volume / b.volume.rolling(20).mean()
    o = osc.shift().fillna(osc)
    d = osc - o
    body_m = np.where(rel < 0.75, 0.74, np.where(rel > 1.25, 1.26, 1.0))
    wick_m = np.where(rel < 0.75, 1.26, np.where(rel > 1.25, 0.74, 1.0))
    c = np.clip(o + d * body_m, 0, 100)
    wick = np.abs(d * body_m) * wick_m
    hi = np.minimum(np.maximum(o, c) + wick, 100)
    lo = np.maximum(np.minimum(o, c) - wick, 0)
    rng = pd.Series(hi - lo, index=b.index)
    return pd.DataFrame({"rng": rng, "avg_prev": rng.rolling(20).mean().shift(), "body": c - o}, index=b.index)


def vpa_side(b: pd.DataFrame) -> pd.Series:
    """The script's 5m VPA engine (f_vpa + same-time-of-day relative volume). +1 bull, -1 bear, 0."""
    vol = b.volume.to_numpy()
    first = np.r_[True, b.index.normalize()[1:] != b.index.normalize()[:-1]]
    slot_avg = np.full(400, np.nan)
    rv = np.full(len(b), np.nan)
    slot, alpha = 0, 2.0 / 21
    for i in range(len(b)):
        slot = 0 if first[i] else slot + 1
        si = min(slot, 399)
        sv = slot_avg[si]
        rv[i] = np.nan if (math.isnan(sv) or sv <= 0) else vol[i] / sv
        slot_avg[si] = vol[i] if math.isnan(sv) else sv * (1 - alpha) + vol[i] * alpha
    a = ind.atr(b).to_numpy()
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    n = 20
    mv = pd.Series(c).shift(1) - pd.Series(c).shift(n + 1)
    p_hi = pd.Series(h).rolling(n).max().shift().to_numpy()
    p_lo = pd.Series(l).rolling(n).min().shift().to_numpy()
    mv = mv.to_numpy()
    side = np.zeros(len(b), dtype=int)
    for i in range(len(b)):
        spr = h[i] - l[i]
        if math.isnan(rv[i]) or math.isnan(a[i]) or a[i] <= 0 or spr <= 0 or math.isnan(mv[i]):
            continue
        body = abs(c[i] - o[i])
        up_w, lo_w = h[i] - max(o[i], c[i]), min(o[i], c[i]) - l[i]
        pos = (c[i] - l[i]) / spr
        ctx_dn, ctx_up = mv[i] < -1.5 * a[i], mv[i] > 1.5 * a[i]
        wide, narrow = spr >= 1.2 * a[i], spr <= 0.7 * a[i]
        min_b = max(body, 0.1 * spr)
        hi_v, ultra, lo_v = rv[i] >= 1.5, rv[i] >= 2.2, rv[i] <= 0.7
        code = 0
        if ultra and wide and ctx_dn and l[i] <= p_lo[i] and pos >= 0.4:
            code = 1
        elif ultra and wide and ctx_up and h[i] >= p_hi[i] and pos <= 0.6:
            code = -1
        elif h[i] > p_hi[i] and c[i] < p_hi[i] and pos <= 0.4 and rv[i] >= 1.0:
            code = -2
        elif l[i] < p_lo[i] and c[i] > p_lo[i] and pos >= 0.6 and rv[i] >= 1.0:
            code = 2
        elif ctx_up and up_w >= 2 * min_b and up_w >= 0.5 * spr and pos <= 0.4:
            code = -3
        elif ctx_dn and lo_w >= 2 * min_b and lo_w >= 0.5 * spr and pos >= 0.6:
            code = 3
        elif ctx_up and lo_w >= 2 * min_b and lo_w >= 0.5 * spr and pos >= 0.6:
            code = -4
        elif hi_v and narrow and ctx_dn:
            code = 4
        elif hi_v and narrow and ctx_up:
            code = -5
        elif lo_v and narrow and c[i] < o[i] and ctx_dn:
            code = 5
        elif lo_v and narrow and c[i] > o[i] and ctx_up:
            code = -6
        side[i] = 1 if 1 <= code <= 5 else (-1 if code < 0 else 0)
    return pd.Series(side, index=b.index)


def inputs(s) -> dict:
    """Per 1-minute bar inputs, all known at that bar's close (as the script sees them)."""
    m1 = s.m1
    start = m1.index.values                      # bar start = when [1]+lookahead_on values update
    clock = s.clock                              # bar close
    w1 = willard_osc(m1)
    o1 = w1.osc.to_numpy()
    x = {"o1": o1, "o1_prev": np.r_[np.nan, o1[:-1]]}
    for tf in ("5m", "9m", "15m"):
        x[f"s_{tf}"] = s.osc_clock[tf]
    # 3m trigger: closed candles only -> value of the last 3m bar closed by this bar's start
    b3 = s.tf["3m"].copy()
    b3["prev"] = b3.osc.shift()
    b3["bull"] = (b3.osc > psar(b3.osc.to_numpy())).astype(float)
    v = asof(b3, start, ["osc", "prev", "bull"])
    x["tA"], x["tA_prev"], x["tA_bull"] = v.osc.to_numpy(), v.prev.to_numpy(), v.bull.to_numpy() == 1
    x["tB_bull"] = o1 > psar(o1)
    # 1m Fire/Ice (chart timeframe): Bollinger 20/2 + ADX/DI 14 above 30
    basis = m1.close.rolling(20).mean()
    dev = 2.0 * m1.close.rolling(20).std(ddof=0)
    dm = ind.dmi(m1)
    adx_hi = dm.adx > 30
    strong = adx_hi & ((dm.pdi > 30) | (dm.mdi > 30))
    x["ice"] = ((m1.low < basis - dev) & strong).to_numpy()
    x["fire"] = ((m1.high > basis + dev) & strong).to_numpy()
    x["cold"] = ((m1.low < basis - dev).astype(int) + adx_hi.astype(int) + (dm.mdi > 30).astype(int)).to_numpy()
    x["hot"] = ((m1.high > basis + dev).astype(int) + adx_hi.astype(int) + (dm.pdi > 30).astype(int)).to_numpy()
    # 5m: ATR (closed, [1]), oscillator for take profit (live) and momentum exit (closed pair)
    b5 = s.tf["5m"].copy()
    b5["prev"] = b5.osc.shift()
    v = asof(b5, start, ["atr", "osc", "prev"])
    x["atr"], x["mo"], x["mo_prev"] = v.atr.to_numpy(), v.osc.to_numpy(), v.prev.to_numpy()
    x["tpo"] = s.osc_clock["5m"]
    # 5m VPA events (arrive at the first 1m bar after the 5m candle closes)
    b5["vside"] = vpa_side(b5)
    b5["barno"] = np.arange(len(b5), dtype=float)
    v = asof(b5, start, ["vside", "barno"])
    newbar = np.r_[True, v.barno.to_numpy()[1:] != v.barno.to_numpy()[:-1]]
    vs = v.vside.fillna(0).to_numpy()
    x["vpa_bull"], x["vpa_bear"] = newbar & (vs == 1), newbar & (vs == -1)
    # 15m EMA9 (live) and the 1m ATR tolerance
    b15 = s.tf["15m"].copy()
    x["ema15"] = asof(b15, clock, ["ema9"]).ema9.to_numpy()
    atr1 = ind.atr(m1).to_numpy()
    lo, hi = m1.low.to_numpy(), m1.high.to_numpy()
    x["near_ema"] = (lo - 0.05 * atr1 <= x["ema15"]) & (hi + 0.05 * atr1 >= x["ema15"])
    # 15m oscillator candle spread (live)
    w15 = willard_osc(b15)
    oc = osc_candle(b15, w15.osc, w15.roc)
    b15 = b15.join(oc)
    v = asof(b15, clock, ["rng", "avg_prev", "body"])
    big = (v.avg_prev > 0) & (v.rng >= 2.5 * v.avg_prev)
    x["big_down"], x["big_up"] = (big & (v.body < 0)).to_numpy(), (big & (v.body > 0)).to_numpy()
    # Session
    ms = s.minute - 1                                      # minutes since 9:30 at bar start
    x["ms"] = ms
    x["late"] = ms >= 359                                  # last 30 minutes (bar closes within 30 min of 16:00)
    x["first"] = np.r_[True, s.day_last[1:] != s.day_last[:-1]]
    x["lastbar"] = np.arange(len(m1)) == s.day_last
    # Relative volatility filter: ATR% vs the same 5-minute slot's EMA over sessions
    atr_pct = x["atr"] / m1.close.to_numpy() * 100
    typ = np.full(len(m1), np.nan)
    slot_a = np.full(100, np.nan)
    alpha = 2.0 / 21
    for i in range(len(m1)):
        k = min(max(int(ms[i] // 5), 0), 99)
        p = slot_a[k]
        typ[i] = p
        if not math.isnan(atr_pct[i]):
            slot_a[k] = atr_pct[i] if math.isnan(p) else p + alpha * (atr_pct[i] - p)
    x["vol_ok"] = np.where(np.isnan(typ) | (typ <= 0), True, atr_pct >= 0.7 * typ)
    # Alignment of the four setup timeframes within the window
    lo_ok = np.ones(len(m1), bool)
    hi_ok = np.ones(len(m1), bool)
    for key, lv in (("s_5m", SETUP["5m"]), ("s_9m", SETUP["9m"]), ("s_15m", SETUP["15m"]), ("o1", TOUCH_1M)):
        lo_ok &= barssince(x[key] <= lv) <= ALIGN
        hi_ok &= barssince(x[key] >= 100 - lv) <= ALIGN
    x["align_buy_evt"] = lo_ok & ~np.r_[False, lo_ok[:-1]]
    x["align_sell_evt"] = hi_ok & ~np.r_[False, hi_ok[:-1]]
    for key, cond in (("bsA_lo", x["tA"] <= ZONE_A), ("bsA_hi", x["tA"] >= 100 - ZONE_A),
                      ("bsB_lo", o1 <= ZONE_B), ("bsB_hi", o1 >= 100 - ZONE_B),
                      ("bsA_bear", ~x["tA_bull"]), ("bsA_bull", x["tA_bull"]),
                      ("bsB_bear", ~x["tB_bull"]), ("bsB_bull", x["tB_bull"]),
                      ("bsIce", x["ice"]), ("bsFire", x["fire"]),
                      ("bsCold", x["cold"] >= 2), ("bsHot", x["hot"] >= 2),
                      ("bsBigDown", x["big_down"]), ("bsBigUp", x["big_up"]),
                      ("bsVpaBull", x["vpa_bull"]), ("bsVpaBear", x["vpa_bear"])):
        x[key] = barssince(cond)
    return x


def run(s, x: dict, bars: pd.DataFrame | None = None, step: pd.Timedelta = pd.Timedelta(minutes=1)
        ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bar-by-bar replay of the setup state machine and the 7 rule backtests.
    `bars` = the chart's bars (default: 1-minute); `x` must be built for the same bars."""
    m1 = s.m1 if bars is None else bars
    O, H, L, C = (m1[k].to_numpy().tolist() for k in ("open", "high", "low", "close"))
    X = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in x.items()}
    n = len(C)
    nan = float("nan")
    setup_dir, arm_bar = 0, -BIG
    last_buy = last_sell = -BIG
    fired = [False] * 7
    seen = dict(FI=False, ZA=False, ZB=False, AdvA=False, AdvB=False, seqA=False)
    star = dict(st=False, em=False, sp=False, vp=False)
    sims = [dict(dir=0) for _ in range(7)]
    trades, setups = [], []
    for i in range(n):
        late, ms = X["late"][i], X["ms"][i]
        sess_ok = ms >= 15 and not late
        do_end = setup_dir != 0 and (i - arm_bar > EXPIRY or (X["first"][i] and i > arm_bar))
        new_dir = 0
        if X["align_buy_evt"][i] and sess_ok and i - last_buy >= COOLDOWN:
            new_dir = 1
        if X["align_sell_evt"][i] and sess_ok and i - last_sell >= COOLDOWN:
            new_dir = -1
        if new_dir != 0 and new_dir == setup_dir and not do_end:
            new_dir = 0
        if new_dir != 0 and setup_dir != 0:
            do_end = True
        if do_end:
            setup_dir = 0
        if new_dir != 0:
            setup_dir, arm_bar = new_dir, i
            fired = [False] * 7
            b = new_dir == 1
            seen = dict(FI=(X["bsIce"] if b else X["bsFire"])[i] <= ALIGN,
                        ZA=(X["bsA_lo"] if b else X["bsA_hi"])[i] <= ALIGN,
                        ZB=(X["bsB_lo"] if b else X["bsB_hi"])[i] <= ALIGN,
                        AdvA=(X["bsA_bear"] if b else X["bsA_bull"])[i] <= ALIGN,
                        AdvB=(X["bsB_bear"] if b else X["bsB_bull"])[i] <= ALIGN, seqA=False)
            star = dict(sp=(X["bsBigDown"] if b else X["bsBigUp"])[i] <= ALIGN, em=X["near_ema"][i],
                        st=(X["bsCold"] if b else X["bsHot"])[i] <= ALIGN,
                        vp=(X["bsVpaBull"] if b else X["bsVpaBear"])[i] <= ALIGN)
            if b:
                last_buy = i
            else:
                last_sell = i
            setups.append(dict(i=i, dir=new_dir, **{f"f_{k}": v for k, v in star.items()}))
        sigs = [0] * 7
        grades = [None] * 7
        if setup_dir != 0:
            b = setup_dir == 1
            star["sp"] |= (X["big_down"] if b else X["big_up"])[i]
            star["em"] |= X["near_ema"][i]
            star["st"] |= ((X["cold"] if b else X["hot"])[i] >= 2)
            star["vp"] |= (X["vpa_bull"] if b else X["vpa_bear"])[i]
            seen["FI"] |= (X["ice"] if b else X["fire"])[i]
            tA, tAp, tB, tBp = X["tA"][i], X["tA_prev"][i], X["o1"][i], X["o1_prev"][i]
            tAb, tBb = X["tA_bull"][i], X["tB_bull"][i]
            if b:
                seen["ZA"] |= tA <= ZONE_A
                seen["ZB"] |= tB <= ZONE_B
                seen["AdvA"] |= not tAb
                seen["AdvB"] |= not tBb
                outA, outB = tA > ZONE_A, tB > ZONE_B
                turnA, turnB = tA > tAp, tB > tBp
                favA, favB = tAb, tBb
                crossB = tB > ZONE_B and tBp <= ZONE_B
                conf = X.get("cold_conf", X["cold"])[i] >= 2
            else:
                seen["ZA"] |= tA >= 100 - ZONE_A
                seen["ZB"] |= tB >= 100 - ZONE_B
                seen["AdvA"] |= tAb
                seen["AdvB"] |= tBb
                outA, outB = tA < 100 - ZONE_A, tB < 100 - ZONE_B
                turnA, turnB = tA < tAp, tB < tBp
                favA, favB = not tAb, not tBb
                crossB = tB < 100 - ZONE_B and tBp >= 100 - ZONE_B
                conf = X.get("hot_conf", X["hot"])[i] >= 2
            if not seen["seqA"] and seen["ZA"] and outA:
                seen["seqA"] = True
            conds = [seen["ZA"] and seen["ZB"] and outA and outB, seen["ZA"] and seen["ZB"] and turnA and turnB,
                     seen["AdvA"] and seen["AdvB"] and favA and favB, seen["seqA"] and crossB,
                     seen["FI"], i == arm_bar, conf]
            if sess_ok:
                for r in range(7):
                    if not fired[r] and conds[r]:
                        fired[r] = True
                        sigs[r] = setup_dir
                        grades[r] = dict(star)
            if all(fired[:4]):
                setup_dir = 0
        can_enter = not X["lastbar"][i] and not late
        for r in range(7):
            sm, sig = sims[r], sigs[r]
            if sm["dir"] != 0 and i > sm["entry_i"]:
                d, xp, why = sm["dir"], None, ""
                if d == 1 and L[i] <= sm["stop"]:
                    xp, why = min(O[i], sm["stop"]), "stop"
                elif d == -1 and H[i] >= sm["stop"]:
                    xp, why = max(O[i], sm["stop"]), "stop"
                elif (d == 1 and X["tpo"][i] >= 95) or (d == -1 and X["tpo"][i] <= 5):
                    xp, why = C[i], "tp"
                elif i > 0 and ((d == 1 and X["mo"][i] < X["mo_prev"][i] and C[i] < L[i - 1]) or
                                (d == -1 and X["mo"][i] > X["mo_prev"][i] and C[i] > H[i - 1])):
                    xp, why = C[i], "momentum"
                elif late or X["lastbar"][i]:
                    xp, why = C[i], "close"
                elif sig == -d:
                    xp, why = C[i], "opposite"
                if xp is not None:
                    e = sm["entry"]
                    pnl = (xp - e) / e * 100 * d - COST_PCT
                    trades.append(dict(rule=RULES[r], dir=d, entry_i=sm["entry_i"], exit_i=i, entry=e, exit=xp,
                                       reason=why, pnl=pnl, arm_i=sm["arm_i"], **sm["grade"]))
                    sm["dir"] = 0
                else:
                    if d == 1:
                        sm["best"] = max(sm["best"], H[i])
                        if sm["best"] - sm["entry"] >= sm["act"]:
                            sm["trail"] = True
                        if sm["trail"]:
                            sm["stop"] = max(sm["stop"], sm["entry"], sm["best"] - sm["dist"])
                    else:
                        sm["best"] = min(sm["best"], L[i])
                        if sm["entry"] - sm["best"] >= sm["act"]:
                            sm["trail"] = True
                        if sm["trail"]:
                            sm["stop"] = min(sm["stop"], sm["entry"], sm["best"] + sm["dist"])
            a = X["atr"][i]
            if sm["dir"] == 0 and sig != 0 and can_enter and X["vol_ok"][i] and a == a:
                sims[r] = dict(dir=sig, entry=C[i], entry_i=i, stop=C[i] - sig * 2.0 * a, best=C[i],
                               act=2.25 * a, dist=1.1 * a, trail=False, arm_i=arm_bar,
                               grade={f"f_{k}": v for k, v in grades[r].items()})
    t = pd.DataFrame(trades)
    if len(t):
        t["time"] = m1.index[t.entry_i.to_numpy()] + step
        t["factors"] = t[["f_st", "f_em", "f_sp", "f_vp"]].sum(axis=1)
    st = pd.DataFrame(setups)
    if len(st):
        st["time"] = m1.index[st.i.to_numpy()] + step
    return t, st


def inputs_5m_chart(s) -> tuple[dict, pd.DataFrame]:
    """The same inputs as `inputs`, but as the script sees them on a 5-MINUTE chart.

    On a 5m chart: the 5m setup value, Fire/Ice, ATR, VPA, take-profit and momentum oscillator
    are the chart's own; 9m/15m are the last closed higher-timeframe bar; the 1m setup value is
    the last 1m bar inside the 5m bar; the 1m/3m trigger values ([1] offset) are the bar before
    the last 1m / 3m bar inside the 5m bar. Bar-count settings (window 16, expiry 30,
    cooldown 10) are counted in 5m bars.
    """
    b = s.tf["5m"].copy()
    start = b.index.values
    close = b.closes_at.values
    one = pd.Timedelta(minutes=1)
    m1 = s.m1
    w1 = willard_osc(m1)
    f1 = pd.DataFrame({"closes_at": s.clock, "osc": w1.osc.to_numpy()}, index=m1.index)
    f1["bull"] = (f1.osc > psar(f1.osc.to_numpy())).astype(float)
    basis1 = m1.close.rolling(20).mean()
    dev1 = 2.0 * m1.close.rolling(20).std(ddof=0)
    dm1 = ind.dmi(m1)
    hi1 = dm1.adx > 30
    f1["cold"] = ((m1.low < basis1 - dev1).astype(int) + hi1.astype(int) + (dm1.mdi > 30).astype(int)).to_numpy()
    f1["hot"] = ((m1.high > basis1 + dev1).astype(int) + hi1.astype(int) + (dm1.pdi > 30).astype(int)).to_numpy()
    osc5 = b.osc.to_numpy()
    x = {"s_5m": osc5, "s_9m": s.osc_clock["9m"], "s_15m": s.osc_clock["15m"]}
    x["s_9m"] = asof(s.tf["9m"], close, ["osc"]).osc.to_numpy()
    x["s_15m"] = asof(s.tf["15m"], close, ["osc"]).osc.to_numpy()
    x["o1_setup"] = asof(f1, close, ["osc"]).osc.to_numpy()
    v = asof(f1, close - one, ["osc", "bull", "cold", "hot"])
    x["o1"], x["tB_bull"] = v.osc.to_numpy(), v.bull.to_numpy() == 1
    x["cold_conf"], x["hot_conf"] = v.cold.fillna(0).to_numpy(), v.hot.fillna(0).to_numpy()
    x["o1_prev"] = asof(f1, close - 2 * one, ["osc"]).osc.to_numpy()
    # 3m: the last 3m bar starting inside this 5m bar is at k3; [1] = the bar that closed at k3
    day = b.index.normalize()
    ms = ((b.index - day) / one).to_numpy().astype(int) - 570
    k3 = ((ms + 4) // 3) * 3
    t_k3 = (day + pd.Timedelta(hours=9, minutes=30) + pd.to_timedelta(k3, unit="m")).values
    b3 = s.tf["3m"].copy()
    b3["bull"] = (b3.osc > psar(b3.osc.to_numpy())).astype(float)
    v = asof(b3, t_k3, ["osc", "bull"])
    x["tA"], x["tA_bull"] = v.osc.to_numpy(), v.bull.to_numpy() == 1
    x["tA_prev"] = asof(b3, t_k3 - np.timedelta64(3, "m"), ["osc"]).osc.to_numpy()
    # Chart-timeframe (5m) Fire/Ice, ATR, VPA, take profit and momentum
    basis = b.close.rolling(20).mean()
    dev = 2.0 * b.close.rolling(20).std(ddof=0)
    dm = ind.dmi(b)
    adx_hi = dm.adx > 30
    strong = adx_hi & ((dm.pdi > 30) | (dm.mdi > 30))
    x["ice"] = ((b.low < basis - dev) & strong).to_numpy()
    x["fire"] = ((b.high > basis + dev) & strong).to_numpy()
    x["cold"] = ((b.low < basis - dev).astype(int) + adx_hi.astype(int) + (dm.mdi > 30).astype(int)).to_numpy()
    x["hot"] = ((b.high > basis + dev).astype(int) + adx_hi.astype(int) + (dm.pdi > 30).astype(int)).to_numpy()
    x["atr"] = b.atr.to_numpy()
    x["tpo"], x["mo"], x["mo_prev"] = osc5, osc5, np.r_[np.nan, osc5[:-1]]
    vs = vpa_side(b).to_numpy()
    x["vpa_bull"], x["vpa_bear"] = vs == 1, vs == -1
    x["ema15"] = asof(s.tf["15m"], close, ["ema9"]).ema9.to_numpy()
    lo, hi = b.low.to_numpy(), b.high.to_numpy()
    x["near_ema"] = (lo - 0.05 * x["atr"] <= x["ema15"]) & (hi + 0.05 * x["atr"] >= x["ema15"])
    b15 = s.tf["15m"].copy()
    w15 = willard_osc(b15)
    b15 = b15.join(osc_candle(b15, w15.osc, w15.roc))
    v = asof(b15, close, ["rng", "avg_prev", "body"])
    big = (v.avg_prev > 0) & (v.rng >= 2.5 * v.avg_prev)
    x["big_down"], x["big_up"] = (big & (v.body < 0)).to_numpy(), (big & (v.body > 0)).to_numpy()
    x["ms"] = ms
    x["late"] = ms >= 355                                  # bar closes within 30 min of 16:00
    dnum = day.to_numpy()
    x["first"] = np.r_[True, dnum[1:] != dnum[:-1]]
    x["lastbar"] = np.r_[dnum[1:] != dnum[:-1], True]
    atr_pct = x["atr"] / b.close.to_numpy() * 100
    typ = np.full(len(b), np.nan)
    slot_a = np.full(100, np.nan)
    for i in range(len(b)):
        k = min(max(int(ms[i] // 5), 0), 99)
        p = slot_a[k]
        typ[i] = p
        if not math.isnan(atr_pct[i]):
            slot_a[k] = atr_pct[i] if math.isnan(p) else p + (2.0 / 21) * (atr_pct[i] - p)
    x["vol_ok"] = np.where(np.isnan(typ) | (typ <= 0), True, atr_pct >= 0.7 * typ)
    lo_ok = np.ones(len(b), bool)
    hi_ok = np.ones(len(b), bool)
    for key, lv in (("s_5m", SETUP["5m"]), ("s_9m", SETUP["9m"]), ("s_15m", SETUP["15m"]), ("o1_setup", TOUCH_1M)):
        lo_ok &= barssince(x[key] <= lv) <= ALIGN
        hi_ok &= barssince(x[key] >= 100 - lv) <= ALIGN
    x["align_buy_evt"] = lo_ok & ~np.r_[False, lo_ok[:-1]]
    x["align_sell_evt"] = hi_ok & ~np.r_[False, hi_ok[:-1]]
    for key, cond in (("bsA_lo", x["tA"] <= ZONE_A), ("bsA_hi", x["tA"] >= 100 - ZONE_A),
                      ("bsB_lo", x["o1"] <= ZONE_B), ("bsB_hi", x["o1"] >= 100 - ZONE_B),
                      ("bsA_bear", ~x["tA_bull"]), ("bsA_bull", x["tA_bull"]),
                      ("bsB_bear", ~x["tB_bull"]), ("bsB_bull", x["tB_bull"]),
                      ("bsIce", x["ice"]), ("bsFire", x["fire"]),
                      ("bsCold", x["cold"] >= 2), ("bsHot", x["hot"] >= 2),
                      ("bsBigDown", x["big_down"]), ("bsBigUp", x["big_up"]),
                      ("bsVpaBull", x["vpa_bull"]), ("bsVpaBear", x["vpa_bear"])):
        x[key] = barssince(cond)
    return x, b
