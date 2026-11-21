"""Replay the paper account's real trades (Nov 4 onward, from Alpaca's fills) under candidate risk rules.

Each rule decides, at a trade's entry time, whether the trade would have been allowed, using only what was known then
(trades already closed, positions already open). A blocked trade's P/L is removed. Simplifications, stated plainly:
- the replay cannot invent trades a rule would have freed room for (e.g. buying power used elsewhere), so it can only
  remove trades; their knock-on effects are ignored;
- the daily loss stop uses realized P/L only (closed trades), not open losses.
Positions = the pieces of one entry (half exits, the breakout's thirds) grouped together, as on the scorecard.

  python scripts/risk_replay.py   -> reports/risk_replay.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import live as LV  # noqa: E402
import eod_report as E  # noqa: E402

START = "2026-11-04"
OUT = Path("reports/risk_replay.md")


def positions():
    now = pd.Timestamp.now(tz="America/New_York")
    cal = requests.get(LV.TRADE + "/calendar", headers=LV.headers(), timeout=30,
                       params={"start": START, "end": f"{now:%Y-%m-%d}"}).json()
    rows = []
    for c in cal:
        if c["date"] >= f"{now:%Y-%m-%d}" and now.strftime("%H:%M") < "15:51":
            continue
        pieces, _ = E.get_pieces(pd.Timestamp(c["date"]))
        df = pd.DataFrame(pieces)
        if not len(df):
            continue
        for (strat, sym, t_in), g in df.groupby(["strat", "sym", "t_in"]):
            rows.append({"day": c["date"], "t_in": t_in, "t_out": g.t_out.max(), "sym": sym, "strat": strat,
                         "side": g.side.iat[0], "pnl": float(g.pnl.sum()), "shares": int(g.q.sum()),
                         "notional": float((g.q * g.entry).sum())})
    return pd.DataFrame(rows).sort_values("t_in").reset_index(drop=True)


def replay(p, allow):
    """allow(trade, taken_so_far_today) -> bool. Returns the taken trades."""
    keep = []
    for day, g in p.groupby("day"):
        taken = []
        for _, t in g.iterrows():
            if allow(t, pd.DataFrame(taken)):
                taken.append(t)
        keep += taken
    return pd.DataFrame(keep)


def closed_before(taken, t):
    return taken[taken.t_out <= t.t_in] if len(taken) else taken


def open_at(taken, t):
    return taken[(taken.t_in <= t.t_in) & (taken.t_out > t.t_in)] if len(taken) else taken


def rules():
    R = {"No rule (what happened)": lambda t, k: True}

    def cooldown(minutes, same_side_only=False):
        def f(t, k):
            c = closed_before(k, t)
            if not len(c):
                return True
            bad = c[(c.sym == t.sym) & (c.pnl < 0)]
            if same_side_only:
                bad = bad[bad.side == t.side]
            if minutes is None:
                return not len(bad)
            return not len(bad[bad.t_out > t.t_in - pd.Timedelta(minutes=minutes)])
        return f
    R["After a loss on a stock: no more trades in it that day"] = cooldown(None)
    R["After a loss on a stock: none in the same direction that day"] = cooldown(None, True)
    R["After a loss on a stock: 60-minute cooldown"] = cooldown(60)
    R["After a loss on a stock: 30-minute cooldown"] = cooldown(30)

    def max_losses_per_stock(n):
        def f(t, k):
            c = closed_before(k, t)
            return not len(c) or ((c.sym == t.sym) & (c.pnl < 0)).sum() < n
        return f
    R["At most 2 losses per stock per day"] = max_losses_per_stock(2)

    def no_adds(t, k):
        o = open_at(k, t)
        return not len(o) or not (o.sym == t.sym).any()
    R["No adds: one open position per stock"] = no_adds

    def daily_stop(x):
        def f(t, k):
            c = closed_before(k, t)
            return not len(c) or c.pnl.sum() > -x
        return f
    for x in (1000, 2000, 3000):
        R[f"Daily loss stop ${x:,} (realized)"] = daily_stop(x)

    def same_dir_cap(n):
        def f(t, k):
            o = open_at(k, t)
            return not len(o) or (o.side == t.side).sum() < n
        return f
    for n in (2, 3):
        R[f"At most {n} open positions in the same direction"] = same_dir_cap(n)

    R["Combined: same-direction no-repeat after a loss + no adds + $2,000 daily stop"] = (
        lambda t, k: cooldown(None, True)(t, k) and no_adds(t, k) and daily_stop(2000)(t, k))
    return R


def summary(name, k, base):
    days = k.groupby("day").pnl.sum() if len(k) else pd.Series(dtype=float)
    allday = base.groupby("day").pnl.sum().index
    days = days.reindex(allday, fill_value=0.0)
    eq = days.cumsum()
    dd = (eq - eq.cummax()).min()
    blocked = len(base) - len(k)
    bl = base[~base.index.isin(k.index)] if len(k) else base
    return (f"| {name} | {len(k)} | {blocked} | {bl.pnl.sum():+,.0f} | {k.pnl.sum():+,.0f} | "
            f"{100 * (k.pnl > 0).mean():.0f}% | {days.min():+,.0f} | {dd:+,.0f} |")


def main():
    p = positions()
    L = ["# Risk rules replayed on the paper account's real trades\n", __doc__.split("\n\n")[1], "",
         f"{len(p)} positions over {p.day.nunique()} trading days ({p.day.min()} to {p.day.max()}). "
         f"Total P/L {p.pnl.sum():+,.0f}.\n",
         "| Rule | Trades kept | Blocked | P/L of the blocked trades | Total P/L | Win rate | Worst day | Worst drawdown |",
         "|---|--:|--:|--:|--:|--:|--:|--:|"]
    for name, f in rules().items():
        L.append(summary(name, replay(p, f), p))
    L += ["\n## P/L by strategy\n", "| Strategy | Positions | Won | P/L | Average |", "|---|--:|--:|--:|--:|"]
    for s, g in p.groupby("strat"):
        L.append(f"| {s} | {len(g)} | {100 * (g.pnl > 0).mean():.0f}% | {g.pnl.sum():+,.0f} | {g.pnl.mean():+,.0f} |")
    L += ["\n## Repeat trades in the same stock on the same day\n",
          "| Trade # in that stock that day | Positions | Won | P/L |", "|---|--:|--:|--:|"]
    p["nth"] = p.groupby(["day", "sym"]).cumcount() + 1
    for n, g in p.groupby(p.nth.clip(upper=4)):
        L.append(f"| {n if n < 4 else '4+'} | {len(g)} | {100 * (g.pnl > 0).mean():.0f}% | {g.pnl.sum():+,.0f} |")
    L += ["\n## By day\n", "| Day | Positions | P/L |", "|---|--:|--:|"]
    for d, g in p.groupby("day"):
        L.append(f"| {d} | {len(g)} | {g.pnl.sum():+,.0f} |")
    OUT.write_text("\n".join(L) + "\n")
    p.to_csv("results/paper_positions.csv", index=False)
    print("\n".join(L))


if __name__ == "__main__":
    main()
