"""Trade journal: every paper position with the context it was taken in, so live results become research data (step 8).

Positions come from Alpaca's fills (half exits / thirds grouped, real P/L, same as the scorecard). Each is matched to the
scanner's own log (logs/live/<day>.jsonl) by symbol and fill time, which adds the plan: timeframe, candle type, gap,
key-level zone, planned entry / stop, and so slippage and the result in R. Market regime (vpa_trading/regime.py, known
before the session) and time of day are added for every position. Rebuilt in full each run.

  python scripts/journal.py   -> results/journal.csv, reports/journal.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import regime  # noqa: E402
from risk_replay import positions  # noqa: E402


def plans():
    rows = []
    for f in sorted(Path("logs/live").glob("2026-*.jsonl")):
        for line in f.open():
            r = json.loads(line)
            if r.get("kind") == "filled" and r.get("fill_time"):
                tags = r.get("tags") or {}
                kz = tags.get("key_zone") or {}
                gex = r.get("gex") or {}
                rows.append({"sym": r["sym"], "fill_time": pd.Timestamp(r["fill_time"]).tz_localize("America/New_York"),
                             "tf": r.get("tf"), "family": r.get("family"), "type": r.get("type"), "plan_entry": r.get("entry"),
                             "plan_stop": r.get("stop"), "plan_qty": r.get("qty"), "fill": r.get("fill"), "gap": r.get("gap") or "-",
                             "key_zone_score": kz.get("score"), "near_wall": gex.get("near") or "",
                             "banks_level": bool(tags.get("banks_level")), "added": bool(tags.get("add"))})
    return pd.DataFrame(rows)


def main():
    p = positions()
    p["t_in"] = pd.to_datetime(p.t_in, utc=True).dt.tz_convert("America/New_York")
    pl = plans()
    j = []
    for _, r in p.iterrows():
        m = pl[(pl.sym == r.sym) & ((pl.fill_time - r.t_in).abs() <= pd.Timedelta(minutes=2))] if len(pl) else pl
        row = r.to_dict()
        if len(m):
            row.update(m.iloc[(m.fill_time - r.t_in).abs().argmin()].drop(["sym"]).to_dict())
        j.append(row)
    j = pd.DataFrame(j)
    side = np.where(j.side == "long", 1, -1)
    risk_ps = (j.plan_entry - j.plan_stop).abs()
    j["risk_usd"] = risk_ps * j.shares
    j["R"] = j.pnl / j.risk_usd
    j["slippage_R"] = (j.fill - j.plan_entry) * side / risk_ps * -1      # positive = filled better than planned
    j["hour_mst"] = j.t_in.dt.tz_convert("America/Denver").dt.hour
    for sym in ("SPY", "QQQ"):                                # refresh the two index files so today's regime is known
        try:
            from osc_oversold_test import daily
            fp = Path("data/daily") / f"{sym}.csv.gz"
            old = fp.read_bytes() if fp.exists() else None
            fp.unlink(missing_ok=True)
            try:
                daily(sym)
            except Exception:                                 # noqa: BLE001
                if old:
                    fp.write_bytes(old)
        except Exception:                                     # noqa: BLE001
            pass
    f = regime.build()
    f = f.replace({"True": 1.0, "False": 0.0, True: 1.0, False: 0.0})
    day = pd.to_datetime(j.day)
    for c in f.columns:
        j[c] = f[c].reindex(day).to_numpy()
    j.to_csv("results/journal.csv", index=False)
    L = ["# Trade journal\n", __doc__.split("\n\n")[1], "",
         f"{len(j)} positions, {j.day.min()} to {j.day.max()}; {j.R.notna().sum()} with a logged plan (R known). "
         f"Total P/L {j.pnl.sum():+,.0f}. Small samples: read these as a running record, not conclusions, until each "
         "row has 30+ trades.\n"]

    def tab(title, key, d):
        L.extend([f"\n## {title}\n", "| Group | Trades | Won | P/L | Average R |", "|---|--:|--:|--:|--:|"])
        for k, g in d.groupby(key, dropna=False):
            L.append(f"| {k} | {len(g)} | {100 * (g.pnl > 0).mean():.0f}% | {g.pnl.sum():+,.0f} | "
                     f"{g.R.mean():+.2f} |" if g.R.notna().any() else f"| {k} | {len(g)} | {100 * (g.pnl > 0).mean():.0f}% | {g.pnl.sum():+,.0f} | - |")
    tab("By strategy", "strat", j)
    k = j[j.R.notna()]
    tab("By timeframe (scanner and alert trades)", "tf", k)
    tab("By candle type", "type", k)
    tab("By gap timeframe at entry", "gap", k)
    tab("Key-level zone at entry", k.key_zone_score.notna().map({True: "at a zone", False: "no zone"}), k)
    tab("Add to an open position?", "added", k)
    tab("Hour of entry (MST)", "hour_mst", j)
    tab("Side", "side", j)
    tab("SPY vs its 200-day (as of the prior close)", j.spy_above200.astype(float).map({1.0: "above", 0.0: "below"}), j)
    tab("SPY volatility", pd.cut(j.vol20.astype(float), [0, 0.12, 0.2, 9], labels=["calm", "normal", "stressed"]), j)
    L += ["\n## Slippage (entry fill vs the planned entry, in R; negative = paid more than planned)\n",
          f"Average {k.slippage_R.mean():+.3f}R, median {k.slippage_R.median():+.3f}R, worst {k.slippage_R.min():+.2f}R over {len(k)} trades."]
    Path("reports/journal.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
