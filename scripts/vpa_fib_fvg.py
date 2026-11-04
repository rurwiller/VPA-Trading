"""Premier VPA candles (docs/vpa-detection-spec.md) on 9 / 15 / 29 / 60-minute candles, with
Fibonacci (1h and daily swings), fair value gaps (1h, 4h, daily) and RSI divergence as factors.

Entry at the close of the signal candle (the 1m close when it completes), scored as
with = trade Coulling's bias (shooting star / hanging man short, hammer long), against = opposite.
Outcomes as in reports/research.md (r15/r60 bps, +0.5%/-0.3% race, 1.5 x ATR(5m) stop / 2R), 2 bps costs.

  python scripts/vpa_fib_fvg.py [SYM ...]   -> results/vpa_fib/<SYM>.pkl, reports/vpa_fib_fvg.md
  python scripts/vpa_fib_fvg.py --report
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
from vpa_trading.data import resample_bars  # noqa: E402
from research_run import DEFAULT  # noqa: E402
from structure_test import swing_feats  # noqa: E402

OUT = Path("results/vpa_fib")
SIGNAL_TFS = ["9m", "15m", "29m", "60m"]
GAP_TFS = {"1h": 5, "4h": 20, "D": 60}        # gap timeframe -> sessions a gap stays live
PREMIER = ["SHOOTING_STAR", "SHOOTING_STAR_IN_DOWNTREND", "HAMMER", "HANGING_MAN",
           "HANGING_MAN_SHOOTING_STAR", "LL_DOJI_AT_HIGH", "LL_DOJI_AT_LOW"]
SPLIT = pd.Timestamp("2024-11-01")


def frame(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    step = pd.Timedelta(tf.replace("m", "min")) if tf.endswith("m") else pd.Timedelta(tf)
    b = resample_bars(m1, tf)
    b["closes_at"] = np.minimum((b.index + step).values, (b.index.normalize() + pd.Timedelta(hours=16)).values)
    b["atr"] = ind.atr(b)
    return b


def premier(b: pd.DataFrame) -> pd.DataFrame:
    """Spec section 3: shooting star, hammer, hanging man (+ combo), long-legged doji at an extreme."""
    det = vpa.detect(b, b.atr)
    det = det[det.type.isin(PREMIER)].copy()
    rng, body = b.high - b.low, (b.close - b.open).abs()
    up, lo = b.high - b[["open", "close"]].max(axis=1), b[["open", "close"]].min(axis=1) - b.low
    lld = (body <= 0.1 * rng) & (up >= 0.3 * rng) & (lo >= 0.3 * rng) & (rng / b.atr >= 1.0)
    ctx = vpa.context(b, b.atr)
    rv = vpa.relvol_tod(b)
    vc = pd.cut(rv, vpa.VOL_CLASSES, labels=vpa.VOL_NAMES, right=False).astype(str)
    rows = [det[["type", "bias", "vol_class", "relvol"] + (["repeat"] if "repeat" in det else [])]]
    for name, m, bias in (("LL_DOJI_AT_HIGH", lld & (ctx.near_high | (ctx.trend == 1)), -1),
                          ("LL_DOJI_AT_LOW", lld & (ctx.near_low | (ctx.trend == -1)) & ~ctx.near_high, 1)):
        rows.append(pd.DataFrame({"type": name, "bias": bias, "vol_class": vc[m], "relvol": rv[m]}, index=b.index[m]))
    out = pd.concat(rows).sort_index()
    out["closes_at"] = b.closes_at.reindex(out.index).to_numpy()
    return out


def live_gaps(s, b: pd.DataFrame, sessions: int) -> pd.DataFrame:
    g = ind.fvgs(b, b.atr, b.volume / b.volume.rolling(20).mean(), b.closes_at, intraday_only=False).reset_index(drop=True)
    lo, hi = s.m1.low.to_numpy(), s.m1.high.to_numpy()
    start = np.searchsorted(s.clock, g.formed_at.values) + 1
    fill = np.full(len(g), -1)
    for k, (d, top, bot, st) in enumerate(zip(g.dir.to_numpy(), g.top.to_numpy(), g.bottom.to_numpy(), start)):
        en = min(st + 390 * sessions, len(lo))
        if st < en:
            hit = lo[st:en] <= bot if d > 0 else hi[st:en] >= top
            if hit.any():
                fill[k] = st + int(np.argmax(hit))
    g["start"], g["fill"], g["expire"] = start, fill, np.minimum(start + 390 * sessions, len(lo))
    return g


def near_gap(g: pd.DataFrame, i: np.ndarray, px: np.ndarray, a: np.ndarray, d: np.ndarray) -> np.ndarray:
    """An unfilled gap on the trade's side (bull gap for a long) with price inside it or within 0.25 ATR."""
    out = np.zeros(len(i), bool)
    st, fi, ex = g.start.to_numpy(), g.fill.to_numpy(), g.expire.to_numpy()
    top, bot, gd = g.top.to_numpy(), g.bottom.to_numpy(), g.dir.to_numpy()
    for n in range(len(i)):
        act = (st <= i[n]) & ((fi < 0) | (fi > i[n])) & (ex > i[n]) & (gd == d[n])
        if act.any():
            buf = 0.25 * a[n]
            out[n] = bool(((px[n] >= bot[act] - buf) & (px[n] <= top[act] + buf)).any())
    return out


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    frames = {tf: frame(s.m1, tf) for tf in SIGNAL_TFS + ["4h"]}
    frames["D"] = fib.daily_bars(s.m1)
    frames["D"]["volume"] = s.m1.volume.groupby(s.m1.index.normalize()).sum()
    frames["D"]["atr"] = ind.atr(frames["D"])
    frames["1h"] = frames["60m"]
    gaps = {tf: live_gaps(s, frames[tf], n) for tf, n in GAP_TFS.items()}
    fstates = {"1h": fib.state(fib.legs(frames["1h"], 3), s.clock), "D": fib.state(fib.legs(frames["D"], 2), s.clock)}
    evs = []
    for tf in SIGNAL_TFS:
        b = frames[tf]
        p = premier(b)
        j = R._bar_close_index(s, pd.Series(p.closes_at.to_numpy()))
        p = p[j >= 0].assign(i=j[j >= 0])
        p = p[R._in_window(s, p.i.to_numpy())]
        sw = swing_feats(b)
        div = R.asof(b.join(sw), s.clock[p.i.to_numpy()], ["div_high", "div_low"])
        p["rsi_div"] = np.where(p.bias < 0, div.div_high, div.div_low) == 1
        for mode in ("with", "against"):
            e = p.reset_index(drop=True).copy()
            e["tf"], e["mode"] = tf, mode
            e["dir"] = e.bias if mode == "with" else -e.bias
            evs.append(e)
    ev = pd.concat(evs, ignore_index=True)
    ev = pd.concat([ev, R.outcomes(s, ev)], axis=1)
    i, px, a5 = ev.i.to_numpy(), s.m1.close.to_numpy()[ev.i.to_numpy()], s.atr5_clock[ev.i.to_numpy()]
    bias = ev.bias.to_numpy()                       # factors are judged against the candle's own bias
    for tag, st in fstates.items():
        ev = pd.concat([ev, fib.features(st.iloc[i].reset_index(drop=True), px, a5, bias, tag)], axis=1)
    for tf, g in gaps.items():
        ev[f"fvg_{tf}"] = near_gap(g, i, px, a5, bias)
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[i])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev) // 2} premier candles"


