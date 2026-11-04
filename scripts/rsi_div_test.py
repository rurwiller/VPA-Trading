"""RSI(14) divergence as the main signal, 9 / 15 / 29 / 60-minute candles, mid-caps (Mag 7+ for comparison).

Definitions (bearish shown; bullish mirrored), all known at the entry bar - no lookahead:
  price_k{1,2,3}  a new pivot high (k candles each side) above the previous pivot high (3-60 candles earlier)
                  with RSI lower than at that previous pivot; enter at the close of the k-th candle after it
  tv5             TradingView "RSI Divergence" style: pivots on RSI itself (5 left / 5 right, 5-60 bars apart),
                  RSI lower high while price made a higher high; enter at the confirming close
  live            the candle whose 3-bar push breaks the last confirmed swing high (2-candle pivot) closes with
                  RSI below the RSI at that swing; first such candle per swing; enter at its close
with = trade the divergence (short a bearish one), against = the opposite. Entries 10:00-15:30 ET.
Outcomes: r15/r60 bps; structure race = stop beyond the pivot extreme (+0.02%), 2R target, 60 and 120 min.

  python scripts/rsi_div_test.py [SYM ...] [--report]   -> results/rsi_div/<SYM>.pkl, reports/rsi_divergence.md
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
from vpa_trading.willard_osc import _rsi  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402
from midcap_test import MAG, MID, cost_bps  # noqa: E402
from pivot_test import in_window, pivot, shapes  # noqa: E402

OUT = Path("results/rsi_div")
TFS = ["9m", "15m", "29m", "60m"]
SPLIT = pd.Timestamp("2024-11-01")


def pairs(piv_pos: np.ndarray, lo_gap: int, hi_gap: int):
    """Consecutive pivots (previous, current) that are lo_gap..hi_gap bars apart."""
    for a, b in zip(piv_pos[:-1], piv_pos[1:]):
        if lo_gap <= b - a <= hi_gap:
            yield a, b


def divergences(b: pd.DataFrame) -> pd.DataFrame:
    rsi = _rsi(b.close, 14).to_numpy()
    H, Lo = b.high.to_numpy(), b.low.to_numpy()
    close_at = b.closes_at.to_numpy()
    sh = shapes(b)
    rows = []

    def add(name, bias, j, conf_pos, p):
        if conf_pos >= len(b):
            return
        rows.append(dict(event=name, bias=bias, pos=j, conf=close_at[conf_pos],
                         ext=H[j] if bias < 0 else Lo[j], rsi_prev=rsi[p], rsi_now=rsi[j],
                         candle=bool(sh.star.iat[j]) if bias < 0 else bool(sh.hammer.iat[j])))

    for k in (1, 2, 3):
        for kind, bias in (("H", -1), ("L", 1)):
            pos = np.flatnonzero(pivot(b, k, kind).to_numpy())
            for p, j in pairs(pos, 3, 60):
                if bias < 0 and H[j] > H[p] and rsi[j] < rsi[p]:
                    add(f"price_k{k}", bias, j, j + k, p)
                if bias > 0 and Lo[j] < Lo[p] and rsi[j] > rsi[p]:
                    add(f"price_k{k}", bias, j, j + k, p)
    # TradingView style: pivots on RSI (5/5), 5-60 bars apart
    r = pd.Series(rsi, index=b.index)
    roll = r.rolling(11, center=True)
    for bias, is_p in ((-1, r == roll.max()), (1, r == roll.min())):
        pos = np.flatnonzero(is_p.fillna(False).to_numpy())
        for p, j in pairs(pos, 5, 60):
            if bias < 0 and rsi[j] < rsi[p] and H[j] > H[p]:
                add("tv5", bias, j, j + 5, p)
            if bias > 0 and rsi[j] > rsi[p] and Lo[j] < Lo[p]:
                add("tv5", bias, j, j + 5, p)
    # live: push through the last confirmed 2-candle swing with lower RSI, first time per swing
    for kind, bias in (("H", -1), ("L", 1)):
        pos = np.flatnonzero(pivot(b, 2, kind).to_numpy())
        known = pos + 2
        x = H if bias < 0 else Lo
        push = pd.Series(x).rolling(3).max().to_numpy() if bias < 0 else pd.Series(x).rolling(3).min().to_numpy()
        ptr, used = -1, set()
        for i in range(len(b)):
            while ptr + 1 < len(pos) and known[ptr + 1] <= i:
                ptr += 1
            if ptr < 0 or pos[ptr] in used or i - pos[ptr] > 60:
                continue
            p = pos[ptr]
            broke = push[i] > x[p] if bias < 0 else push[i] < x[p]
            if broke:
                used.add(p)
                if (rsi[i] < rsi[p]) if bias < 0 else (rsi[i] > rsi[p]):
                    add("live", bias, i, i, p)
    return pd.DataFrame(rows)


def race(s, ev: pd.DataFrame, horizon: int) -> pd.DataFrame:
    C, H, L = (s.m1[c].to_numpy() for c in ("close", "high", "low"))
    i, d, e = ev.i.to_numpy(), ev.dir.to_numpy().astype(float), ev.entry.to_numpy()
    risk = np.maximum(np.abs(ev.ext.to_numpy() - e) + 0.0002 * e, 0.0005 * e)
    last = s.day_last[i]
    J = i[:, None] + np.arange(1, horizon + 1)
    valid = J <= last[:, None]
    Jc = np.minimum(J, last[:, None])
    fav = np.where(valid, np.where(d[:, None] > 0, H[Jc] - e[:, None], e[:, None] - L[Jc]), -np.inf)
    adv = np.where(valid, np.where(d[:, None] > 0, e[:, None] - L[Jc], H[Jc] - e[:, None]), -np.inf)
    hs, ht = adv >= risk[:, None], fav >= 2 * risk[:, None]
    fs = np.where(hs.any(1), hs.argmax(1), 10**6)
    ft = np.where(ht.any(1), ht.argmax(1), 10**6)
    end = d * (C[np.minimum(i + horizon, last)] - e)
    res = np.where((fs <= ft) & (fs < 10**6), -risk, np.where(ft < fs, 2 * risk, end))
    return pd.DataFrame({f"st{horizon}_win": ft < fs, f"st{horizon}_pct": res / e * 100, "risk_pct": risk / e * 100})


def run_symbol(sym: str) -> str:
    m1x = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1x)
    evs = []
    for tf in TFS:
        b = V.frame(s.m1, tf)
        d = divergences(b)
        if not len(d):
            continue
        j = R._bar_close_index(s, pd.Series(pd.to_datetime(d.conf).to_numpy()))
        d = d[j >= 0].assign(i=j[j >= 0])
        d = d[in_window(s, d.i.to_numpy())]
        d["tf"] = tf
        evs.append(d)
    ev = pd.concat(evs, ignore_index=True).drop_duplicates(["event", "tf", "bias", "i"])
    parts = []
    for mode in ("with", "against"):
        e = ev.copy()
        e["mode"], e["dir"] = mode, e.bias if mode == "with" else -e.bias
        parts.append(e)
    ev = pd.concat(parts, ignore_index=True).reset_index(drop=True)
    ev = pd.concat([ev, R.outcomes(s, ev)], axis=1)
    ev = pd.concat([ev, race(s, ev, 60), race(s, ev, 120).drop(columns="risk_pct")], axis=1)
    ev["sym"], ev["time"] = sym, pd.to_datetime(s.clock[ev.i.to_numpy()])
    OUT.mkdir(parents=True, exist_ok=True)
    ev.to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(ev) // 2} divergences"


def agg(g: pd.DataFrame) -> dict:
    n = len(g)
    if not n:
        return {"n": 0}
    c = g.sym.map(cost_bps).to_numpy()
    r15, r60 = g.r15.to_numpy() + 2 - c, g.r60.to_numpy() + 2 - c
    s60 = (g.st60_pct.to_numpy() - c / 100) / g.risk_pct.to_numpy()
    s120 = (g.st120_pct.to_numpy() - c / 100) / g.risk_pct.to_numpy()
    return {"n": n, "win15": round((r15 > 0).mean() * 100, 1), "r15": round(r15.mean(), 1), "r60": round(r60.mean(), 1),
            "r60_2se": round(2 * r60.std() / np.sqrt(n), 1), "2R@60 hit%": round(g.st60_win.mean() * 100, 1),
            "R@60": round(s60.mean(), 3), "R@120": round(s120.mean(), 3), "R@120_2se": round(2 * s120.std() / np.sqrt(n), 3)}


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
    ev["rsi_zone"] = np.where(((ev.bias < 0) & (ev.rsi_prev >= 70)) | ((ev.bias > 0) & (ev.rsi_prev <= 30)), "OB/OS (70/30)",
                     np.where(((ev.bias < 0) & (ev.rsi_prev >= 60)) | ((ev.bias > 0) & (ev.rsi_prev <= 40)), "60/40", "neither"))
    ev["side"] = np.where(ev.bias < 0, "bearish (short)", "bullish (long)")
    w = ev[ev["mode"] == "with"]
    L = ["# RSI(14) divergence as the main signal\n",
         f"{len(w)} divergences on {len(ev.sym.unique())} tickers, {ev.time.min():%Y-%m-%d} to {ev.time.max():%Y-%m-%d}; "
         "entries 10:00-15:30 ET. `_d` = before 2024-11-01, `_h` = after. Costs = each ticker's spread + 1 bp.",
         "win15 / r15 / r60 after costs (bps); 2R@60 hit% = 2R target before the structure stop within 60 min; "
         "R@60 / R@120 = average R after costs with the structure stop and 2R target, exit at 60 / 120 min.\n",
         "## 1. Each definition, timeframe and side\n", two(ev, ["universe", "event", "tf", "mode"]).to_markdown(index=False),
         "\n## 2. With the divergence, by direction\n", two(w, ["universe", "event", "side"]).to_markdown(index=False),
         "\n## 3. With the divergence, by RSI zone at the first pivot\n", two(w, ["universe", "event", "rsi_zone"]).to_markdown(index=False),
         "\n## 4. With the divergence, pivot candle is a shooting star / hammer\n", two(w, ["universe", "event", "candle"]).to_markdown(index=False),
         "\n## 5. Mid-caps by ticker (with, all definitions pooled)\n", two(w[w.universe == "mid-cap"], ["sym"]).to_markdown(index=False)]
    Path("reports/rsi_divergence.md").write_text("\n".join(L) + "\n")
    print("wrote reports/rsi_divergence.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or MID + MAG):
                print(msg, flush=True)
    report()
