"""Multi-timeframe oscillator rule on Alpaca 1m bars (run scripts/alpaca_pull.py first).

Rule: slow (default 1h, closed bars only) and fast (default 5m) oscillators both at an
extreme -> both high = short, both low = long. Prints, per time split, trades / win / avg R
after costs, both for the ATR stop/target race and the oscillator-midline exit.

Usage:
  python scripts/mtf_backtest.py                       # default levels, all 7 tickers
  python scripts/mtf_backtest.py --grid                # sweep levels; pick on first half, check on second
  python scripts/mtf_backtest.py --trigger flip --lvl-slow 20 --lvl-fast 12
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import mtf  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402

DEFAULT = ["TSLA", "SPY", "QQQ", "AAPL", "NVDA", "AMD", "META"]


def prepare(sym: str, slow_iv: str, fast_iv: str, data_dir: str):
    b1 = load_bars_file(Path(data_dir) / f"{sym}-1m.csv.gz")
    slow, fast = mtf.osc_on(b1, slow_iv), mtf.osc_on(b1, fast_iv)
    fast_close = fast.index + pd.Timedelta(fast_iv.replace("m", "min"))
    slow_at_fast = mtf.closed_value(slow, pd.DatetimeIndex(fast_close))
    slow_at_fast.index = fast.index
    return fast, slow_at_fast


def run(prep: dict, a) -> pd.DataFrame:
    out = []
    for sym, (fast, slow_v) in prep.items():
        lg, sh = mtf.signals(fast, slow_v, a.lvl_slow, a.lvl_fast, a.trigger, a.within)
        t = mtf.backtest(fast, lg, sh, a.k, a.rr, a.cost_bps, a.cooldown, exit_level=a.exit_level)
        out.append(t.assign(sym=sym))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def stats(t: pd.DataFrame, col: str) -> str:
    if len(t) < 2:
        return f"n={len(t):4}"
    r = t[col] - t.cost_r
    se = r.std(ddof=1) / len(r) ** 0.5
    win = (t.real_outcome == "target").mean() if col == "real_r" else (r > 0).mean()
    return f"n={len(t):4} win {win:5.1%} avgR {r.mean():+.3f} (+/-{2 * se:.3f})"


def show(t: pd.DataFrame, split: pd.Timestamp, label: str) -> None:
    print(f"\n{label}")
    for name, s in (("all", t), ("first half", t[t.time < split]), ("second half", t[t.time >= split])):
        print(f"  {name:12} race: {stats(s, 'real_r')}   | midline exit: {stats(s, 'rule_r')}")
    for side in ("long", "short"):
        print(f"    {side:6}     race: {stats(t[t.side == side], 'real_r')}   | midline exit: {stats(t[t.side == side], 'rule_r')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=DEFAULT)
    ap.add_argument("--data-dir", default="data/alpaca")
    ap.add_argument("--slow", default="1h")
    ap.add_argument("--fast", default="5m")
    ap.add_argument("--lvl-slow", type=float, default=20, help="slow osc <= L long, >= 100-L short")
    ap.add_argument("--lvl-fast", type=float, default=10, help="fast osc <= L long, >= 100-L short")
    ap.add_argument("--trigger", choices=["immediate", "flip"], default="immediate")
    ap.add_argument("--within", type=int, default=3)
    ap.add_argument("--k", type=float, default=1.5)
    ap.add_argument("--rr", type=float, default=2.0)
    ap.add_argument("--cost-bps", type=float, default=2.0)
    ap.add_argument("--cooldown", type=int, default=4, help="fast bars between same-side signals")
    ap.add_argument("--exit-level", type=float, default=50)
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--save", help="write the trade list to this CSV")
    a = ap.parse_args()

    prep = {s: prepare(s, a.slow, a.fast, a.data_dir) for s in a.symbols}
    first = min(f.index[0] for f, _ in prep.values())
    last = max(f.index[-1] for f, _ in prep.values())
    split = first + (last - first) / 2
    print(f"{len(prep)} tickers, {first:%Y-%m-%d}..{last:%Y-%m-%d}, split at {split:%Y-%m-%d}; "
          f"costs {a.cost_bps} bps; avg R is per trade in multiples of risk, +/- ~95% noise band")

    if not a.grid:
        t = run(prep, a)
        show(t, split, f"{a.slow}+{a.fast} {a.trigger}: slow<= {a.lvl_slow:g}/>= {100 - a.lvl_slow:g}, "
                       f"fast<= {a.lvl_fast:g}/>= {100 - a.lvl_fast:g}")
        if a.save:
            t.to_csv(a.save, index=False)
        return

    rows = []
    for trig, ls, lf in itertools.product(("immediate", "flip"), (10, 20, 30, 40), (5, 10, 15, 25)):
        a.trigger, a.lvl_slow, a.lvl_fast = trig, ls, lf
        t = run(prep, a)
        for half, s in (("first", t[t.time < split]), ("second", t[t.time >= split])):
            r, m = s.real_r - s.cost_r, s.rule_r - s.cost_r
            rows.append(dict(trigger=trig, slow=ls, fast=lf, half=half, n=len(s),
                             race_R=r.mean(), midline_R=m.mean()))
    g = pd.DataFrame(rows).pivot_table(index=["trigger", "slow", "fast"], columns="half",
                                       values=["n", "race_R", "midline_R"])
    print("\nGrid (choose on the first half, then see whether the second half agrees):")
    print(g.round(3).to_string())


if __name__ == "__main__":
    main()
