"""Two questions on every current S&P 500 stock (daily bars since 2016, split-adjusted):

PART 1. The oversold setup in 2026: daily AND live weekly Willard oscillator below 10 (first day of each run),
        with and without the daily-gap filter, compared with the years before.

PART 2. Pivot candles (the scanner's hammer / shooting star: rejection wick >= 40% of the range and >= the body,
        opposite wick <= 30%) on the DAILY and WEEKLY charts, alone and when the oscillator is at an extreme:
          long:  hammer (wick at the bottom)      with the oscillator below 10 (oversold)
          short: shooting star (wick at the top)  with the oscillator above 90 (overbought)
        Weekly candles are finished weeks; their oscillator is the weekly value at that week's close.
        Daily candles use the live weekly value that day (the week so far), so nothing looks ahead.
        "High volume" = the candle's volume at least 1.5x its 20-bar average.
  Two ways to score each candle:
    drift  return from the candle's close to 5 / 10 / 20 trading days later, in the trade's direction, minus that
           stock's average move over the same days (so "short" is not penalised just for the bull market... it is:
           a short has to beat minus the usual move).
    trade  how the scanner trades it: buy a break of the candle's high (short: break of the low) during the next bar
           (next day for daily candles, next week for weekly), stop at the other end of the candle, target 1R,
           otherwise out at the close 20 trading days after entry. Result in R (risk units) before costs; a day
           that touches both stop and target counts as a stop.

  python scripts/htf_candles_test.py [--cached]   -> reports/htf_candles.md
"""
from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading.willard_osc import willard_osc  # noqa: E402
from osc_oversold_test import daily  # noqa: E402
from osc_oversold_v2 import at_gap, bull_gaps  # noqa: E402

H = (5, 10, 20)
Y26 = pd.Timestamp("2026-01-01")


def members():
    return pd.read_csv("data/sp500/constituents.csv").Symbol.tolist()


def pivots(b):
    rng = (b.high - b.low).replace(0, np.nan)
    up = b.high - b[["open", "close"]].max(axis=1)
    dn = b[["open", "close"]].min(axis=1) - b.low
    body = (b.close - b.open).abs()
    ham = (dn >= 0.4 * rng) & (dn >= body) & (up <= 0.3 * rng)
    star = (up >= 0.4 * rng) & (up >= body) & (dn <= 0.3 * rng)
    hv = b.volume >= 1.5 * b.volume.rolling(20).mean().shift(1)
    return ham.fillna(False), star.fillna(False), hv.fillna(False)


def trade(d, i_last, j0, j1, side, hi, lo):
    """Stop entry at the candle's high (long) / low (short) on days j0..j1; stop the other end; 1R target; 20 days."""
    O, Hh, L, C = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    for j in range(j0, min(j1, len(d) - 1) + 1):
        if (side > 0 and Hh[j] > hi) or (side < 0 and L[j] < lo):
            e = max(hi, O[j]) if side > 0 else min(lo, O[j])
            stop = lo if side > 0 else hi
            risk = abs(e - stop)
            if risk <= 0:
                return np.nan
            tgt = e + side * risk
            for t in range(j, min(j + 20, len(d) - 1) + 1):
                if t > j or True:
                    if (side > 0 and L[t] <= stop) or (side < 0 and Hh[t] >= stop):
                        return -1.0
                    if (side > 0 and Hh[t] >= tgt) or (side < 0 and L[t] <= tgt):
                        return 1.0
            end = min(j + 20, len(d) - 1)
            return side * (C[end] - e) / risk
    return np.nan


def study(sym):
    try:
        d = daily(sym)[["open", "high", "low", "close", "volume"]]
    except Exception:                                                       # noqa: BLE001
        return None
    if len(d) < 250:
        return None
    do = willard_osc(d)["osc"]
    wk = d.index.to_period("W-FRI")
    full = d.groupby(wk).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                             close=("close", "last"), volume=("volume", "sum"))
    wfull = willard_osc(full)["osc"]
    c = d.close.to_numpy()
    avg = {n: np.nanmean(c[n:] / c[:-n] - 1) * 100 for n in H}
    dh, ds, dv = pivots(d)
    wh, ws, wv = pivots(full)

    def live_w(i):
        day, w = d.index[i], wk[i]
        x = d[(wk == w) & (d.index <= day)]
        part = pd.DataFrame({"open": [x.open.iat[0]], "high": [x.high.max()], "low": [x.low.min()],
                             "close": [x.close.iat[-1]], "volume": [x.volume.sum()]}, index=[w])
        return willard_osc(pd.concat([full[full.index < w].iloc[-150:], part]))["osc"].iat[-1]

    def drift(i, side):
        return {f"x{n}": side * ((c[i + n] / c[i] - 1) * 100) - side * avg[n] if i + n < len(c) else np.nan for n in H}

    rows = []
    # daily candles + PART 1 (oversold runs)
    need = (do < 10) | dh | ds
    wl = pd.Series(np.nan, index=d.index)
    for i in np.flatnonzero(need.to_numpy()):
        if i >= 60:
            wl.iat[i] = live_w(int(i))
    dgaps = bull_gaps(d)
    dl, dc = d.low.to_numpy(), d.close.to_numpy()
    both = ((do < 10) & (wl < 10)).to_numpy()
    for i in range(60, len(d)):
        i = int(i)
        if both[i] and not both[i - 1]:
            r = {"kind": "oversold", "sym": sym, "day": d.index[i], "side": 1, "dgap": at_gap(dl, dc, dgaps, i, lambda g, k: g < k)}
            r.update(drift(i, 1))
            rows.append(r)
        for flag, side in ((dh, 1), (ds, -1)):
            if flag.iat[i]:
                r = {"kind": "candle", "tf": "daily", "sym": sym, "day": d.index[i], "side": side, "hv": bool(dv.iat[i]),
                     "osc_d": do.iat[i], "osc_w": wl.iat[i],
                     "R": trade(d, i, i + 1, i + 1, side, d.high.iat[i], d.low.iat[i])}
                r.update(drift(i, side))
                rows.append(r)
    # weekly candles
    for k in range(60, len(full)):
        for flag, side in ((wh, 1), (ws, -1)):
            if not flag.iat[k]:
                continue
            days = np.flatnonzero(wk == full.index[k])
            i = int(days[-1])
            nxt = np.flatnonzero(wk == full.index[k + 1]) if k + 1 < len(full) else []
            R = trade(d, i, int(nxt[0]), int(nxt[-1]), side, full.high.iat[k], full.low.iat[k]) if len(nxt) else np.nan
            r = {"kind": "candle", "tf": "weekly", "sym": sym, "day": d.index[i], "side": side, "hv": bool(wv.iat[k]),
                 "osc_d": do.iat[i], "osc_w": wfull.iat[k], "osc_w_prev": wfull.iat[k - 1], "R": R}
            r.update(drift(i, side))
            rows.append(r)
    return pd.DataFrame(rows)


