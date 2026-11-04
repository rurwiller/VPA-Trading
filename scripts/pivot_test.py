"""Pivot shooting stars / hammers and pivots in general, on 9 / 15 / 29 / 60-minute candles.

Pivot high (k): the candle's high is above the k candles before and the k after (same session); known when
the k-th candle after it closes. Pivot low mirrored.
Shapes (the user's looser shooting star): upper wick >= 45% of the range, upper wick > body, lower wick <= 25%.
Hammer mirrored. "strict" = the spec's premier shapes (vpa.detect / vpa_fib_fvg.premier).
Events (each scored with = short at a pivot high / long at a pivot low, and against):
  star_pivot1 / star_pivot2   loose star or hammer that is a pivot (k=1 / k=2), enter at the confirming close
  star_break                  loose star / hammer above (below) the 2 prior candles; enter when price breaks its
                              low (high) within the next 2 candles before taking its high (low) - stop-order fill
  strict_pivot1               spec premier candle that is a k=1 pivot, enter at the confirming close
  pivot2 / pivot3             any pivot, k=2 / k=3, enter at the confirming close
Entries only 10:00-15:30 ET (not the first or last 30 minutes). Outcomes: research.outcomes (r15/r60, ATR race)
plus a structure race: stop just beyond the pivot candle's extreme (+0.02%), target 2x that risk, within 60 min.

  python scripts/pivot_test.py [SYM ...] [--report]   -> results/pivots/<SYM>.pkl, reports/pivots.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import fib, indicators as ind, research as R, vpa  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402
from midcap_test import MAG, MID, cost_bps  # noqa: E402
from structure_test import swing_feats  # noqa: E402

OUT = Path("results/pivots")
TFS = ["9m", "15m", "29m", "60m"]
SPLIT = pd.Timestamp("2024-11-01")
STRICT_BEAR = {"SHOOTING_STAR", "SHOOTING_STAR_IN_DOWNTREND", "HANGING_MAN", "HANGING_MAN_SHOOTING_STAR", "LL_DOJI_AT_HIGH"}
STRICT_BULL = {"HAMMER", "LL_DOJI_AT_LOW"}


def pivot(b: pd.DataFrame, k: int, kind: str) -> pd.Series:
    x = b.high if kind == "H" else b.low
    day = pd.Series(b.index.normalize(), index=b.index)
    ok = pd.Series(True, index=b.index)
    for j in range(1, k + 1):
        for sh in (j, -j):
            other = x.shift(sh)
            ok &= (x > other) if kind == "H" else (x < other)
            ok &= day.shift(sh) == day
    return ok.fillna(False)


def shapes(b: pd.DataFrame) -> pd.DataFrame:
    rng = (b.high - b.low).replace(0, np.nan)
    top, bot = b[["open", "close"]].max(axis=1), b[["open", "close"]].min(axis=1)
    up, lo, body = (b.high - top) / rng, (bot - b.low) / rng, (top - bot) / rng
    return pd.DataFrame({"star": (up >= 0.45) & (up > body) & (lo <= 0.25),
                         "hammer": (lo >= 0.45) & (lo > body) & (up <= 0.25)}, index=b.index).fillna(False)


def in_window(s, idx: np.ndarray) -> np.ndarray:
    m = s.minute[idx]                      # minutes since 9:30 at the 1m close
    return (m >= 30) & (m <= 360)


def events(s, b: pd.DataFrame, tf: str) -> pd.DataFrame:
    sh = shapes(b)
    strict = V.premier(b)
    st_bear = pd.Series(False, index=b.index)
    st_bull = pd.Series(False, index=b.index)
    st_bear.loc[strict.index[strict.type.isin(STRICT_BEAR)].unique()] = True
    st_bull.loc[strict.index[strict.type.isin(STRICT_BULL)].unique()] = True
    rv = vpa.relvol_tod(b)
    vc = pd.cut(rv, vpa.VOL_CLASSES, labels=vpa.VOL_NAMES, right=False).astype(str)
    defs = []
    for k in (1, 2, 3):
        ph, pl = pivot(b, k, "H"), pivot(b, k, "L")
        conf = b.closes_at.shift(-k)
        if k in (1, 2):
            defs.append((f"star_pivot{k}", ph & sh.star, pl & sh.hammer, conf))
        if k == 1:
            defs.append(("strict_pivot1", ph & st_bear, pl & st_bull, conf))
        if k in (2, 3):
            defs.append((f"pivot{k}", ph, pl, conf))
    rows = []
    for name, mh, ml, conf in defs:
        for bias, m in ((-1, mh), (1, ml)):
            m = m & conf.notna()
            j = R._bar_close_index(s, pd.Series(conf[m].to_numpy()))
            keep = j >= 0
            idx = b.index[m][keep]
            rows.append(pd.DataFrame({"event": name, "bias": bias, "i": j[keep], "bar": idx,
                                      "ext": (b.high if bias < 0 else b.low).reindex(idx).to_numpy()}))
    # star_break: left side only (above the 2 prior highs), then a break of the star's low within 2 candles
    lo1, hi1 = s.m1.low.to_numpy(), s.m1.high.to_numpy()
    op1 = s.m1.open.to_numpy()
    step = b.closes_at - b.index.to_series()
    for bias, m in ((-1, sh.star & (b.high > b.high.shift(1)) & (b.high > b.high.shift(2))),
                    (1, sh.hammer & (b.low < b.low.shift(1)) & (b.low < b.low.shift(2)))):
        cand = b[m]
        start = np.searchsorted(s.clock, cand.closes_at.values)  # first 1m bar after the candle closes
        ii, px, bars_ = [], [], []
        for n, (t0, H, L) in enumerate(zip(start, cand.high.to_numpy(), cand.low.to_numpy())):
            span = int(2 * step.loc[cand.index[n]] / pd.Timedelta(minutes=1))
            last = min(t0 + span, len(lo1)) - 1
            if t0 > last or s.day_last[t0] != s.day_last[min(last, len(lo1) - 1)]:
                last = min(last, s.day_last[min(t0, len(lo1) - 1)])
            for q in range(t0, last + 1):
                if bias < 0:
                    if hi1[q] > H:
                        break
                    if lo1[q] < L:
                        ii.append(q); px.append(min(op1[q], L)); bars_.append(cand.index[n]); break
                else:
                    if lo1[q] < L:
                        break
                    if hi1[q] > H:
                        ii.append(q); px.append(max(op1[q], H)); bars_.append(cand.index[n]); break
        bars_ = pd.DatetimeIndex(bars_)
        rows.append(pd.DataFrame({"event": "star_break", "bias": bias, "i": np.array(ii, dtype=int), "bar": bars_,
                                  "ext": (b.high if bias < 0 else b.low).reindex(bars_).to_numpy(),
                                  "entry_px": np.array(px, dtype=float)}))
    ev = pd.concat(rows, ignore_index=True)
    ev = ev[in_window(s, ev.i.to_numpy())].reset_index(drop=True)
    ev["tf"] = tf
    ev["vol_class"] = vc.reindex(ev.bar).to_numpy()
    sw = b.join(swing_feats(b))
    div = R.asof(sw, b.closes_at.reindex(ev.bar).to_numpy(), ["div_high", "div_low"])
    ev["rsi_div"] = np.where(ev.bias < 0, div.div_high, div.div_low) == 1
    return ev


def structure_race(s, ev: pd.DataFrame) -> pd.DataFrame:
    """Stop just beyond the pivot candle's extreme, target 2R, 60 minutes, same bar = stop."""
    C, H, L = (s.m1[c].to_numpy() for c in ("close", "high", "low"))
    i, d = ev.i.to_numpy(), ev.dir.to_numpy().astype(float)
    e = ev.entry.to_numpy()
    lim = ev.entry_px.notna().to_numpy() if "entry_px" in ev else np.zeros(len(ev), bool)
    # stop beyond the pivot extreme when trading with the bias; for "against", mirror the same distance
    risk = np.abs(ev.ext.to_numpy() * (1 + 0.0002 * np.sign(ev.ext.to_numpy() - e)) - e)
    risk = np.maximum(risk, 0.0005 * e)
    last = s.day_last[i]
    J = i[:, None] + np.arange(1, R.HORIZON + 1)
    valid = J <= last[:, None]
    Jc = np.minimum(J, last[:, None])
    fav = np.where(d[:, None] > 0, H[Jc] - e[:, None], e[:, None] - L[Jc])
    adv = np.where(d[:, None] > 0, e[:, None] - L[Jc], H[Jc] - e[:, None])
    fav, adv = np.where(valid, fav, -np.inf), np.where(valid, adv, -np.inf)
    adv0 = np.where(lim, np.where(d > 0, e - L[i], H[i] - e), -np.inf)
    adv = np.column_stack([adv0, adv])
    fav = np.column_stack([np.full(len(i), -np.inf), fav])
    hs, ht = adv >= risk[:, None], fav >= 2 * risk[:, None]
    fs = np.where(hs.any(1), hs.argmax(1), 10**6)
    ft = np.where(ht.any(1), ht.argmax(1), 10**6)
    end = d * (C[np.minimum(i + R.HORIZON, last)] - e)
    res = np.where((fs <= ft) & (fs < 10**6), -risk, np.where(ft < fs, 2 * risk, end))
    return pd.DataFrame({"st_win": ft < fs, "st_gross_pct": res / e * 100, "st_risk_pct": risk / e * 100})


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    frames = {tf: V.frame(s.m1, tf) for tf in TFS + ["4h"]}
    frames["D"] = fib.daily_bars(s.m1)
    frames["D"]["volume"] = s.m1.volume.groupby(s.m1.index.normalize()).sum()
    frames["D"]["atr"] = ind.atr(frames["D"])
    frames["1h"] = frames["60m"]
    gaps = {tf: V.live_gaps(s, frames[tf], n) for tf, n in V.GAP_TFS.items()}
    fstates = {"1h": fib.state(fib.legs(frames["1h"], 3), s.clock), "D": fib.state(fib.legs(frames["D"], 2), s.clock)}
    ev = pd.concat([events(s, frames[tf], tf) for tf in TFS], ignore_index=True)
    parts = []
    for mode in ("with", "against"):
        e = ev.copy()
        e["mode"], e["dir"] = mode, e.bias if mode == "with" else -e.bias
        if mode == "against":
            e["entry_px"] = np.nan          # the opposite side enters at market on the same minute
        parts.append(e)
    ev = pd.concat(parts, ignore_index=True)
    out = []
    for a in range(0, len(ev), 40000):
        ch = ev.iloc[a:a + 40000].reset_index(drop=True)
        oc = R.outcomes(s, ch)
        ch = pd.concat([ch, oc], axis=1)
        ch = pd.concat([ch, structure_race(s, ch)], axis=1)
        out.append(ch)
    ev = pd.concat(out, ignore_index=True)
    i, px, a5, bias = ev.i.to_numpy(), ev.entry.to_numpy(), s.atr5_clock[ev.i.to_numpy()], ev.bias.to_numpy()
    for tag, st in fstates.items():
        f = fib.features(st.iloc[i].reset_index(drop=True), px, a5, bias, tag)
        ev[f"fib_{tag}"] = (f[f"fib{tag}_gp"] | f[f"fib{tag}_retr"]).to_numpy()
    w = ev["mode"] == "with"
    for tf, g in gaps.items():
        col = np.zeros(len(ev), bool)
        col[w.to_numpy()] = V.near_gap(g, i[w], px[w], a5[w], bias[w])
        ev[f"fvg_{tf}"] = col
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[i])
    ev = ev.drop(columns=["bar"])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev) // 2} events"


