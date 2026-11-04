"""Oscillator stack (1h + 15m, optionally + 5m) with fib / FVG context, and the user's runner exits.

Signals: research.stack_events for 1h+15m and 1h+15m+5m at levels 15/20/25 (closed bars, rising edge), entries
10:00-15:00 ET, scored as fade (against the stretch) and cont (with it).
Context on the trade's side: fib = at a fitting 1h / daily retracement or golden pocket (within 0.25 ATR(5m));
fvg = in or within 0.25 ATR(5m) of an unfilled 1h / 4h / daily fair value gap.
Exit plans with 2 units (results are the average of the two units, after each ticker's cost per unit):
  A  both at +0.3%           B  both at +0.5%
  C  +0.3% and +0.5%, stop stays at the original level
  D  +0.3% and +0.5%, the second unit's stop moves to breakeven once the first is sold
  E  +0.3% and +1.0%, breakeven stop after the first
Stops: 0.3%, 0.5%, 1.5 x ATR(5m). Held to targets / stop, else flat at the session close. Same minute = stop first.

  python scripts/runner_test.py [SYM ...] [--report]   -> results/runner/<SYM>.pkl, reports/runner.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import fib, indicators as ind, research as R  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402
from midcap_test import MAG, MID, cost_bps  # noqa: E402

OUT = Path("results/runner")
SPLIT = pd.Timestamp("2024-11-01")
STACKS = [["1h", "15m"], ["1h", "15m", "5m"]]
LEVELS = [15, 20, 25]
PLANS = {"A all@0.3": (0.3, 0.3, False), "B all@0.5": (0.5, 0.5, False), "C 0.3+0.5": (0.3, 0.5, False),
         "D 0.3+0.5 BE": (0.3, 0.5, True), "E 0.3+1.0 BE": (0.3, 1.0, True)}
BIG = 10**6


def first(mask: np.ndarray) -> np.ndarray:
    return np.where(mask.any(1), mask.argmax(1), BIG)


def plans(s, i, d, stop_pct):
    """Per trade, the average % result of 2 units under each plan (before costs)."""
    H, L, C = (s.m1[c].to_numpy() for c in ("high", "low", "close"))
    e = C[i]
    last = s.day_last[i]
    span = int((last - i).max())
    J = i[:, None] + np.arange(1, span + 1)
    valid = J <= last[:, None]
    Jc = np.minimum(J, last[:, None])
    fav = np.where(valid, np.where(d[:, None] > 0, H[Jc] - e[:, None], e[:, None] - L[Jc]), -np.inf) / e[:, None] * 100
    adv = np.where(valid, np.where(d[:, None] > 0, e[:, None] - L[Jc], H[Jc] - e[:, None]), -np.inf) / e[:, None] * 100
    end = d * (C[last] - e) / e * 100
    fs = first(adv >= stop_pct[:, None])
    stopped = lambda f: (fs <= f) & (fs < BIG)  # noqa: E731  (stop first on ties)
    out = {}
    for name, (t1, t2, be) in PLANS.items():
        f1, f2 = first(fav >= t1), first(fav >= t2)
        u1 = np.where(stopped(f1), -stop_pct, np.where(f1 < BIG, t1, end))
        if not be:
            u2 = np.where(stopped(f2), -stop_pct, np.where(f2 < BIG, t2, end))
        else:
            # after the first target, the second unit is stopped at entry (adv >= 0) from the next minute on
            after = np.arange(span)[None, :] > f1[:, None]
            fbe = first((adv >= 0) & after)
            u2 = np.where(stopped(f1), -stop_pct,
                          np.where(f1 == BIG, end,
                                   np.where(f2 <= fbe, np.where(f2 < BIG, t2, end), 0.0)))
            u2 = np.where((f1 < BIG) & ~stopped(f1) & (f2 == BIG) & (fbe == BIG), end, u2)
        out[name] = (u1 + u2) / 2
    return out


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    ev = pd.concat([R.stack_events(s, tfs, lv) for tfs in STACKS for lv in LEVELS], ignore_index=True)
    ev = ev[(s.minute[ev.i.to_numpy()] >= 30) & (s.minute[ev.i.to_numpy()] <= 330)].reset_index(drop=True)
    i, d = ev.i.to_numpy(), ev.dir.to_numpy().astype(float)
    px, a5 = s.m1.close.to_numpy()[i], s.atr5_clock[i]
    # context on the trade's side
    frames = {"1h": V.frame(s.m1, "60m"), "4h": V.frame(s.m1, "4h")}
    dd = fib.daily_bars(s.m1)
    dd["volume"] = s.m1.volume.groupby(s.m1.index.normalize()).sum()
    dd["atr"] = ind.atr(dd)
    frames["D"] = dd
    fstates = {"1h": fib.state(fib.legs(frames["1h"], 3), s.clock), "D": fib.state(fib.legs(frames["D"], 2), s.clock)}
    fibfit = np.zeros(len(ev), bool)
    for tag, st in fstates.items():
        f = fib.features(st.iloc[i].reset_index(drop=True), px, a5, d, tag)
        fibfit |= (f[f"fib{tag}_gp"] | f[f"fib{tag}_retr"]).to_numpy()
    fvgfit = np.zeros(len(ev), bool)
    for tf, n in V.GAP_TFS.items():
        fvgfit |= V.near_gap(V.live_gaps(s, frames[tf], n), i, px, a5, d)
    ev["fib"], ev["fvg"] = fibfit, fvgfit
    res = []
    for sname in ("0.3%", "0.5%", "1.5ATR"):
        sp = np.full(len(ev), float(sname[:-1])) if sname.endswith("%") else 1.5 * a5 / px * 100
        for a in range(0, len(ev), 4000):
            sl = slice(a, a + 4000)
            out = plans(s, i[sl], d[sl], sp[sl])
            chunk = ev.iloc[sl][["variant", "mode", "fib", "fvg"]].copy()
            chunk["stop"], chunk["stop_pct"] = sname, sp[sl]
            for k, v in out.items():
                chunk[k] = v
            chunk["time"] = pd.to_datetime(s.clock[i[sl]])
            res.append(chunk)
    r = pd.concat(res, ignore_index=True)
    r["sym"] = sym
    OUT.mkdir(parents=True, exist_ok=True)
    r.to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev)} stack signals"


def report() -> None:
    t = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    t["universe"] = np.where(t.sym.isin(MID), "mid-cap", "Mag7+")
    t["cost"] = t.sym.map(cost_bps) / 100
    t["context"] = np.select([t.fib & t.fvg, t.fib, t.fvg], ["fib + fvg", "fib only", "fvg only"], "neither")
    t["period"] = np.where(t.time < SPLIT, "d", "h")

    def tab(g, by):
        rows = []
        for key, gg in g.groupby(by, observed=True):
            key = key if isinstance(key, tuple) else (key,)
            r = dict(zip(by, key))
            for p in ("d", "h"):
                q = gg[gg.period == p]
                r[f"n_{p}"] = len(q)
                for name in PLANS:
                    net = q[name] - q.cost
                    r[f"{name.split()[0]} avg%_{p}"] = round(net.mean(), 3)
                    if name.startswith(("A", "D")):
                        r[f"{name.split()[0]} win%_{p}"] = round((net > 0).mean() * 100, 1)
            rows.append(r)
        return pd.DataFrame(rows)

    L = ["# Oscillator stack (1h + 15m [+ 5m]) with fib / FVG context, and runner exits\n",
         f"{t.groupby(['sym','variant','mode','time']).ngroups // 1} trades x 3 stops on {len(t.sym.unique())} tickers. "
         "`_d` = before 2024-11-01, `_h` = after. Each trade = 2 units; avg% = average per trade (both units) after each "
         "ticker's cost; win% = trade net > 0. Plans: A both at +0.3%; B both at +0.5%; C +0.3% then +0.5% (stop stays); "
         "D +0.3% then +0.5% with breakeven stop after the first; E +0.3% then +1.0% with breakeven.\n"]
    for stop in ("0.3%", "0.5%", "1.5ATR"):
        g = t[t.stop == stop]
        L.append(f"\n## Stop {stop}: by stack, level and side\n")
        L.append(tab(g, ["universe", "variant", "mode"]).to_markdown(index=False))
        L.append(f"\n## Stop {stop}: by fib / FVG context (all stacks pooled)\n")
        L.append(tab(g, ["universe", "mode", "context"]).to_markdown(index=False))
    Path("reports/runner.md").write_text("\n".join(L) + "\n")
    print("wrote reports/runner.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
