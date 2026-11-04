"""Stocks in play: tests on each day's biggest opening gappers (data from scripts/gappers_pull.py).

On each gapper stock-day (1m regular session):
  ORB-ATR    first 5-minute candle (9:30-9:35) sets the direction (green = long, red = short), enter at 9:35,
             stop 10% of the prior 14-day ATR, hold to the close (Zarattini & Aziz "stocks in play" style)
  ORB-range  same entry, stop beyond the first 5-minute candle's low / high, hold to the close
  gap-go / gap-fade   at 9:35 trade with / against the opening gap, 10% ATR stop, hold to the close
  star_break your pivot shooting star / hammer on 5m / 9m / 15m (above the 2 prior highs), entered when price breaks
             its low / high within 2 candles; 10:00-15:30 ET; exits +0.3%/-0.5% and structure (beyond the wick, 2R)
  random     random minute 10:00-15:30 and direction, same exits as star_break (structure uses a 0.5% stop)
Context: is the signal at an unfilled DAILY fair value gap on its side (from prior days' daily bars)?
Costs (gappers have wider spreads): 2 cents / price + 2 bps per round trip.

  python scripts/gapper_test.py [--report]   -> results/gappers.pkl, reports/gappers.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading.data import resample_bars  # noqa: E402
from pivot_test import shapes  # noqa: E402

D = Path("data/gappers")
OUT = Path("results/gappers.pkl")
SPLIT = pd.Timestamp("2024-11-01")


def daily_fvgs(dd: pd.DataFrame) -> pd.DataFrame:
    """Daily 3-bar FVGs per symbol, with the first later date that fully fills them."""
    out = []
    for sym, x in dd.groupby("sym"):
        x = x.reset_index(drop=True)
        h, l = x.high.to_numpy(), x.low.to_numpy()
        for i in range(2, len(x)):
            for d, ok, bot, top in ((1, l[i] > h[i - 2], h[i - 2], l[i]), (-1, h[i] < l[i - 2], h[i], l[i - 2])):
                if not ok:
                    continue
                after = l[i + 1:] <= bot if d > 0 else h[i + 1:] >= top
                j = np.argmax(after) if after.any() else -1
                out.append((sym, d, bot, top, x.date.iat[i], x.date.iat[i + 1 + j] if j >= 0 else pd.Timestamp.max))
    return pd.DataFrame(out, columns=["sym", "dir", "bottom", "top", "formed", "filled"])


def race(H, L, C, i0, d, e, stop, tgt, end_i):
    """Single-trade race on one day's 1m arrays from index i0+1 to end_i (same bar = stop)."""
    hh, ll = H[i0 + 1:end_i + 1], L[i0 + 1:end_i + 1]
    hs = ll <= stop if d > 0 else hh >= stop
    ht = (hh >= tgt if d > 0 else ll <= tgt) if tgt is not None else np.zeros(len(hh), bool)
    fs = np.argmax(hs) if hs.any() else 10**9
    ft = np.argmax(ht) if ht.any() else 10**9
    if fs <= ft and fs < 10**9:
        return 0, (stop - e) * d / e * 100
    if ft < 10**9:
        return 1, (tgt - e) * d / e * 100
    return 2, (C[end_i] - e) * d / e * 100