def agg(g: pd.DataFrame) -> dict:
    n = len(g)
    if not n:
        return {"n": 0}
    c = g.sym.map(cost_bps).to_numpy()
    r15, r60 = g.r15.to_numpy() + 2 - c, g.r60.to_numpy() + 2 - c            # outcomes were net of 2 bps
    st = g.st_gross_pct.to_numpy() - c / 100
    st_r = st / g.st_risk_pct.to_numpy()
    return {"n": n, "win15": round((r15 > 0).mean() * 100, 1), "r15": round(r15.mean(), 1), "r60": round(r60.mean(), 1),
            "st_win": round(g.st_win.mean() * 100, 1), "st_R": round(st_r.mean(), 3),
            "st_2se": round(2 * st_r.std() / np.sqrt(n), 3), "risk%": round(g.st_risk_pct.mean(), 2)}


def two(t: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for key, g in t.groupby(by, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(by, key))
        for p, gg in (("d", g[g.time < SPLIT]), ("h", g[g.time >= SPLIT])):
            r.update({f"{k}_{p}": v for k, v in agg(gg).items()})
        rows.append(r)
    return pd.DataFrame(rows)


def report() -> None:
    ev = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    ev["universe"] = np.where(ev.sym.isin(MID), "mid-cap", "Mag7+")
    w = ev[ev["mode"] == "with"].copy()
    w["fib"] = w.fib_1h | w.fib_D
    w["fvg"] = w.fvg_1h | w.fvg_4h | w.fvg_D
    L = ["# Pivot shooting stars / hammers and pivots in general\n",
         f"{len(w)} signals on {len(ev.sym.unique())} tickers, {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}, "
         "entries 10:00-15:30 ET only. `_d` = before 2024-11-01, `_h` = after.",
         "Costs = each ticker's measured spread + 1 bp. win15 = % in profit after 15 min; r15/r60 = bps after cost; "
         "st_* = structure stop just beyond the pivot candle's extreme, 2R target, 60 min: st_win = target first, "
         "st_R = average R after cost, risk% = average stop distance.",
         "with = short at a pivot high / long at a pivot low; against = the opposite.\n",
         "## 1. Every event, timeframe and side (both universes)\n", two(ev, ["universe", "event", "tf", "mode"]).to_markdown(index=False)]
    for c in ["vol_class", "fib", "fvg", "rsi_div"]:
        L.append(f"\n## By {c} (with, pooled timeframes)\n")
        L.append(two(w, ["universe", "event", c]).to_markdown(index=False))
    Path("reports/pivots.md").write_text("\n".join(L) + "\n")
    print("wrote reports/pivots.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
