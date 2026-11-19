"""The gold opening-range breakdown (scripts/commodity_orb_test.py) on markets related to gold or driven by the same macro
forces, several of them thinner than GLD: gold miners, silver miners, safe-haven currencies, the dollar, Treasuries.

Same rule and scaling as commodity_orb_test.py: on gap-down days, short when a 30-minute block closes below the first
30 minutes' low; stop 0.97 x and target 0.73 x the 14-day average daily range; one trade a day; out by the close.
Costs are estimated (round-trip spread + 1 bp) and rough for the thin funds, so the before-cost column is shown too.

  python scripts/gold_orb_relatives_test.py   -> reports/gold_orb_relatives.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from commodity_orb_test import SPLIT, cell, gold_multiples, run  # noqa: E402

FUNDS = {"GLD": ("gold (reference)", 1.6), "GDX": ("gold miners", 2.5), "GDXJ": ("junior gold miners", 4.0),
         "NEM": ("Newmont", 2.5), "AEM": ("Agnico Eagle", 2.5), "SIL": ("silver miners", 8.0),
         "FXF": ("Swiss franc", 10.0), "FXY": ("Japanese yen", 5.0), "UUP": ("US dollar", 5.0),
         "TLT": ("20y+ Treasuries", 2.0), "IEF": ("7-10y Treasuries", 2.2)}


def main() -> None:
    ks, kt = gold_multiples()
    L = ["# The gold opening-range breakdown on gold's relatives (5 years of 1m bars)\n", __doc__.split("\n\n")[1], "",
         "Each cell: trades | average bps per trade | t (mean / standard error; above about 2 is unlikely to be luck).\n"]
    for title, side, gap in (("The rule: short on gap-down days", -1, "down"),
                             ("Contrast: the same short on days that did NOT gap down", -1, "notdown")):
        L += [f"\n## {title}\n", "| Fund | Market | Before costs | After costs | Before Nov 2024 | Since Nov 2024 | Win % |",
              "|---|---|---|---|---|---|---|"]
        for sym, (name, cost) in FUNDS.items():
            t = run(sym, side, gap, ks, kt, cost)
            if not len(t):
                L.append(f"| {sym} | {name} | - | - | - | - | - |")
                continue
            raw = t.assign(bps=t.bps + cost)
            a, b = t[t.day < SPLIT], t[t.day >= SPLIT]
            L.append(f"| {sym} | {name} | {cell(raw)} | {cell(t)} | {cell(a)} | {cell(b)} | {100 * (t.bps > 0).mean():.0f} |")
    Path("reports/gold_orb_relatives.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
