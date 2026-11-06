"""Run the standing tests on gold (GLD) and silver (SLV) and set them beside the Mag 7 group (AAPL MSFT GOOGL AMZN NVDA META TSLA + SPY QQQ AMD).

  python scripts/commodity_compare.py [--run]   --run first runs the four test scripts on GLD and SLV (a few minutes)
Reads results/pivot_relax, results/ema_gap, results/osc_pivot, results/intraday_mom -> reports/commodities.md
Each cell: average net result (avg R per trade, or bps per ticker-day) and the number of trades / days in brackets.
Before = before 2024-11-01, After = from 2024-11-01. Costs: ticker spread + 1 bp per round trip (GLD 2.0 bps, SLV 3.1, Mag7 2-3).
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from midcap_test import MAG, cost_bps  # noqa: E402

NEW = ["GLD", "SLV"]
SPLIT = pd.Timestamp("2024-11-01")
GROUPS = {"GLD": ["GLD"], "SLV": ["SLV"], "Mag7+": MAG}


def job(args):
    name, sym = args
    import pivot_relax_test, ema_gap_test, osc_pivot_test, intraday_momentum_test
    mod = {"pivot": pivot_relax_test, "ema": ema_gap_test, "osc": osc_pivot_test, "mom": intraday_momentum_test}[name]
    return f"{name} {mod.run_symbol(sym)}"


def load(dirname: str, pattern: str) -> pd.DataFrame:
    return pd.concat([pd.read_pickle(p) for p in sorted(Path(dirname).glob(pattern))
                      if p.name.split("_")[0].split(".")[0] in sum(GROUPS.values(), [])], ignore_index=True)


def cell(df: pd.DataFrame, mask: pd.Series, col: str = "r_net", filled: bool = True) -> str:
    g = df[mask]
    if filled and "status" in g:
        g = g[g.status > 0]
    if len(g) < 5:
        return f"- ({len(g)})"
    return f"{g[col].mean():+.3f} ({len(g):,})"


def table(df: pd.DataFrame, rows: list[tuple[str, pd.Series]], col: str = "r_net", filled: bool = True) -> pd.DataFrame:
    out = []
    for name, m in rows:
        r = {"set": name}
        for gname, syms in GROUPS.items():
            for per, pm in (("before", df.time < SPLIT), ("after", df.time >= SPLIT)):
                r[f"{gname} {per}"] = cell(df, m & df.sym.isin(syms) & pm, col, filled)
        out.append(r)
    return pd.DataFrame(out)


def main() -> None:
    if "--run" in sys.argv:
        jobs = [(n, s) for s in NEW for n in ("pivot", "ema", "osc", "mom")]
        with ProcessPoolExecutor(max_workers=4) as ex:
            for msg in ex.map(job, jobs):
                print(msg, flush=True)
    L = ["# Gold (GLD) and silver (SLV) against the Mag 7 group\n",
         "Same tests as the other reports, same order mechanics (stop-entry through the candle, stop beyond the wick, 1R target). "
         "Cells are average net result and (count). Mag7+ = AAPL MSFT GOOGL AMZN NVDA META TSLA SPY QQQ AMD.\n"]
    # ---- candle rules
    pv = load("results/pivot_relax", "*.pkl")
    pv = pv[pv.tf.isin(["9m", "15m"])]
    rows = [("pivot-wick shorts at a 1h/4h/D gap (the scanner's rule)", pv.U & (pv.dir < 0) & pv.at_gap),
            ("pivot-wick shorts, no gap needed", pv.U & (pv.dir < 0)),
            ("pivot-wick longs at a gap (volume >= 3x)", pv.U & (pv.dir > 0) & pv.at_gap),
            ("old live rules, both sides, at a gap", pv.A & pv.at_gap),
            ("relaxed shape + pivot, shorts at a gap", pv.C & (pv.dir < 0) & pv.at_gap),
            ("relaxed shape + pivot, longs at a gap", pv.C & (pv.dir > 0) & pv.at_gap)]
    L += ["\n## Candle rules (9m + 15m), avg R per trade\n", table(pv, rows).to_markdown(index=False)]
    cost = pv[pv.status > 0].groupby("sym").cost_r.mean().round(3)
    L.append("\nAverage cost per trade in R (higher = costs eat more of each trade): " +
             ", ".join(f"{k} {cost.get(k, float('nan')):.3f}" for k in NEW) + f", Mag7+ {cost[cost.index.isin(MAG)].mean():.3f}")
    # ---- EMA + gap
    cs = load("results/ema_gap", "*_candle.pkl")
    cs = cs[cs.tf.isin(["9m", "15m"])]
    cs["any_gap"] = cs[["gap_15m", "gap_1h", "gap_4h", "gap_D"]].any(axis=1)
    cs["any_ema"] = cs.near_dEMA9 | cs.near_dEMA21 | cs.near_hEMA9 | cs.near_hEMA21
    rows = [("pivot-wick candle at an EMA inside a gap, long", (cs.dir > 0) & cs.any_gap & cs.any_ema),
            ("pivot-wick candle at an EMA inside a gap, short", (cs.dir < 0) & cs.any_gap & cs.any_ema),
            ("every pivot-wick candle, long", cs.dir > 0), ("every pivot-wick candle, short", cs.dir < 0)]
    L += ["\n## EMA + gap bounce (9m + 15m candles), avg R per trade\n", table(cs, rows).to_markdown(index=False)]
    ts = load("results/ema_gap", "*_touch.pkl")
    rows = [(f"touch {lv} + gap, {sd}", (ts.level == lv) & (ts.dir == dv) & ts.at_gap)
            for lv in ("dEMA9", "dEMA21") for sd, dv in (("long", 1), ("short", -1))]
    L += ["\n## Limit order at the daily EMA (stop and target 1 ATR), avg R\n", table(ts, rows).to_markdown(index=False)]
    # ---- oscillator
    os_ = load("results/osc_pivot", "*.pkl")
    a = os_[["osc_5m", "osc_9m", "osc_15m"]]
    hi80 = np.where(os_.dir < 0, a.min(axis=1) >= 80, a.max(axis=1) <= 20)
    rows = [("every pivot-wick candle (5m/9m/15m), short", os_.dir < 0), ("oscillators 15/9/5 all >= 80, short", (os_.dir < 0) & hi80),
            ("oscillators all <= 20, long", (os_.dir > 0) & hi80),
            ("oscillators >= 80 + volume >= 2x, short", (os_.dir < 0) & hi80 & (os_.rvol >= 2)),
            ("oscillators <= 20 + volume >= 2x, long", (os_.dir > 0) & hi80 & (os_.rvol >= 2))]
    L += ["\n## Pivot wick + 15/9/5 oscillators elevated, avg R per trade\n", table(os_, rows).to_markdown(index=False)]
    # ---- day-level strategies
    dm = load("results/intraday_mom", "*.pkl")
    dm["time"] = dm.day
    dm["mom"] = np.sign(dm.sig_full) * dm.last30 - dm.cost
    dm["nb_gross"] = dm.nb_ret + dm.nb_trades * dm.cost
    for c in ("mom", "nb_ret", "nb_gross"):
        dm[c + "_bps"] = dm[c] * 1e4
    rows = [("momentum into the close (day so far -> last 30 min), net bps/day", dm.nb_ret.notna())]
    t1 = table(dm, [("momentum into the close (day so far -> last 30 min)", dm.nb_ret.notna())], "mom_bps", False)
    t2 = table(dm, [("trend-day breakout (noise band), net", dm.nb_ret.notna())], "nb_ret_bps", False)
    t3 = table(dm, [("trend-day breakout, before costs", dm.nb_ret.notna())], "nb_gross_bps", False)
    L += ["\n## Day-level strategies, average bps per ticker-day (net of costs unless marked)\n", pd.concat([t1, t2, t3]).to_markdown(index=False)]
    sh = []
    for gname, syms in GROUPS.items():
        r = {"group": gname}
        for per, pm in (("before", dm.day < SPLIT), ("after", dm.day >= SPLIT)):
            x = dm[dm.sym.isin(syms) & pm].nb_ret.dropna()
            r[f"breakout Sharpe {per}"] = round(float(x.mean() / x.std() * np.sqrt(252)), 2) if len(x) > 2 else np.nan
            r[f"share of days with a trade {per}"] = f"{(dm[dm.sym.isin(syms) & pm].nb_trades > 0).mean():.0%}"
        sh.append(r)
    L += ["\nBreakout Sharpe ratio (per ticker, annualised) and how often it trades:\n", pd.DataFrame(sh).to_markdown(index=False)]
    # ---- character of the instruments
    ch = []
    for sym in NEW + ["TSLA", "SPY", "QQQ", "AAPL"]:
        d = dm[dm.sym == sym]
        ch.append({"ticker": sym, "avg |open->close| %": round(d.oc.abs().mean() * 100, 2), "cost bps": round(cost_bps(sym), 1)})
    L += ["\nHow big a typical day is (average absolute open-to-close move) and the round-trip cost used:\n", pd.DataFrame(ch).to_markdown(index=False)]
    Path("reports/commodities.md").write_text("\n".join(L) + "\n")
    print("wrote reports/commodities.md")


if __name__ == "__main__":
    main()