def run() -> pd.DataFrame:
    ev = pd.read_csv(D / "events.csv", parse_dates=["date"])
    dd = pd.read_csv(D / "daily.csv.gz", parse_dates=["date"])
    dd = dd[dd.sym.isin(ev.sym.unique())]
    fv = daily_fvgs(dd)
    fvg_by_sym = {s: g for s, g in fv.groupby("sym")}
    m1 = pd.read_csv(D / "m1.csv.gz", index_col=0, parse_dates=True)
    rng = np.random.default_rng(3)
    rows = []
    for (sym, ds), x in m1.groupby(["sym", "date"]):
        day = pd.Timestamp(ds)
        e_ = ev[(ev.sym == sym) & (ev.date == day)]
        if not len(e_) or len(x) < 300:
            continue
        info = e_.iloc[0]
        x = x.sort_index()
        O, H, L, C = (x[k].to_numpy() for k in ("open", "high", "low", "close"))
        mins = ((x.index - day) / pd.Timedelta(minutes=1)).to_numpy().astype(int) - 570   # minutes since 9:30 (bar start)
        last = len(x) - 1
        atr = info.atr14_prev
        base = dict(sym=sym, date=day, gap=info.gap, price=info.prev_close, atr_pct=atr / info.prev_close * 100)
        live = fvg_by_sym.get(sym)
        live = live[(live.formed < day) & (live.filled >= day)] if live is not None else None

        def at_gap(px, d):
            if live is None or not len(live):
                return False
            g = live[live.dir == d]
            buf = 0.1 * atr
            return bool(((px >= g.bottom - buf) & (px <= g.top + buf)).any())

        k5 = np.flatnonzero(mins < 5)
        if len(k5) >= 3 and mins[k5[-1]] == 4:
            o5, c5, h5, l5 = O[k5[0]], C[k5[-1]], H[k5].max(), L[k5].min()
            i0, e = k5[-1], C[k5[-1]]
            d = int(np.sign(c5 - o5))
            if d != 0:
                for name, stop in (("ORB-ATR", e - d * 0.1 * atr), ("ORB-range", l5 if d > 0 else h5)):
                    if (e - stop) * d > 0:
                        o, pct = race(H, L, C, i0, d, e, stop, None, last)
                        rows.append(dict(base, signal=name, side="with", dir=d, entry=e, stop_pct=abs(e - stop) / e * 100,
                                         out=o, pct=pct, exit_kind="EOD"))
            for name, dg in (("gap-go", int(np.sign(info.gap))), ("gap-fade", -int(np.sign(info.gap)))):
                stop = e - dg * 0.1 * atr
                o, pct = race(H, L, C, i0, dg, e, stop, None, last)
                rows.append(dict(base, signal=name, side="with", dir=dg, entry=e, stop_pct=abs(e - stop) / e * 100,
                                 out=o, pct=pct, exit_kind="EOD"))
        # star / hammer break entries
        x5 = x[["open", "high", "low", "close", "volume"]]
        for tf in ("5m", "9m", "15m"):
            b = resample_bars(x5, tf)
            step = pd.Timedelta(tf.replace("m", "min"))
            sh = shapes(b)
            for bias, mset, ext_s in ((-1, sh.star & (b.high > b.high.shift(1)) & (b.high > b.high.shift(2)), b.high),
                                      (1, sh.hammer & (b.low < b.low.shift(1)) & (b.low < b.low.shift(2)), b.low)):
                for t in b.index[mset.to_numpy()]:
                    j0 = x.index.searchsorted(t + step)                  # first 1m bar after the candle closes
                    jend = min(j0 + int(2 * step / pd.Timedelta(minutes=1)), last)
                    Hc, Lc = b.high.at[t], b.low.at[t]
                    hit = None
                    for q in range(j0, jend):
                        if bias < 0:
                            if H[q] > Hc:
                                break
                            if L[q] < Lc:
                                hit = (q, min(O[q], Lc))
                                break
                        else:
                            if L[q] < Lc:
                                break
                            if H[q] > Hc:
                                hit = (q, max(O[q], Hc))
                                break
                    if hit is None or not (30 <= mins[hit[0]] <= 359):
                        continue
                    q, e = hit
                    ext = float(ext_s.at[t])
                    for side, d in (("with", bias), ("opposite", -bias)):
                        r = dict(base, signal="star_break", tf=tf, side=side, dir=d, entry=e, at_daily_fvg=at_gap(ext, bias))
                        # same-minute fill: count that minute's adverse extreme against the stop
                        o1, p1 = race(H, L, C, q - 1, d, e, e * (1 - d * 0.005), e * (1 + d * 0.003), min(q + 120, last))
                        risk = abs(e - ext) + 0.0002 * e if side == "with" else abs(e - ext) + 0.0002 * e
                        o2, p2 = race(H, L, C, q - 1, d, e, e - d * risk, e + d * 2 * risk, last)
                        rows.append(dict(r, out=o1, pct=p1, exit_kind="T0.3/S0.5"))
                        rows.append(dict(r, out=o2, pct=p2, exit_kind="struct 2R", stop_pct=risk / e * 100))
        # random baseline: 3 random entries per day
        ok = np.flatnonzero((mins >= 30) & (mins <= 359))
        for q in rng.choice(ok, size=min(3, len(ok)), replace=False):
            d = int(rng.choice([-1, 1]))
            e = C[q]
            o1, p1 = race(H, L, C, q, d, e, e * (1 - d * 0.005), e * (1 + d * 0.003), min(q + 120, last))
            rows.append(dict(base, signal="random", side="random", dir=d, entry=e, out=o1, pct=p1, exit_kind="T0.3/S0.5"))
            risk = 0.005 * e
            o2, p2 = race(H, L, C, q, d, e, e - d * risk, e + d * 2 * risk, last)
            rows.append(dict(base, signal="random", side="random", dir=d, entry=e, out=o2, pct=p2, exit_kind="struct 2R", stop_pct=0.5))
    t = pd.DataFrame(rows)
    t["cost_pct"] = (0.02 / t.entry + 0.0002) * 100
    t["net"] = t.pct - t.cost_pct
    t["R"] = np.where(t.stop_pct > 0, t.net / t.stop_pct, np.nan)
    t.to_pickle(OUT)
    return t


