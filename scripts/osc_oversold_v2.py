"""Daily + weekly Willard oscillator both below 10, refined with fair value gaps and the 1-hour oscillator,
on a wider list of stocks (Mag 7 + ~70 other liquid large caps, growth names and ETFs).

Setup: the first day of each run where the daily AND the live weekly oscillator close below 10 (the weekly value is
the current week built from its days so far, as TradingView shows it live).
Variants:
  base        buy that day's close.
  daily gap   ...only if that day's low dipped into an unfilled bullish daily fair value gap (3-candle gap,
              at least 0.1 x the 14-day ATR) and the close held above the gap's bottom.
  weekly gap  same with an unfilled bullish weekly gap (from finished weeks).
  1h oversold ...only if the 1-hour oscillator is also below 10 at that close (all three oversold).
  1h turn     wait: buy at the close of the first 1-hour bar in the next 5 days where the 1-hour oscillator
              crosses up through 20 (momentum leaving oversold). No cross -> no trade.
  gap + turn  either gap, then wait for the 1-hour turn.
Returns from the entry price to the close 5, 10 and 20 trading days after the entry day, minus that stock's own
average move over the same number of days (taking out the bull market). No costs (tiny at these horizons).
1-hour bars are built from 30-minute regular-session bars, starting 9:30.

  python scripts/osc_oversold_v2.py [--cached]   -> reports/osc_oversold_v2.md
"""
from __future__ import annotations

import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import alpaca  # noqa: E402
from vpa_trading.willard_osc import willard_osc  # noqa: E402
from osc_oversold_test import daily  # noqa: E402

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
OTHERS = ["QQQ", "SPY", "IWM", "DIA", "SMH", "XLK", "XLF", "XLE",
          "AMD", "AVGO", "NFLX", "ORCL", "CRM", "ADBE", "INTC", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "TXN", "MRVL",
          "IBM", "NOW", "PANW", "CRWD", "SNOW", "SHOP", "UBER", "ABNB", "PYPL", "COIN", "PLTR", "ROKU", "SMCI",
          "JPM", "GS", "MS", "BAC", "WFC", "C", "V", "MA", "AXP",
          "XOM", "CVX", "UNH", "LLY", "PFE", "MRK", "ABBV", "JNJ",
          "COST", "WMT", "HD", "LOW", "TGT", "MCD", "SBUX", "NKE", "KO", "PEP", "PG", "DIS", "BA", "CAT", "DE", "GE",
          "F", "GM"]
H = (5, 10, 20)
LVL = 10
SPLIT = pd.Timestamp("2024-11-01")
END = (pd.Timestamp.now() - pd.Timedelta(days=1)).strftime("%Y-%m-%dT21:00:00Z")


def hourly(sym):
    p = Path("data/m30") / f"{sym}.csv.gz"
    if not p.exists():
        alpaca.fetch_bars(sym, "2016-01-01", END, timeframe="30Min").to_csv(p)
    m = pd.read_csv(p, index_col=0, parse_dates=True)
    d = m.index.normalize()
    bucket = ((m.index - d) / pd.Timedelta(minutes=1) - 570) // 60
    key = d + pd.to_timedelta(570 + bucket * 60 + 60, unit="min")          # the hour bar's closing time
    key = key.where(key <= d + pd.Timedelta(hours=16), d + pd.Timedelta(hours=16))
    h = m.groupby(key).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                           close=("close", "last"), volume=("volume", "sum"))
    h["osc"] = willard_osc(h)["osc"]
    return h


def bull_gaps(b):
    """Bullish 3-candle gaps on bars b: list of (formed index position, bottom, top)."""
    atr = (b.high - b.low).rolling(14).mean()
    h2 = b.high.shift(2)
    ok = (b.low > h2) & ((b.low - h2) >= 0.1 * atr)
    return [(i, h2.iat[i], b.low.iat[i]) for i in np.flatnonzero(ok.to_numpy())]


