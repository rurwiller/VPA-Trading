"""Trade only at 1h / 4h / daily fair value gaps: premier VPA candles (9/15/29/60m) and climaxes (2/5/9/15m).

A signal counts as "at a gap" when the candle's extreme (low for a bullish signal, high for a bearish one) is inside, or
within 0.25 ATR(5m) of, an unfilled gap on the signal's side (bull gap = support for longs, bear gap = resistance for
shorts). Signals away from any gap are kept as the comparison. Each is scored with Coulling's bias ("with") and the
opposite. Entry at the signal candle's close; entries 10:00-15:30 ET.
Exits (1m bars, up to 120 min, same minute = stop): +0.3% target with a 0.5% stop; +0.3% with a 0.3% stop;
structure = stop just beyond the signal's extreme (+0.02%), target 2R. Costs = each ticker's spread + 1 bp.

  python scripts/fvg_candle_test.py [SYM ...] [--report]   -> results/fvg_candles/<SYM>.pkl, reports/fvg_candles.md
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
import vpa_fib_fvg as V  # noqa: E402
from midcap_test import MAG, MID, cost_bps  # noqa: E402
from small_target_test import race  # noqa: E402

OUT = Path("results/fvg_candles")
SPLIT = pd.Timestamp("2024-11-01")
CLIMAX_TYPES = {"SELLING_CLIMAX", "BUYING_CLIMAX", "STOPPING_VOLUME", "TOPPING_OUT_VOLUME"}


def climax_events(b: pd.DataFrame) -> pd.DataFrame:
    det = vpa.detect(b, b.atr)
    det = det[det.type.isin(CLIMAX_TYPES)]
    hi3, lo3 = b.high.rolling(3).max(), b.low.rolling(3).min()
    rows = [pd.DataFrame({"type": det.type, "bias": det.bias,
                          "ext": np.where(det.bias < 0, hi3.reindex(det.index), lo3.reindex(det.index))}, index=det.index)]
    rv = ind.rvol(b)
    c = ind.climaxes(b, ind.candles(b, b.atr), rv, min_rvol=2.0, min_wick=0.4)
    for col, bias, ext in (("buy_climax", -1, b.high), ("sell_climax", 1, b.low)):   # top = bearish, bottom = bullish
        m = c[col].fillna(False)
        rows.append(pd.DataFrame({"type": "single-bar climax " + ("top" if bias < 0 else "bottom"), "bias": bias,
                                  "ext": ext[m]}, index=b.index[m]))
    out = pd.concat(rows).sort_index()
    out["closes_at"] = b.closes_at.reindex(out.index).to_numpy()
    return out


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    frames = {"1h": V.frame(s.m1, "60m"), "4h": V.frame(s.m1, "4h")}
    dd = fib.daily_bars(s.m1)
    dd["volume"] = s.m1.volume.groupby(s.m1.index.normalize()).sum()
    dd["atr"] = ind.atr(dd)
    frames["D"] = dd
    gaps = {tf: V.live_gaps(s, frames[tf], n) for tf, n in V.GAP_TFS.items()}
    evs = []
    for tf in ("9m", "15m", "29m", "60m"):
        b = V.frame(s.m1, tf)
        p = V.premier(b)
        p["ext"] = np.where(p.bias < 0, b.high.reindex(p.index), b.low.reindex(p.index))
        evs.append(p[["type", "bias", "ext", "closes_at"]].assign(family="premier", tf=tf))
    for tf in ("2m", "5m", "9m", "15m"):
        b = V.frame(s.m1, tf)
        evs.append(climax_events(b).assign(family="climax", tf=tf))
    ev = pd.concat(evs)
    j = R._bar_close_index(s, pd.Series(pd.to_datetime(ev.closes_at).to_numpy()))
    ev = ev[j >= 0].assign(i=j[j >= 0]).reset_index(drop=True)
    m = s.minute[ev.i.to_numpy()]
    ev = ev[(m >= 30) & (m <= 360)].reset_index(drop=True)
    i, bias, ext = ev.i.to_numpy(), ev.bias.to_numpy(), ev.ext.to_numpy().astype(float)
    a5 = s.atr5_clock[i]
    for tf, g in gaps.items():
        ev[f"gap_{tf}"] = V.near_gap(g, i, ext, a5, bias)
    ev["at_gap"] = ev.gap_1h | ev.gap_4h | ev.gap_D
    ev["gap_tf"] = np.select([ev.gap_D, ev.gap_4h, ev.gap_1h], ["D", "4h", "1h"], "none")   # biggest timeframe present
    H, L, C = (s.m1[k].to_numpy() for k in ("high", "low", "close"))
    last = s.day_last
    parts = []
    for side in ("with", "opposite"):
        e = ev.copy()
        e["side"], e["dir"] = side, bias if side == "with" else -bias
        parts.append(e)
    ev = pd.concat(parts, ignore_index=True)
    i, d = ev.i.to_numpy(), ev.dir.to_numpy().astype(float)
    entry = C[i]
    ev["entry"] = entry
    for name, sp in (("T0.3_S0.5", 0.005), ("T0.3_S0.3", 0.003)):
        o, pct = race(H, L, C, last[i], i, d, entry, entry * (1 - d * sp), entry * (1 + d * 0.003))
        ev[f"out_{name}"], ev[f"pct_{name}"] = o, pct
    # structure: stop beyond the signal's extreme when trading with it; the opposite side mirrors the distance
    risk = np.maximum(np.abs(entry - ev.ext.to_numpy().astype(float)) + 0.0002 * entry, 0.0005 * entry)
    o, pct = race(H, L, C, last[i], i, d, entry, entry - d * risk, entry + d * 2 * risk)
    ev["out_struct"], ev["pct_struct"], ev["risk_pct"] = o, pct, risk / entry * 100
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[i])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.drop(columns=["closes_at"]).to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev) // 2} signals, {int(ev.at_gap.sum() // 2)} at a 1h/4h/D gap"


def agg(g: pd.DataFrame) -> dict:
    n = len(g)
    if not n:
        return {"n": 0}
    c = g.sym.map(cost_bps).to_numpy() / 100
    r = {"n": n}
    for name in ("T0.3_S0.5", "T0.3_S0.3"):
        net = g[f"pct_{name}"].to_numpy() - c
        r[f"{name} hit%"] = round((g[f"out_{name}"] == 1).mean() * 100, 1)
        r[f"{name} avg%"] = round(net.mean(), 3)
    sr = (g.pct_struct.to_numpy() - c) / g.risk_pct.to_numpy()
    r["struct 2R hit%"] = round((g.out_struct == 1).mean() * 100, 1)
    r["struct avg R"] = round(sr.mean(), 3)
    r["struct 2se"] = round(2 * sr.std() / np.sqrt(n), 3) if n > 1 else np.nan
    return r


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
    ev["where"] = np.where(ev.at_gap, "at 1h/4h/D gap", "no gap")
    L = ["# Premier candles and climaxes at 1h / 4h / daily fair value gaps\n",
         f"{len(ev) // 2} signals on {len(ev.sym.unique())} tickers, {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}; "
         "entries 10:00-15:30 ET. `_d` = before 2024-11-01, `_h` = after. Costs = each ticker's spread + 1 bp.",
         "T0.3_S0.5 = +0.3% target / 0.5% stop (breakeven hit rate before costs 62.5%); T0.3_S0.3 = +0.3% / 0.3% (50%); "
         "struct = stop beyond the signal's extreme, 2R target (breakeven 33%). Up to 120 min, then exit at market.\n"]
    for fam in ("premier", "climax"):
        f = ev[ev.family == fam]
        L.append(f"\n## {fam}: at a gap vs not, with vs opposite\n")
        L.append(two(f, ["universe", "where", "side"]).to_markdown(index=False))
        g = f[f.at_gap]
        L.append(f"\n## {fam} at a gap: by biggest gap timeframe\n")
        L.append(two(g, ["universe", "gap_tf", "side"]).to_markdown(index=False))
        L.append(f"\n## {fam} at a gap (with): by type\n")
        L.append(two(g[g.side == "with"], ["universe", "type"]).to_markdown(index=False))
        L.append(f"\n## {fam} at a gap (with): by signal timeframe\n")
        L.append(two(g[g.side == "with"], ["universe", "tf"]).to_markdown(index=False))
    Path("reports/fvg_candles.md").write_text("\n".join(L) + "\n")
    print("wrote reports/fvg_candles.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
