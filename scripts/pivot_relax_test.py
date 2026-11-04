"""Pivot-style premier candles vs the live scanner's rules, traded with the scanner's own mechanics.

Signal candle on 2m/5m/9m/15m. Order mechanics = vpa_trading/live.py: stop-entry one cent beyond the candle's far side
(short below its low, long above its high) within 2 candles, cancelled if the wick is taken first, stop one cent beyond the
wick (+0.02%), target 1R, flat at 15:50 ET, entries 10:00-15:30 ET. Sized so a stop-out = 1R. Costs = ticker spread + 1 bp.

Variants (same 1h/4h/D gap rule as live, also shown without a gap):
  A  live rules      vpa.detect premier types (star / hammer shapes with the trend or near-high/low context)
  B  strict+pivot    spec star / hammer shape, wick is the highest / lowest of the last 12 candles
  C  relaxed+pivot   relaxed shape (wick >= 45% of range and >= 1.2x body, other wick <= 25%, close in the right half),
                     wick is the extreme of the last 12 candles
  D  relaxed+pivot6  same, extreme of the last 6 candles
  E  relaxed+context relaxed shape with the live context (prior trend / near high-low)
Shorts are also shown with the live trend filter (price below session VWAP and 5m EMA9 below EMA21).

  python scripts/pivot_relax_test.py [SYM ...] [--report]   -> results/pivot_relax/<SYM>.pkl, reports/pivot_relax.md
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
from vpa_trading import fib, indicators as ind, research as R, vpa  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402
from midcap_test import MAG, MID, cost_bps  # noqa: E402

OUT = Path("results/pivot_relax")
SPLIT = pd.Timestamp("2024-11-01")
TFS = ("2m", "5m", "9m", "15m")   # the report also splits out 5m/9m/15m
PREMIER_TYPES = {"SHOOTING_STAR", "SHOOTING_STAR_IN_DOWNTREND", "HAMMER", "HANGING_MAN", "HANGING_MAN_SHOOTING_STAR"}
FLAT_MIN = 380    # 15:50 ET = 380 minutes after 9:30


def shapes(b: pd.DataFrame) -> dict[str, pd.Series]:
    rng = (b.high - b.low).replace(0, np.nan)
    top, bot = b[["open", "close"]].max(axis=1), b[["open", "close"]].min(axis=1)
    body, up, lo = (b.close - b.open).abs(), b.high - top, bot - b.low
    loc = (b.close - b.low) / rng
    return {"star": (up >= 2 * body) & (up >= 0.5 * rng) & (lo <= 0.15 * rng) & (top <= b.low + rng / 3),
            "ham": (lo >= 2 * body) & (lo >= 0.5 * rng) & (up <= 0.15 * rng) & (bot >= b.high - rng / 3),
            "star_r": (up >= 0.45 * rng) & (up >= 1.2 * body) & (lo <= 0.25 * rng) & (loc <= 0.5),
            "ham_r": (lo >= 0.45 * rng) & (lo >= 1.2 * body) & (up <= 0.25 * rng) & (loc >= 0.5)}


def candidates(b: pd.DataFrame) -> pd.DataFrame:
    """One row per (candle, direction) that any variant could trade, with a flag per variant."""
    sh = shapes(b)
    c = vpa.context(b, b.atr)
    det = vpa.detect(b, b.atr)
    det = det[det.type.isin(PREMIER_TYPES)]
    rng = (b.high - b.low).replace(0, np.nan)
    top, bot = b[["open", "close"]].max(axis=1), b[["open", "close"]].min(axis=1)
    body, upw, low_w = (b.close - b.open).abs(), b.high - top, bot - b.low
    user_top = (upw >= 0.4 * rng) & (upw >= body) & (low_w <= 0.3 * rng)
    user_bot = (low_w >= 0.4 * rng) & (low_w >= body) & (upw <= 0.3 * rng)
    rv = vpa.relvol_tod(b)
    parts = []
    for d, strict, relaxed, ext, ctx in ((-1, sh["star"], sh["star_r"], b.high, (c.trend == 1) | c.near_high),
                                         (1, sh["ham"], sh["ham_r"], b.low, (c.trend == -1) | c.near_low)):
        piv = {n: (ext >= ext.rolling(n).max()) if d < 0 else (ext <= ext.rolling(n).min()) for n in (6, 12)}
        flags = pd.DataFrame({"A": b.index.isin(det.index[det.bias == d]),
                              "B": strict & piv[12], "C": relaxed & piv[12], "D": relaxed & piv[6], "E": relaxed & ctx,
                              "U": (user_top if d < 0 else user_bot & (rv >= 3.0)) & piv[12]}, index=b.index)
        flags = flags[flags.any(axis=1)]
        flags["dir"], flags["ext"] = d, ext.reindex(flags.index)
        flags["hi"], flags["lo"] = b.high.reindex(flags.index), b.low.reindex(flags.index)
        flags["closes_at"] = b.closes_at.reindex(flags.index)
        parts.append(flags)
    return pd.concat(parts)


def sim(O, H, L, C, minute, last, i: int, d: int, hi: float, lo: float, step: int) -> tuple[int, float, float]:
    """(status 0 none / 1 target / 2 stop / 3 flat, (exit - fill) * d, planned risk)."""
    wick = hi if d < 0 else lo
    entry = round(lo - 0.01, 2) if d < 0 else round(hi + 0.01, 2)
    stop = math.ceil(wick * 1.0002 * 100 + 1) / 100 if d < 0 else math.floor(wick * 0.9998 * 100 - 1) / 100
    risk = abs(entry - stop)
    if risk <= 0:
        return 0, 0.0, 0.0
    target = entry + d * risk
    end = min(i + 2 * step, last[i])
    fill = None
    for j in range(i + 1, end + 1):
        if (d < 0 and H[j] > wick) or (d > 0 and L[j] < wick):
            return 0, 0.0, risk
        if (d < 0 and L[j] <= entry) or (d > 0 and H[j] >= entry):
            fill = min(O[j], entry) if d < 0 else max(O[j], entry)
            if (d < 0 and H[j] >= stop) or (d > 0 and L[j] <= stop):
                return 2, (stop - fill) * d, risk
            break
    if fill is None:
        return 0, 0.0, risk
    k0, k1 = j + 1, last[j]
    cut = np.flatnonzero(minute[k0:k1 + 1] >= FLAT_MIN)
    if len(cut):
        k1 = k0 + int(cut[0])
    if k1 < k0:
        return 3, (C[j] - fill) * d, risk
    h, l, c = H[k0:k1 + 1], L[k0:k1 + 1], C[k0:k1 + 1]
    hs = h >= stop if d < 0 else l <= stop
    ht = l <= target if d < 0 else h >= target
    fs = int(hs.argmax()) if hs.any() else 10**9
    ft = int(ht.argmax()) if ht.any() else 10**9
    if fs <= ft and fs < 10**9:
        return 2, (stop - fill) * d, risk
    if ft < fs:
        return 1, (target - fill) * d, risk
    return 3, (c[-1] - fill) * d, risk


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    frames = {"1h": V.frame(s.m1, "60m"), "4h": V.frame(s.m1, "4h")}
    dd = fib.daily_bars(s.m1)
    dd["volume"] = s.m1.volume.groupby(s.m1.index.normalize()).sum()
    dd["atr"] = ind.atr(dd)
    frames["D"] = dd
    gaps = {tf: V.live_gaps(s, frames[tf], n) for tf, n in V.GAP_TFS.items()}
    b5 = V.frame(s.m1, "5m")
    ema9, ema21 = b5.close.ewm(span=9, adjust=False).mean(), b5.close.ewm(span=21, adjust=False).mean()
    O, H, L, C = (s.m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    evs = []
    for tf in TFS:
        e = candidates(V.frame(s.m1, tf))
        e["tf"] = tf
        evs.append(e)
    ev = pd.concat(evs)
    j = R._bar_close_index(s, pd.Series(pd.to_datetime(ev.closes_at).to_numpy()))
    ev = ev[j >= 0].assign(i=j[j >= 0]).reset_index(drop=True)
    mi = s.minute[ev.i.to_numpy()]
    ev = ev[(mi >= 30) & (mi <= 360)].reset_index(drop=True)
    i, d, ext = ev.i.to_numpy(), ev.dir.to_numpy(), ev.ext.to_numpy().astype(float)
    a5 = s.atr5_clock[i]
    for tf, g in gaps.items():
        ev[f"gap_{tf}"] = V.near_gap(g, i, ext, a5, d)
    ev["at_gap"] = ev.gap_1h | ev.gap_4h | ev.gap_D
    last5 = np.searchsorted(b5.closes_at.to_numpy(), s.clock[i], side="right") - 1
    ok5 = last5 >= 0
    e9, e21 = ema9.to_numpy()[np.maximum(last5, 0)], ema21.to_numpy()[np.maximum(last5, 0)]
    ev["trend_ok"] = np.where(d < 0, (C[i] < s.vwap[i]) & (e9 < e21), True) & ok5
    res = [sim(O, H, L, C, s.minute, s.day_last, int(a), int(b), float(h), float(l), int(t.rstrip("m")))
           for a, b, h, l, t in zip(i, d, ev.hi, ev.lo, ev.tf)]
    ev["status"], ev["move"], ev["risk"] = (np.array([r[k] for r in res]) for k in range(3))
    fill_px = C[i]  # only for the cost scale (close ~ fill price)
    ev["cost_r"] = np.where(ev.risk > 0, fill_px * cost_bps(sym) / 1e4 / ev.risk.replace(0, np.nan), 0.0)
    ev["r_net"] = np.where(ev.status > 0, ev.move / ev.risk.replace(0, np.nan) - ev.cost_r, 0.0)
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[i])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.drop(columns=["closes_at"]).to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev)} candidate signals, {int((ev.status > 0).sum())} filled"


def agg(g: pd.DataFrame) -> dict:
    f = g[g.status > 0]
    n = len(f)
    if not n:
        return {"sig": len(g), "n": 0}
    r = f.r_net.to_numpy()
    return {"sig": len(g), "n": n, "win%": round((f.status == 1).mean() * 100, 1), "avg R": round(r.mean(), 3),
            "2se": round(2 * r.std() / np.sqrt(n), 3) if n > 1 else np.nan, "$/trade": round(r.mean() * 1000)}


def table(ev: pd.DataFrame, rows: list[tuple[str, pd.Series]]) -> pd.DataFrame:
    out = []
    for name, m in rows:
        g = ev[m]
        r = {"set": name}
        for p, gg in (("d", g[g.time < SPLIT]), ("h", g[g.time >= SPLIT])):
            r.update({f"{k}_{p}": v for k, v in agg(gg).items()})
        out.append(r)
    return pd.DataFrame(out)


NAMES = {"U": "U new pivot rules (longs need rvol >= 3)", "A": "A live rules", "B": "B strict + pivot12", "C": "C relaxed + pivot12", "D": "D relaxed + pivot6", "E": "E relaxed + context"}


def report() -> None:
    ev = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    ev["universe"] = np.where(ev.sym.isin(MID), "mid-cap", "Mag7+")
    days = ev.groupby("sym").time.agg(lambda t: t.dt.normalize().nunique()).sum()
    L = ["# Pivot-style candles vs the live scanner's rules\n",
         f"{len(ev):,} candidate signals, {ev.sym.nunique()} tickers, {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}. "
         "Scanner mechanics (see the script header), 1R target, costs = spread + 1 bp. `_d` = before 2024-11-01, `_h` = after. "
         "`sig` = signals, `n` = orders that filled, `win%` = target hit of the filled, `avg R` = net of costs, "
         "`2se` = two standard errors. Breakeven win rate at 1R is above 50% once costs are paid.\n"]
    for uni in ("Mag7+", "mid-cap"):
        u = ev[ev.universe == uni]
        for gap_name, gm in (("at a 1h/4h/D gap (as live)", u.at_gap), ("no gap required", u.at_gap | ~u.at_gap)):
            for side, sm in (("short", u.dir < 0), ("long", u.dir > 0)):
                rows = [(NAMES[v], u[v] & gm & sm) for v in "UABCDE"]
                if side == "short":
                    rows += [(NAMES[v] + " + trend filter", u[v] & gm & sm & u.trend_ok) for v in "UABCDE"]
                L.append(f"\n## {uni}: {side}s, {gap_name}\n")
                L.append(table(u, rows).to_markdown(index=False))
    Path("reports/pivot_relax.md").write_text("\n".join(L) + "\n")
    print("wrote reports/pivot_relax.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
