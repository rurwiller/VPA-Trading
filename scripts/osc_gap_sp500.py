"""The best oversold setup on every current S&P 500 stock: daily AND live weekly Willard oscillator below 10, and that
day's low dips into an unfilled bullish daily fair value gap with the close holding above the gap's bottom
(rules exactly as in scripts/osc_oversold_v2.py "daily gap"). Buy that day's close.

Returns: to the close 5, 10 and 20 trading days later, minus that stock's own average move over the same days.
Also split by market regime on the setup day, to check the bear-market worry:
  SPY above / below its 200-day average, and SPY's last 20 days up / down.
Caveat: today's S&P 500 members (survivorship bias: stocks that crashed out of the index are missing, which
flatters a buy-the-dip rule). Members list from the public datasets/s-and-p-500-companies file.

  python scripts/osc_gap_sp500.py [--cached]   -> reports/osc_gap_sp500.md
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading.willard_osc import willard_osc  # noqa: E402
from osc_oversold_test import daily  # noqa: E402
from osc_oversold_v2 import at_gap, bull_gaps  # noqa: E402

H = (5, 10, 20)
LVL = 10
SPLIT = pd.Timestamp("2024-11-01")


def members():
    return pd.read_csv("data/sp500/constituents.csv").Symbol.tolist()


def study(sym):
    try:
        d = daily(sym)[["open", "high", "low", "close", "volume"]]
    except Exception as e:                                                  # noqa: BLE001
        return sym, str(e)
    if len(d) < 200:
        return sym, "short history"
    do = willard_osc(d)["osc"]
    wk = d.index.to_period("W-FRI")
    full = d.groupby(wk).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                             close=("close", "last"), volume=("volume", "sum"))
    dgaps = bull_gaps(d)
    dl, dc = d.low.to_numpy(), d.close.to_numpy()
    avg = {n: np.nanmean(dc[n:] / dc[:-n] - 1) * 100 for n in H}
    wo = pd.Series(np.nan, index=d.index)
    rows, prev_flag = [], False
    for i in range(60, len(d)):
        flag = False
        if do.iat[i] < LVL:
            day, w = d.index[i], wk[i]
            x = d[(wk == w) & (d.index <= day)]
            part = pd.DataFrame({"open": [x.open.iat[0]], "high": [x.high.max()], "low": [x.low.min()],
                                 "close": [x.close.iat[-1]], "volume": [x.volume.sum()]}, index=[w])
            wo.iat[i] = willard_osc(pd.concat([full[full.index < w].iloc[-150:], part]))["osc"].iat[-1]
            flag = wo.iat[i] < LVL
        if flag and not prev_flag and at_gap(dl, dc, dgaps, i, lambda g, k: g < k):
            r = {"sym": sym, "day": d.index[i], "daily": do.iat[i], "weekly": wo.iat[i], "close": dc[i]}
            for n in H:
                r[f"r{n}"] = (dc[i + n] / dc[i] - 1) * 100 if i + n < len(dc) else np.nan
                r[f"x{n}"] = r[f"r{n}"] - avg[n] if i + n < len(dc) else np.nan
            r["dd10"] = (dl[i + 1:i + 11].min() / dc[i] - 1) * 100 if i + 1 < len(dc) else np.nan
            rows.append(r)
        prev_flag = flag
    return sym, pd.DataFrame(rows)


def cell(x):
    x = x.dropna()
    if len(x) < 3:
        return "-"
    return f"{x.mean():+.2f}% (t {x.mean() / (x.std() / np.sqrt(len(x))):+.1f}, {100 * (x > 0).mean():.0f}%)"


def table(groups):
    L = ["| Group | Setups | +5 days | +10 days | +20 days | Raw +10 days (up %) | Avg worst dip in 10 days |",
         "|---|--:|--:|--:|--:|--:|--:|"]
    for name, e in groups:
        L.append(f"| {name} | {int(e.x5.notna().sum())} | {cell(e.x5)} | {cell(e.x10)} | {cell(e.x20)} | "
                 f"{e.r10.mean():+.2f}% ({100 * (e.r10.dropna() > 0).mean():.0f}%) | {e.dd10.mean():+.1f}% |")
    return L


def main():
    cache = Path("results/osc_gap_sp500.pkl")
    if "--cached" in sys.argv and cache.exists():
        ev = pd.read_pickle(cache)
    else:
        syms = members()
        for s in syms:                                                      # download serially (rate limit)
            for a in range(4):
                try:
                    daily(s)
                    break
                except Exception as e:                                      # noqa: BLE001
                    if "429" in str(e):
                        time.sleep(20)
                    else:
                        print(s, "no data:", e, flush=True)
                        break
        with Pool(4) as p:
            res = p.map(study, syms)
        ev = pd.concat([r for _, r in res if isinstance(r, pd.DataFrame) and len(r)], ignore_index=True)
        print("skipped:", [s for s, r in res if not isinstance(r, pd.DataFrame)])
        cache.parent.mkdir(exist_ok=True)
        ev.to_pickle(cache)
    spy = daily("SPY").close
    ma = spy.rolling(200).mean()
    ev["spy_above200"] = ev.day.map(spy > ma)
    ev["spy_20d_up"] = ev.day.map(spy > spy.shift(20))
    L = ["# Oversold daily + weekly oscillator at a daily gap: all S&P 500 stocks\n", __doc__.split("\n\n")[1],
         "", __doc__.split("\n\n")[2], "",
         "Cells: average return beyond the stock's usual move (t; above about 2 is unlikely to be luck; share that beat "
         "the usual move). 'Worst dip' = lowest low in the next 10 days vs the entry close.\n"]
    L += ["## Overall\n"] + table([
        ("All setups", ev),
        ("Before Nov 2024", ev[ev.day < SPLIT]),
        ("Since Nov 2024", ev[ev.day >= SPLIT])])
    L += ["\n## By market regime on the setup day\n"] + table([
        ("SPY above its 200-day", ev[ev.spy_above200 == True]),          # noqa: E712
        ("SPY below its 200-day", ev[ev.spy_above200 == False]),         # noqa: E712
        ("SPY up over the last 20 days", ev[ev.spy_20d_up == True]),     # noqa: E712
        ("SPY down over the last 20 days", ev[ev.spy_20d_up == False]),  # noqa: E712
        ("SPY below 200-day AND down 20 days", ev[(ev.spy_above200 == False) & (ev.spy_20d_up == False)])])  # noqa: E712
    L += ["\n## By year\n"] + table([(str(y), g) for y, g in ev.groupby(ev.day.dt.year)])
    m = ev.dropna(subset=["x10"]).groupby(ev.day.dt.to_period("M")).x10.mean()
    L += ["", f"Averaging by month first (setups bunch up in selloffs): {len(m)} months, +10 days {m.mean():+.2f}% "
          f"(t {m.mean() / (m.std() / np.sqrt(len(m))):+.1f}).",
          f"\nSetups per year: {ev.groupby(ev.day.dt.year).size().to_dict()}",
          f"\nSPY today: {spy.iat[-1]:.2f}, 200-day average {ma.iat[-1]:.2f}, 20 days ago {spy.iat[-21]:.2f}.",
          "\n## Live setups (last 20 trading days)\n", "| Day | Stock | Daily | Weekly | Close | Since then |", "|---|---|--:|--:|--:|--:|"]
    recent = ev[ev.day >= spy.index[-20]].sort_values("day")
    for _, r in recent.iterrows():
        last = daily(r.sym).close.iat[-1]
        L.append(f"| {r.day:%Y-%m-%d} | {r.sym} | {r.daily:.1f} | {r.weekly:.1f} | {r.close:.2f} | {(last / r.close - 1) * 100:+.1f}% |")
    Path("reports/osc_gap_sp500.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
