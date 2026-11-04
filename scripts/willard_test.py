"""Replay the Willard 3.0 MTF signal system on every ticker, add Fibonacci / FVG context, report.

  python scripts/willard_test.py [SYM ...]
    -> results/willard/<SYM>_{trades,setups,fib}.pkl and reports/willard.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import fib, research as R, willard_signals as W  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
from research_run import DEFAULT  # noqa: E402

OUT = Path("results/willard")
SPLIT = pd.Timestamp("2024-11-01")
PER_SYMBOL = {"TSLA": "Color Flip", "AMD": "Fire/Ice"}   # from the script's default per-symbol list


def context(s, i: np.ndarray, d: np.ndarray, fstates: dict) -> pd.DataFrame:
    """Fib (1h and daily) and FVG context at 1m bar indices i for trade direction d."""
    px = s.m1.close.to_numpy()[i]
    a5 = s.atr5_clock[i]
    parts = [fib.features(st.iloc[i].reset_index(drop=True), px, a5, d, tag) for tag, st in fstates.items()]
    f = R.features(s, i)
    bull = (f[[f"near_bull_fvg_{tf}" for tf in ("15m", "1h")]].max(axis=1) == 1).to_numpy()
    bear = (f[[f"near_bear_fvg_{tf}" for tf in ("15m", "1h")]].max(axis=1) == 1).to_numpy()
    out = pd.concat(parts, axis=1)
    out["fvg_fit"] = np.where(d > 0, bull, bear)
    out["osc5"] = f["osc_5m"].to_numpy()
    out["adx15"] = f["adx_15m"].to_numpy()
    return out


def run_symbol(sym: str) -> str:
    m1 = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1)
    x = W.inputs(s)
    tr, st = W.run(s, x)
    fstates = {"1h": fib.state(fib.legs(s.tf["1h"], 3), s.clock),
               "D": fib.state(fib.legs(fib.daily_bars(s.m1), 2), s.clock)}
    tr = pd.concat([tr.reset_index(drop=True),
                    context(s, tr.entry_i.to_numpy(), tr.dir.to_numpy(), fstates)], axis=1)
    tr["sym"] = sym
    st["sym"] = sym
    ev = pd.concat([fib.gp_touch_events(s, fs, tag) for tag, fs in fstates.items()], ignore_index=True)
    ev = pd.concat([ev, R.outcomes(s, ev)], axis=1)
    ctx = context(s, ev.i.to_numpy(), ev.dir.to_numpy(), fstates)
    ev = pd.concat([ev, ctx[["fvg_fit", "osc5", "adx15"]]], axis=1)
    ev["time"] = pd.to_datetime(s.clock[ev.i.to_numpy()])
    OUT.mkdir(parents=True, exist_ok=True)
    tr.to_pickle(OUT / f"{sym}_trades.pkl")
    st.to_pickle(OUT / f"{sym}_setups.pkl")
    ev.to_pickle(OUT / f"{sym}_fib.pkl")
    return f"{sym}: {len(st)} setups, {len(tr)} trades, {len(ev)} fib events"


def stats(t: pd.DataFrame) -> dict:
    n = len(t)
    if not n:
        return {"n": 0}
    gw, gl = t.pnl[t.pnl > 0].sum(), -t.pnl[t.pnl <= 0].sum()
    return {"n": n, "win%": round((t.pnl > 0).mean() * 100, 1), "avg%": round(t.pnl.mean(), 3),
            "net%": round(t.pnl.sum(), 1), "PF": round(gw / gl, 2) if gl > 0 else np.nan,
            "2se": round(2 * t.pnl.std() / np.sqrt(n), 3) if n > 1 else np.nan}


def two(t: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for key, g in t.groupby(by, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        r = dict(zip(by, key))
        for per, gg in (("d", g[g.time < SPLIT]), ("h", g[g.time >= SPLIT])):
            r.update({f"{k}_{per}": v for k, v in stats(gg).items()})
        rows.append(r)
    return pd.DataFrame(rows)


def md(t: pd.DataFrame) -> str:
    return t.to_markdown(index=False) if len(t) else "(none)"


def report() -> None:
    import research_report as rr
    tr = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*_trades.pkl"))], ignore_index=True)
    st = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*_setups.pkl"))], ignore_index=True)
    fe = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*_fib.pkl"))], ignore_index=True)
    tr["labeled"] = np.where(tr.factors >= 1, "label (>=1 factor)", "no factor")
    L = ["# Willard 3.0 MTF signals: replay, factors, Fibonacci and FVG\n",
         f"{len(st)} Ready setups and {len(tr)} trades (all 7 rules) on {', '.join(sorted(tr.sym.unique()))}, "
         f"{tr.time.min():%Y-%m-%d} to {tr.time.max():%Y-%m-%d}. `_d` = before {SPLIT:%Y-%m-%d}, `_h` = after.",
         "Indicator defaults (2x ATR(5m) stop, trail, 5m-osc take profit, momentum exit, 0.02% costs). "
         "win% = trades with pnl > 0 after costs; avg% / net% = stock % move per trade / summed (not option P&L).\n",
         "## 1. Every rule, all trades (the scorecard view)\n", md(two(tr, ["rule"])),
         "\n## 2. Every rule, only trades that would show a CALL/PUT label (>= 1 factor)\n",
         md(two(tr[tr.factors >= 1], ["rule"])),
         "\n## 3. Color Flip (TSLA's rule) by ticker\n", md(two(tr[tr.rule == "Color Flip"], ["sym"])),
         "\n## 4. Best rule per ticker? Each ticker x rule (choose on _d, check _h)\n",
         md(two(tr, ["sym", "rule"])),
         "\n## 5. Factors (Color Flip, all tickers): with vs without\n"]
    cf = tr[tr.rule == "Color Flip"]
    for f_ in ("f_st", "f_em", "f_sp", "f_vp"):
        L.append(f"\n**{f_}**\n")
        L.append(md(two(cf, [f_])))
    L.append("\n**number of factors**\n")
    L.append(md(two(cf, ["factors"])))
    L.append("\n## 6. Fibonacci and FVG at the entry (Color Flip and all rules pooled)\n")
    L.append("fibX_gp = entry inside the golden pocket (0.618-0.65) of the last X swing, on the side that fits the "
             "trade; fibX_retr = within 0.25 ATR(5m) of any retracement that fits; fibX_ext = at a fitting "
             "1.272/1.618 extension; fvg_fit = an unfilled 15m/1h FVG on the trade's side within 0.25 ATR.\n")
    tr["fib_any"] = tr.fib1h_any | tr.fibD_any
    tr["fib_and_fvg"] = tr.fib_any & tr.fvg_fit
    tr["gp_and_fvg"] = (tr.fib1h_gp | tr.fibD_gp) & tr.fvg_fit
    for c in ["fib1h_gp", "fib1h_retr", "fib1h_ext", "fibD_gp", "fibD_retr", "fibD_ext", "fvg_fit", "fib_any",
              "fib_and_fvg", "gp_and_fvg"]:
        L.append(f"\n**{c}**\n")
        L.append(md(two(tr[tr.rule == "Color Flip"], [c])))
        L.append("\nAll rules pooled:\n")
        L.append(md(two(tr, [c])))
    L.append("\n## 7. Golden pocket on its own: first touch of each swing's 0.618-0.65 zone\n")
    L.append("fade = bounce, cont = break through. Same outcome columns as reports/research.md "
             "(win15 = up after 15 min, pct_win = +0.5% before -0.3%, atr_R = 1.5 ATR stop / 2R).\n")
    fe["period"] = np.where(fe.time < SPLIT, "disc", "hold")
    fe["osc5_fits"] = np.where(((fe.dir > 0) & (fe.osc5 <= 20)) | ((fe.dir < 0) & (fe.osc5 >= 80)), "yes", "no")
    fe["fvg_fits"] = np.where(fe.fvg_fit, "yes", "no")
    fe["osc_and_fvg"] = np.where((fe.osc5_fits == "yes") & fe.fvg_fit, "yes", "no")
    for by in (["variant", "mode"], ["variant", "mode", "osc5_fits"], ["variant", "mode", "fvg_fits"],
               ["variant", "mode", "osc_and_fvg"]):
        L.append(f"\n**by {', '.join(by)}**\n")
        L.append(rr.md(rr.two_period(fe, by)))
    Path("reports/willard.md").write_text("\n".join(L) + "\n")
    print("wrote reports/willard.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or DEFAULT):
                print(msg, flush=True)
    report()