def summ(g: pd.DataFrame) -> pd.Series:
    n = len(g)
    return pd.Series({"n": n, "win%": round((g.net > 0).mean() * 100, 1), "avg net %": round(g.net.mean(), 3),
                      "2se %": round(2 * g.net.std() / np.sqrt(n), 3) if n > 1 else np.nan,
                      "avg R": round(g.R.mean(), 3) if g.R.notna().any() else np.nan,
                      "median cost %": round(g.cost_pct.median(), 3)})


def two(t: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    a = t[t.date < SPLIT].groupby(by).apply(summ, include_groups=False).add_suffix("_d")
    b = t[t.date >= SPLIT].groupby(by).apply(summ, include_groups=False).add_suffix("_h")
    return a.join(b, how="outer").reset_index()


def report(t: pd.DataFrame) -> None:
    t["gap_dir"] = np.where(t.gap > 0, "gap up", "gap down")
    t["price_band"] = pd.cut(t.price, [0, 10, 20, 50, 1e9], labels=["$5-10", "$10-20", "$20-50", "$50+"]).astype(str)
    L = ["# Stocks in play: each day's 5 biggest opening gappers (|gap| >= 4%, price >= $5, avg volume >= 1M)\n",
         f"{t.groupby(['sym','date']).ngroups} stock-days, {t.date.min():%Y-%m-%d} to {t.date.max():%Y-%m-%d}. "
         "`_d` = before 2024-11-01, `_h` = after. Costs = 2 cents / price + 2 bps per round trip. avg R = net / stop distance.\n",
         "## Opening-range and gap trades (9:35 entry, held to the close)\n",
         two(t[t.signal.isin(["ORB-ATR", "ORB-range", "gap-go", "gap-fade"])], ["signal"]).to_markdown(index=False),
         "\n**...by gap direction**\n",
         two(t[t.signal.isin(["ORB-ATR", "gap-go", "gap-fade"])], ["signal", "gap_dir"]).to_markdown(index=False),
         "\n**...by price**\n", two(t[t.signal == "ORB-ATR"], ["price_band"]).to_markdown(index=False),
         "\n## Star / hammer break entries vs random (10:00-15:30 ET)\n",
         two(t[t.signal.isin(["star_break", "random"])], ["signal", "side", "exit_kind"]).to_markdown(index=False),
         "\n**...by timeframe (with)**\n",
         two(t[(t.signal == "star_break") & (t.side == "with")], ["tf", "exit_kind"]).to_markdown(index=False),
         "\n**...at an unfilled daily fair value gap (with)**\n",
         two(t[(t.signal == "star_break") & (t.side == "with")], ["at_daily_fvg", "exit_kind"]).to_markdown(index=False)]
    Path("reports/gappers.md").write_text("\n".join(L) + "\n")
    print("wrote reports/gappers.md")


if __name__ == "__main__":
    report(pd.read_pickle(OUT) if "--report" in sys.argv else run())
