"""Trend pullbacks (The Elite Trader's Handbook, ch. 4 / 8): trade WITH the higher-timeframe trend on a pullback
into the 20/50 EMA cloud of the trading timeframe.

Trend (1h, closed bars only):
  struct  last two confirmed 1h pivot highs AND lows rising (HH+HL) and 1h close > EMA50 (mirror for down)
  ema     1h close > EMA50 and EMA20 > EMA50 (mirror)
Pullback on the 5m / 15m chart (long; short mirrored):
  armed after 3 bars with low > EMA20; a bar dips into the cloud (low <= EMA20) without closing below EMA50.
  red     enter at the close of the first red bar in the cloud (touch bar or within 3 bars)   - "buy red candles"
  resume  enter at the close of the first bar (within 6) closing above the prior bar's high and above EMA20
  A close below EMA50 before entry cancels; after an entry or cancel the setup re-arms only after 3 bars above EMA20.
Stop: just below the lowest low of the pullback (-0.02%). Targets: 2R, or the swing high of the 20 bars before the
pullback ("zone to zone"). Held to stop / target, else flat at the 15:59 close. Entries 10:00-15:00 ET.
Every pullback is recorded with the 1h trend at entry: with / against / none.

  python scripts/trend_pullback.py [SYM ...] [--report]   -> results/pullbacks/<SYM>.pkl, reports/trend_pullback.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import research as R  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402
from midcap_test import MAG, MID, cost_bps  # noqa: E402
from pivot_test import pivot  # noqa: E402

OUT = Path("results/pullbacks")
SPLIT = pd.Timestamp("2024-11-01")


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False).mean()


def trend_1h(b: pd.DataFrame) -> pd.DataFrame:
    """Per 1h bar (known at its close): structure trend and EMA trend, +1 / -1 / 0."""
    e20, e50 = ema(b.close, 20), ema(b.close, 50)
    out = pd.DataFrame(index=b.index)
    for kind in ("H", "L"):
        x = b.high if kind == "H" else b.low
        pv = x.where(pivot(b, 2, kind)).shift(2)          # value known 2 bars after the pivot
        p = pv.dropna()
        out[f"last{kind}"] = p.reindex(b.index).ffill()
        out[f"prev{kind}"] = p.shift().reindex(b.index).ffill()
    up = (out.lastH > out.prevH) & (out.lastL > out.prevL) & (b.close > e50)
    dn = (out.lastH < out.prevH) & (out.lastL < out.prevL) & (b.close < e50)
    out["struct"] = np.where(up, 1, np.where(dn, -1, 0))
    out["ema"] = np.where((b.close > e50) & (e20 > e50), 1, np.where((b.close < e50) & (e20 < e50), -1, 0))
    out["closes_at"] = b.closes_at
    return out


def pullbacks(b: pd.DataFrame) -> pd.DataFrame:
    """Scan one chart timeframe for cloud pullbacks; both entry styles; both directions."""
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    e20, e50 = ema(b.close, 20).to_numpy(), ema(b.close, 50).to_numpy()
    n = len(b)
    day = b.index.normalize().to_numpy()
    rows = []
    for d in (1, -1):
        above = (l > e20) if d > 0 else (h < e20)
        run = 0
        armed, touch = False, -1
        done = {"red": False, "resume": False}
        for i in range(60, n):
            if touch < 0:
                run = run + 1 if above[i] else 0
                if not armed and run >= 3:
                    armed = True
                in_cloud = (l[i] <= e20[i] and c[i] > e50[i]) if d > 0 else (h[i] >= e20[i] and c[i] < e50[i])
                if armed and in_cloud:
                    touch, done = i, {"red": False, "resume": False}
                    swing = h[max(0, i - 20):i].max() if d > 0 else l[max(0, i - 20):i].min()
                    ext = l[i] if d > 0 else h[i]
                else:
                    continue
            # inside an active pullback (bar i, touch at `touch`); setups never carry over a session
            if day[i] != day[touch]:
                touch, armed, run = -1, False, 0
                continue
            ext = min(ext, l[i]) if d > 0 else max(ext, h[i])
            broke = c[i] < e50[i] if d > 0 else c[i] > e50[i]
            if broke:
                touch, armed, run = -1, False, 0
                continue
            k = i - touch
            red = (c[i] < o[i]) if d > 0 else (c[i] > o[i])
            if not done["red"] and k <= 3 and red:
                rows.append(dict(style="red", dir=d, bar=i, ext=ext, swing=swing))
                done["red"] = True
            resume = (c[i] > h[i - 1] and c[i] > e20[i]) if d > 0 else (c[i] < l[i - 1] and c[i] < e20[i])
            if not done["resume"] and k >= 1 and k <= 6 and resume:
                rows.append(dict(style="resume", dir=d, bar=i, ext=ext, swing=swing))
                done["resume"] = True
            if (done["red"] and done["resume"]) or k > 6:
                touch, armed, run = -1, False, 0
    ev = pd.DataFrame(rows)
    if len(ev):
        ev["closes_at"] = b.closes_at.to_numpy()[ev.bar.to_numpy()]
    return ev


def race_to_close(s, i, d, e, stop, target):
    """1m race from the bar after entry to the session's last bar; same bar = stop. Returns (outcome, exit)."""
    H, L, C = s.m1.high.to_numpy(), s.m1.low.to_numpy(), s.m1.close.to_numpy()
    out, px = np.zeros(len(i), int), np.zeros(len(i))
    for n, (ii, dd, ee, ss, tt) in enumerate(zip(i, d, e, stop, target)):
        last = s.day_last[ii]
        hh, ll = H[ii + 1:last + 1], L[ii + 1:last + 1]
        hs = ll <= ss if dd > 0 else hh >= ss
        ht = hh >= tt if dd > 0 else ll <= tt
        fs = np.argmax(hs) if hs.any() else 10**9
        ft = np.argmax(ht) if ht.any() else 10**9
        if fs <= ft and fs < 10**9:
            out[n], px[n] = 0, ss
        elif ft < 10**9:
            out[n], px[n] = 1, tt
        else:
            out[n], px[n] = 2, C[last]
    return out, px


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    t1 = trend_1h(V.frame(s.m1, "60m"))
    evs = []
    for tf in ("5m", "15m"):
        b = V.frame(s.m1, tf)
        ev = pullbacks(b)
        if not len(ev):
            continue
        j = R._bar_close_index(s, pd.Series(pd.to_datetime(ev.closes_at).to_numpy()))
        ev = ev[j >= 0].assign(i=j[j >= 0], tf=tf)
        m = s.minute[ev.i.to_numpy()]
        ev = ev[(m >= 30) & (m <= 330)]                 # 10:00-15:00 ET
        evs.append(ev)
    ev = pd.concat(evs, ignore_index=True)
    i = ev.i.to_numpy()
    e = s.m1.close.to_numpy()[i]
    d = ev.dir.to_numpy()
    stop = ev.ext.to_numpy() * (1 - 0.0002 * d)
    risk = np.maximum(np.abs(e - stop), 0.0005 * e)
    stop = e - d * risk
    tr = R.asof(t1, s.clock[i], ["struct", "ema"])
    ev["entry"], ev["risk_pct"] = e, risk / e * 100
    for name, col in (("trend_struct", "struct"), ("trend_ema", "ema")):
        t = tr[col].fillna(0).to_numpy()
        ev[name] = np.where(t == d, "with", np.where(t == -d, "against", "none"))
    ev["swing_rr"] = (ev.swing.to_numpy() - e) * d / risk
    for name, target in (("2R", e + d * 2 * risk), ("swing", ev.swing.to_numpy())):
        ok = (target - e) * d > 0
        o, px = race_to_close(s, i, d, e, stop, np.where(ok, target, e + d * 2 * risk))
        ev[f"{name}_out"] = o
        ev[f"{name}_pct"] = (px - e) * d / e * 100
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[i])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.drop(columns=["closes_at"]).to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev)} pullback entries"


