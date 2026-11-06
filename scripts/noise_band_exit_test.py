"""Trend-day breakout: get out when an opposite pivot-wick candle on volume shows up.

While the breakout holds a long, a pivot-wick TOP candle (upper wick >= 40% of the range and >= the body, small lower wick,
wick = highest of the last 12 candles) on 9m (and/or 15m) with volume >= X times the usual closes -> sell the rest at that
candle's close. Mirror for shorts with a pivot-wick BOTTOM. Everything else as the live breakout: checks every 30 minutes
10:00-15:30 ET, thirds at +1% / +2%, stop to breakeven after the first third, costs = spread + 1 bp per round trip.
Candle events come from results/osc_pivot/<SYM>.pkl (run scripts/osc_pivot_test.py first).

  python scripts/noise_band_exit_test.py TSLA AMD QQQ
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import intraday_momentum_test as T  # noqa: E402
from midcap_test import cost_bps  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402

SPLIT = pd.Timestamp("2024-11-01")
CHECKS = list(range(29, 360, 30))


def load(sym: str):
    m1 = load_bars_file(f"data/alpaca/{sym}-1m-ext.csv.gz")
    C, O, VW = T.matrices(sym)
    day = m1.index.normalize()
    mi = ((m1.index - day) / pd.Timedelta(minutes=1)).astype(int) - 570
    m1 = m1.assign(day=day, mi=mi)
    m1 = m1[(m1.mi >= 0) & (m1.mi < 390)]
    full = m1.groupby("day").mi.max() >= 389
    m1 = m1[m1.day.isin(full.index[full])]
    piv = lambda col: m1.pivot(index="day", columns="mi", values=col).reindex(columns=range(390)).ffill(axis=1).reindex(C.index).to_numpy()  # noqa: E731
    return C, O, VW, piv("high"), piv("low")


def flags(sym: str, idx: pd.DatetimeIndex, tfs, min_rvol):
    ev = pd.read_pickle(f"results/osc_pivot/{sym}.pkl")
    ev = ev[ev.tf.isin(tfs) & (ev.rvol >= min_rvol)]
    top = np.zeros((len(idx), 390), bool)
    bot = np.zeros((len(idx), 390), bool)
    t = pd.to_datetime(ev.time) - pd.Timedelta(minutes=1)          # the last 1m bar of the candle
    day = t.dt.normalize()
    b = ((t - day) / pd.Timedelta(minutes=1)).astype(int) - 570
    k = idx.get_indexer(day)
    ok = (k >= 0) & (b >= 0) & (b < 390)
    for kk, bb, d in zip(k[ok], b[ok], ev.dir[ok]):
        (top if d < 0 else bot)[kk, bb] = True
    return top, bot


def run(sym, data, opp=None, scale=True, be=True) -> pd.Series:
    C, O, VW, Hh, Ll = data
    c, o, vw = C.to_numpy(), O.to_numpy(), VW.to_numpy()
    prev = np.r_[np.nan, c[:-1, 389]]
    sigma = pd.DataFrame(np.abs(c / o[:, None] - 1)).rolling(14).mean().shift(1).to_numpy()
    cost = cost_bps(sym) / 1e4
    ub0, lb0 = np.fmax(o, prev), np.fmin(o, prev)
    levels, fracs = ([0.01, 0.02], [1 / 3, 1 / 3]) if scale else ([], [])
    out = np.full(len(c), np.nan)
    for k in range(len(c)):
        if np.isnan(sigma[k, CHECKS[0]]) or np.isnan(prev[k]):
            continue
        pos, entry, rem, ret, targets, tfr, be_on = 0, 0.0, 0.0, 0.0, [], [], False

        def close(px, frac):
            nonlocal ret
            ret += frac * (pos * (px / entry - 1) - cost)
        for ci, t in enumerate(CHECKS):
            px = c[k, t]
            ub, lb = ub0[k] * (1 + sigma[k, t]), lb0[k] * (1 - sigma[k, t])
            want = pos
            if pos == 1 and px < max(ub, vw[k, t]):
                want = 0
            elif pos == -1 and px > min(lb, vw[k, t]):
                want = 0
            if want == 0:
                want = 1 if px > ub else (-1 if px < lb else 0)
            if want != pos:
                if pos != 0 and rem > 1e-9:
                    close(px, rem)
                    rem = 0.0
                if want != 0:
                    entry, rem, targets, tfr, be_on = px, 1.0, [px * (1 + want * l) for l in levels], list(fracs), False
                pos = want
            if pos == 0:
                continue
            end = CHECKS[ci + 1] if ci + 1 < len(CHECKS) else 389
            for b in range(t + 1, end + 1):
                if be and be_on and rem > 1e-9 and ((pos > 0 and Ll[k, b] <= entry) or (pos < 0 and Hh[k, b] >= entry)):
                    close(entry, rem)
                    rem, pos = 0.0, 0
                    break
                while tfr and ((Hh[k, b] >= targets[0]) if pos > 0 else (Ll[k, b] <= targets[0])):
                    close(targets[0], tfr[0])
                    rem -= tfr[0]
                    targets.pop(0)
                    tfr.pop(0)
                    be_on = True
                if opp is not None and rem > 1e-9 and ((pos > 0 and opp[0][k, b]) or (pos < 0 and opp[1][k, b])):
                    close(c[k, b], rem)
                    rem, pos = 0.0, 0
                    break
        if pos != 0 and rem > 1e-9:
            close(c[k, 389], rem)
        out[k] = ret
    return pd.Series(out, index=C.index)


def main() -> None:
    for sym in (sys.argv[1:] or ["TSLA", "AMD", "QQQ"]):
        data = load(sym)
        idx = data[0].index
        rows = []
        variants = [("live breakout (thirds + breakeven), no opposite-signal exit", None)]
        for tfs in (("9m",), ("9m", "15m"), ("5m", "9m", "15m")):
            for rv in (1.5, 2.0, 3.0):
                variants.append((f"+ exit on opposite pivot candle, {'+'.join(tfs)}, volume >= {rv}x", flags(sym, idx, tfs, rv)))
        for name, opp in variants:
            r = run(sym, data, opp)
            d = r.index < SPLIT
            rows.append({"variant": name, "bps_before": r[d].mean() * 1e4, "bps_after": r[~d].mean() * 1e4,
                         "sharpe_before": r[d].mean() / r[d].std() * np.sqrt(252),
                         "sharpe_after": r[~d].mean() / r[~d].std() * np.sqrt(252), "worst_day_bps": r.min() * 1e4,
                         "pct_green": (r[r != 0] > 0).mean() * 100})
        print(sym)
        print(pd.DataFrame(rows).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
