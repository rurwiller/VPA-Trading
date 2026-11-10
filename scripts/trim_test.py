"""Profit trimming: fixed partials, breakeven stops and an auto-trim when the 15m oscillator turns against the position.

Two parts, both over 5 years of 1m bars, costs = ticker spread + 1 bp per round trip:

A. TSLA trend-day breakout (live rules: checks every 30 min, thirds at +1% / +2%, stop to breakeven after the first take).
   Added variants: when the 15m oscillator (port of the user's oscillator, closed candles) crosses into the zone against the
   position after the entry (>= LEVEL while long, <= 100 - LEVEL while short) and the trade is in profit, sell a part at
   that minute's close and move the stop to breakeven.
B. Candle trades (pivot-wick candles on 9m / 15m, scanner entry: stop-entry through the candle, stop beyond the wick):
   all at 1R (live), half at +0.5R then breakeven, and the same oscillator auto-trim.

  python scripts/trim_test.py          -> reports/trim_test.md
"""
from __future__ import annotations

import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import research as R  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402
from midcap_test import cost_bps  # noqa: E402

SPLIT = pd.Timestamp("2024-11-01")
CHECKS = list(range(29, 360, 30))
FLAT_MIN = 380


# ------------------------------------------------------------------ A. breakout
def matrices(s):
    m = s.m1.copy()
    day = m.index.normalize()
    mi = ((m.index - day) / pd.Timedelta(minutes=1)).astype(int) - 570
    m = m.assign(day=day, mi=mi, osc=s.osc_clock["15m"])
    m = m[(m.mi >= 0) & (m.mi < 390)]
    full = m.groupby("day").mi.max() >= 389
    m = m[m.day.isin(full.index[full])]
    piv = lambda col: m.pivot(index="day", columns="mi", values=col).reindex(columns=range(390)).ffill(axis=1)  # noqa: E731
    C = piv("close")
    O = m[m.mi == m.groupby("day").mi.transform("min")].set_index("day").open.reindex(C.index)
    pv = (m.vwap.fillna(m.close) * m.volume) if "vwap" in m else m.close * m.volume
    m = m.assign(pv=pv)
    PV = m.pivot(index="day", columns="mi", values="pv").reindex(columns=range(390)).fillna(0).cumsum(axis=1)
    VV = m.pivot(index="day", columns="mi", values="volume").reindex(columns=range(390)).fillna(0).cumsum(axis=1)
    VW = (PV / VV.replace(0, np.nan)).ffill(axis=1)
    return C, O, VW, piv("high").to_numpy(), piv("low").to_numpy(), piv("osc").to_numpy()


def breakout(sym, mats, osc_trim=None, fixed=(0.01, 0.02)) -> pd.Series:
    """osc_trim = (level, fraction) or None. fixed = profit levels for the thirds (empty = none)."""
    C, O, VW, Hh, Ll, OS = mats
    c, o, vw = C.to_numpy(), O.to_numpy(), VW.to_numpy()
    prev = np.r_[np.nan, c[:-1, 389]]
    sigma = pd.DataFrame(np.abs(c / o[:, None] - 1)).rolling(14).mean().shift(1).to_numpy()
    cost = cost_bps(sym) / 1e4
    ub0, lb0 = np.fmax(o, prev), np.fmin(o, prev)
    out = np.full(len(c), np.nan)
    for k in range(len(c)):
        if np.isnan(sigma[k, CHECKS[0]]) or np.isnan(prev[k]):
            continue
        st = dict(pos=0, entry=0.0, rem=0.0, ret=0.0, targets=[], fr=[], be=False, armed=False, trimmed=False)

        def close(px, frac):
            st["ret"] += frac * (st["pos"] * (px / st["entry"] - 1) - cost)
        for ci, t in enumerate(CHECKS):
            px = c[k, t]
            ub, lb = ub0[k] * (1 + sigma[k, t]), lb0[k] * (1 - sigma[k, t])
            pos = st["pos"]
            want = pos
            if pos == 1 and px < max(ub, vw[k, t]):
                want = 0
            elif pos == -1 and px > min(lb, vw[k, t]):
                want = 0
            if want == 0:
                want = 1 if px > ub else (-1 if px < lb else 0)
            if want != pos:
                if pos != 0 and st["rem"] > 1e-9:
                    close(px, st["rem"])
                    st["rem"] = 0.0
                if want != 0:
                    st.update(entry=px, rem=1.0, targets=[px * (1 + want * l) for l in fixed], fr=[1 / 3] * len(fixed),
                              be=False, armed=False, trimmed=False)
                st["pos"] = want
            if st["pos"] == 0:
                continue
            end = CHECKS[ci + 1] if ci + 1 < len(CHECKS) else 389
            for b in range(t + 1, end + 1):
                pos, e = st["pos"], st["entry"]
                if st["be"] and st["rem"] > 1e-9 and ((pos > 0 and Ll[k, b] <= e) or (pos < 0 and Hh[k, b] >= e)):
                    close(e, st["rem"])
                    st["rem"], st["pos"] = 0.0, 0
                    break
                while st["fr"] and ((Hh[k, b] >= st["targets"][0]) if pos > 0 else (Ll[k, b] <= st["targets"][0])):
                    f = min(st["fr"][0], st["rem"])
                    close(st["targets"][0], f)
                    st["rem"] -= f
                    st["targets"].pop(0)
                    st["fr"].pop(0)
                    st["be"] = True
                if osc_trim and not st["trimmed"] and st["rem"] > 1e-9:
                    lvl, frac = osc_trim
                    v = OS[k, b]
                    against = (pos > 0 and v >= lvl) or (pos < 0 and v <= 100 - lvl)
                    if not against:
                        st["armed"] = True          # it has to cross into the zone after the entry
                    elif st["armed"] and (c[k, b] - e) * pos > 0:
                        f = min(frac, st["rem"])
                        close(c[k, b], f)
                        st["rem"] -= f
                        st["trimmed"], st["be"] = True, True
                        if st["fr"]:                  # the trim replaces the next fixed third
                            st["targets"].pop(0)
                            st["fr"].pop(0)
        if st["pos"] != 0 and st["rem"] > 1e-9:
            close(c[k, 389], st["rem"])
        out[k] = st["ret"]
    return pd.Series(out, index=C.index)