def cell(x):
    x = x.dropna()
    if len(x) < 5:
        return "-"
    return f"{x.mean():+.2f}% (t {x.mean() / (x.std() / np.sqrt(len(x))):+.1f})"


def rcell(x):
    x = x.dropna()
    if len(x) < 5:
        return "- | -"
    return f"{len(x)} | {x.mean():+.2f}R ({100 * (x > 0).mean():.0f}% won)"


def ctable(groups):
    L = ["| Candle | Count | +5 days | +10 days | +20 days | Triggered | Trade result |", "|---|--:|--:|--:|--:|--:|--:|"]
    for name, e in groups:
        L.append(f"| {name} | {len(e)} | {cell(e.x5)} | {cell(e.x10)} | {cell(e.x20)} | {rcell(e.R)} |")
    return L


def main():
    cache = Path("results/htf_candles.pkl")
    if "--cached" in sys.argv and cache.exists():
        ev = pd.read_pickle(cache)
    else:
        with Pool(4) as p:
            ev = pd.concat([x for x in p.map(study, members()) if x is not None and len(x)], ignore_index=True)
        cache.parent.mkdir(exist_ok=True)
        ev.to_pickle(cache)
    spy = daily("SPY").close
    ev["spy_up"] = ev.day.map(spy > spy.rolling(200).mean())
    L = ["# Higher-timeframe candles and the oversold setup: all S&P 500 stocks\n", __doc__.split("\n\n", 1)[1].rsplit("\n\n", 1)[0], "",
         "Drift cells: average return in the trade's direction beyond the stock's usual move (t; above about 2 is "
         "unlikely to be luck). Trade result: average R per triggered trade (share that made money).\n"]
    o = ev[ev.kind == "oversold"].copy()
    o["dgap"] = o.dgap.astype(bool)
    L += ["## Part 1: daily + weekly oscillator below 10, 2026 vs before\n",
          "| Setups | Count | +5 days | +10 days | +20 days |", "|---|--:|--:|--:|--:|"]
    for name, e in (("2016-2025, all", o[o.day < Y26]), ("2026, all", o[o.day >= Y26]),
                    ("2016-2025, at a daily gap", o[(o.day < Y26) & o.dgap]), ("2026, at a daily gap", o[(o.day >= Y26) & o.dgap]),
                    ("2026, no gap", o[(o.day >= Y26) & ~o.dgap])):
        L.append(f"| {name} | {len(e)} | {cell(e.x5)} | {cell(e.x10)} | {cell(e.x20)} |")
    o26 = o[o.day >= Y26]
    L += ["", "2026 by month (all setups):", "", "| Month | Setups | +5 days | +10 days | +20 days |", "|---|--:|--:|--:|--:|"]
    for m, g in o26.groupby(o26.day.dt.to_period("M")):
        L.append(f"| {m} | {len(g)} | {cell(g.x5)} | {cell(g.x10)} | {cell(g.x20)} |")
    cd = ev[ev.kind == "candle"]
    for period, sub in (("2016-2026", cd), ("2026 only", cd[cd.day >= Y26])):
        L += [f"\n## Part 2: pivot candles, {period}\n"]
        for tf in ("daily", "weekly"):
            t = sub[sub.tf == tf]
            hm, st = t[t.side > 0], t[t.side < 0]
            L += [f"\n### {tf.title()} candles\n"] + ctable([
                ("Hammer, any", hm),
                ("Hammer, weekly osc below 10", hm[hm.osc_w < 10]),
                ("Hammer, daily AND weekly osc below 10", hm[(hm.osc_w < 10) & (hm.osc_d < 10)]),
                ("Hammer, weekly osc below 10, high volume", hm[(hm.osc_w < 10) & hm.hv]),
                ("Hammer, weekly below 10, SPY above 200-day", hm[(hm.osc_w < 10) & (hm.spy_up == True)]),   # noqa: E712
                ("Hammer, weekly below 10, SPY below 200-day", hm[(hm.osc_w < 10) & (hm.spy_up == False)]),  # noqa: E712
                ("Shooting star, any", st),
                ("Shooting star, weekly osc above 90", st[st.osc_w > 90]),
                ("Shooting star, daily AND weekly above 90", st[(st.osc_w > 90) & (st.osc_d > 90)]),
                ("Shooting star, weekly above 90, high volume", st[(st.osc_w > 90) & st.hv]),
                ("Shooting star, weekly above 90, SPY below 200-day", st[(st.osc_w > 90) & (st.spy_up == False)])])  # noqa: E712
    Path("reports/htf_candles.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
