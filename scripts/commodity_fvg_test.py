"""Two tests on 7 commodity ETFs (gold, silver, oil, natural gas, copper, platinum, agriculture), 5 years of 1m bars.

A. The fair-value-gap candle study (scripts/fvg_candle_test.py, run per fund into results/fvg_candles/): premier candles
   and climaxes, traded in their own direction (Coulling's bias), at an unfilled 1h / 4h / daily gap vs away from any gap.
   Exit as the live scanner does it: stop just beyond the candle's extreme (+0.02%), entry at the candle's close.
   The study's own exit is a 2R target or 120 minutes; results in R (multiples of the risk) after each fund's cost.
B. Combined with the opening-range breakdown (scripts/commodity_orb_test.py: gap-down day, short when a 30-minute block
   closes below the first 30 minutes' low):
   B1  breakdown trades split by whether a bearish premier / climax AT A GAP printed earlier that day (from 10:00 to entry)
   B2  bearish gap signals split by whether they came on a gap-down day after the opening range broke down
Before / after = before Nov 2024 / since. t = mean / standard error.

  python scripts/commodity_fvg_test.py   -> reports/commodity_fvg.md   (needs results/fvg_candles/<SYM>.pkl for each fund)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import commodity_orb_test as O  # noqa: E402

SPLIT = pd.Timestamp("2024-11-01")


def t_of(x) -> float:
    x = np.asarray(x, float)
    return x.mean() / (x.std() / np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else np.nan


def fmt(x, unit) -> str:
    x = pd.Series(x, dtype=float)
    return f"{len(x)} | {x.mean():+.{3 if unit == 'R' else 1}f} | {t_of(x):+.1f}" if len(x) else "- | - | -"


def load_ev(sym: str) -> pd.DataFrame:
    ev = pd.read_pickle(Path("results/fvg_candles") / f"{sym}.pkl")
    ev = ev[ev.side == "with"].copy()
    cost = O.FUNDS[sym][1] / 100                               # % of price
    ev["R"] = (ev.pct_struct - cost) / ev.risk_pct
    ev["day"] = ev.time.dt.normalize()
    return ev


def main() -> None:
    L = ["# Commodities: the fair-value-gap candles, and the gaps combined with the opening-range breakdown\n",
         __doc__.split("\n\n")[1], "", "Cells: trades | average after costs | t.\n"]
    # ---------- A
    L += ["\n## A. Gap candles (premier + climax, own direction), structure stop, 2R target, average R\n",
          "| Fund | Market | At a 1h/4h/D gap, all | before | since Nov 2024 | Away from gaps, all | 9m/15m at a gap (the live scanner's) |",
          "|---|---|---|---|---|---|---|"]
    evs = {}
    for sym, (name, _) in O.FUNDS.items():
        p = Path("results/fvg_candles") / f"{sym}.pkl"
        if not p.exists():
            L.append(f"| {sym} | {name} | not run | | | | |")
            continue
        ev = evs[sym] = load_ev(sym)
        g = ev[ev.at_gap]
        live = g[g.tf.isin(["9m", "15m"])]
        L.append(f"| {sym} | {name} | {fmt(g.R, 'R')} | {fmt(g[g.time < SPLIT].R, 'R')} | {fmt(g[g.time >= SPLIT].R, 'R')} | "
                 f"{fmt(ev[~ev.at_gap].R, 'R')} | {fmt(live.R, 'R')} |")
    if evs:
        allg = pd.concat([e[e.at_gap] for e in evs.values()])
        alln = pd.concat([e[~e.at_gap] for e in evs.values()])
        L.append(f"| **All 7** | | {fmt(allg.R, 'R')} | {fmt(allg[allg.time < SPLIT].R, 'R')} | {fmt(allg[allg.time >= SPLIT].R, 'R')} | "
                 f"{fmt(alln.R, 'R')} | {fmt(allg[allg.tf.isin(['9m', '15m'])].R, 'R')} |")
    # ---------- B1
    ks, kt = O.gold_multiples()
    L += ["\n## B1. Opening-range breakdown shorts, split by a gap signal earlier that day (bps per trade)\n",
          "| Fund | Market | All breakdown shorts | After a bearish gap signal | After a bullish gap signal | No gap signal |",
          "|---|---|---|---|---|---|"]
    pool = {"all": [], "bear": [], "bull": [], "none": []}
    orb_days = {}
    for sym, (name, cost) in O.FUNDS.items():
        t = O.run(sym, -1, "down", ks, kt, cost)
        orb_days[sym] = t
        if sym not in evs or not len(t):
            continue
        ev = evs[sym][evs[sym].at_gap]
        tag = []
        for r in t.itertuples():
            same = ev[(ev.day == r.day) & (ev.time <= r.time)]
            tag.append("bear" if (same.bias < 0).any() else ("bull" if (same.bias > 0).any() else "none"))
        t = t.assign(tag=tag)
        for k in pool:
            pool[k].append(t if k == "all" else t[t.tag == k])
        L.append(f"| {sym} | {name} | {fmt(t.bps, 'b')} | {fmt(t[t.tag == 'bear'].bps, 'b')} | {fmt(t[t.tag == 'bull'].bps, 'b')} | "
                 f"{fmt(t[t.tag == 'none'].bps, 'b')} |")
    if pool["all"]:
        P = {k: pd.concat(v) for k, v in pool.items()}
        L.append(f"| **All 7** | | {fmt(P['all'].bps, 'b')} | {fmt(P['bear'].bps, 'b')} | {fmt(P['bull'].bps, 'b')} | {fmt(P['none'].bps, 'b')} |")
    # ---------- B2
    L += ["\n## B2. Bearish gap signals (own direction = short), split by the day (average R)\n",
          "| Fund | Market | After an opening-range breakdown on a gap-down day | Any other time |", "|---|---|---|---|"]
    on_all, off_all = [], []
    for sym, (name, _) in O.FUNDS.items():
        if sym not in evs:
            continue
        ev = evs[sym]
        b = ev[ev.at_gap & (ev.bias < 0)]
        t = orb_days[sym]
        brk = dict(zip(t.day, t.time)) if len(t) else {}
        on = b.apply(lambda r: r.day in brk and r.time >= brk[r.day], axis=1) if len(b) else pd.Series(dtype=bool)
        on_all.append(b[on]); off_all.append(b[~on])
        L.append(f"| {sym} | {name} | {fmt(b[on].R, 'R')} | {fmt(b[~on].R, 'R')} |")
    if on_all:
        a, z = pd.concat(on_all), pd.concat(off_all)
        L.append(f"| **All 7** | | {fmt(a.R, 'R')} | {fmt(z.R, 'R')} |")
    Path("reports/commodity_fvg.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