# ------------------------------------------------------------------ B. candle trades
def candle_sim(O, H, L, C, OS, minute, last, i, d, hi, lo, step, mode):
    wick = hi if d < 0 else lo
    entry = round(lo - 0.01, 2) if d < 0 else round(hi + 0.01, 2)
    stop = math.ceil(wick * 1.0002 * 100 + 1) / 100 if d < 0 else math.floor(wick * 0.9998 * 100 - 1) / 100
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    end = min(i + 2 * step, last[i])
    fill, j = None, None
    for jj in range(i + 1, end + 1):
        if (d < 0 and H[jj] > wick) or (d > 0 and L[jj] < wick):
            return None
        if (d < 0 and L[jj] <= entry) or (d > 0 and H[jj] >= entry):
            fill, j = (min(O[jj], entry) if d < 0 else max(O[jj], entry)), jj
            break
    if fill is None:
        return None
    tgt_r = 2.0 if mode.endswith("2R") else 1.0
    target = entry + d * tgt_r * risk
    half = entry + d * 0.5 * risk
    stop_px, rem, pnl, trimmed, armed = stop, 1.0, 0.0, False, False
    if (d < 0 and H[j] >= stop) or (d > 0 and L[j] <= stop):
        return (stop - fill) * d / risk
    k1 = last[j]
    cut = np.flatnonzero(minute[j + 1:k1 + 1] >= FLAT_MIN)
    if len(cut):
        k1 = j + 1 + int(cut[0])
    for k in range(j + 1, k1 + 1):
        if (d > 0 and L[k] <= stop_px) or (d < 0 and H[k] >= stop_px):
            pnl += rem * (stop_px - fill) * d
            rem = 0.0
            break
        if mode.startswith("half") and not trimmed and ((d > 0 and H[k] >= half) or (d < 0 and L[k] <= half)):
            pnl += 0.5 * (half - fill) * d
            rem, trimmed, stop_px = 0.5, True, fill
        if mode.startswith("osc") and not trimmed:
            v = OS[k]
            against = (d > 0 and v >= 80) or (d < 0 and v <= 20)
            if not against:
                armed = True
            elif armed and (C[k] - fill) * d > 0:
                pnl += 0.5 * (C[k] - fill) * d
                rem, trimmed, stop_px = 0.5, True, fill
        if (d > 0 and H[k] >= target) or (d < 0 and L[k] <= target):
            pnl += rem * (target - fill) * d
            rem = 0.0
            break
    if rem > 0:
        pnl += rem * (C[k1] - fill) * d
    return pnl / risk


MODES = ["full_1R", "half05_BE_1R", "half05_BE_2R", "osc80_BE_1R", "osc80_BE_2R"]


