"""Summarise results/events/*.pkl into reports/research.md.

Discovery = before --split (default 2024-11-01); holdout = after. Everything is ranked on
discovery only; a shortlist chosen there is then shown on the holdout exactly once.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPS = {  # one representative variant per family for the condition tables
    "stack": ["1h+15m+5m L20", "1h+30m+15m+5m L25", "15m+9m+5m L20", "1h+15m+9m+5m L20 trig3m"],
    "candle": ["5m L20", "15m L20"],
    "climax": ["5m rvol2 wick0.4", "15m rvol2 wick0.4"],
    "fvg": ["5m", "15m", "1h"],
}


def load(d: str) -> pd.DataFrame:
    ev = pd.concat([pd.read_pickle(p) for p in sorted(Path(d).glob("*.pkl"))], ignore_index=True)
    st = ev.stretch
    ev["adx15_band"] = pd.cut(ev.adx_15m, [0, 15, 20, 25, 30, 40, 100], right=False).astype(str)
    ev["adx5_band"] = pd.cut(ev.adx_5m, [0, 15, 20, 25, 30, 40, 100], right=False).astype(str)
    ev["adx15_rising"] = np.where(ev.adx_slope_15m > 0, "rising", "falling")
    ev["di15_with_stretch"] = np.where((ev.pdi_15m > ev.mdi_15m) == (st > 0), "yes", "no")
    ev["tod_band"] = pd.cut(ev.tod, [0, 60, 150, 270, 400], labels=["09:30-10:30", "10:30-12:00",
                                                                     "12:00-14:00", "14:00-15:00"]).astype(str)
    ev["vwap_stretch_atr"] = pd.cut(ev.vwap_dist_atr * st, [-np.inf, 0, 1, 2, 4, np.inf]).astype(str)
    ev["ema15_with_stretch"] = np.where((ev.ema9_15m > ev.ema21_15m) == (st > 0), "yes", "no")
    ev["ema5_with_stretch"] = np.where((ev.ema9_5m > ev.ema21_5m) == (st > 0), "yes", "no")
    ev["rejection_5m"] = np.where(((st > 0) & (ev.inv_hammer_5m == 1)) | ((st < 0) & (ev.hammer_5m == 1)), "yes", "no")
    ev["rejection_15m"] = np.where(((st > 0) & (ev.inv_hammer_15m == 1)) | ((st < 0) & (ev.hammer_15m == 1)), "yes", "no")
    ev["rvol5_band"] = pd.cut(ev.rvol_5m, [0, 1, 2, 3, np.inf]).astype(str)
    opp = lambda tf: ((st > 0) & (ev[f"near_bear_fvg_{tf}"] == 1)) | ((st < 0) & (ev[f"near_bull_fvg_{tf}"] == 1))  # noqa: E731
    ev["fvg_against_stretch"] = np.where(opp("5m") | opp("15m") | opp("1h"), "yes", "no")
    if "gap_disp_rvol" in ev:
        ev["gap_disp_rvol_band"] = pd.cut(ev.gap_disp_rvol, [0, 1, 2, 3, np.inf]).astype(str)
        ev["gap_size_band"] = pd.cut(ev.gap_size_atr, [0, 0.25, 0.5, 1, np.inf]).astype(str)
        ev["gap_same_day"] = np.where(ev.gap_same_day == 1, "same day", "older")
    return ev


SPLITS = ["adx15_band", "adx5_band", "adx15_rising", "di15_with_stretch", "tod_band", "vwap_stretch_atr",
          "ema15_with_stretch", "ema5_with_stretch", "rejection_5m", "rejection_15m", "rvol5_band",
          "fvg_against_stretch", "sym"]
FVG_SPLITS = ["gap_disp_rvol_band", "gap_size_band", "gap_same_day"]


def metrics(g: pd.DataFrame) -> pd.Series:
    n = len(g)
    se = g.atr_r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    return pd.Series({
        "n": n,
        "win15": (g.r15 > 0).mean(), "r15_bps": g.r15.mean(), "r60_bps": g.r60.mean(),
        "pct_win": (g.pct_out == 1).mean(), "pct_ret": g.pct_ret.mean(),
        "atr_win": (g.atr_out == 1).mean(), "atr_R": g.atr_r.mean(), "atr_R_2se": 2 * se,
    })


def table(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    return df.groupby(by, observed=True).apply(metrics, include_groups=False)


def fmt(t: pd.DataFrame) -> str:
    t = t.copy()
    for c in ("win15", "pct_win", "atr_win"):
        if c in t:
            t[c] = (t[c] * 100).round(1)
    for c in ("r15_bps", "r60_bps"):
        if c in t:
            t[c] = t[c].round(1)
    for c in ("pct_ret", "atr_R", "atr_R_2se"):
        if c in t:
            t[c] = t[c].round(3)
    if "n" in t:
        t["n"] = t["n"].astype(int)
    return t.to_markdown()


def adx_decides(df: pd.DataFrame) -> pd.DataFrame:
    """Fade when ADX(15m) < X, ride (cont) when ADX >= X and +DI/-DI agree with the stretch."""
    rows = []
    for x in (15, 20, 25, 30, 35, 40):
        f = df[(df["mode"] == "fade") & (df.adx_15m < x)]
        c = df[(df["mode"] == "cont") & (df.adx_15m >= x) & (df.di15_with_stretch == "yes")]
        m = metrics(pd.concat([f, c]))
        m["adx_x"], m["n_fade"], m["n_cont"] = x, len(f), len(c)
        rows.append(m)
    return pd.DataFrame(rows).set_index("adx_x")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="results/events")
    ap.add_argument("--split", default="2024-11-01")
    ap.add_argument("--out", default="reports/research.md")
    ap.add_argument("--min-n", type=int, default=300)
    a = ap.parse_args()

    ev = load(a.events)
    cut = pd.Timestamp(a.split)
    disc, hold = ev[ev.time < cut], ev[ev.time >= cut]
    L = [f"# Research report\n",
         f"Events from {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}, tickers: {', '.join(sorted(ev.sym.unique()))}.",
         f"**Discovery** = before {a.split}; **holdout** = after (kept aside, see the last section).",
         "Costs: 2 bps round trip. win15 = share of trades up after 15 min; r15/r60 = average return in bps;",
         "pct = race to +0.5% / -0.3% within 60 min, else exit at 60 min (pct_win = target hit first, pct_ret = avg % per trade);",
         "atr = race to 2R target / 1.5 x ATR(5m) stop within 60 min, else exit at 60 min (atr_win = target hit first;",
         "most trades end at the 60-minute exit), atr_R = average R per trade, atr_R_2se = ~95% noise band.\n",
         "## 1. Baselines (discovery)\n"]
    base = table(disc, ["family", "variant", "mode"])
    L.append(fmt(base))

    L.append("\n## 2. Conditions (discovery), representative variants\n")
    for fam, vs in REPS.items():
        for v in vs:
            sub = disc[(disc.family == fam) & (disc.variant == v)]
            if not len(sub):
                continue
            L.append(f"\n### {fam} {v}\n")
            for sp in SPLITS + (FVG_SPLITS if fam == "fvg" else []):
                L.append(f"\n**{sp}**\n")
                L.append(fmt(table(sub, [sp, "mode"])))
            L.append("\n**ADX decides** (fade below X, continuation at/above X when DI agrees)\n")
            L.append(fmt(adx_decides(sub)))

    L.append("\n## 3. Stop research (discovery): how far do *winners* go against you first?\n")
    L.append("Winners = up after 60 min. mae_atr = worst move against the trade in ATR(5m) units.\n")
    w = disc[disc.r60 > 0]
    st = w.groupby(["family", "mode"]).mae_atr.describe(percentiles=[.5, .75, .8, .9])[["count", "50%", "75%", "80%", "90%"]]
    L.append(st.round(2).to_markdown())
    lw = disc[disc.r60 <= 0].groupby(["family", "mode"]).mae_atr.describe(percentiles=[.5, .8])[["count", "50%", "80%"]]
    L.append("\nLosers for comparison:\n")
    L.append(lw.round(2).to_markdown())

    # Shortlist: every (variant x condition) cell with enough discovery trades, ranked by atr_R.
    cells = []
    for sp in [None] + SPLITS + FVG_SPLITS:
        if sp and sp not in disc:
            continue
        by = ["family", "variant", "mode"] + ([sp] if sp else [])
        t = disc.groupby(by, observed=True).agg(n=("atr_r", "size"), atr_R=("atr_r", "mean"),
                                                 sd=("atr_r", "std"), pct_ret=("pct_ret", "mean"))
        t = t[t.n >= a.min_n].reset_index()
        t["condition"] = (sp + "=" + t[sp].astype(str)) if sp else "all"
        cells.append(t.drop(columns=[sp] if sp else []))
    cells = pd.concat(cells, ignore_index=True)
    cells["t"] = cells.atr_R / (cells.sd / np.sqrt(cells.n))
    n_cells = len(cells)
    top = cells.sort_values("t", ascending=False).head(25)
    L.append(f"\n## 4. Shortlist: best of {n_cells} discovery cells (n >= {a.min_n}) by t-stat of atr_R, "
             f"and the same cells on the holdout\n")
    L.append("With this many cells, several will look good by luck alone; the holdout column is the real test.\n")
    rows = []
    for _, r in top.iterrows():
        h = hold[(hold.family == r.family) & (hold.variant == r.variant) & (hold["mode"] == r["mode"])]
        if r.condition != "all":
            sp, val = r.condition.split("=", 1)
            h = h[h[sp].astype(str) == val]
        rows.append(dict(family=r.family, variant=r.variant, mode=r["mode"], condition=r.condition,
                         disc_n=int(r.n), disc_atr_R=round(r.atr_R, 3), disc_t=round(r.t, 1),
                         disc_pct_ret=round(r.pct_ret, 3), hold_n=len(h),
                         hold_atr_R=round(h.atr_r.mean(), 3) if len(h) else np.nan,
                         hold_2se=round(2 * h.atr_r.std() / np.sqrt(len(h)), 3) if len(h) > 1 else np.nan,
                         hold_pct_ret=round(h.pct_ret.mean(), 3) if len(h) else np.nan,
                         hold_atr_win=round((h.atr_out == 1).mean() * 100, 1) if len(h) else np.nan))
    L.append(pd.DataFrame(rows).to_markdown(index=False))
    Path(a.out).parent.mkdir(exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n")
    print(f"wrote {a.out}: {len(ev)} trades, {n_cells} shortlist cells")


if __name__ == "__main__":
    main()
