"""A 0.3% profit target on premier-candle signals, with several stops, vs the opposite side and random entries.

Signals (with Coulling's bias, from earlier tests): pivot star-break and star_pivot1 (results/pivots), strict premier
candles on 9/15/29/60m (results/vpa_fib). Baselines: the same moments traded the other way, and random minutes in the
same 10:00-15:30 ET window with a random direction. Race on 1m bars up to 120 minutes (same bar = stop), else exit.
Costs = each ticker's spread + 1 bp.

  python scripts/small_target_test.py [--report]   -> results/small_target/<SYM>.pkl, reports/small_target.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading.alpaca import load_bars_file  # noqa: E402
from midcap_test import MAG, MID, cost_bps  # noqa: E402

OUT = Path("results/small_target")
SPLIT = pd.Timestamp("2024-11-01")
TARGET = 0.003
STOPS = {"0.2%": 0.002, "0.3%": 0.003, "0.5%": 0.005, "1.0%": 0.010, "structure": None}
HORIZON = 120


def race(H, L, C, last, i, d, e, stop_px, tgt_px):
    n = len(i)
    J = i[:, None] + np.arange(1, HORIZON + 1)
    valid = J <= last[:, None]
    Jc = np.minimum(J, last[:, None])
    hs = np.where(d[:, None] > 0, L[Jc] <= stop_px[:, None], H[Jc] >= stop_px[:, None]) & valid
    ht = np.where(d[:, None] > 0, H[Jc] >= tgt_px[:, None], L[Jc] <= tgt_px[:, None]) & valid
    fs = np.where(hs.any(1), hs.argmax(1), 10**6)
    ft = np.where(ht.any(1), ht.argmax(1), 10**6)
    endpx = C[np.minimum(i + HORIZON, last)]
    px = np.where((fs <= ft) & (fs < 10**6), stop_px, np.where(ft < fs, tgt_px, endpx))
    return np.where((fs <= ft) & (fs < 10**6), 0, np.where(ft < fs, 1, 2)), (px - e) * d / e * 100


def run_symbol(sym: str) -> str:
    m1 = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz")
    H, L, C = (m1[k].to_numpy() for k in ("high", "low", "close"))
    day = m1.index.normalize()
    last = pd.Series(np.arange(len(m1)), index=m1.index).groupby(day).transform("max").to_numpy()
    minute = ((m1.index - day) / pd.Timedelta(minutes=1)).to_numpy().astype(int) - 570 + 1
    parts = []
    p = pd.read_pickle(Path("results/pivots") / f"{sym}.pkl")
    p = p[p.event.isin(["star_break", "star_pivot1"]) & (p["mode"] == "with")]
    parts.append(pd.DataFrame({"signal": p.event, "tf": p.tf, "i": p.i, "bias": p.bias, "ext": p.ext,
                               "entry": p.entry, "time": p.time}))
    v = pd.read_pickle(Path("results/vpa_fib") / f"{sym}.pkl")
    v = v[v["mode"] == "with"]
    vh = m1.high.to_numpy()
    parts.append(pd.DataFrame({"signal": "strict_premier", "tf": v.tf, "i": v.i, "bias": v.bias, "ext": np.nan,
                               "entry": C[v.i.to_numpy()], "time": v.time}))
    ev = pd.concat(parts, ignore_index=True)
    rows = []
    for side in ("with", "opposite"):
        e = ev.copy()
        e["side"] = side
        e["dir"] = e.bias if side == "with" else -e.bias
        rows.append(e)
    rng = np.random.default_rng(11)
    ok = np.flatnonzero((minute >= 30) & (minute <= 360))
    pick = rng.choice(ok, size=min(20000, len(ok)), replace=False)
    rows.append(pd.DataFrame({"signal": "random", "tf": "-", "i": pick, "bias": 0, "ext": np.nan, "entry": C[pick],
                              "time": m1.index[pick] + pd.Timedelta(minutes=1), "side": "random",
                              "dir": rng.choice([-1, 1], size=len(pick))}))
    ev = pd.concat(rows, ignore_index=True)
    ev = ev[(minute[ev.i.to_numpy()] >= 30) & (minute[ev.i.to_numpy()] <= 360)].reset_index(drop=True)
    i, d, e = ev.i.to_numpy(), ev.dir.to_numpy().astype(float), ev.entry.to_numpy()
    tgt = e * (1 + d * TARGET)
    for name, sp in STOPS.items():
        if sp is None:
            ext = ev.ext.to_numpy()
            ok_ = ~np.isnan(ext) & (ev.side.to_numpy() == "with") & ((e - ext) * d > 0)
            stop_px = np.where(ok_, ext * (1 - 0.0002 * d), np.nan)
        else:
            stop_px = e * (1 - d * sp)
        o = np.full(len(ev), -1)
        pct = np.full(len(ev), np.nan)
        m = ~np.isnan(stop_px)
        for a in range(0, m.sum(), 50000):
            idx = np.flatnonzero(m)[a:a + 50000]
            oo, pp = race(H, L, C, last[i[idx]], i[idx], d[idx], e[idx], stop_px[idx], tgt[idx])
            o[idx], pct[idx] = oo, pp
        ev[f"out_{name}"], ev[f"pct_{name}"] = o, pct
        ev[f"stop%_{name}"] = np.abs(stop_px - e) / e * 100
    ev["sym"] = sym
    OUT.mkdir(parents=True, exist_ok=True)
    ev.to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev)} entries"


def report() -> None:
    ev = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    ev["universe"] = np.where(ev.sym.isin(MID), "mid-cap", "Mag7+")
    ev["period"] = np.where(ev.time < SPLIT, "2021-24", "2024-26")
    ev["cost%"] = ev.sym.map(cost_bps) / 100
    rows = []
    for (u, sig, side, per), g in ev.groupby(["universe", "signal", "side", "period"]):
        r = {"universe": u, "signal": sig, "side": side, "period": per}
        for name in STOPS:
            gg = g[g[f"out_{name}"] >= 0]
            if not len(gg):
                continue
            net = gg[f"pct_{name}"] - gg["cost%"]
            r[f"{name} n"] = len(gg)
            r[f"{name} hit 0.3%"] = round((gg[f"out_{name}"] == 1).mean() * 100, 1)
            r[f"{name} avg %"] = round(net.mean(), 3)
            if name == "structure":
                r["structure stop %"] = round(gg["stop%_structure"].median(), 2)
        rows.append(r)
    t = pd.DataFrame(rows)
    L = ["# A 0.3% profit target on premier-candle signals\n",
         "Race to +0.3% vs the stop on 1m bars, up to 120 min (then exit at market), same bar = stop. Entries 10:00-15:30 ET. "
         "`hit 0.3%` = % of trades that reach +0.3% before the stop; `avg %` = average result per trade after each ticker's "
         "cost (stock % move, not option P&L). Breakeven hit rate before costs = stop / (stop + 0.3%): 40% for a 0.2% stop, "
         "50% for 0.3%, 62.5% for 0.5%, 77% for 1.0%.\n", t.to_markdown(index=False)]
    Path("reports/small_target.md").write_text("\n".join(L) + "\n")
    print("wrote reports/small_target.md")


if __name__ == "__main__":
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, MAG + MID):
                print(msg, flush=True)
    report()