def at_gap(lows, closes, gaps, k, formed_before):
    """Did bar k's low dip into an unfilled gap (formed before k) and close above its bottom?"""
    for i, bot, top in gaps:
        if not formed_before(i, k):
            continue
        prior = lows[i + 1:k]            # only bars before k (a numpy-int k once made this look at the future)
        if len(prior) and prior.min() < bot:                                # already filled
            continue
        if lows[k] <= top and closes[k] >= bot:
            return True
    return False


def study(sym):
    try:
        d = daily(sym)[["open", "high", "low", "close", "volume"]]
        h = hourly(sym)
    except Exception as e:                                                  # noqa: BLE001
        print(sym, "skipped:", e, flush=True)
        return None
    do = willard_osc(d)["osc"]
    wk = d.index.to_period("W-FRI")
    full = d.groupby(wk).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                             close=("close", "last"), volume=("volume", "sum"))
    wo = pd.Series(np.nan, index=d.index)
    for i in np.flatnonzero((do < LVL).to_numpy()):                         # live weekly only where it matters
        day, w = d.index[i], wk[i]
        x = d[(wk == w) & (d.index <= day)]
        part = pd.DataFrame({"open": [x.open.iat[0]], "high": [x.high.max()], "low": [x.low.min()],
                             "close": [x.close.iat[-1]], "volume": [x.volume.sum()]}, index=[w])
        wo.iat[i] = willard_osc(pd.concat([full[full.index < w].iloc[-150:], part]))["osc"].iat[-1]
    flag = ((do < LVL) & (wo < LVL)).to_numpy()
    first = flag & ~np.r_[False, flag[:-1]]
    dgaps, wgaps = bull_gaps(d), bull_gaps(full)
    dl, dc = d.low.to_numpy(), d.close.to_numpy()
    wl = full.low.to_numpy()
    c = d.close.to_numpy()
    avg = {n: np.nanmean(c[n:] / c[:-n] - 1) * 100 for n in H}
    hidx = h.index
    rows = []
    for i in np.flatnonzero(first):
        if i < 60:
            continue
        day = d.index[i]
        wpos = full.index.get_loc(wk[i])
        wk_lows = np.r_[wl[:wpos], d.low[(wk == wk[i]) & (d.index <= day)].min()]
        wk_close = np.r_[full.close.to_numpy()[:wpos], dc[i]]
        r = {"sym": sym, "day": day, "daily": do.iat[i], "weekly": wo.iat[i],
             "dgap": at_gap(dl, dc, dgaps, i, lambda g, k: g < k),
             "wgap": at_gap(wk_lows, wk_close, [g for g in wgaps if g[0] < wpos], wpos, lambda g, k: True)}
        close_t = day + pd.Timedelta(hours=16)
        r["h1"] = h.osc[hidx <= close_t].iat[-1] if (hidx <= close_t).any() else np.nan
        # entries: base at the day's close; 1h turn = first cross up through 20 within the next 5 days
        entries = {"base": (i, c[i])}
        if i + 5 < len(d):
            win = h[(hidx > close_t) & (hidx <= d.index[i + 5] + pd.Timedelta(hours=16))]
            prev = h.osc[hidx <= close_t].iat[-1] if (hidx <= close_t).any() else np.nan
            o = np.r_[prev, win.osc.to_numpy()]
            cross = np.flatnonzero((o[1:] > 20) & (o[:-1] <= 20))
            if len(cross):
                t = win.index[cross[0]]
                entries["turn"] = (d.index.get_indexer([t.normalize()])[0], win.close.iat[cross[0]])
        for name, (k, px) in entries.items():
            for n in H:
                r[f"{name}{n}"] = (c[k + n] / px - 1) * 100 - avg[n] if k + n < len(c) else np.nan
        rows.append(r)
    print(sym, len(rows), flush=True)
    return pd.DataFrame(rows)


