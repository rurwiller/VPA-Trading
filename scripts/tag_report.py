"""Do signals with an EMA + gap confluence (or sitting at a GEX wall) do better than the rest?

  python scripts/tag_report.py            # every day in logs/live/*.jsonl
Reads the candle scanner's own log (not the TSLA breakout). One row per signal that filled and closed; pnl in $ and in R
(R = the planned stop distance x shares). Confluence = the wick is within 0.25 ATR(5m) of the daily or 1h EMA 9/21 AND
inside an unfilled gap on 15m / 1h / 4h / D in the trade's direction. Tags are only logged, never used as a filter.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

last: dict = {}
for f in sorted(Path("logs/live").glob("2*.jsonl")):
    for line in f.read_text().splitlines():
        d = json.loads(line)
        if d.get("strategy"):
            continue
        last[(f.stem, d["sym"], d["tf"], d["signal_close"], d["type"])] = d
rows = []
for (day, *_), d in last.items():
    t, g = d.get("tags") or {}, d.get("gex") or {}
    row = dict(day=day, sym=d["sym"], tf=d["tf"], type=d["type"], side="long" if d["side"] > 0 else "short", status=d["status"],
               confluence=bool(t.get("confluence")), near_ema="+".join(t.get("near_ema", [])) or "-",
               gaps="+".join(t.get("gap_tfs", [])) or "-", gex_near=bool(g.get("near")))
    if d["status"] == "closed" and d.get("fill") and d.get("exit"):
        risk = abs(d["entry"] - d["stop"]) * d["qty"]
        row["pnl"] = (d["exit"] - d["fill"]) * d["side"] * d["qty"]
        row["R"] = row["pnl"] / risk if risk else float("nan")
    rows.append(row)
df = pd.DataFrame(rows)
if df.empty or "pnl" not in df:
    print("no closed signals logged yet")
    raise SystemExit
tagged = df[df.day >= df[df.confluence].day.min()] if df.confluence.any() else df
print(f"{len(df)} signals, {int(df.pnl.notna().sum())} filled and closed since {df.day.min()}\n")
for col in ("confluence", "gex_near", "near_ema", "side", "tf"):
    g = df.dropna(subset=["pnl"]).groupby(col).agg(trades=("pnl", "size"), win_pct=("pnl", lambda x: round((x > 0).mean() * 100)),
                                                    total_pnl=("pnl", "sum"), avg_R=("R", "mean")).round(2)
    print(f"by {col}\n{g.to_string()}\n")
