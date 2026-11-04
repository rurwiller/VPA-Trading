"""Examples for the last week of data: live 1h/4h/D fair value gaps, 1h and daily fib levels, and every premier
candle (9/15/29/60m) with whether it touched a gap on its side.   python scripts/week_examples.py [SYM ...]"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import fib, indicators as ind, research as R  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402

FROM = pd.Timestamp("2026-10-26")
MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


def mst(t) -> str:
    return (pd.Timestamp(t) - pd.Timedelta(hours=2)).strftime("%a %b %d %H:%M")


def one(sym: str) -> list[str]:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False).loc["2025-06-01":]
    s = R.prepare(sym, m1x)
    last_i = len(s.m1) - 1
    px = float(s.m1.close.iat[-1])
    frames = {"1h": V.frame(s.m1, "60m"), "4h": V.frame(s.m1, "4h")}
    dd = fib.daily_bars(s.m1)
    dd["volume"] = s.m1.volume.groupby(s.m1.index.normalize()).sum()
    dd["atr"] = ind.atr(dd)
    frames["D"] = dd
    L = [f"\n## {sym} (last close {px:.2f})\n", "**Unfilled fair value gaps at the close (nearest first)**\n"]
    rows = []
    for tf, n in V.GAP_TFS.items():
        g = V.live_gaps(s, frames[tf], n)
        live = g[(g.start <= last_i) & ((g.fill < 0) | (g.fill > last_i)) & (g.expire > last_i)]
        for _, r in live.iterrows():
            rows.append(dict(tf=tf, kind="bull (support)" if r.dir > 0 else "bear (resistance)",
                             zone=f"{r.bottom:.2f} - {r.top:.2f}", formed=mst(r.formed_at),
                             dist=round(((r.top if r.dir > 0 else r.bottom) - px) / px * 100, 2)))
    gt = pd.DataFrame(rows)
    L.append(gt.reindex(gt.dist.abs().sort_values().index).head(8).rename(columns={"dist": "distance %"}).to_markdown(index=False)
             if len(gt) else "(none)")
    L.append("\n**Fibonacci levels (last confirmed swing)**\n")
    frows = []
    for tag, b, k in (("1h", frames["1h"], 3), ("D", frames["D"], 2)):
        st = fib.state(fib.legs(b, k), s.clock[-1:]).iloc[0]
        lv = fib.levels(pd.DataFrame([st]))
        leg = "up leg (retracements = support)" if st.up else "down leg (retracements = resistance)"
        frows.append(dict(swing=tag, leg=leg, high=round(st.H, 2), low=round(st.L, 2),
                          **{k_: round(float(v[0]), 2) for k_, v in lv.items() if k_ in ("r0.382", "r0.5", "r0.618", "r0.65", "r0.786")}))
    L.append(pd.DataFrame(frows).rename(columns={"r0.618": "GP 0.618", "r0.65": "GP 0.65"}).to_markdown(index=False))
    e = pd.read_pickle(Path("results/fvg_candles") / f"{sym}.pkl")
    e = e[(e.family == "premier") & (e.side == "with") & (e.time >= FROM)].sort_values("time")
    L.append("\n**Premier candles (signal known at the candle close; MST)**\n")
    if len(e):
        t = pd.DataFrame({"close (MST)": e.time.map(mst), "tf": e.tf, "type": e.type,
                          "bias": np.where(e.bias > 0, "bullish", "bearish"), "entry": e.entry.round(2),
                          "at gap": np.where(e.at_gap, e.gap_tf, "-"),
                          "+0.3% before -0.5%?": np.where(e["out_T0.3_S0.5"] == 1, "yes", np.where(e["out_T0.3_S0.5"] == 0, "stopped", "neither")),
                          "result %": e["pct_T0.3_S0.5"].round(2)})
        L.append(t.to_markdown(index=False))
    else:
        L.append("(none in 10:00-15:30 ET)")
    return L


if __name__ == "__main__":
    out = ["# Last week's examples: gaps, fibs and premier candles\n",
           f"Data through {pd.Timestamp('2026-11-03'):%a %b %d, %Y} close. Gaps: 1h / 4h / daily, unfilled. Fib swings: "
           "1h (3-candle pivots) and daily (2-day pivots). Premier candles: spec shapes on 9/15/29/60m, entries 10:00-15:30 ET "
           "(8:00-13:30 MST), result = +0.3% target / 0.5% stop race before costs."]
    for sym in (sys.argv[1:] or MAG7):
        out += one(sym)
    Path("reports/last_week_examples.md").write_text("\n".join(out) + "\n")
    print("wrote reports/last_week_examples.md")
