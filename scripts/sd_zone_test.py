"""Supply/demand zone system (The Elite Trader's Handbook, ch. 5-10): 1h zones, 5-minute entries, zone-to-zone targets.

Zones (1h bars, known when the impulse candle closes):
  base     1-3 consecutive candles with range <= 0.7 x ATR(1h, 14)
  impulse  the next candle: range >= 1.5 x ATR and body >= 60% of range (up = demand, down = supply), or a gap
           (open beyond the base's high / low by >= 0.5 ATR) in that direction
  zone     [lowest low, highest high] of the base. Broken when a 1h candle closes beyond it; expires after 20 sessions.
Setups on the 5m chart while a closed 5m bar trades inside a live zone (demand shown; supply mirrored):
  continuation  a bar within the last 6 dipped into the zone and this bar closes above the prior bar's high
  hammer        lower wick >= 45% of range, > body, upper wick <= 25%; low reaches into the zone; close above zone low
  Entry at that 5m close. Stop: min(zone low, pullback / hammer low) - 0.02%. Target: bottom of the nearest live supply
  zone above (zone to zone), else 2R. Held to stop / target, else flat at the close. One trade per zone, setup, day.
Factors recorded: 1h structure trend (with / against / none), 5m RSI(14) divergence, the zone overlapping a
volume-profile HVN (prior 10 sessions, top-20% volume price bins), and prior touches of the zone (fresh = 0).

  python scripts/sd_zone_test.py [SYM ...] [--report]   -> results/sd_zones/<SYM>.pkl, reports/sd_zones.md
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
from structure_test import swing_feats  # noqa: E402
from trend_pullback import race_to_close, trend_1h  # noqa: E402

OUT = Path("results/sd_zones")
SPLIT = pd.Timestamp("2024-11-01")


def zones(b: pd.DataFrame) -> pd.DataFrame:
    o, h, l, c, a = (b[k].to_numpy() for k in ("open", "high", "low", "close", "atr"))
    rng = h - l
    small = rng <= 0.7 * a
    rows = []
    for i in range(3, len(b)):
        if not small[i - 1] or np.isnan(a[i]):
            continue
        k = 1
        while k < 3 and small[i - 1 - k]:
            k += 1
        base = slice(i - k, i)
        bl, bh = l[base].min(), h[base].max()
        body = abs(c[i] - o[i])
        strong = rng[i] >= 1.5 * a[i] and body >= 0.6 * rng[i]
        for d in (1, -1):
            gap = (o[i] - bh >= 0.5 * a[i]) if d > 0 else (bl - o[i] >= 0.5 * a[i])
            moved = (c[i] > o[i] and c[i] > bh) if d > 0 else (c[i] < o[i] and c[i] < bl)
            if (strong and moved) or (gap and moved):
                rows.append(dict(kind=d, bottom=bl, top=bh, made=i, formed_at=b.closes_at.iat[i]))
    z = pd.DataFrame(rows)
    if not len(z):
        return z
    # broken: first later 1h close beyond the zone (demand: close < bottom; supply: close > top)
    brk = []
    for d, bot, top, i in zip(z.kind, z.bottom, z.top, z.made):
        after = c[i + 1:]
        hit = (after < bot) if d > 0 else (after > top)
        j = np.argmax(hit) if hit.any() else -1
        brk.append(b.closes_at.iat[i + 1 + j] if j >= 0 else pd.Timestamp.max)
    z["broken_at"] = brk
    z["expire_at"] = z.formed_at + pd.Timedelta(days=28)            # ~20 sessions
    # 1h touches after formation (low reaching the zone for demand, high for supply), with their close times
    z["touch_times"] = [list(b.closes_at.iloc[i + 1:][((l[i + 1:] <= top) & (h[i + 1:] >= bot))])
                        for bot, top, i in zip(z.bottom, z.top, z.made)]
    return z


def hvn_by_day(m1: pd.DataFrame) -> dict:
    """For each session: HVN price bins (top 20% by volume) from the prior 10 sessions, bin = 0.1% of price."""
    days = m1.index.normalize()
    ud = days.unique()
    out = {}
    px, vol = m1.close.to_numpy(), m1.volume.to_numpy()
    day_pos = pd.Series(np.arange(len(m1))).groupby(days.to_numpy()).agg(["min", "max"])
    for n in range(10, len(ud)):
        lo, hi = day_pos.loc[ud[n - 10], "min"], day_pos.loc[ud[n - 1], "max"]
        p, v = px[lo:hi + 1], vol[lo:hi + 1]
        w = p.mean() * 0.001
        k = np.floor(p / w).astype(np.int64)
        kk, inv = np.unique(k, return_inverse=True)
        tot = np.bincount(inv, weights=v)
        thr = np.quantile(tot, 0.8)
        out[ud[n]] = (kk[tot >= thr] + 0.5) * w
    return out


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    b1 = V.frame(s.m1, "60m")
    z = zones(b1)
    t1 = trend_1h(b1)
    b5 = V.frame(s.m1, "5m")
    sw = b5.join(swing_feats(b5))
    hv = hvn_by_day(s.m1)
    o, h, l, c = (b5[k].to_numpy() for k in ("open", "high", "low", "close"))
    start, close_at = b5.index, b5.closes_at
    rng = h - l
    top_b, bot_b = np.maximum(o, c), np.minimum(o, c)
    with np.errstate(invalid="ignore", divide="ignore"):
        up_w, lo_w, body = (h - top_b) / rng, (bot_b - l) / rng, (top_b - bot_b) / rng
    hammer = (lo_w >= 0.45) & (lo_w > body) & (up_w <= 0.25)
    star = (up_w >= 0.45) & (up_w > body) & (lo_w <= 0.25)
    zf, zb, zt, zk = z.formed_at.to_numpy(), z.broken_at.to_numpy(), z.expire_at.to_numpy(), z.kind.to_numpy()
    zbot, ztop = z.bottom.to_numpy(), z.top.to_numpy()
    used = set()
    rows = []
    for i in range(6, len(b5)):
        t0, t1c = start[i].to_datetime64(), close_at.iat[i].to_datetime64()
        live = np.flatnonzero((zf <= t0) & (zb > t1c) & (zt > t1c))
        if not len(live):
            continue
        day = start[i].normalize()
        for q in live:
            d, bot, top = zk[q], zbot[q], ztop[q]
            inside = (l[i] <= top and h[i] >= bot)
            if not inside:
                continue
            dipped = (l[i - 5:i + 1] <= top).any() if d > 0 else (h[i - 5:i + 1] >= bot).any()
            cont = dipped and ((c[i] > h[i - 1] and c[i] >= bot) if d > 0 else (c[i] < l[i - 1] and c[i] <= top))
            ham = (hammer[i] and l[i] <= top and c[i] > bot) if d > 0 else (star[i] and h[i] >= bot and c[i] < top)
            for style, ok in (("continuation", cont), ("hammer", ham)):
                key = (q, style, day)
                if ok and key not in used:
                    used.add(key)
                    ext = (min(l[i - 5:i + 1].min(), bot) if style == "continuation" else min(l[i], bot)) if d > 0 else \
                          (max(h[i - 5:i + 1].max(), top) if style == "continuation" else max(h[i], top))
                    # nearest live opposing zone in the trade's direction (its near edge)
                    opp = np.flatnonzero((zk == -d) & (zf <= t0) & (zb > t1c) & (zt > t1c))
                    if d > 0:
                        cand = zbot[opp][zbot[opp] > c[i]]
                        tgt = cand.min() if len(cand) else np.nan
                    else:
                        cand = ztop[opp][ztop[opp] < c[i]]
                        tgt = cand.max() if len(cand) else np.nan
                    tt = z.touch_times.iat[q]
                    rows.append(dict(style=style, dir=d, bar=i, ext=ext, zone_target=tgt, zone=q,
                                     touches=sum(1 for x in tt if x <= t0), zone_h_atr=(top - bot),
                                     hvn=bool(day in hv and ((hv[day] >= bot) & (hv[day] <= top)).any())))
    ev = pd.DataFrame(rows)
    j = R._bar_close_index(s, close_at.iloc[ev.bar.to_numpy()].reset_index(drop=True))
    ev = ev[j >= 0].assign(i=j[j >= 0]).reset_index(drop=True)
    m = s.minute[ev.i.to_numpy()]
    ev = ev[(m >= 30) & (m <= 330)].reset_index(drop=True)
    i, d = ev.i.to_numpy(), ev.dir.to_numpy()
    e = s.m1.close.to_numpy()[i]
    stop = ev.ext.to_numpy() * (1 - 0.0002 * d)
    risk = np.maximum(np.abs(e - stop), 0.0005 * e)
    stop = e - d * risk
    zt_ = ev.zone_target.to_numpy()
    has_zone_tgt = ~np.isnan(zt_) & ((zt_ - e) * d > 0)
    tgt = np.where(has_zone_tgt, zt_, e + d * 2 * risk)
    ev["entry"], ev["risk_pct"] = e, risk / e * 100
    ev["rr"] = (tgt - e) * d / risk
    ev["target_kind"] = np.where(has_zone_tgt, "next zone", "2R (no zone)")
    out, px = race_to_close(s, i, d, e, stop, tgt)
    ev["out"], ev["pct"] = out, (px - e) * d / e * 100
    tr = R.asof(t1, s.clock[i], ["struct"])["struct"].fillna(0).to_numpy()
    ev["trend"] = np.where(tr == d, "with", np.where(tr == -d, "against", "none"))
    dv = R.asof(sw, s.clock[i], ["div_high", "div_low"])
    ev["rsi_div"] = np.where(d > 0, dv.div_low, dv.div_high) == 1
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[i])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(z)} zones, {len(ev)} zone trades"


def agg(g: pd.DataFrame) -> dict:
    n = len(g)
    if not n:
        return {"n": 0}
    cst = g.sym.map(cost_bps).to_numpy() / 100
    pct = g.pct.to_numpy() - cst
    r = pct / g.risk_pct.to_numpy()
    return {"n": n, "win%": round((pct > 0).mean() * 100, 1), "target%": round((g.out == 1).mean() * 100, 1),
            "RR": round(g.rr.median(), 2), "avg R": round(r.mean(), 3), "R_2se": round(2 * r.std() / np.sqrt(n), 3),
            "avg %": round(pct.mean(), 3)}


def two(t: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for key, g in t.groupby(by, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(by, key))
        for p, gg in (("d", g[g.time < SPLIT]), ("h", g[g.time >= SPLIT])):
            r.update({f"{k}_{p}": v for k, v in agg(gg).items()})
        rows.append(r)
    return pd.DataFrame(rows)


def report() -> None:
    ev = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    ev["universe"] = np.where(ev.sym.isin(MID), "mid-cap", "Mag7+")
    ev["fresh"] = np.where(ev.touches == 0, "fresh", np.where(ev.touches <= 2, "1-2 touches", "3+ touches"))
    ev["rr_band"] = pd.cut(ev.rr, [0, 1, 1.5, 3, np.inf], right=False).astype(str)
    # the book's checklist: continuation WITH the trend; reversal (hammer) with RSI divergence; zone has an HVN; RR >= 1
    ev["all_factors"] = np.where((ev.hvn) & (ev.rr >= 1) & (((ev["style"] == "continuation") & (ev.trend == "with")) |
                                 ((ev["style"] == "hammer") & ev.rsi_div)), "yes", "no")
    L = ["# Supply/demand zone system (Elite Trader's Handbook)\n",
         f"{len(ev)} zone trades on {len(ev.sym.unique())} tickers, {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}, "
         "1h zones, 5m entries 10:00-15:00 ET. `_d` = before 2024-11-01, `_h` = after. Costs = each ticker's spread + 1 bp.",
         "win% = profitable after costs; target% = target hit before stop; RR = median planned reward/risk; avg R / avg % after costs.\n"]
    for by in (["universe", "style"], ["universe", "style", "target_kind"], ["universe", "style", "trend"],
               ["universe", "style", "rsi_div"], ["universe", "style", "hvn"], ["universe", "style", "fresh"],
               ["universe", "style", "rr_band"], ["universe", "style", "all_factors"]):
        L.append(f"\n## By {', '.join(by[1:])}\n")
        L.append(two(ev, by).to_markdown(index=False))
    L.append("\n## All factors aligned, by ticker\n")
    L.append(two(ev[ev.all_factors == "yes"], ["universe", "sym"]).to_markdown(index=False))
    Path("reports/sd_zones.md").write_text("\n".join(L) + "\n")
    print("wrote reports/sd_zones.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=2) as ex:
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
