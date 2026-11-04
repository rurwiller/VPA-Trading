"""Exit test for the Willard 3.0 MTF signals on a 5-minute chart: same entries, different exits.

Every variant is a combination of settings the indicator already has (Backtest: Stop, Trail, Time Exit;
Take Profit: osc level, % target; Momentum Exit on/off, grace, price confirmation), so a winner can be
applied in TradingView directly. Choose on discovery (before 2024-11-01), believe the holdout.

  python scripts/willard_exit_test.py [SYM ...]   -> results/willard_exits/<SYM>.pkl, reports/willard_exits.md
  python scripts/willard_exit_test.py --report
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import research as R, willard_signals as W  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
from research_run import DEFAULT  # noqa: E402

OUT = Path("results/willard_exits")
SPLIT = pd.Timestamp("2024-11-01")
# name -> overrides of W.EXIT_DEFAULTS (indicator defaults: 2 ATR stop, trail 2.25/1.1, 5m osc TP at 95/5,
# momentum exit on, grace 0, prior-candle confirmation, no time exit, no % target)
CONFIGS = {
    "default": {},
    "mom off": dict(mom_on=False),
    "mom grace 3 bars": dict(mom_grace=3),
    "mom grace 6 bars": dict(mom_grace=6),
    "mom confirm EMA9": dict(mom_ema=True),
    "mom EMA9 + grace 3": dict(mom_ema=True, mom_grace=3),
    "mom off, time 3 bars": dict(mom_on=False, max_bars=3),
    "mom off, time 6 bars": dict(mom_on=False, max_bars=6),
    "mom off, time 12 bars": dict(mom_on=False, max_bars=12),
    "TP osc 10": dict(tp_osc=10.0),
    "TP osc 20": dict(tp_osc=20.0),
    "TP 0.5% (no osc TP)": dict(tp_osc=None, tp_pct=0.5),
    "TP osc 5 + 0.3%": dict(tp_pct=0.3),
    "stop 1.5 ATR": dict(stop_atr=1.5),
    "stop 3 ATR": dict(stop_atr=3.0),
    "trail off": dict(trail_act=None),
    "trail 1.0 / 1.0": dict(trail_act=1.0, trail_dist=1.0),
    "trail 1.5 / 1.0": dict(trail_act=1.5, trail_dist=1.0),
    "mom off, time 6, trail 1/1": dict(mom_on=False, max_bars=6, trail_act=1.0, trail_dist=1.0),
    "mom off, time 12, TP 0.5%": dict(mom_on=False, max_bars=12, tp_osc=None, tp_pct=0.5),
    "mom EMA9+grace 3, trail off": dict(mom_ema=True, mom_grace=3, trail_act=None),
    "mom off, TP osc 20, time 12": dict(mom_on=False, tp_osc=20.0, max_bars=12),
}


def run_symbol(sym: str) -> str:
    m1 = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1)
    x, bars = W.inputs_5m_chart(s)
    out = []
    for name, cfg in CONFIGS.items():
        tr, _ = W.run(s, x, bars=bars, step=pd.Timedelta(minutes=5), exits=cfg)
        out.append(tr[["rule", "dir", "time", "pnl", "reason", "entry_i", "exit_i"]].assign(cfg=name))
    t = pd.concat(out, ignore_index=True)
    t["sym"] = sym
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(t)} trades over {len(CONFIGS)} exit settings"


def stats(g: pd.DataFrame) -> dict:
    n = len(g)
    if not n:
        return {"n": 0}
    w, l = g.pnl[g.pnl > 0], g.pnl[g.pnl <= 0]
    return {"n": n, "win%": round(len(w) / n * 100, 1), "avg%": round(g.pnl.mean(), 4),
            "PF": round(w.sum() / -l.sum(), 2) if l.sum() < 0 else np.nan,
            "2se": round(2 * g.pnl.std() / np.sqrt(n), 4), "bars": round((g.exit_i - g.entry_i).mean(), 1)}


def table(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in CONFIGS:
        g = t[t.cfg == name]
        r = {"exit setting": name}
        for per, gg in (("d", g[g.time < SPLIT]), ("h", g[g.time >= SPLIT])):
            r.update({f"{k}_{per}": v for k, v in stats(gg).items()})
        rows.append(r)
    return pd.DataFrame(rows)


def report() -> None:
    t = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    L = ["# Willard 3.0 exits test (5-minute chart, same entries)\n",
         f"{', '.join(sorted(t.sym.unique()))}, {t.time.min():%Y-%m-%d} to {t.time.max():%Y-%m-%d}. "
         f"`_d` = before {SPLIT:%Y-%m-%d} (choose here), `_h` = after (check here). avg% = stock % per trade after "
         "0.02% costs; bars = average 5m bars held.\n",
         "## All 7 rules pooled\n", table(t).to_markdown(index=False),
         "\n## Color Flip only\n", table(t[t.rule == "Color Flip"]).to_markdown(index=False)]
    for rule in W.RULES:
        if rule == "Color Flip":
            continue
        L.append(f"\n## {rule}\n")
        L.append(table(t[t.rule == rule]).to_markdown(index=False))
    Path("reports/willard_exits.md").write_text("\n".join(L) + "\n")
    print("wrote reports/willard_exits.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or DEFAULT):
                print(msg, flush=True)
    report()