def run_symbol(sym: str):
    s = R.prepare(sym, load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False))
    out = {"sym": sym}
    if sym in ("TSLA", "AMD", "QQQ", "NVDA", "META"):
        mats = matrices(s)
        out["breakout"] = {
            "live: thirds at 1% / 2%, breakeven after the first": breakout(sym, mats),
            "+ auto-trim a third when the 15m osc crosses 80 against": breakout(sym, mats, osc_trim=(80, 1 / 3)),
            "+ auto-trim a third at 90": breakout(sym, mats, osc_trim=(90, 1 / 3)),
            "+ auto-trim half at 80": breakout(sym, mats, osc_trim=(80, 0.5)),
            "auto-trim at 80 instead of the +1% third": breakout(sym, mats, osc_trim=(80, 1 / 3), fixed=(0.02,)),
            "no trimming at all (hold to the rule)": breakout(sym, mats, fixed=()),
        }
    O, H, L, C = (s.m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    OS = np.asarray(s.osc_clock["15m"], float)
    rows = []
    for tf in ("9m", "15m"):
        b = V.frame(s.m1, tf)
        rng = (b.high - b.low).replace(0, np.nan)
        top, bot = b[["open", "close"]].max(axis=1), b[["open", "close"]].min(axis=1)
        body, upw, low_w = (b.close - b.open).abs(), b.high - top, bot - b.low
        ut = (upw >= 0.4 * rng) & (upw >= body) & (low_w <= 0.3 * rng) & (b.high >= b.high.rolling(12).max())
        ub = (low_w >= 0.4 * rng) & (low_w >= body) & (upw <= 0.3 * rng) & (b.low <= b.low.rolling(12).min())
        for d, m in ((-1, ut), (1, ub)):
            e = b[m]
            j = R._bar_close_index(s, pd.Series(e.closes_at.to_numpy()))
            for jj, hi, lo in zip(j, e.high, e.low):
                if jj < 0 or not (30 <= s.minute[jj] <= 360):
                    continue
                cost_r = None
                r = {"time": pd.Timestamp(s.clock[jj]), "dir": d, "tf": tf}
                for mode in MODES:
                    v = candle_sim(O, H, L, C, OS, s.minute, s.day_last, int(jj), d, float(hi), float(lo), int(tf[:-1]), mode)
                    if v is None:
                        break
                    if cost_r is None:
                        risk = abs((lo - 0.01 if d < 0 else hi + 0.01) - (hi if d < 0 else lo))
                        cost_r = C[jj] * cost_bps(sym) / 1e4 / max(risk, 1e-9)
                    r[mode] = v - cost_r
                else:
                    rows.append(r)
    out["candles"] = pd.DataFrame(rows).assign(sym=sym)
    return out


def main() -> None:
    syms = ["TSLA", "AMD", "QQQ", "NVDA", "META", "AAPL", "MSFT", "GOOGL", "AMZN"]
    with ProcessPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(run_symbol, syms))
    L = ["# Profit trimming test\n", "5 years of 1m bars. Before = before 2024-11-01, after = from 2024-11-01. Costs = spread + 1 bp.\n",
         "## A. Trend-day breakout, average per day in bps (Sharpe), per ticker\n"]
    for r in res:
        if "breakout" not in r:
            continue
        L.append(f"\n**{r['sym']}**\n\n| Variant | Before | After | Sharpe before | Sharpe after | Worst day | Winning days |\n|---|--:|--:|--:|--:|--:|--:|")
        for name, x in r["breakout"].items():
            d = x.index < SPLIT
            sh = lambda y: y.mean() / y.std() * np.sqrt(252)  # noqa: E731
            L.append(f"| {name} | {x[d].mean() * 1e4:+.1f} | {x[~d].mean() * 1e4:+.1f} | {sh(x[d]):.2f} | {sh(x[~d]):.2f} | "
                     f"{x.min() * 1e4:+.0f} | {(x[x != 0] > 0).mean():.0%} |")
    cd = pd.concat([r["candles"] for r in res], ignore_index=True)
    L.append("\n## B. Candle trades (pivot-wick candles, 9m and 15m, 9 tickers), average R per trade after costs\n")
    L.append("| Exit | Before | After | Share of trades that made money (after) |\n|---|--:|--:|--:|")
    names = {"full_1R": "all at 1R (live)", "half05_BE_1R": "half at +0.5R, rest to breakeven stop / 1R",
             "half05_BE_2R": "half at +0.5R, rest to breakeven stop / 2R", "osc80_BE_1R": "half when the 15m osc turns against (80/20), then breakeven / 1R",
             "osc80_BE_2R": "half when the 15m osc turns against, then breakeven / 2R"}
    for m, nm in names.items():
        d = cd.time < SPLIT
        L.append(f"| {nm} | {cd.loc[d, m].mean():+.3f} | {cd.loc[~d, m].mean():+.3f} | {(cd.loc[~d, m] > 0).mean():.0%} |")
    L.append(f"\n{len(cd):,} trades that filled.")
    Path("reports/trim_test.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
