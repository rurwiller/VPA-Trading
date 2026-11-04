"""Lower-frequency intraday ideas from the literature, where the move per trade is large next to costs.

1. Market intraday momentum (Gao, Han, Li, Zhou 2018, JFE; Baltussen, Da, Lammers, Martens 2021, JFE):
   the return from the prior close to 15:30 ET predicts the last half hour. Trade 15:30 -> 16:00 in the
   direction of the day so far. Variants: signal = first 30 min only; only when the day's move is large.
2. Noise-area breakout (Zarattini, Aziz, Barbon 2024, "Beat the market: an effective intraday momentum
   strategy for SPY"): the "noise area" at minute t is the average absolute move from the open at that same
   minute over the last 14 days. Upper band = max(open, prior close) x (1 + sigma_t), lower = min(...) x (1 - sigma_t).
   Checked only at :00 / :30 from 10:00 to 15:30: above the band -> long, below -> short. Exit when price is back
   past max(band, VWAP) (long) / min(band, VWAP) (short) at a check, or at the close. Fixed notional, no leverage.
Both are scored per day with each ticker's cost (spread + 1 bp per round trip). Discovery before 2024-11-01,
holdout after. Half-days are skipped.

  python scripts/intraday_momentum_test.py            -> results/intraday_mom/<SYM>.pkl, reports/intraday_momentum.md
  python scripts/intraday_momentum_test.py --report
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading.alpaca import load_bars_file  # noqa: E402
from midcap_test import MAG, MID, cost_bps  # noqa: E402

OUT = Path("results/intraday_mom")
SPLIT = pd.Timestamp("2024-11-01")
CHECKS = list(range(29, 360, 30))      # bar index whose close is 10:00, 10:30, ..., 15:30


def matrices(sym: str):
    m = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz")
    day = m.index.normalize()
    mi = ((m.index - day) / pd.Timedelta(minutes=1)).astype(int) - 570
    m = m.assign(day=day, mi=mi)
    m = m[(m.mi >= 0) & (m.mi < 390)]
    full = m.groupby("day").mi.max() >= 389
    m = m[m.day.isin(full.index[full])]
    C = m.pivot(index="day", columns="mi", values="close").reindex(columns=range(390)).ffill(axis=1)
    O = m[m.mi == m.groupby("day").mi.transform("min")].set_index("day").open
    pv = (m.vwap.fillna(m.close) * m.volume)
    m = m.assign(pv=pv)
    PV = m.pivot(index="day", columns="mi", values="pv").reindex(columns=range(390)).fillna(0).cumsum(axis=1)
    V = m.pivot(index="day", columns="mi", values="volume").reindex(columns=range(390)).fillna(0).cumsum(axis=1)
    VW = (PV / V.replace(0, np.nan)).ffill(axis=1)
    return C, O.reindex(C.index), VW


def run_symbol(sym: str) -> str:
    C, O, VW = matrices(sym)
    c = C.to_numpy()
    o = O.to_numpy()
    days = C.index
    prev = np.r_[np.nan, c[:-1, 389]]
    cost = cost_bps(sym) / 1e4
    rows = []
    # ---- 1. market intraday momentum
    sig_full = c[:, 359] / prev - 1           # prior close -> 15:30
    sig_open = c[:, 29] / prev - 1            # prior close -> 10:00 (first half hour incl. overnight)
    last = c[:, 389] / c[:, 359] - 1          # 15:30 -> 16:00
    # ---- 2. noise area
    move = np.abs(c / o[:, None] - 1)
    sigma = pd.DataFrame(move).rolling(14).mean().shift(1).to_numpy()   # previous 14 days, same minute
    vw = VW.to_numpy()
    ub_base, lb_base = np.fmax(o, prev), np.fmin(o, prev)
    for k in range(len(days)):
        r = {"sym": sym, "day": days[k], "sig_full": sig_full[k], "sig_open": sig_open[k], "last30": last[k],
             "oc": c[k, 389] / o[k] - 1, "cost": cost}
        if np.isnan(sigma[k, CHECKS[0]]) or np.isnan(prev[k]):
            r["nb_ret"], r["nb_trades"] = np.nan, 0
            rows.append(r)
            continue
        pos, entry, ret, trades = 0, 0.0, 0.0, 0
        for t in CHECKS:
            px = c[k, t]
            ub, lb = ub_base[k] * (1 + sigma[k, t]), lb_base[k] * (1 - sigma[k, t])
            want = pos
            if pos == 1 and px < max(ub, vw[k, t]):
                want = 0
            elif pos == -1 and px > min(lb, vw[k, t]):
                want = 0
            if want == 0:
                want = 1 if px > ub else (-1 if px < lb else 0)
            if want != pos:
                if pos != 0:
                    ret += pos * (px / entry - 1) - cost
                if want != 0:
                    entry, trades = px, trades + 1
                pos = want
        if pos != 0:
            ret += pos * (c[k, 389] / entry - 1) - cost
        r["nb_ret"], r["nb_trades"] = ret, trades
        rows.append(r)
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_pickle(OUT / f"{sym}.pkl")
    return f"{sym}: {len(df)} days, noise-band trades {int(df.nb_trades.sum())}"


def stats(x: pd.Series) -> dict:
    x = x.dropna()
    n = len(x)
    if n < 2:
        return {"n": n}
    return {"n": n, "avg bps": round(x.mean() * 1e4, 2), "2se bps": round(2 * x.std() / np.sqrt(n) * 1e4, 2),
            "win%": round((x > 0).mean() * 100, 1), "ann. Sharpe": round(x.mean() / x.std() * np.sqrt(252), 2)}


def split(df: pd.DataFrame, col: str, name: str) -> dict:
    r = {"strategy": name}
    for p, g in (("d", df[df.day < SPLIT]), ("h", df[df.day >= SPLIT])):
        r.update({f"{k}_{p}": v for k, v in stats(g[col]).items()})
    return r


def report() -> None:
    df = pd.concat([pd.read_pickle(p) for p in sorted(OUT.glob("*.pkl"))], ignore_index=True)
    df["universe"] = np.where(df.sym.isin(MID), "mid-cap", "Mag7+")
    # momentum P&L per day (one round trip when traded)
    df["mom_full"] = np.sign(df.sig_full) * df.last30 - df.cost
    df["mom_open"] = np.sign(df.sig_open) * df.last30 - df.cost
    df["mom_full_gross"] = np.sign(df.sig_full) * df.last30
    big = df.groupby("sym").sig_full.transform(lambda s: s.abs().rolling(60, min_periods=20).quantile(0.67).shift(1))
    df["mom_big"] = np.where(df.sig_full.abs() >= big, df.mom_full, np.nan)
    df["buyhold_last30"] = df.last30 - df.cost
    df["nb_gross"] = df.nb_ret + df.nb_trades * df.cost
    df["nb_traded"] = np.where(df.nb_trades > 0, df.nb_ret, np.nan)
    L = ["# Intraday momentum (lower-frequency) on 5 years of 1m bars\n",
         f"{df.day.min():%Y-%m-%d} to {df.day.max():%Y-%m-%d}, {df.sym.nunique()} tickers. One row = one ticker-day. "
         "`_d` before 2024-11-01, `_h` after. avg / 2se in bps of the position per day (net of each ticker's spread + 1 bp "
         "per round trip unless marked gross). ann. Sharpe = per ticker-day mean / std x sqrt(252) (one ticker traded alone).\n"]
    for uni in ("Mag7+", "mid-cap"):
        u = df[df.universe == uni]
        rows = [split(u, "buyhold_last30", "always long 15:30-16:00 (baseline)"),
                split(u, "mom_full_gross", "momentum: day so far -> last 30 min (gross)"),
                split(u, "mom_full", "momentum: day so far -> last 30 min"),
                split(u, "mom_big", "momentum, only top third of day moves"),
                split(u, "mom_open", "momentum: first 30 min -> last 30 min"),
                split(u, "nb_gross", "noise-band breakout, every day (gross)"),
                split(u, "nb_ret", "noise-band breakout, every day"),
                split(u, "nb_traded", "noise-band breakout, days with a trade")]
        L.append(f"\n## {uni}\n")
        L.append(pd.DataFrame(rows).to_markdown(index=False))
        per = []
        for s, g in u.groupby("sym"):
            r = {"sym": s}
            for col, nm in (("mom_full", "mom"), ("nb_ret", "noise")):
                for p, gg in (("d", g[g.day < SPLIT]), ("h", g[g.day >= SPLIT])):
                    r[f"{nm} bps_{p}"] = round(gg[col].mean() * 1e4, 2)
            per.append(r)
        L.append(f"\n### {uni} by ticker (avg bps per day, net)\n")
        L.append(pd.DataFrame(per).to_markdown(index=False))
        yr = u.assign(year=u.day.dt.year).groupby("year")[["mom_full", "nb_ret"]].mean().mul(1e4).round(2)
        L.append(f"\n### {uni} by year (avg bps per ticker-day, net)\n")
        L.append(yr.to_markdown())
    Path("reports/intraday_momentum.md").write_text("\n".join(L) + "\n")
    print("wrote reports/intraday_momentum.md")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--report"]
    if "--report" not in sys.argv:
        with ProcessPoolExecutor(max_workers=3) as ex:
            for msg in ex.map(run_symbol, args or MAG + MID):
                print(msg, flush=True)
    report()