def report() -> None:
    import research_report as rr
    ev = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    ev["period"] = np.where(ev.time < SPLIT, "disc", "hold")
    ev["fib_1h"] = ev.fib1h_gp | ev.fib1h_retr
    ev["fib_D"] = ev.fibD_gp | ev.fibD_retr
    ev["fib_any"] = ev.fib_1h | ev.fib_D
    ev["fvg_any"] = ev.fvg_1h | ev.fvg_4h | ev.fvg_D
    ev["vol_avg_plus"] = ev.vol_class.isin(["AVERAGE", "HIGH", "ULTRA_HIGH"])
    ev["n_factors"] = (ev.fib_any.astype(int) + ev.fvg_any.astype(int) + ev.rsi_div.astype(int))
    for c in ["fib1h_gp", "fib1h_retr", "fib1h_ext", "fibD_gp", "fibD_retr", "fibD_ext", "fib_any",
              "fvg_1h", "fvg_4h", "fvg_D", "fvg_any", "rsi_div", "vol_avg_plus"]:
        ev[c] = np.where(ev[c], "yes", "no")
    w = ev[ev["mode"] == "with"]
    L = ["# Premier VPA candles + Fibonacci + FVG + RSI divergence\n",
         f"{len(w)} premier candles on {', '.join(sorted(ev.sym.unique()))}, {ev.time.min():%Y-%m-%d} to "
         f"{ev.time.max():%Y-%m-%d}; candles 9/15/29/60 min. `_d` = before {SPLIT:%Y-%m-%d}, `_h` = after.",
         "with = trade Coulling's bias; against = the opposite. win15 = % up after 15 min (in the trade's "
         "direction); pct_win = +0.5% before -0.3% within 60 min; atr_R = 1.5 ATR(5m) stop / 2R target, "
         "exit at 60 min. Costs 2 bps.",
         "Factors are on the candle's side: fib = at a fitting 1h/daily retracement or golden pocket; "
         "fvg = price in or within 0.25 ATR of an unfilled 1h/4h/daily gap on that side; rsi_div = RSI(14) "
         "divergence vs the last swing on the candle's own timeframe.\n",
         "## 1. Each candle type and timeframe\n", rr.md(rr.two_period(ev, ["tf", "type", "mode"]))]
    L.append("\n## 2. Volume grade (with bias)\n")
    L.append(rr.md(rr.two_period(w, ["tf", "vol_class"])))
    for c in ["fib1h_gp", "fib1h_retr", "fib1h_ext", "fibD_gp", "fibD_retr", "fibD_ext", "fib_any",
              "fvg_1h", "fvg_4h", "fvg_D", "fvg_any", "rsi_div"]:
        L.append(f"\n## Factor: {c} (with bias), all timeframes pooled, then by timeframe\n")
        L.append(rr.md(rr.two_period(w, [c])))
        L.append(rr.md(rr.two_period(w, ["tf", c])))
    L.append("\n## Number of factors present (fib, fvg, rsi_div), with bias\n")
    L.append(rr.md(rr.two_period(w, ["n_factors"])))
    L.append(rr.md(rr.two_period(w, ["tf", "n_factors"])))
    L.append("\n## At least average volume AND at least one factor, with bias\n")
    L.append(rr.md(rr.two_period(w[(w.vol_avg_plus == "yes") & (w.n_factors >= 1)], ["tf"])))
    Path("reports/vpa_fib_fvg.md").write_text("\n".join(L) + "\n")
    print("wrote reports/vpa_fib_fvg.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or DEFAULT):
                print(msg, flush=True)
    report()
