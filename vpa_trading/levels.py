"""Hand-entered price levels (an analyst's posted levels, your own), used to tag scanner signals.

Files: data/levels/<YYYY-MM-DD>_<source>.csv with columns date, source, sym, lo, hi, role, note.
  role: long_trigger, short_trigger, target_up, target_down, support, resistance
The newest file per source dated on or before the trading day is used. data/levels/ is git-ignored: posted levels from a
paid feed stay on this machine. Logged only, never a filter.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DIR = Path("data/levels")


def load(day: pd.Timestamp, folder: Path = DIR) -> pd.DataFrame:
    files = sorted(folder.glob("*.csv")) if folder.exists() else []
    latest: dict[str, Path] = {}
    for f in files:
        try:
            d, src = f.stem.split("_", 1)
            if pd.Timestamp(d) <= day.normalize():
                latest[src] = f                 # sorted by name = by date, so the last one wins
        except ValueError:
            continue
    if not latest:
        return pd.DataFrame(columns=["date", "source", "sym", "lo", "hi", "role", "note"])
    return pd.concat([pd.read_csv(f) for f in latest.values()], ignore_index=True)


def near(lv: pd.DataFrame, sym: str, px: float, tol: float) -> list[dict]:
    """Levels of `sym` within `tol` of `px` (inside a zone counts as 0), closest first."""
    x = lv[lv.sym == sym]
    out = []
    for r in x.itertuples():
        dist = 0.0 if r.lo <= px <= r.hi else min(abs(px - r.lo), abs(px - r.hi))
        if dist <= tol:
            zone = f"{r.lo:g}" if r.lo == r.hi else f"{r.lo:g}-{r.hi:g}"
            out.append({"source": r.source, "level": zone, "role": r.role, "dist": round(dist, 2),
                        "note": r.note if isinstance(r.note, str) else ""})
    return sorted(out, key=lambda d: d["dist"])


def label(hits: list[dict]) -> str:
    return "; ".join(f"{h['source']} {h['role'].replace('_', ' ')} {h['level']}" for h in hits[:2])
