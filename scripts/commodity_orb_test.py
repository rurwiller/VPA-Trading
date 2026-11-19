"""The gold opening-range breakdown (scripts/gold_orb_test.py) on other commodity ETFs.

Same rule: on days the ETF opens below the prior close, short when a 30-minute block (from 9:30 ET) closes below the low of
the first 30 minutes; one trade a day; out at the target, the stop or the 16:00 close. Stop and target are scaled to each
fund's own average daily range (high - low over the prior 14 sessions), using the multiples the posted 20 / 15 points
were on gold (the median over 5 years), so a jumpy market like natural gas gets a proportionally wider stop.
Results in basis points of price (1 bp = 0.01%) after each fund's cost (half-spread twice, estimated, + 1 bp).
Contrast rows: the same short on days that did NOT open lower, and the mirrored long on gap-up days.
Thin funds (CPER, PPLT, DBA) trade only some minutes; missing minutes are filled with the last price, so their results
are rougher.

  python scripts/commodity_orb_test.py   -> reports/commodity_orb.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading.alpaca import load_bars_file  # noqa: E402

FUNDS = {"GLD": ("gold", 1.6), "SLV": ("silver", 3.1), "USO": ("crude oil", 3.0), "UNG": ("natural gas", 4.0),
         "CPER": ("copper", 11.0), "PPLT": ("platinum", 9.0), "DBA": ("agriculture", 6.0)}   # name, cost bps per round trip
SPLIT = pd.Timestamp("2024-11-01")
R_GOLD = 10.86


def days(sym: str):
    m = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz")
    d = m.index.normalize()
    mi = ((m.index - d) / pd.Timedelta(minutes=1)).astype(int) - 570
    m = m.assign(day=d, mi=mi)
    m = m[(m.mi >= 0) & (m.mi < 390)]
    cnt = m.groupby("day").mi.count()
    m = m[m.day.isin(cnt.index[(cnt >= 60) & (m.groupby("day").mi.max() >= 380)])]   # skip half days / near-empty days
    piv = lambda c: m.pivot(index="day", columns="mi", values=c).reindex(columns=range(390))  # noqa: E731
    C = piv("close").ffill(axis=1)
    H = piv("high").fillna(C)
    L = piv("low").fillna(C)
    O = m[m.mi == m.groupby("day").mi.transform("min")].set_index("day").open.reindex(C.index)
    adr = (H.max(axis=1) - L.min(axis=1)).rolling(14).mean().shift(1)
    return C, H, L, O, adr


def gold_multiples() -> tuple[float, float]:
    C, H, L, O, adr = days("GLD")
    pts_per_dollar = 1 / R_GOLD                                  # 1 gold point in GLD dollars
    r = (20 * pts_per_dollar / adr).dropna()
    return float(r.median()), float((15 * pts_per_dollar / adr).dropna().median())


def run(sym, side, gap, ks, kt, cost):
    C, H, L, O, adr = days(sym)
    c, h, l, o = C.to_numpy(), H.to_numpy(), L.to_numpy(), O.to_numpy()
    prev = np.r_[np.nan, c[:-1, 389]]
    rows = []
    for k in range(len(c)):
        a = adr.iat[k]
        if not (a == a) or not (prev[k] == prev[k]) or not (o[k] == o[k]):
            continue
        down = o[k] < prev[k]
        if not {"down": down, "notdown": not down, "up": o[k] > prev[k]}[gap]:
            continue
        lvl = np.nanmin(l[k, :30]) if side < 0 else np.nanmax(h[k, :30])
        for j in range(59, 389, 30):
            if (side < 0 and c[k, j] < lvl) or (side > 0 and c[k, j] > lvl):
                e = c[k, j]
                stop, tgt = e - side * ks * a, e + side * kt * a
                out, why = c[k, 389], "close"
                for t in range(j + 1, 390):
                    if (side < 0 and h[k, t] >= stop) or (side > 0 and l[k, t] <= stop):
                        out, why = stop, "stop"
                        break
                    if (side < 0 and l[k, t] <= tgt) or (side > 0 and h[k, t] >= tgt):
                        out, why = tgt, "target"
                        break
                rows.append({"day": C.index[k], "bps": side * (out / e - 1) * 1e4 - cost, "why": why})
                break
    return pd.DataFrame(rows)


def cell(t):
    if not len(t):
        return "- | - | -"
    p = t.bps
    return f"{len(p)} | {p.mean():+.1f} | {p.mean() / (p.std() / np.sqrt(len(p))):+.1f}"


def main() -> None:
    ks, kt = gold_multiples()
    L = ["# The gold opening-range breakdown on other commodities (5 years of 1m bars)\n", __doc__.split("\n\n")[1], "",
         f"Stop = {ks:.2f} x the average daily range, target = {kt:.2f} x (the posted 20 / 15 points on gold, as a median). "
         "Each cell: trades | average bps per trade after costs | t (mean / standard error; above about 2 is unlikely to be luck).\n"]
    for title, side, gap in (("The rule: short on gap-down days", -1, "down"),
                             ("Contrast: the same short on days that did NOT gap down", -1, "notdown"),
                             ("Mirror: long on gap-up days above the first-30-min high", 1, "up")):
        L += [f"\n## {title}\n", "| Fund | Market | All 5 years | Before Nov 2024 | Since Nov 2024 |", "|---|---|---|---|---|"]
        for sym, (name, cost) in FUNDS.items():
            t = run(sym, side, gap, ks, kt, cost)
            a, b = (t[t.day < SPLIT], t[t.day >= SPLIT]) if len(t) else (t, t)
            L.append(f"| {sym} | {name} | {cell(t)} | {cell(a)} | {cell(b)} |")
    Path("reports/commodity_orb.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
