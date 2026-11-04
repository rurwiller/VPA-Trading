"""Last 52 weeks of premier candles on the Mag 7: counts, at-gap counts, +0.3% / -0.5% outcomes, by stock / month / type.
Writes reports/last_52_weeks.md and results/last_52_weeks_premier.csv (every candle)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from midcap_test import cost_bps  # noqa: E402

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
FROM, TO = pd.Timestamp("2025-11-03"), pd.Timestamp("2026-11-04")


def summ(g: pd.DataFrame) -> pd.Series:
    o = g["out_T0.3_S0.5"]
    net = g["pct_T0.3_S0.5"] - g["cost_pct"]
    return pd.Series({"candles": len(g), "at a gap": int(g.at_gap.sum()), "hit +0.3%": int((o == 1).sum()),
                      "stopped -0.5%": int((o == 0).sum()), "neither (2h)": int((o == 2).sum()),
                      "hit rate %": round((o == 1).mean() * 100, 1), "sum before costs %": round(g["pct_T0.3_S0.5"].sum(), 1),
                      "avg per trade after costs %": round(net.mean(), 3),
                      "at-gap hit rate %": round((o[g.at_gap] == 1).mean() * 100, 1) if g.at_gap.any() else np.nan})


def main() -> None:
    e = pd.concat([pd.read_pickle(Path("results/fvg_candles") / f"{s}.pkl") for s in MAG7], ignore_index=True)
    e = e[(e.family == "premier") & (e.side == "with") & (e.time >= FROM) & (e.time < TO)].sort_values(["sym", "time"])
    e["month"] = e.time.dt.to_period("M").astype(str)
    e["cost_pct"] = e.sym.map(cost_bps) / 100
    out = e[["sym", "time", "tf", "type", "bias", "entry", "at_gap", "gap_tf", "out_T0.3_S0.5", "pct_T0.3_S0.5"]].copy()
    out["time_MST"] = (out.time - pd.Timedelta(hours=2)).dt.strftime("%Y-%m-%d %H:%M")
    out.to_csv("results/last_52_weeks_premier.csv", index=False)
    L = ["# Last 52 weeks: premier candles on the Mag 7\n",
         f"{FROM:%b %d %Y} to {TO - pd.Timedelta(days=1):%b %d %Y}. Spec premier candles on 9/15/29/60m, entries 10:00-15:30 ET, "
         "traded with Coulling's bias; +0.3% target vs 0.5% stop within 2 hours (else exit at market). Breakeven hit rate "
         "before costs is 62.5%; costs ~2 bps per trade. 'At a gap' = wick at an unfilled 1h/4h/daily fair value gap.\n",
         "## By stock\n", e.groupby("sym").apply(summ, include_groups=False).to_markdown(),
         "\n## All seven, by month\n", e.groupby("month").apply(summ, include_groups=False).to_markdown(),
         "\n## By candle type\n", e.groupby("type").apply(summ, include_groups=False).to_markdown(),
         "\n## By timeframe\n", e.groupby("tf").apply(summ, include_groups=False).to_markdown(),
         "\n## At a gap vs not, by gap timeframe\n", e.groupby("gap_tf").apply(summ, include_groups=False).to_markdown(),
         "\n## Total\n", summ(e).to_frame("all").T.to_markdown()]
    Path("reports/last_52_weeks.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
