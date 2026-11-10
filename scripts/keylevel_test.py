"""Do the key levels (vpa_trading/keylevels.py) mean anything? 5 years of 1m bars, 9 tickers, levels as known before each open.

A. First touch of a level in the session (9:45-15:30 ET; opening-range levels from 10:00), coming from one side:
     held    price moves a quarter of the average daily range away again before a 1m close an eighth of it through
     broke   the close through comes first            (60 minutes, else neither)
   Every level is compared with two CONTROL prices 0.3-0.7 daily ranges away from it (not within reach of a real level),
   scored the same way: "held" has to beat that, or the level is just a price.
B. Pivot-wick candles (9m / 15m, the scanner's shape and pivot rule, scanner order mechanics, half at +0.5R then breakeven /
   1R, costs = spread + 1 bp) with the wick at a zone vs away from every zone, by zone score, family and volume.
Before = before 2024-11-01, after = from then (the check on unseen data).

  python scripts/keylevel_test.py            -> results/keylevels/*.pkl, reports/keylevels.md
  python scripts/keylevel_test.py --report
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import keylevels as K, live as LV, vpa  # noqa: E402
from vpa_trading.alpaca import load_bars_file, regular_session  # noqa: E402
from vpa_trading.willard_osc import willard_osc  # noqa: E402
from midcap_test import cost_bps  # noqa: E402
import trim_test as TT  # noqa: E402

SYMS = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "QQQ", "SPY"]
OUT = Path("results/keylevels")
SPLIT = pd.Timestamp("2024-11-01")
AWAY, THRU, HORIZON = 0.25, 0.125, 60


def touch(H, L, C, lo, hi, adr, start):
    """(side, result) of the first touch of [lo, hi] from bar `start` on: side +1 = came from above (a support test)."""
    hit = np.flatnonzero((L[start:331] <= hi) & (H[start:331] >= lo))
    if not len(hit):
        return None
    i = start + int(hit[0])
    side = 1 if C[i - 1] > hi else (-1 if C[i - 1] < lo else 0)
    if side == 0:
        return None
    for j in range(i, min(i + HORIZON, len(C))):
        if (side > 0 and C[j] < lo - THRU * adr) or (side < 0 and C[j] > hi + THRU * adr):
            return side, "broke"
        if (side > 0 and H[j] >= hi + AWAY * adr) or (side < 0 and L[j] <= lo - AWAY * adr):
            return side, "held"
    return side, "neither"


def run(sym: str) -> str:
    ext = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    m = regular_session(ext)
    ctx = K.Context(ext)
    rng = np.random.default_rng(sum(map(ord, sym)))       # the same control prices on every run
    day = m.index.normalize()
    pos = ctx.days.searchsorted(day)
    H, L, C, O = (m[k].to_numpy() for k in ("high", "low", "close", "open"))
    minute = ((m.index - day) / pd.Timedelta(minutes=1)).to_numpy().astype(int) - 570 + 1
    st, en = np.searchsorted(pos, np.arange(len(ctx.days)), "left"), np.searchsorted(pos, np.arange(len(ctx.days)), "right")
    day_last = (en - 1)[pos]
    clock = (m.index + pd.Timedelta(minutes=1)).values
    zones_by_day: dict[int, list] = {}
    A = []
    for i in range(130, len(ctx.days)):
        s, e = st[i], en[i]
        adr, tol = ctx.adr[i], ctx.tol(i)
        if e - s < 380 or not adr == adr:
            continue
        raw = ctx.raw(i)
        zs = K.cluster(raw, tol)
        zones_by_day[i] = zs
        h, l, c = H[s:e], L[s:e], C[s:e]
        o0 = O[s]
        prices = np.array([p for p, _ in raw])
        seen = set()
        for p, kind in raw:
            if abs(p - o0) > 3 * adr or (round(p, 2), kind) in seen:
                continue
            seen.add((round(p, 2), kind))
            start = 30 if kind.startswith("or_") else 15
            z = K.at(zs, p, 0)
            r = touch(h, l, c, p - 0.4 * tol, p + 0.4 * tol, adr, start)
            if r:
                A.append((ctx.days[i], kind, "real", r[0], r[1], z.score if z else 0.0, len(z.families) if z else 1))
            for _ in range(2):
                q = p + rng.choice([-1, 1]) * rng.uniform(0.3, 0.7) * adr
                if np.abs(prices - q).min() <= 2 * tol:
                    continue
                r = touch(h, l, c, q - 0.4 * tol, q + 0.4 * tol, adr, start)
                if r:
                    A.append((ctx.days[i], kind, "control", r[0], r[1], 0.0, 0))
    A = pd.DataFrame(A, columns=["day", "kind", "set", "side", "res", "score", "nfam"]).assign(sym=sym)
    # ---- B. pivot-wick candles
    cost, rows = cost_bps(sym), []
    OS = np.zeros(len(C))
    osc = {}
    for tf in ("5m", "9m", "15m"):               # the oscillator on closed candles of each timeframe
        f = LV.frame(m, tf)
        osc[tf] = (f.closes_at.to_numpy(), willard_osc(f).osc.to_numpy())
    for tf in ("9m", "15m"):
        b = LV.frame(m, tf)
        rv = vpa.relvol_tod(b)
        rg = (b.high - b.low).replace(0, np.nan)
        top, bot = b[["open", "close"]].max(axis=1), b[["open", "close"]].min(axis=1)
        body, upw, loww = (b.close - b.open).abs(), b.high - top, bot - b.low
        ut = (upw >= 0.4 * rg) & (upw >= body) & (loww <= 0.3 * rg) & (b.high >= b.high.rolling(12).max())
        ub = (loww >= 0.4 * rg) & (loww >= body) & (upw <= 0.3 * rg) & (b.low <= b.low.rolling(12).min())
        step = int(tf[:-1])
        for d, mask in ((-1, ut), (1, ub)):
            ev = b[mask.to_numpy()]
            jj = np.searchsorted(clock, ev.closes_at.to_numpy())
            for j, hi, lo, r_ in zip(jj, ev.high, ev.low, rv[mask.to_numpy()]):
                if j >= len(C) or clock[j] != clock[min(j, len(C) - 1)] or not (30 <= minute[j] <= 360):
                    continue
                i = int(pos[j])
                zs = zones_by_day.get(i)
                if zs is None:
                    continue
                res = {}
                for mode in ("full_1R", "half05_BE_1R", "half05_BE_2R"):
                    v = TT.candle_sim(O, H, L, C, OS, minute, day_last, int(j), d, float(hi), float(lo), step, mode)
                    if v is None:
                        break
                    res[mode] = v
                else:
                    wick = float(hi if d < 0 else lo)
                    risk = abs((lo - 0.01 if d < 0 else hi + 0.01) - wick)
                    cr = C[j] * cost / 1e4 / max(risk, 1e-9)
                    use = [z for z in zs if not (minute[j] < 30 + step and set(z.kinds) <= {"or_high", "or_low"})]
                    if minute[j] < 30 + step:       # the opening range is not a level for the candle that made it
                        use = [K._zone([(p, k) for p, k in zip([z.lo] * len(z.kinds), z.kinds) if not k.startswith("or_")])
                               if any(k.startswith("or_") for k in z.kinds) and not set(z.kinds) <= {"or_high", "or_low"} else z
                               for z in use]
                    z = K.at(use, wick, 0.6 * ctx.tol(i))
                    ov = {t_: float(v_[max(np.searchsorted(c_, clock[j], "right") - 1, 0)]) for t_, (c_, v_) in osc.items()}
                    rows.append({"time": pd.Timestamp(clock[j]), "sym": sym, "tf": tf, "dir": d, "rvol": float(r_),
                                 "osc5": ov["5m"], "osc9": ov["9m"], "osc15": ov["15m"],
                                 **{k: v - cr for k, v in res.items()}, "score": z.score if z else 0.0,
                                 "fams": ",".join(z.families) if z else "", "kinds": ",".join(sorted(set(z.kinds))) if z else ""})
    OUT.mkdir(parents=True, exist_ok=True)
    A.to_pickle(OUT / f"{sym}_touch.pkl")
    pd.DataFrame(rows).to_pickle(OUT / f"{sym}_candles.pkl")
    return f"{sym}: {len(A):,} touches, {len(rows):,} candle trades"


def report() -> None:
    A = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*_touch.pkl"))], ignore_index=True)
    B = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*_candles.pkl"))], ignore_index=True)
    A["late"], B["late"] = A.day >= SPLIT, B.time >= SPLIT
    L = ["# Key levels: do they hold, and do pivot candles at them work better?\n",
         f"{A.day.min():%Y-%m-%d} to {A.day.max():%Y-%m-%d}, {A.sym.nunique()} tickers. " + __doc__.split("\n\n")[1].replace("\n", " "), ""]

    def rate(g):
        return (g.res == "held").mean(), (g.res == "broke").mean(), len(g)
    L += ["## A. First touch: held / broke, level vs control prices\n",
          "Edge = held% of the level minus held% of its control prices, in points. An edge near zero means the level holds no "
          "better than a random nearby price.\n",
          "| Level | Touches | Held | Broke | Control held | Edge before | Edge after |", "|---|--:|--:|--:|--:|--:|--:|"]
    rowsA = []
    for kind, g in A.groupby("kind"):
        r, c = g[g.set == "real"], g[g.set == "control"]
        e = [rate(r[r.late == x])[0] - rate(c[c.late == x])[0] for x in (False, True)]
        rowsA.append((kind, len(r), rate(r)[0], rate(r)[1], rate(c)[0], e[0], e[1]))
    for kind, n, hd, br, ch, e0, e1 in sorted(rowsA, key=lambda x: -(x[5] + x[6])):
        L.append(f"| {K.NAME[kind]} | {n:,} | {hd:.0%} | {br:.0%} | {ch:.0%} | {e0 * 100:+.1f} | {e1 * 100:+.1f} |")
    r, c = A[A.set == "real"], A[A.set == "control"]
    L.append(f"| **All levels** | {len(r):,} | {rate(r)[0]:.0%} | {rate(r)[1]:.0%} | {rate(c)[0]:.0%} | "
             f"{(rate(r[~r.late])[0] - rate(c[~c.late])[0]) * 100:+.1f} | {(rate(r[r.late])[0] - rate(c[c.late])[0]) * 100:+.1f} |")
    L += ["\n### By how many kinds of level stack in the zone\n", "| Families in the zone | Touches | Held | Broke | Edge vs control |", "|---|--:|--:|--:|--:|"]
    base = rate(c)[0]
    for lab, g in (("1", r[r.nfam <= 1]), ("2", r[r.nfam == 2]), ("3", r[r.nfam == 3]), ("4 or more", r[r.nfam >= 4])):
        L.append(f"| {lab} | {len(g):,} | {rate(g)[0]:.0%} | {rate(g)[1]:.0%} | {(rate(g)[0] - base) * 100:+.1f} |")
    L += ["\n### By zone score\n", "| Zone score | Touches | Held | Broke | Edge vs control |", "|---|--:|--:|--:|--:|"]
    for lab, g in (("under 4", r[r.score < 4]), ("4 to 7", r[(r.score >= 4) & (r.score < 7)]), ("7 to 10", r[(r.score >= 7) & (r.score < 10)]),
                   ("10 or more", r[r.score >= 10])):
        L.append(f"| {lab} | {len(g):,} | {rate(g)[0]:.0%} | {rate(g)[1]:.0%} | {(rate(g)[0] - base) * 100:+.1f} |")

    col = "half05_BE_1R"

    def line(name, g):
        a, b = g[~g.late][col], g[g.late][col]
        t = lambda x: x.mean() / (x.std() / np.sqrt(len(x))) if len(x) > 2 else np.nan  # noqa: E731
        return f"| {name} | {len(g):,} | {a.mean():+.3f} | {b.mean():+.3f} | {t(b):+.1f} | {(b > 0).mean():.0%} | {g[g.late].half05_BE_2R.mean():+.3f} |"
    hdr = ["| Group | Trades | Avg R before | Avg R after | t after | Won (after) | 2R runner after |", "|---|--:|--:|--:|--:|--:|--:|"]
    L += ["\n## B. Pivot-wick candles: at a key zone vs not\n", "Average R per trade after costs, half at +0.5R then breakeven / 1R.\n"] + hdr
    L.append(line("All candles", B))
    L.append(line("Wick away from every zone", B[B.score == 0]))
    L.append(line("Wick at a zone", B[B.score > 0]))
    for lab, g in (("zone score under 4", B[(B.score > 0) & (B.score < 4)]), ("zone score 4 to 7", B[(B.score >= 4) & (B.score < 7)]),
                   ("zone score 7 to 10", B[(B.score >= 7) & (B.score < 10)]), ("zone score 10 or more", B[B.score >= 10])):
        L.append(line(lab, g))
    hv = B[B.rvol >= 2]
    L += ["\n### Only candles on volume 2x usual or more\n"] + hdr
    L.append(line("Away from every zone", hv[hv.score == 0])); L.append(line("At a zone", hv[hv.score > 0]))
    L.append(line("At a zone scoring 7 or more", hv[hv.score >= 7]))
    L += ["\n### By family in the zone the wick is at (a candle counts once per family)\n"] + hdr
    fam_rows = []
    for f in sorted({x for s in B.fams.unique() for x in s.split(",") if x}):
        g = B[B.fams.str.split(",").apply(lambda xs: f in xs)]
        fam_rows.append((g[g.late][col].mean(), line(f, g)))
    L += [x for _, x in sorted(fam_rows, key=lambda x: -x[0])]
    # ---- oscillator at the extreme when the candle prints (>= 80 at a top, <= 20 at a bottom)
    ext = lambda c_, lv: np.where(B["dir"] < 0, B[c_] >= lv, B[c_] <= 100 - lv)  # noqa: E731
    B["o15"], B["o_all"] = ext("osc15", 80), ext("osc5", 75) & ext("osc9", 75) & ext("osc15", 75)
    zone, strong, vol = B.score > 0, B.score >= 7, B.rvol >= 2
    L += ["\n### Oscillator at the extreme when the candle prints\n",
          "15m oscillator 80+ at a top / 20 or less at a bottom; \"all three\" = the 5m, 9m and 15m oscillators all past 75 / 25 "
          "(the alert mode's rule).\n"] + hdr
    for name, mask in (("15m oscillator NOT at the extreme", ~B.o15), ("15m oscillator at the extreme", B.o15),
                       ("all three at the extreme", B.o_all),
                       ("at a zone, 15m oscillator not extreme", zone & ~B.o15), ("at a zone + 15m oscillator extreme", zone & B.o15),
                       ("at a zone + all three extreme", zone & B.o_all),
                       ("zone 7+ and 15m oscillator extreme", strong & B.o15),
                       ("volume 2x + 15m oscillator extreme, away from zones", vol & B.o15 & ~zone),
                       ("volume 2x + zone + 15m oscillator extreme", vol & zone & B.o15),
                       ("volume 2x + zone 7+ + 15m oscillator extreme", vol & strong & B.o15),
                       ("volume 2x + zone 7+, oscillator NOT extreme", vol & strong & ~B.o15)):
        L.append(line(name, B[mask]))
    L += ["\n### Longs and shorts at a zone\n"] + hdr
    L.append(line("longs at a zone (bottom wick)", B[(B.score > 0) & (B["dir"] > 0)])); L.append(line("shorts at a zone (top wick)", B[(B.score > 0) & (B["dir"] < 0)]))
    Path("reports/keylevels.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run, [a for a in sys.argv[1:] if not a.startswith("-")] or SYMS):
                print(msg, flush=True)
    report()
