"""Bounces where a moving average and an unfilled fair value gap line up (the AAPL 2026-11-05 chart).

Levels (all known at the time, nothing from the future):
  dEMA9 / dEMA21   daily EMA including the current price (TradingView's live daily EMA: prev EMA * (1-a) + price * a)
  hEMA9 / hEMA21   1h EMA of closed 1h candles
  gap              unfilled bullish gap (for longs) / bearish gap (shorts) on 15m, 1h, 4h or daily, price within 0.25 ATR(5m)

A. Candle bounce: the scanner's pivot-wick candle (upper / lower wick >= 40% of the range and >= the body, small other
   wick, wick = extreme of the last 12 candles) on 9m / 15m / 5m, whose wick is within 0.25 ATR(5m) of the EMA.
   Orders and exits exactly as vpa_trading/live.py (stop-entry through the candle, stop beyond the wick, 1R target).
B. Touch limit: first touch (10:00-15:30 ET) of the EMA from the trade's side by at least 0.2 ATR(5m); limit order at the
   EMA, stop 1 ATR(5m) beyond it, 1R (= 1 ATR(5m)) target, flat at 15:50.
Costs = ticker spread + 1 bp. `_d` before 2024-11-01, `_h` after.

  python scripts/ema_gap_test.py [SYM ...] [--report]  -> results/ema_gap/<SYM>.pkl, reports/ema_gap.md
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
from pivot_relax_test import sim, FLAT_MIN  # noqa: E402

OUT = Path("results/ema_gap")
SPLIT = pd.Timestamp("2024-11-01")
TFS = ("5m", "9m", "15m")
TOL = 0.25


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    O, H, L, C = (s.m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    n1 = len(C)
    frames = {"1h": V.frame(s.m1, "60m"), "4h": V.frame(s.m1, "4h")}
    dd = fib.daily_bars(s.m1)
    dd["volume"] = s.m1.volume.groupby(s.m1.index.normalize()).sum()
    dd["atr"] = ind.atr(dd)
    frames["D"] = dd
    gaps = {tf: V.live_gaps(s, frames[tf], k) for tf, k in V.GAP_TFS.items()}
    gaps["15m"] = V.live_gaps(s, V.frame(s.m1, "15m"), 3)
    # ---- levels at every minute close
    day = s.m1.index.normalize()
    lev = {}
    for n in (9, 21):
        a = 2 / (n + 1)
        prev = dd.close.ewm(span=n, adjust=False).mean().shift(1).reindex(day).to_numpy()
        lev[f"dEMA{n}"] = a * C + (1 - a) * prev
    b1 = frames["1h"]
    k1 = np.searchsorted(b1.closes_at.to_numpy(), s.clock, side="right") - 1
    for n in (9, 21):
        e = b1.close.ewm(span=n, adjust=False).mean().to_numpy()
        lev[f"hEMA{n}"] = np.where(k1 >= 0, e[np.maximum(k1, 0)], np.nan)
    a5 = s.atr5_clock
    mi = s.minute
    rows = []
    # ---------------- A. candle bounce
    for tf in TFS:
        b = V.frame(s.m1, tf)
        rng = (b.high - b.low).replace(0, np.nan)
        top, bot = b[["open", "close"]].max(axis=1), b[["open", "close"]].min(axis=1)
        body, upw, low_w = (b.close - b.open).abs(), b.high - top, bot - b.low
        ut = (upw >= 0.4 * rng) & (upw >= body) & (low_w <= 0.3 * rng) & (b.high >= b.high.rolling(12).max())
        ub = (low_w >= 0.4 * rng) & (low_w >= body) & (upw <= 0.3 * rng) & (b.low <= b.low.rolling(12).min())
        rv = vpa.relvol_tod(b)
        for d, m, ext in ((-1, ut, b.high), (1, ub, b.low)):
            e = pd.DataFrame({"hi": b.high[m], "lo": b.low[m], "ext": ext[m], "rvol": rv[m], "closes_at": b.closes_at[m]})
            e["dir"], e["tf"], e["kind"] = d, tf, "candle"
            rows.append(e)
    ev = pd.concat(rows)
    j = R._bar_close_index(s, pd.Series(pd.to_datetime(ev.closes_at).to_numpy()))
    ev = ev[j >= 0].assign(i=j[j >= 0]).reset_index(drop=True)
    ev = ev[(mi[ev.i.to_numpy()] >= 30) & (mi[ev.i.to_numpy()] <= 360)].reset_index(drop=True)
    i, d, ext = ev.i.to_numpy(), ev.dir.to_numpy(), ev.ext.to_numpy().astype(float)
    a = a5[i]
    for name, v in lev.items():
        ev[f"near_{name}"] = np.abs(ext - v[i]) <= TOL * a
    for tf, g in gaps.items():
        ev[f"gap_{tf}"] = V.near_gap(g, i, ext, a, d)
    res = [sim(O, H, L, C, s.minute, s.day_last, int(x), int(y), float(h), float(l), int(t.rstrip("m")))
           for x, y, h, l, t in zip(i, d, ev.hi, ev.lo, ev.tf)]
    ev["status"], ev["move"], ev["risk"] = (np.array([r[k] for r in res]) for k in range(3))
    ev["cost_r"] = np.where(ev.risk > 0, C[i] * cost_bps(sym) / 1e4 / ev.risk.replace(0, np.nan), 0.0)
    ev["r_net"] = np.where(ev.status > 0, ev.move / ev.risk.replace(0, np.nan) - ev.cost_r, 0.0)
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[i])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.drop(columns=["closes_at"]).to_pickle(OUT / f"{sym}_candle.pkl")
    # ---------------- B. touch limit at the EMA
    last = s.day_last
    out = []
    for name, v in lev.items():
        for d in (1, -1):
            seen: set = set()
            for i0 in range(1, n1 - 1):
                if not (30 <= mi[i0] <= 360):
                    continue
                L0 = v[i0 - 1]
                if np.isnan(L0) or np.isnan(a5[i0 - 1]):
                    continue
                touch = (L[i0] <= L0) if d > 0 else (H[i0] >= L0)
                if not touch:
                    continue
                if not ((C[i0 - 1] - L0) * d >= 0.2 * a5[i0 - 1]):
                    continue                      # must come from the right side by 0.2 ATR
                key = day[i0]
                if key in seen:
                    continue
                seen.add(key)
                out.append((name, d, i0, L0, a5[i0 - 1]))
    if out:
        B = pd.DataFrame(out, columns=["level", "dir", "i", "px", "atr"])
        for tf, g in gaps.items():
            B[f"gap_{tf}"] = V.near_gap(g, B.i.to_numpy(), B.px.to_numpy(), B.atr.to_numpy(), B.dir.to_numpy())
        status, mv = [], []
        for i0, dr, px, at in zip(B.i, B.dir, B.px, B.atr):
            stop, tgt = px - dr * at, px + dr * at
            fill = min(O[i0], px) if dr > 0 else max(O[i0], px)
            k1_ = last[i0]
            cut = np.flatnonzero(mi[i0 + 1:k1_ + 1] >= FLAT_MIN)
            if len(cut):
                k1_ = i0 + 1 + int(cut[0])
            if k1_ <= i0:
                status.append(3), mv.append(0.0)
                continue
            h_, l_ = H[i0 + 1:k1_ + 1], L[i0 + 1:k1_ + 1]
            hs = l_ <= stop if dr > 0 else h_ >= stop
            ht = h_ >= tgt if dr > 0 else l_ <= tgt
            fs = int(hs.argmax()) if hs.any() else 10 ** 9
            ft = int(ht.argmax()) if ht.any() else 10 ** 9
            if fs <= ft and fs < 10 ** 9:
                status.append(2), mv.append((stop - fill) * dr)
            elif ft < fs:
                status.append(1), mv.append((tgt - fill) * dr)
            else:
                status.append(3), mv.append((C[k1_] - fill) * dr)
        B["status"], B["move"], B["risk"] = status, mv, B.atr
        B["cost_r"] = B.px * cost_bps(sym) / 1e4 / B.atr
        B["r_net"] = B.move / B.atr - B.cost_r
        B["sym"], B["time"] = sym, pd.to_datetime(s.clock[B.i.to_numpy()])
        B["at_gap"] = B[[f"gap_{t}" for t in gaps]].any(axis=1)
        B.to_pickle(OUT / f"{sym}_touch.pkl")
    return f"{sym}: {len(ev)} candle events, {len(out)} touch events"


def agg(g: pd.DataFrame) -> dict:
    f = g[g.status > 0]
    n = len(f)
    if not n:
        return {"n": 0}
    r = f.r_net.to_numpy()
    return {"n": n, "win%": round((f.status == 1).mean() * 100, 1), "avgR": round(r.mean(), 3),
            "2se": round(2 * r.std() / np.sqrt(n), 3) if n > 1 else np.nan}


def table(ev: pd.DataFrame, rows: list[tuple[str, pd.Series]]) -> pd.DataFrame:
    out = []
    for name, m in rows:
        r = {"set": name}
        for p, g in (("d", ev[m & (ev.time < SPLIT)]), ("h", ev[m & (ev.time >= SPLIT)])):
            r.update({f"{k}_{p}": v for k, v in agg(g).items()})
        out.append(r)
    return pd.DataFrame(out)


def report() -> None:
    cs = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*_candle.pkl"))], ignore_index=True)
    ts = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*_touch.pkl"))], ignore_index=True)
    for df in (cs, ts):
        df["uni"] = np.where(df.sym.isin(MID), "mid-cap", "Mag7+")
    cs["any_gap"] = cs[["gap_15m", "gap_1h", "gap_4h", "gap_D"]].any(axis=1)
    cs["d_ema"] = cs.near_dEMA9 | cs.near_dEMA21
    cs["h_ema"] = cs.near_hEMA9 | cs.near_hEMA21
    cs["any_ema"] = cs.d_ema | cs.h_ema
    L = ["# Moving average + fair value gap bounces\n",
         f"{len(cs):,} pivot-wick candles and {len(ts):,} first-touch events, {cs.sym.nunique()} tickers, "
         f"{cs.time.min():%Y-%m-%d} to {cs.time.max():%Y-%m-%d}. See scripts/ema_gap_test.py for the rules. "
         "`_d` = before 2024-11-01, `_h` = after; avgR is net of costs; 2se = two standard errors.\n"]
    for uni in ("Mag7+", "mid-cap"):
        c = cs[(cs.uni == uni) & cs.tf.isin(["9m", "15m"])]
        for side, sm in (("long (bounce up)", c.dir > 0), ("short (rejection down)", c.dir < 0)):
            rows = [("every pivot-wick candle", sm),
                    ("at a gap, no EMA", sm & c.any_gap & ~c.any_ema),
                    ("near an EMA, no gap", sm & ~c.any_gap & c.any_ema),
                    ("EMA + gap (any)", sm & c.any_gap & c.any_ema),
                    ("dEMA9 + gap", sm & c.any_gap & c.near_dEMA9),
                    ("dEMA21 + gap", sm & c.any_gap & c.near_dEMA21),
                    ("hEMA9 + gap", sm & c.any_gap & c.near_hEMA9),
                    ("hEMA21 + gap", sm & c.any_gap & c.near_hEMA21),
                    ("daily EMA + 1h/4h/D gap", sm & c.d_ema & (c.gap_1h | c.gap_4h | c.gap_D)),
                    ("EMA + gap + rvol >= 2", sm & c.any_gap & c.any_ema & (c.rvol >= 2))]
            L.append(f"\n## A. candle bounce, {uni}, {side}, 9m + 15m\n")
            L.append(table(c, rows).to_markdown(index=False))
        c5 = cs[(cs.uni == uni) & (cs.tf == "5m")]
        L.append(f"\n## A. candle bounce, {uni}, 5m only, EMA + gap\n")
        L.append(table(c5, [("long, EMA + gap", (c5.dir > 0) & c5.any_gap & c5.any_ema),
                            ("short, EMA + gap", (c5.dir < 0) & c5.any_gap & c5.any_ema)]).to_markdown(index=False))
    for uni in ("Mag7+", "mid-cap"):
        t = ts[ts.uni == uni]
        rows = []
        for lvl in ("dEMA9", "dEMA21", "hEMA9", "hEMA21"):
            for side, dv in (("long", 1), ("short", -1)):
                m = (t.level == lvl) & (t.dir == dv)
                rows += [(f"{lvl} {side}, touch", m), (f"{lvl} {side}, touch + gap", m & t.at_gap)]
        L.append(f"\n## B. touch limit at the EMA, {uni} (stop 1 ATR(5m), target 1 ATR(5m))\n")
        L.append(table(t, rows).to_markdown(index=False))
    Path("reports/ema_gap.md").write_text("\n".join(L) + "\n")
    print("wrote reports/ema_gap.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
