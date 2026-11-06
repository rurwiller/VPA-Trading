"""Mid-cap universe: the Willard indicator (5-minute chart, all exit settings) and the premier VPA
candle test, scored with each ticker's real cost (measured median bid-ask spread + 1 bp slippage).

  python scripts/midcap_test.py [--report]   -> reports/midcaps.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vpa_fib_fvg as V  # noqa: E402
import willard_exit_test as X  # noqa: E402

MID = ["SOFI", "HOOD", "RIVN", "AFRM", "MARA", "RIOT", "SMCI", "DKNG", "ROKU", "CVNA"]
MAG = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "SPY", "QQQ", "AMD"]
# median quoted spread (bps), sampled from Alpaca SIP quotes on 2026-10-28 and 2026-11-03 at 10:00/13:00/15:30 ET
SPREAD_BPS = {"SOFI": 5.9, "HOOD": 3.3, "RIVN": 8.6, "AFRM": 13.8, "MARA": 14.2, "RIOT": 7.3, "SMCI": 3.2,
              "DKNG": 5.0, "ROKU": 1.9, "CVNA": 5.1, "TSLA": 1.5, "NVDA": 0.9, "AAPL": 0.9, "SPY": 0.4,
              "GLD": 0.6, "SLV": 2.1}
SPLIT = pd.Timestamp("2024-11-01")


def cost_bps(sym: str) -> float:
    return max(2.0, SPREAD_BPS.get(sym, 1.0) + 1.0)   # cross the spread once per round trip + 1 bp


def both(sym: str) -> str:
    return X.run_symbol(sym) + " | " + V.run_symbol(sym)


def per(g: pd.DataFrame, col: str, scale: float) -> dict:
    """col = gross return per trade in % (scale 1) or bps (scale 100); net uses each ticker's own cost."""
    if not len(g):
        return {"n": 0}
    gross = g[col]
    net = gross - g.sym.map(cost_bps) / 100 * scale
    se = 2 * net.std() / np.sqrt(len(g))
    return {"n": len(g), "gross": round(gross.mean(), 4 if scale == 1 else 1), "net": round(net.mean(), 4 if scale == 1 else 1),
            "win% net": round((net > 0).mean() * 100, 1), "2se": round(se, 4 if scale == 1 else 1)}


def two(t: pd.DataFrame, by: list[str], col: str, scale: float) -> pd.DataFrame:
    rows = []
    for key, g in t.groupby(by, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(by, key))
        for p, gg in (("d", g[g.time < SPLIT]), ("h", g[g.time >= SPLIT])):
            r.update({f"{k}_{p}": v for k, v in per(gg, col, scale).items()})
        rows.append(r)
    return pd.DataFrame(rows)


def report() -> None:
    wt = pd.concat([pd.read_pickle(X.OUT / f"{s}.pkl") for s in MID + MAG if (X.OUT / f"{s}.pkl").exists()], ignore_index=True)
    wt["gross"] = wt.pnl + 0.02                                     # undo the replay's flat 0.02% cost
    wt["universe"] = np.where(wt.sym.isin(MID), "mid-cap", "Mag7+")
    ve = pd.concat([pd.read_pickle(V.OUT / f"{s}.pkl") for s in MID + MAG if (V.OUT / f"{s}.pkl").exists()], ignore_index=True)
    ve["universe"] = np.where(ve.sym.isin(MID), "mid-cap", "Mag7+")
    for h in ("r15", "r60"):
        ve[f"{h}_gross"] = ve[h] + 2.0                              # outcomes were net of 2 bps
    ve["fib"] = ve.fib1h_gp | ve.fib1h_retr | ve.fibD_gp | ve.fibD_retr
    ve["fvg"] = ve.fvg_1h | ve.fvg_4h | ve.fvg_D
    ve["n_factors"] = ve.fib.astype(int) + ve.fvg.astype(int) + ve.rsi_div.astype(int)
    d = wt[wt.cfg == "default"]
    L = ["# Mid-cap universe vs Mag 7+\n",
         f"Mid-caps: {', '.join(MID)}. Costs per ticker = measured median spread + 1 bp "
         f"({', '.join(f'{s} {cost_bps(s):.1f}' for s in MID)} bps; Mag 7+ ~2-2.5 bps). "
         f"`_d` = before {SPLIT:%Y-%m-%d}, `_h` = after. gross / net = average per trade before / after cost.\n",
         "## 1. Willard indicator, 5-minute chart, default exits (all 7 rules pooled), % per trade\n",
         two(d, ["universe"], "gross", 1).to_markdown(index=False),
         "\n**By ticker**\n", two(d, ["universe", "sym"], "gross", 1).to_markdown(index=False),
         "\n**By rule, mid-caps**\n", two(d[d.universe == "mid-cap"], ["rule"], "gross", 1).to_markdown(index=False),
         "\n## 2. Exit settings, mid-caps (all rules pooled), % per trade\n",
         two(wt[wt.universe == "mid-cap"], ["cfg"], "gross", 1).to_markdown(index=False),
         "\n## 3. Premier VPA candles (with Coulling's bias), bps after 15 and 60 min\n"]
    w = ve[ve["mode"] == "with"]
    for h in ("r15", "r60"):
        L.append(f"\n**{h}, by universe and timeframe**\n")
        L.append(two(w, ["universe", "tf"], f"{h}_gross", 100).to_markdown(index=False))
    L.append("\n**r60, mid-caps, by candle type**\n")
    L.append(two(w[w.universe == "mid-cap"], ["type"], "r60_gross", 100).to_markdown(index=False))
    L.append("\n**r60, mid-caps, by volume grade**\n")
    L.append(two(w[w.universe == "mid-cap"], ["vol_class"], "r60_gross", 100).to_markdown(index=False))
    for f in ["fib", "fvg", "rsi_div", "n_factors"]:
        L.append(f"\n**r60, mid-caps, by {f}**\n")
        L.append(two(w[w.universe == "mid-cap"], [f], "r60_gross", 100).to_markdown(index=False))
    Path("reports/midcaps.md").write_text("\n".join(L) + "\n")
    print("wrote reports/midcaps.md")


if __name__ == "__main__":
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(both, MID):
                print(msg, flush=True)
    report()
