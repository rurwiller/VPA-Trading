"""Summarise results/events/*.pkl into reports/research.md.

Discovery = before --split (default 2024-11-01); holdout = after. Everything is chosen on
discovery only; the holdout columns sit next to it so nothing is picked by looking at them.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

NEAR = 0.25  # ATR(5m)


def load(d: str, syms: list[str] | None = None) -> pd.DataFrame:
    files = sorted(Path(d).glob("*.pkl"))
    ev = pd.concat([pd.read_pickle(p) for p in files if not syms or p.stem in syms], ignore_index=True)
    st = ev.stretch
    ev["adx15_band"] = pd.cut(ev.adx_15m, [0, 15, 20, 25, 30, 40, 100], right=False).astype(str)
    ev["adx15_rising"] = np.where(ev.adx_slope_15m > 0, "rising", "falling")
    ev["di15_with_stretch"] = np.where((ev.pdi_15m > ev.mdi_15m) == (st > 0), "yes", "no")
    ev["tod_band"] = pd.cut(ev.tod, [0, 60, 150, 270, 400], labels=["09:30-10:30", "10:30-12:00",
                                                                     "12:00-14:00", "14:00-15:00"]).astype(str)
    ev["vwap_stretch_atr"] = pd.cut(ev.vwap_dist_atr * st, [-np.inf, 0, 1, 2, 4, np.inf]).astype(str)
    ev["ema15_with_stretch"] = np.where((ev.ema9_15m > ev.ema21_15m) == (st > 0), "yes", "no")
    ev["rvol5_band"] = pd.cut(ev.rvol_5m, [0, 1, 2, 3, np.inf]).astype(str)
    ev["near_level"] = np.where(ev.level_dist_atr <= NEAR, "yes", "no")
    ev["near_ema"] = np.where(ev.ema_dist_atr <= NEAR, "yes", "no")
    ev["near_level_or_ema"] = np.where((ev.near_level == "yes") | (ev.near_ema == "yes"), "yes", "no")
    opp = lambda tf: ((st > 0) & (ev[f"near_bear_fvg_{tf}"] == 1)) | ((st < 0) & (ev[f"near_bull_fvg_{tf}"] == 1))  # noqa: E731
    ev["fvg_against_stretch"] = np.where(opp("5m") | opp("15m") | opp("1h"), "yes", "no")
    # VPA evidence for a reversal of the stretch (bearish detection after a push up, etc.)
    for tf in ("2m", "5m", "15m"):
        ev[f"vpa_reversal_{tf}"] = np.where(((st > 0) & (ev[f"vpa_bear_{tf}"] == 1)) |
                                            ((st < 0) & (ev[f"vpa_bull_{tf}"] == 1)), "yes", "no")
        ev[f"star_reversal_{tf}"] = np.where(((st > 0) & (ev[f"star_recent_{tf}"] == 1)) |
                                             ((st < 0) & (ev[f"hammer_recent_{tf}"] == 1)), "yes", "no")
    ev["dominant_1h"] = np.where(ev.trend_1h == 0, "range", np.where(np.sign(ev.trend_1h) == ev.dir, "with trade", "against trade"))
    # Oscillator agreeing with a VPA detection: bearish signal with 5m osc >= 80, bullish <= 20.
    bias = np.where(ev["mode"].isin(["with"]), ev.dir, -ev.dir)
    ev["osc5_agrees"] = np.where(((bias < 0) & (ev.osc_5m >= 80)) | ((bias > 0) & (ev.osc_5m <= 20)), "yes", "no")
    ev["osc15_agrees"] = np.where(((bias < 0) & (ev.osc_15m >= 80)) | ((bias > 0) & (ev.osc_15m <= 20)), "yes", "no")
    if "gap_disp_rvol" in ev:
        ev["gap_size_band"] = pd.cut(ev.gap_size_atr, [0, 0.25, 0.5, 1, np.inf]).astype(str)
        ev["gap_same_day"] = np.where(ev.gap_same_day == 1, "same day", np.where(ev.gap_same_day == 0, "older", "n/a"))
    ev["period"] = "disc"
    return ev


SPLITS = ["adx15_band", "adx15_rising", "di15_with_stretch", "tod_band", "vwap_stretch_atr", "ema15_with_stretch",
          "rvol5_band", "near_level", "near_ema", "near_level_or_ema", "fvg_against_stretch",
          "vpa_reversal_2m", "vpa_reversal_5m", "vpa_reversal_15m", "star_reversal_5m", "star_reversal_15m",
          "dominant_1h", "osc5_agrees", "osc15_agrees", "vol_class", "gap_size_band", "gap_same_day", "sym"]


def agg(g: pd.DataFrame) -> dict:
    n = len(g)
    return {"n": n, "win15": (g.r15 > 0).mean() * 100, "r15": g.r15.mean(), "r60": g.r60.mean(),
            "pct_win": (g.pct_out == 1).mean() * 100, "atr_R": g.atr_r.mean(),
            "2se": 2 * g.atr_r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan}


def two_period(df: pd.DataFrame, by: list[str], min_n: int = 1) -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(by, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(by, key))
        for per in ("disc", "hold"):
            a = agg(g[g.period == per]) if (g.period == per).any() else {"n": 0}
            r.update({f"{k}_{per[0]}": v for k, v in a.items()})
        if r.get("n_d", 0) >= min_n:
            rows.append(r)
    t = pd.DataFrame(rows)
    if not len(t):
        return t
    for c in t.columns:
        if c.startswith("n_"):
            t[c] = t[c].fillna(0).astype(int)
        elif t[c].dtype.kind == "f":
            t[c] = t[c].round(3 if c.startswith(("atr_R", "2se")) else 1)
    return t


def md(t: pd.DataFrame) -> str:
    return t.to_markdown(index=False) if len(t) else "(no rows)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="results/events")
    ap.add_argument("--split", default="2024-11-01")
    ap.add_argument("--out", default="reports/research.md")
    ap.add_argument("--min-n", type=int, default=300)
    ap.add_argument("--syms", nargs="*")
    a = ap.parse_args()

    ev = load(a.events, a.syms)
    ev.loc[ev.time >= pd.Timestamp(a.split), "period"] = "hold"
    disc = ev[ev.period == "disc"]
    L = ["# Research report\n",
         f"Events {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}; tickers: {', '.join(sorted(ev.sym.unique()))}.",
         f"Columns ending `_d` = discovery (before {a.split}), `_h` = holdout (after). Pick on `_d`, believe `_h`.",
         "Costs 2 bps round trip. win15 = % of trades up after 15 min; r15/r60 = avg return in bps;",
         "pct_win = % that hit +0.5% before -0.3% within 60 min; atr_R = avg R with a 1.5 x ATR(5m) stop and",
         "2R target, exit at 60 min if neither (2se = ~95% noise band on atr_R).",
         "Modes: fade = against the stretch, cont = with it; FVG/level: fade = bounce, cont = break;",
         "VPA: with = trade Coulling's bias, against = the opposite. `limit` = limit order at the zone/level.\n"]

    # A. The user's question: 15m + 9m + 5m elevated, near a level or EMA, with VPA confirmation.
    L.append("## A. 15m + 9m + 5m all at an extreme: near a level / EMA / with VPA confirmation\n")
    s = ev[(ev.family == "stack") & ev.variant.str.startswith("15m+9m+5m L") & ~ev.variant.str.contains("trig")]
    for cond in ["near_level", "near_ema", "near_level_or_ema", "vpa_reversal_5m", "vpa_reversal_2m",
                 "star_reversal_5m", "star_reversal_15m", "fvg_against_stretch", "tod_band", "adx15_band"]:
        L.append(f"\n**{cond}**\n")
        L.append(md(two_period(s, ["variant", "mode", cond])))
    combo = s[(s.near_level_or_ema == "yes") & ((s.vpa_reversal_5m == "yes") | (s.vpa_reversal_2m == "yes"))]
    L.append("\n**Near a level or EMA AND a 2m/5m VPA reversal signal**\n")
    L.append(md(two_period(combo, ["variant", "mode"])))

    # B. VPA detections.
    L.append("\n## B. Coulling VPA detections (docs/vpa-detection-spec.md)\n")
    v = ev[ev.family == "vpa"]
    L.append(md(two_period(v, ["variant", "mode"])))
    stars = v[v.variant.str.contains("SHOOTING_STAR$|HAMMER$|HANGING_MAN$", regex=True) & (v["mode"] == "with")]
    for cond in ["vol_class", "osc5_agrees", "osc15_agrees", "near_level_or_ema", "dominant_1h"]:
        L.append(f"\n**Shooting star / hammer / hanging man (with bias) by {cond}**\n")
        L.append(md(two_period(stars, ["variant", cond])))
    if "repeat" in stars:
        st2 = stars.assign(repeat_band=np.where(stars.repeat >= 2, "2+", "1"))
        L.append("\n**...by repeat count in the same price area (spec 4)**\n")
        L.append(md(two_period(st2, ["variant", "repeat_band"])))
    cl = v[v.variant.str.contains("CLIMAX|STOPPING|TOPPING|TEST_OF")]
    L.append("\n**Climax / stopping / topping-out / tests by 1h dominant trend**\n")
    L.append(md(two_period(cl, ["variant", "mode", "dominant_1h"], min_n=20)))
    old = ev[ev.family == "climax"]
    L.append("\n**Single-bar climax candidates (fresh 20-bar extreme + high relative volume + wick)**\n")
    L.append("Here fade = Coulling's reading (high-volume top -> short), cont = enter in the bar's direction.\n")
    L.append(md(two_period(old, ["variant", "mode"])))

    # C. Levels and FVGs.
    L.append("\n## C. Key levels and fair value gaps (first touch)\n")
    lv = ev[ev.family.isin(["level", "fvg"])]
    L.append(md(two_period(lv, ["family", "variant", "mode"])))
    for cond in ["vpa_reversal_2m", "vpa_reversal_5m", "near_ema", "tod_band", "gap_size_band", "gap_same_day"]:
        sub = lv[lv.variant.str.endswith("limit") & (lv[cond] != "n/a")] if cond.startswith("gap") else lv[lv.variant.str.endswith("limit")]
        if cond.startswith("gap"):
            sub = sub[sub.family == "fvg"]
        L.append(f"\n**Limit-order bounces by {cond}**\n")
        L.append(md(two_period(sub, ["family", "variant", cond], min_n=50)))

    # D. Stops.
    L.append("\n## D. Stop research: how far trades that end up winning go against you first\n")
    L.append("Winners = up after 60 min. mae_atr = worst move against the trade, in ATR(5m) units.\n")
    w = disc[disc.r60 > 0]
    q = w.groupby(["family"]).mae_atr.quantile([.5, .8, .9]).unstack().round(2)
    q.columns = ["median", "80th pct", "90th pct"]
    L.append(q.reset_index().to_markdown(index=False))
    q2 = w.groupby("sym").agg(median=("mae_atr", "median"), p90=("mae_atr", lambda x: x.quantile(.9)),
                              atr5_pct=("atr5_pct", "median")).round(3).reset_index()
    L.append("\nBy ticker (atr5_pct = typical 5m ATR as % of price, so 1.5 ATR ~ 1.5 x that %):\n")
    L.append(q2.to_markdown(index=False))

    # E. Shortlist over everything.
    cells = []
    for sp in [None] + SPLITS:
        if sp and sp not in disc:
            continue
        by = ["family", "variant", "mode"] + ([sp] if sp else [])
        t = disc.groupby(by, observed=True).agg(n=("atr_r", "size"), atr_R=("atr_r", "mean"), sd=("atr_r", "std"),
                                                 win15=("r15", lambda x: (x > 0).mean() * 100))
        t = t[t.n >= a.min_n].reset_index()
        t["condition"] = (sp + "=" + t[sp].astype(str)) if sp else "all"
        cells.append(t.drop(columns=[sp] if sp else []))
    cells = pd.concat(cells, ignore_index=True)
    cells["t"] = cells.atr_R / (cells.sd / np.sqrt(cells.n))
    top = cells.sort_values("t", ascending=False).head(30)
    hold = ev[ev.period == "hold"]
    rows = []
    for _, r in top.iterrows():
        h = hold[(hold.family == r.family) & (hold.variant == r.variant) & (hold["mode"] == r["mode"])]
        if r.condition != "all":
            sp, val = r.condition.split("=", 1)
            h = h[h[sp].astype(str) == val]
        hh = agg(h) if len(h) > 1 else {"n": len(h)}
        rows.append(dict(family=r.family, variant=r.variant, mode=r["mode"], condition=r.condition,
                         n_d=int(r.n), win15_d=round(r.win15, 1), atr_R_d=round(r.atr_R, 3), t_d=round(r.t, 1),
                         n_h=hh["n"], win15_h=round(hh.get("win15", np.nan), 1),
                         atr_R_h=round(hh.get("atr_R", np.nan), 3), se2_h=round(hh.get("2se", np.nan), 3)))
    L.append(f"\n## E. Shortlist: best 30 of {len(cells)} discovery cells (n >= {a.min_n}) by t-stat, then the holdout\n")
    L.append("With this many cells, the top ones look good partly by luck; the `_h` columns are the real test.\n")
    L.append(pd.DataFrame(rows).to_markdown(index=False))
    Path(a.out).parent.mkdir(exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n")
    print(f"wrote {a.out}: {len(ev)} trades, {len(cells)} discovery cells")


if __name__ == "__main__":
    main()