def agg(g: pd.DataFrame, tgt: str) -> dict:
    n = len(g)
    if not n:
        return {"n": 0}
    c = g.sym.map(cost_bps).to_numpy() / 100
    r = (g[f"{tgt}_pct"].to_numpy() - c) / g.risk_pct.to_numpy()
    pct = g[f"{tgt}_pct"].to_numpy() - c
    return {"n": n, "win%": round((pct > 0).mean() * 100, 1), "target%": round((g[f"{tgt}_out"] == 1).mean() * 100, 1),
            "avg R": round(r.mean(), 3), "R_2se": round(2 * r.std() / np.sqrt(n), 3), "avg %": round(pct.mean(), 3)}


def two(t: pd.DataFrame, by: list[str], tgt: str) -> pd.DataFrame:
    rows = []
    for key, g in t.groupby(by, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(by, key))
        for p, gg in (("d", g[g.time < SPLIT]), ("h", g[g.time >= SPLIT])):
            r.update({f"{k}_{p}": v for k, v in agg(gg, tgt).items()})
        rows.append(r)
    return pd.DataFrame(rows)


def report() -> None:
    ev = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    ev["universe"] = np.where(ev.sym.isin(MID), "mid-cap", "Mag7+")
    L = ["# Trend pullbacks into the 20/50 EMA cloud (Elite Trader's Handbook)\n",
         f"{len(ev)} pullback entries on {len(ev.sym.unique())} tickers, {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}, "
         "entries 10:00-15:00 ET. `_d` = before 2024-11-01, `_h` = after. Costs = each ticker's spread + 1 bp.",
         "Stop below the pullback low; held to stop / target or the close. win% = profitable after costs; "
         "target% = target hit first; avg R / avg % after costs.\n"]
    for tgt in ("2R", "swing"):
        L.append(f"\n## Target {tgt}: by 1h structure trend (HH+HL and EMA50)\n")
        L.append(two(ev, ["universe", "tf", "style", "trend_struct"], tgt).to_markdown(index=False))
        L.append(f"\n## Target {tgt}: by 1h EMA trend\n")
        L.append(two(ev, ["universe", "tf", "style", "trend_ema"], tgt).to_markdown(index=False))
    w = ev[ev.trend_struct == "with"]
    L.append("\n## With the structure trend, 2R target, by ticker\n")
    L.append(two(w, ["universe", "sym"], "2R").to_markdown(index=False))
    L.append("\n## With the structure trend, by direction (2R)\n")
    L.append(two(w.assign(side=np.where(w.dir > 0, "long", "short")), ["universe", "side"], "2R").to_markdown(index=False))
    Path("reports/trend_pullback.md").write_text("\n".join(L) + "\n")
    print("wrote reports/trend_pullback.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=2) as ex:      # Kronos is using the other cores
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