def line(name, e, col="base"):
    if not len(e):
        return f"| {name} | 0 | - | - | - | - | - |"
    s = [f"| {name} | {int(e[f'{col}5'].notna().sum())}"]
    for n in H:
        x = e[f"{col}{n}"].dropna()
        s.append(f"{x.mean():+.2f}% (t {x.mean() / (x.std() / np.sqrt(len(x))):+.1f}, {100 * (x > 0).mean():.0f}% beat)"
                 if len(x) > 2 else "-")
    a, b = e[e.day < SPLIT][f"{col}5"].dropna(), e[e.day >= SPLIT][f"{col}5"].dropna()
    s.append(f"{a.mean():+.2f}% / {b.mean():+.2f}% ({len(a)}/{len(b)})")
    return " | ".join(s) + " |"


def main():
    cache = Path("results/osc_oversold_v2.pkl")
    if "--cached" in sys.argv and cache.exists():
        ev = pd.read_pickle(cache)
    else:
        with Pool(4) as p:
            ev = pd.concat([x for x in p.map(study, MAG7 + OTHERS) if x is not None], ignore_index=True)
        cache.parent.mkdir(exist_ok=True)
        ev.to_pickle(cache)
    L = ["# Daily + weekly oscillator below 10, with gaps and the 1-hour oscillator\n", __doc__.split("\n\n")[1], "",
         "Each cell: average return beyond the stock's usual move (t; above about 2 is unlikely to be luck; "
         "share of setups that beat the usual move). Last column: the +5-day figure before / since Nov 2024 (counts).\n"]
    head = ["| Variant | Setups | +5 days | +10 days | +20 days | +5d before / since Nov 2024 |", "|---|--:|--:|--:|--:|--:|"]
    for title, e in (("Mag 7", ev[ev.sym.isin(MAG7)]), ("Everything else (no Mag 7)", ev[~ev.sym.isin(MAG7)]),
                     (f"All {ev.sym.nunique()} symbols", ev)):
        g = e.dgap | e.wgap
        L += [f"\n## {title}\n"] + head + [
            line("base: buy the close", e),
            line("daily gap", e[e.dgap]),
            line("weekly gap", e[e.wgap]),
            line("either gap", e[g]),
            line("no gap", e[~g]),
            line("1h also below 10", e[e.h1 < LVL]),
            line("1h not below 10", e[~(e.h1 < LVL)]),
            line("1h turn (wait for cross above 20)", e, "turn"),
            line("either gap + 1h turn", e[g], "turn"),
            line("daily gap + 1h turn", e[e.dgap], "turn")]
    g = ev[ev.dgap].dropna(subset=["base10"])
    m = g.groupby(g.day.dt.to_period("M")).base10.mean()
    L += ["\n## The daily-gap check, after fixing a look-ahead bug\n",
          "An earlier version of this report showed the daily gap as a huge edge (+6% in 10 days, 88% beating the usual move). "
          "That was a bug: the 'gap still unfilled' test also looked at prices AFTER the setup day, so it kept only gaps "
          "that price never went back below. Fixed on Nov 21 2026; the numbers in this report are the corrected ones.",
          f"Averaging by month first: {len(m)} months, +10 days "
          f"{m.mean():+.2f}% (t {m.mean() / (m.std() / np.sqrt(len(m))):+.1f}). Median setup {g.base10.median():+.2f}%, "
          f"worst {g.base10.min():+.1f}%.",
          "\n## Every daily-gap setup\n", "| Day | Stock | Daily | Weekly | +5 days | +10 days | +20 days |",
          "|---|---|--:|--:|--:|--:|--:|"]
    for _, r in ev[ev.dgap].sort_values("day").iterrows():
        L.append(f"| {r.day:%Y-%m-%d} | {r.sym} | {r.daily:.1f} | {r.weekly:.1f} | {r.base5:+.1f}% | {r.base10:+.1f}% | "
                 f"{r.base20:+.1f}% |".replace("+nan%", "-"))
    Path("reports/osc_oversold_v2.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
