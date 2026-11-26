"""The SOXL fixed-dollar band strategy from the post the user shared (Nov 26 2026), rebuilt and stress-tested.

Rules as described in the post:
  - Start: $5,000 of SOXL (bought at the first open) and $5,000 cash. Target stays $5,000 for good.
  - After each close, value the SOXL shares at the close:
      at or below 90% of target  -> buy back up to the target at the next open (only with cash on hand)
      at or above 110% of target -> trim back to the target at the next open
      ...but in a strong trend the trim trigger is 150% ($7,500). Strong trend = SOXX closes above its 20-day average
         and the 20-day average is above the 100-day average (today counted in both).
  - Orders are sized at the next open from the open price (a gap can shrink or cancel them). Fractional shares.
    Cost 0.10% of each trade after the first. Cash earns nothing. No deposits, no borrowing.
Data: Alpaca daily bars, split-adjusted only (no dividends; SOXL pays almost none), 2016 to Nov 2026.

Tested: the base rule from every month-start 2017-2025 (not just one lucky start), the band settings moved around,
no trend rule, and benchmarks (half SOXL / half cash held, all SOXL, all SOXX, SPY, QQQ, QQQ 200-day sleeve).

  python scripts/soxl_band_test.py   -> reports/soxl_band.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import pit  # noqa: E402
from osc_oversold_test import daily  # noqa: E402

COST = 0.001
END = None


def data():
    soxl = daily("SOXL")[["open", "close"]]
    soxx = daily("SOXX").close.rename("soxx")
    d = soxl.join(soxx, how="inner")
    d["s20"] = d.soxx.rolling(20).mean()
    d["s100"] = d.soxx.rolling(100).mean()
    d["strong"] = (d.soxx > d.s20) & (d.s20 > d.s100)
    return d.dropna()


def run(d, start, target=5000.0, cash=5000.0, buy_band=0.10, trim_band=0.10, strong_trigger=1.5, trend=True):
    d = d[d.index >= start]
    if len(d) < 30:
        return None
    o, c, strong = d.open.to_numpy(), d.close.to_numpy(), d.strong.to_numpy()
    sh = target / o[0]
    trades, short_cash, eq, cash_path = 0, 0, [], []
    pending = 0                                  # +1 buy, -1 trim, scheduled at the previous close
    for i in range(len(d)):
        if i > 0 and pending:
            val = sh * o[i]
            if pending > 0 and val < target:
                amt = min(target - val, cash / (1 + COST))
                if amt < target - val - 1e-6:
                    short_cash += 1
                if amt > 1:
                    sh += amt / o[i]
                    cash -= amt * (1 + COST)
                    trades += 1
            elif pending < 0 and val > target:
                amt = val - target
                sh -= amt / o[i]
                cash += amt * (1 - COST)
                trades += 1
            pending = 0
        val = sh * c[i]
        trig = strong_trigger if (trend and strong[i]) else 1 + trim_band
        if val <= target * (1 - buy_band):
            pending = 1
        elif val >= target * trig:
            pending = -1
        eq.append(val + cash)
        cash_path.append(cash)
    eq = pd.Series(eq, index=d.index)
    return eq, trades, short_cash, pd.Series(cash_path, index=d.index)


def hold(series, start, frac=1.0, total=10_000.0):
    s = series[series.index >= start]
    return total * (1 - frac) + total * frac * s / s.iat[0]


def stats(eq):
    r = eq.pct_change().dropna()
    yrs = len(r) / 252
    cagr = (eq.iat[-1] / eq.iat[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return eq.iat[-1], cagr, sh, dd


def fmt(eq):
    v, cagr, sh, dd = stats(eq)
    return f"${v:,.0f} | {cagr * 100:+.1f}% | {sh:.2f} | {dd * 100:.1f}%"


def qqq_sleeve(start):
    q = daily("QQQ").close
    on = (q > q.rolling(200).mean()).shift(1).fillna(False)
    r = q.pct_change().where(on, 0.0)
    r = r[r.index >= start]
    return 10_000 * (1 + r).cumprod()


def main():
    d = data()
    first = d.index[0]
    L = ["# SOXL fixed-dollar band strategy (from the post), rebuilt and stress-tested\n", __doc__.split("\n\n")[1], "",
         __doc__.split("\n\n")[2], "", f"Data {first:%Y-%m-%d} to {d.index[-1]:%Y-%m-%d} (after the 100-day warm-up).",
         "Cells: final value of $10,000 | yearly growth | Sharpe | worst drop from a high.\n"]

    def block(title, start):
        res = run(d, start)
        eq, tr, short, cash = res
        soxl, soxx = daily("SOXL").close, daily("SOXX").close
        L.extend([f"\n## {title} ({start:%Y-%m-%d} to {d.index[-1]:%Y-%m-%d})\n", "| Approach | Result |", "|---|---|",
                  f"| Band strategy (post's rules) | {fmt(eq)} |",
                  f"| Same start, held: $5k SOXL + $5k cash | {fmt(hold(soxl, start, 0.5))} |",
                  f"| All $10k in SOXL, held | {fmt(hold(soxl, start))} |",
                  f"| All $10k in SOXX, held | {fmt(hold(soxx, start))} |",
                  f"| All $10k in SPY, held | {fmt(hold(daily('SPY').close, start))} |",
                  f"| All $10k in QQQ, held | {fmt(hold(daily('QQQ').close, start))} |",
                  f"| QQQ 200-day sleeve (our live rule, full $10k) | {fmt(qqq_sleeve(start))} |",
                  "", f"Band strategy: {tr} trades; {short} buys cut short for lack of cash; lowest cash ${cash.min():,.0f}."])
    block("From the first possible day", first)
    block("From January 2022 (the post's bad start)", pd.Timestamp("2022-01-03"))
    block("2026 only (the post's main example)", pd.Timestamp("2026-01-02"))
    block("Five years, as in the post", pd.Timestamp("2021-11-24"))

    # every month-start
    starts = pd.date_range(first + pd.Timedelta(days=5), "2025-12-01", freq="MS")
    rows = []
    for s in starts:
        res = run(d, s)
        if res is None:
            continue
        eq = res[0]
        v, cagr, sh, dd = stats(eq)
        h = hold(daily("SOXL").close, s, 0.5)
        hv, hc, hs, hd = stats(h)
        sp = hold(daily("SPY").close, s)
        spv, spc, sps, spd = stats(sp)
        rows.append({"start": s, "band": v, "band_dd": dd, "band_sh": sh, "held": hv, "held_dd": hd, "spy": spv, "spy_dd": spd,
                     "band_cagr": cagr, "spy_cagr": spc})
    m = pd.DataFrame(rows)
    L += ["\n## Every start month, 2016-2025, held to Nov 24 2026\n",
          f"{len(m)} start months. Band strategy vs holding $5k SOXL + $5k cash from the same day, and vs SPY.\n",
          "| | Band strategy | Held half SOXL | SPY |", "|---|--:|--:|--:|",
          f"| Median final value of $10k | ${m.band.median():,.0f} | ${m.held.median():,.0f} | ${m.spy.median():,.0f} |",
          f"| Worst final value | ${m.band.min():,.0f} | ${m.held.min():,.0f} | ${m.spy.min():,.0f} |",
          f"| Starts that ended below $10,000 | {(m.band < 10_000).sum()} | {(m.held < 10_000).sum()} | {(m.spy < 10_000).sum()} |",
          f"| Median worst drawdown | {m.band_dd.median() * 100:.0f}% | {m.held_dd.median() * 100:.0f}% | {m.spy_dd.median() * 100:.0f}% |",
          f"| Worst drawdown of any start | {m.band_dd.min() * 100:.0f}% | {m.held_dd.min() * 100:.0f}% | {m.spy_dd.min() * 100:.0f}% |",
          f"| Band beat held-half-SOXL | {(m.band > m.held).mean() * 100:.0f}% of starts | | |",
          f"| Band beat SPY | {(m.band > m.spy).mean() * 100:.0f}% of starts | | |"]
    worst = m.nsmallest(3, "band")
    L.append("\nWorst starts for the band strategy: " + ", ".join(f"{r.start:%b %Y} -> ${r.band:,.0f} (drawdown {r.band_dd * 100:.0f}%)"
                                                               for r in worst.itertuples()))

    # settings moved around
    L += ["\n## How much the settings matter (from the first possible day)\n",
          "| Buy band | Trim band | Strong-trend trigger | Trend rule | Result | Trades |", "|--:|--:|--:|---|---|--:|"]
    for bb, tb, st, tr in [(0.10, 0.10, 1.5, True), (0.10, 0.10, 1.5, False), (0.05, 0.05, 1.5, True), (0.15, 0.15, 1.5, True),
                           (0.20, 0.20, 1.5, True), (0.10, 0.10, 1.3, True), (0.10, 0.10, 2.0, True), (0.10, 0.10, 3.0, True),
                           (0.20, 0.10, 1.5, True), (0.10, 0.20, 1.5, True)]:
        eq, n, short, _ = run(d, first, buy_band=bb, trim_band=tb, strong_trigger=st, trend=tr)
        L.append(f"| {bb:.0%} | {tb:.0%} | {st:.0%} of target | {'on' if tr else 'off'} | {fmt(eq)} | {n} |")
    pit.log_trial("soxl_band", "post's rules + 9 setting variants + all start months", len(m), float("nan"), float("nan"))
    Path("reports/soxl_band.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
