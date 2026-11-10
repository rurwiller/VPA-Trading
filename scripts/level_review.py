"""Do posted levels hold? Every touch of a posted level vs touches of random look-alike levels.

  python scripts/level_review.py                  # all files in data/levels/, every day since each file's date
  python scripts/level_review.py --source jgbanks

A touch: the first 1m bar of a day (9:45-15:30 ET) that trades into the zone (+/- 0.05%) coming from one side.
Outcome over the next 60 minutes:
  held    price moves 0.5% away from the zone on the side it came from before closing 0.3% through it
  broke   price closes 0.3% through the zone first
  neither otherwise
Control: for each level, 10 random levels within +/-3% of it (same symbols and days, same rules). If posted levels "hold"
no more often than the random ones, they are not adding information. Output: reports/level_review_<source>.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import live as LV, levels as LVL  # noqa: E402

AWAY, THRU, PAD, HORIZON = 0.005, 0.003, 0.0005, 60


def touches(m: pd.DataFrame, lo: float, hi: float) -> list[str]:
    out = []
    for _, g in m.groupby(m.index.normalize()):
        g = g.between_time("09:45", "15:59")
        H, L, C = g.high.to_numpy(), g.low.to_numpy(), g.close.to_numpy()
        zl, zh = lo * (1 - PAD), hi * (1 + PAD)
        for i in range(1, len(g)):
            if g.index[i].time() > pd.Timestamp("15:30").time():
                break
            if not (L[i] <= zh and H[i] >= zl):
                continue
            side = 1 if C[i - 1] > zh else (-1 if C[i - 1] < zl else 0)     # +1 came from above (support test)
            if side == 0:
                continue
            res = "neither"
            for j in range(i, min(i + HORIZON, len(g))):
                if side > 0 and C[j] < lo * (1 - THRU) or side < 0 and C[j] > hi * (1 + THRU):
                    res = "broke"
                    break
                if side > 0 and H[j] >= hi * (1 + AWAY) or side < 0 and L[j] <= lo * (1 - AWAY):
                    res = "held"
                    break
            out.append(res)
            break                                   # first touch per day
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None)
    a = ap.parse_args()
    lv = pd.concat([pd.read_csv(f) for f in sorted(LVL.DIR.glob("*.csv"))], ignore_index=True)
    if a.source:
        lv = lv[lv.source == a.source]
    lv["date"] = pd.to_datetime(lv.date)
    start = lv.date.min() + pd.Timedelta(days=1)
    now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    bars = LV.fetch_bars(sorted(lv.sym.unique()), start, now - pd.Timedelta(minutes=20), feed="sip")
    rng = np.random.default_rng(7)
    real, ctrl = [], []
    for r in lv.itertuples():
        m = bars.get(r.sym)
        if m is None or not len(m):
            continue
        m = m[m.index >= r.date + pd.Timedelta(days=1)]
        real += [(r.sym, r.role, x) for x in touches(m, r.lo, r.hi)]
        for k in rng.uniform(-0.03, 0.03, 10):
            ctrl += [(r.sym, r.role, x) for x in touches(m, r.lo * (1 + k), r.hi * (1 + k))]
    R, C = pd.DataFrame(real, columns=["sym", "role", "res"]), pd.DataFrame(ctrl, columns=["sym", "role", "res"])
    src = a.source or "all"
    out = [f"# Do the posted levels hold? ({src}, since {start:%Y-%m-%d})\n", __doc__.split("\n\n")[2], "",
           "| | Touches | Held | Broke | Neither |", "|---|--:|--:|--:|--:|"]
    for name, d in (("Posted levels", R), ("Random levels (control)", C)):
        n = len(d)
        out.append(f"| {name} | {n} | " + " | ".join(f"{(d.res == k).mean():.0%}" if n else "-" for k in ("held", "broke", "neither")) + " |")
    if len(R):
        out.append("\n## Posted levels by symbol\n\n| Symbol | Touches | Held | Broke |\n|---|--:|--:|--:|")
        for s, g in R.groupby("sym"):
            out.append(f"| {s} | {len(g)} | {(g.res == 'held').mean():.0%} | {(g.res == 'broke').mean():.0%} |")
    out.append("\nA handful of days is far too few to judge; this needs weeks of posts before it means anything.")
    Path(f"reports/level_review_{src}.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
