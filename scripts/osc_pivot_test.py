"""Pivot wick candle + the 15 / 9 / 5 minute oscillator all elevated (+ a volume surge): the TSLA 12:15 shooting star.

Candle: the scanner's pivot-wick candle (upper / lower wick >= 40% of the range and >= the body, small other wick, wick =
extreme of the last 12 candles) on 5m, 9m or 15m. Oscillator = the port of the user's Willard oscillator
(research.prepare -> osc_clock), read at the candle close. "Elevated" = the 5m, 9m and 15m oscillators all >= LEVEL for a
short, all <= 100 - LEVEL for a long. Volume surge = the candle's volume vs the median at that time of day (rvol).
Orders and exits as vpa_trading/live.py (stop-entry through the candle, stop beyond the wick, 1R target, flat 15:50).
Costs = ticker spread + 1 bp. `_d` before 2024-11-01, `_h` after.

  python scripts/osc_pivot_test.py [SYM ...]     -> results/osc_pivot/<SYM>.pkl, reports/osc_pivot.md
  python scripts/osc_pivot_test.py --report
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
from pivot_relax_test import sim  # noqa: E402

OUT = Path("results/osc_pivot")
SPLIT = pd.Timestamp("2024-11-01")
TFS = ("5m", "9m", "15m")


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    O, H, L, C = (s.m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    frames = {"1h": V.frame(s.m1, "60m"), "4h": V.frame(s.m1, "4h")}
    dd = fib.daily_bars(s.m1)
    dd["volume"] = s.m1.volume.groupby(s.m1.index.normalize()).sum()
    dd["atr"] = ind.atr(dd)
    frames["D"] = dd
    gaps = {tf: V.live_gaps(s, frames[tf], n) for tf, n in V.GAP_TFS.items()}
    rows = []
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
            e["dir"], e["tf"] = d, tf
            rows.append(e)
    ev = pd.concat(rows)
    j = R._bar_close_index(s, pd.Series(pd.to_datetime(ev.closes_at).to_numpy()))
    ev = ev[j >= 0].assign(i=j[j >= 0]).reset_index(drop=True)
    mi = s.minute[ev.i.to_numpy()]
    ev = ev[(mi >= 30) & (mi <= 360)].reset_index(drop=True)
    i, d, ext = ev.i.to_numpy(), ev.dir.to_numpy(), ev.ext.to_numpy().astype(float)
    for t in ("5m", "9m", "15m"):
        ev[f"osc_{t}"] = s.osc_clock[t][i]
    # 15m EMA 9 as drawn on the chart: includes the current price (partial candle)
    b15 = V.frame(s.m1, "15m")
    e15 = b15.close.ewm(span=9, adjust=False).mean().to_numpy()
    k = np.searchsorted(b15.closes_at.to_numpy(), s.clock[i], side="right") - 1
    k = np.maximum(k, 0)
    just_closed = b15.closes_at.to_numpy()[k] == s.clock[i]
    ev["ema15"] = np.where(just_closed, e15[k], 0.2 * C[i] + 0.8 * e15[k])
    ev["stretch"] = np.where(d < 0, ext - ev.ema15, ev.ema15 - ext) / s.atr5_clock[i]     # ATR(5m) units beyond the 15m EMA 9
    for tf, g in gaps.items():
        ev[f"gap_{tf}"] = V.near_gap(g, i, ext, s.atr5_clock[i], d)
    ev["at_gap"] = ev.gap_1h | ev.gap_4h | ev.gap_D
    res = [sim(O, H, L, C, s.minute, s.day_last, int(x), int(y), float(h), float(l), int(t.rstrip("m")))
           for x, y, h, l, t in zip(i, d, ev.hi, ev.lo, ev.tf)]
    ev["status"], ev["move"], ev["risk"] = (np.array([r[k] for r in res]) for k in range(3))
    ev["cost_r"] = np.where(ev.risk > 0, C[i] * cost_bps(sym) / 1e4 / ev.risk.replace(0, np.nan), 0.0)
    ev["r_net"] = np.where(ev.status > 0, ev.move / ev.risk.replace(0, np.nan) - ev.cost_r, 0.0)
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[i])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.drop(columns=["closes_at"]).to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev)} pivot-wick candles"


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
    ev = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    ev["uni"] = np.where(ev.sym.isin(MID), "mid-cap", "Mag7+")
    L = ["# Pivot wick candle + oscillator (15 / 9 / 5) all elevated + volume surge\n",
         f"{len(ev):,} pivot-wick candles, {ev.sym.nunique()} tickers, {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}. "
         "See scripts/osc_pivot_test.py. avgR net of costs; 2se = two standard errors; `_d` before 2024-11-01, `_h` after.\n"]
    for uni in ("Mag7+", "mid-cap"):
        u = ev[ev.uni == uni]
        for side, sm in (("short (all three oscillators high)", u.dir < 0), ("long (all three low)", u.dir > 0)):
            def hi(level):
                lo_ = 100 - level
                a = u[["osc_5m", "osc_9m", "osc_15m"]]
                return (a.min(axis=1) >= level) if u.dir.iloc[0] < 0 or True else None
            osc = {}
            for level in (70, 80, 90):
                osc[level] = np.where(u.dir < 0, u[["osc_5m", "osc_9m", "osc_15m"]].min(axis=1) >= level,
                                      u[["osc_5m", "osc_9m", "osc_15m"]].max(axis=1) <= 100 - level)
            rows = [("every pivot-wick candle (5m/9m/15m)", sm)]
            for x in (0.5, 1.0, 1.5):
                rows.append((f"wick {x} ATR(5m) beyond the 15m EMA 9", sm & (u.stretch >= x)))
            for x in (0.5, 1.0, 1.5):
                rows.append((f"{x} ATR beyond EMA + oscillators >= 80", sm & (u.stretch >= x) & osc[80]) if x == 0.5 else
                            (f"{x} ATR beyond EMA + oscillators >= 80", sm & (u.stretch >= x) & osc[80]))
            for x in (0.5, 1.0):
                rows.append((f"{x} ATR beyond EMA + osc >= 80 + rvol >= 2", sm & (u.stretch >= x) & osc[80] & (u.rvol >= 2)))
            rows.append(("1.0 ATR beyond EMA + osc >= 80 + rvol >= 2, 5m only", sm & (u.stretch >= 1.0) & osc[80] & (u.rvol >= 2) & (u.tf == "5m")))
            rows.append(("1.0 ATR beyond EMA + osc >= 80 + rvol >= 2 + gap", sm & (u.stretch >= 1.0) & osc[80] & (u.rvol >= 2) & u.at_gap))
            for level in (70, 80, 90):
                rows.append((f"all three oscillators >= {level} (<= {100 - level} for longs)", sm & osc[level]))
            rows += [("oscillators >= 80 + rvol >= 2", sm & osc[80] & (u.rvol >= 2)),
                     ("oscillators >= 80 + rvol >= 3", sm & osc[80] & (u.rvol >= 3)),
                     ("oscillators >= 80 + rvol >= 2 + at a 1h/4h/D gap", sm & osc[80] & (u.rvol >= 2) & u.at_gap),
                     ("oscillators >= 80, 5m candles only", sm & osc[80] & (u.tf == "5m")),
                     ("oscillators >= 80, 5m, rvol >= 3", sm & osc[80] & (u.tf == "5m") & (u.rvol >= 3)),
                     ("oscillators >= 80, 9m + 15m only", sm & osc[80] & u.tf.isin(["9m", "15m"]))]
            L.append(f"\n## {uni}: {side}\n")
            L.append(table(u, rows).to_markdown(index=False))
    Path("reports/osc_pivot.md").write_text("\n".join(L) + "\n")
    print("wrote reports/osc_pivot.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
