"""The "15m EMA 20" idea from X (@piru4o, a gold trader), tested on 5 years of 1m bars.

Rules as posted (mirrored for shorts):
  1. a 15m candle crosses the EMA 20 from below and CLOSES above it -> longs are armed
  2. while candles stay above the EMA 20, buy when price comes back and touches the EMA 20
The post gives no stop or exit, so three common ones are tested:
  1R / 2R   stop 1 ATR(15m) beyond the entry, target 1R or 2R
  ema       hold until a 15m candle closes back on the other side of the EMA 20 (stop 1 ATR as a guard)
Entry: a limit at the EMA 20 of the last closed 15m candle, filled when a 1m bar touches it (10:00-15:30 ET), first touch
after each cross only ("first") or every touch while armed ("every", one trade at a time). Flat at 15:50 ET. Regular
hours only, EMA carried across days like a chart. Costs: ticker spread + 1 bp per round trip.

  python scripts/ema20_test.py   -> reports/ema20_test.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading.alpaca import load_bars_file  # noqa: E402
import vpa_fib_fvg as V  # noqa: E402
from midcap_test import cost_bps  # noqa: E402

SYMS = ["GLD", "SLV", "SPY", "QQQ", "TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD"]
SPLIT = pd.Timestamp("2024-11-01")
EXITS = ["1R", "2R", "ema"]


def run(sym: str) -> pd.DataFrame:
    m = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=True)
    b = V.frame(m, "15m")
    b["ema"] = b.close.ewm(span=20, adjust=False).mean()
    side = np.sign(b.close - b.ema).to_numpy()
    cross = np.r_[0, np.where(side[1:] != side[:-1], side[1:], 0)]       # +1 closed above after being below, -1 mirror
    t1 = m.index.to_numpy()
    H, L, C = m.high.to_numpy(), m.low.to_numpy(), m.close.to_numpy()
    mins = ((m.index - m.index.normalize()) / pd.Timedelta(minutes=1)).to_numpy().astype(int) - 570
    day = m.index.normalize().to_numpy()
    cl, em, at, ca = b.closes_at.to_numpy(), b.ema.to_numpy(), b.atr.to_numpy(), b.close.to_numpy()
    cost = cost_bps(sym)
    rows = []
    for mode in ("first", "every"):
        armed, busy_until = 0, np.datetime64("1970-01-01")
        for k in range(30, len(b) - 1):
            if cross[k]:
                armed = int(cross[k])
            elif side[k] != armed:
                armed = 0
            if not armed:
                continue
            lvl, a = em[k], at[k]
            if not (a > 0):
                continue
            i0 = np.searchsorted(t1, cl[k])                   # 1m bars inside the next 15m candle
            i1 = np.searchsorted(t1, cl[k + 1])
            for i in range(i0, i1):
                if day[i] != day[i0] or not 30 <= mins[i] <= 360 or t1[i] < busy_until:
                    break
                if (armed > 0 and L[i] <= lvl) or (armed < 0 and H[i] >= lvl):
                    d, e = armed, lvl
                    res = {}
                    for ex in EXITS:
                        stop = e - d * a
                        tgt = e + d * (2 if ex == "2R" else 1) * a
                        out, j = None, i
                        kk = k + 1
                        for j in range(i, len(C)):
                            if day[j] != day[i] or mins[j] >= 380:
                                out = C[j - 1]
                                break
                            if (d > 0 and L[j] <= stop) or (d < 0 and H[j] >= stop):
                                out = stop
                                break
                            if ex != "ema" and j > i and ((d > 0 and H[j] >= tgt) or (d < 0 and L[j] <= tgt)):
                                out = tgt
                                break
                            if ex == "ema":
                                while kk < len(cl) and cl[kk] <= t1[j]:
                                    kk += 1
                                if kk - 1 > k and cl[kk - 1] == t1[j] + np.timedelta64(60, "s") and (ca[kk - 1] - em[kk - 1]) * d < 0:
                                    out = C[j]
                                    break
                        if out is None:
                            out = C[j]
                        res[ex] = d * (out - e) / e * 1e4 - cost
                        if ex == "ema":
                            busy_until = t1[j]
                    rows.append({"sym": sym, "mode": mode, "time": pd.Timestamp(t1[i]), "dir": d, **res})
                    if mode == "first":
                        armed = 0
                    break
    return pd.DataFrame(rows)


def main() -> None:
    with ProcessPoolExecutor(6) as ex:
        df = pd.concat(list(ex.map(run, SYMS)))
    df["late"] = df.time >= SPLIT
    out = ["# The 15m EMA 20 idea (@piru4o), 5 years of 1m bars\n", __doc__.split("\n\n")[1], "",
           "Average result per trade in basis points (1 bp = 0.01%) after costs; win % in brackets. "
           "Before / after Nov 2024 (the later part is the out-of-sample check).\n"]
    for mode in ("first", "every"):
        out.append(f"\n## Entry on the {'first touch after each cross' if mode == 'first' else 'every touch while above / below'}\n")
        out.append("| Ticker | Trades | " + " | ".join(f"{e} before | {e} after" for e in EXITS) + " |")
        out.append("|---|--:|" + "--:|" * (2 * len(EXITS)))
        g0 = df[df["mode"] == mode]
        for sym, g in list(g0.groupby("sym", sort=False)) + [("**All**", g0)]:
            cells = []
            for e in EXITS:
                for late in (False, True):
                    x = g[g.late == late][e]
                    cells.append(f"{x.mean():+.1f} ({(x > 0).mean():.0%})" if len(x) else "-")
            out.append(f"| {sym} | {len(g)} | " + " | ".join(cells) + " |")
        for d, name in ((1, "longs"), (-1, "shorts")):
            x = g0[g0.dir == d]
            out.append(f"\n{name}: " + ", ".join(f"{e} {x[e].mean():+.1f} bps" for e in EXITS))
    Path("reports/ema20_test.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
