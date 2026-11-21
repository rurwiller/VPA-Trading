"""What happens after the Willard oscillator is below 10 on BOTH the daily and the weekly chart?

Daily bars from Alpaca (split-adjusted, since 2016) for the Mag 7, QQQ, SPY and 20 other large caps.
The weekly value on each day is what TradingView would show live that day: the current week's bar built from the
week's days so far (not the finished week, which would look ahead). Entry at that day's close; returns are
measured to the close 1, 5, 10 and 20 trading days later, in % (no costs; at these horizons costs are tiny).
"Episodes" counts only the first day of each run of signal days per stock, so one long oversold stretch
is not counted 15 times.

  python scripts/osc_oversold_test.py   -> reports/osc_oversold.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import alpaca  # noqa: E402
from vpa_trading.willard_osc import willard_osc  # noqa: E402

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
OTHERS = ["QQQ", "SPY", "AMD", "AVGO", "NFLX", "ORCL", "CRM", "ADBE", "INTC", "QCOM", "JPM", "XOM", "UNH",
          "COST", "WMT", "LLY", "BA", "DIS", "NKE", "HD", "CAT", "V"]
DIR = Path("data/daily")
H = (1, 5, 10, 20)
LVL = 10


def daily(sym):
    p = DIR / f"{sym}.csv.gz"
    if not p.exists():
        df = alpaca.fetch_bars(sym, "2016-01-01", (pd.Timestamp.now() - pd.Timedelta(days=1)).strftime("%Y-%m-%dT21:00:00Z"), timeframe="1Day",
                               regular_only=False)
        df.index = df.index.normalize()
        df.to_csv(p)
    return pd.read_csv(p, index_col=0, parse_dates=True)


def live_weekly_osc(d: pd.DataFrame) -> pd.Series:
    wk = d.index.to_period("W-FRI")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = pd.Series(np.nan, index=d.index)
    weeks = sorted(set(wk))
    full = d.groupby(wk).agg(agg)                        # finished weeks
    for w in weeks:
        days = d.index[wk == w]
        prior = full[full.index < w]
        for k in range(1, len(days) + 1):                # the week so far, as it looked on each day
            x = d.loc[days[:k]]
            part = pd.DataFrame({"open": [x.open.iat[0]], "high": [x.high.max()], "low": [x.low.min()],
                                 "close": [x.close.iat[-1]], "volume": [x.volume.sum()]}, index=[w])
            bars = pd.concat([prior.iloc[-400:], part])
            out[days[k - 1]] = willard_osc(bars)["osc"].iat[-1]
    return out


def study(sym):
    d = daily(sym)[["open", "high", "low", "close", "volume"]]
    do = willard_osc(d)["osc"]
    wo = live_weekly_osc(d)
    c = d.close
    f = pd.DataFrame({f"r{h}": (c.shift(-h) / c - 1) * 100 for h in H})
    f["daily"], f["weekly"], f["sym"] = do, wo, sym
    return f.iloc[60:]                                   # skip the oscillator's warm-up


def row(name, t):
    s = [f"{name} | {len(t)}"]
    for h in H:
        x = t[f"r{h}"].dropna()
        s.append(f"{x.mean():+.2f}% ({100 * (x > 0).mean():.0f}% up)" if len(x) else "-")
    x = t["r10"].dropna()
    s.append(f"{x.mean() / (x.std() / np.sqrt(len(x))):+.1f}" if len(x) > 2 else "-")
    return "| " + " | ".join(s) + " |"


def first_days(t):
    return t[t.groupby("sym")["flag"].transform(lambda s: s & ~s.shift(1, fill_value=False))]


def excess(t, flag):
    """Per-episode return minus that stock's own average over the same horizon (removes the bull-market drift)."""
    t = t.copy()
    for h in H:
        t[f"x{h}"] = t[f"r{h}"] - t.groupby("sym")[f"r{h}"].transform("mean")
    e = first_days(t.assign(flag=flag))
    cells = []
    for h in H:
        x = e[f"x{h}"].dropna()
        cells.append(f"{x.mean():+.2f}% (t {x.mean() / (x.std() / np.sqrt(len(x))):+.1f})")
    a, b = e[e.index < "2024-11-01"].x5.dropna(), e[e.index >= "2024-11-01"].x5.dropna()
    return cells, len(e), f"{a.mean():+.2f}% / {b.mean():+.2f}%"


def main():
    cache = Path("results/osc_oversold.pkl")
    if "--cached" in sys.argv and cache.exists():
        allf = pd.read_pickle(cache)
    else:
        allf = pd.concat([study(s) for s in MAG7 + OTHERS])
        cache.parent.mkdir(exist_ok=True)
        allf.to_pickle(cache)
    head = "| Group | Days | +1 day | +5 days | +10 days | +20 days | t (10 days) |\n|---|--:|--:|--:|--:|--:|--:|"
    L = ["# Daily AND weekly Willard oscillator below 10\n", __doc__.split("\n\n")[1], "",
         "Each return cell: average % move from that close (share of cases that were up). "
         "t above about 2 is unlikely to be luck; overlapping days inflate t, so the episode rows are the honest ones.\n"]
    for title, uni in (("Mag 7", MAG7), ("All 29 stocks and ETFs", MAG7 + OTHERS)):
        t = allf[allf.sym.isin(uni)].copy()
        both = (t.daily < LVL) & (t.weekly < LVL)
        L += [f"\n## {title}\n", head,
              row("Every day (baseline)", t),
              row("Daily below 10 (any weekly)", t[t.daily < LVL]),
              row("Weekly below 10 (any daily)", t[t.weekly < LVL]),
              row("**Both below 10**", t[both]),
              row("Both below 10, first day of each episode", first_days(t.assign(flag=both))),
              row("Daily below 10 only, first day of each episode", first_days(t.assign(flag=(t.daily < LVL) & ~(t.weekly < LVL))))]
        L += ["", "Better than usual? Each episode's return minus that stock's own average return over the same "
              "number of days (so the 2017-2026 bull market is taken out):", "",
              "| Episodes (first day) | Count | +1 day | +5 days | +10 days | +20 days | +5 days before / since Nov 2024 |",
              "|---|--:|--:|--:|--:|--:|--:|"]
        for lab, fl in (("Both below 10", both), ("Daily below 10, weekly not", (t.daily < LVL) & ~(t.weekly < LVL))):
            c, n, split = excess(t, fl)
            L.append(f"| {lab} | {n} | " + " | ".join(c) + f" | {split} |")
        L.append("")
        bt = t[both]
        L.append("Both below 10, by period: " + ", ".join(
            f"{y}: {len(g)} days, +10d {g.r10.mean():+.2f}%" for y, g in bt.groupby(bt.index.year)))
    t = allf[allf.sym.isin(MAG7)]
    ep = first_days(t.assign(flag=(t.daily < LVL) & (t.weekly < LVL)))
    L += ["\n## Every Mag 7 episode (first day)\n", "| Day | Stock | Daily | Weekly | +5 days | +10 days | +20 days |",
          "|---|---|--:|--:|--:|--:|--:|"]
    for dt, r in ep.sort_index().iterrows():
        L.append(f"| {dt:%Y-%m-%d} | {r.sym} | {r.daily:.1f} | {r.weekly:.1f} | {r.r5:+.1f}% | {r.r10:+.1f}% | {r.r20:+.1f}% |"
                 .replace("nan%", "-"))
    Path("reports/osc_oversold.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
