"""Review a day's candles: which big reversals (pivots) were there, and did the system see them?

  python scripts/day_review.py [YYYY-MM-DD] [SYM ...]      (default: today, the Mag 7; IEX bars like the live scanner)

A pivot = a 9m candle whose high (low) is the highest (lowest) of the 5 candles either side AND price then moves >= 3 ATR(5m)
the other way within the next 6 candles (about an hour). Options: --atr=2 --look=8 loosen it. Pivots can only be confirmed about 45 minutes later, so the last
hour of the day is not reviewed. For each pivot: the candle's shape, the volume, which of the system's rules it met, whether the
live system actually signalled it (logs/live/<date>.jsonl), and what the scanner's own mechanics (stop-entry through the candle,
stop beyond the wick, 1R target, $1,000 risk) would have made. Hindsight: these are the pivots that worked.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import live as LV, vpa  # noqa: E402
from vpa_trading.alert import pivot_wick  # noqa: E402
from vpa_trading.willard_osc import willard_osc  # noqa: E402

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


def main() -> None:
    args = sys.argv[1:]
    opts = {a.split("=")[0]: float(a.split("=")[1]) for a in args if a.startswith("--") and "=" in a}
    args = [a for a in args if not a.startswith("--")]
    move_atr, look = opts.get("--atr", 3.0), int(opts.get("--look", 6))
    day = pd.Timestamp(args[0] if args and args[0][:2] == "20" else pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d"))
    syms = [a.upper() for a in args if not a[:2] == "20"] or MAG7
    end = min(day + pd.Timedelta(days=1), pd.Timestamp.now(tz="America/New_York").tz_localize(None))
    hist = LV.fetch_bars(syms, day - pd.Timedelta(days=45), end, feed="iex")
    daily = LV.fetch_bars(syms, day - pd.Timedelta(days=500), day, tf="1Day", feed="sip")
    cfg = LV.Config(symbols=syms, tfs=("9m", "15m"), risk_usd=1000.0, target="1R", require_gap=False, short_trend_filter=False, max_adds=9)
    logged = {}
    lp = Path("logs/live") / f"{day:%Y-%m-%d}.jsonl"
    if lp.exists():
        for line in lp.read_text().splitlines():
            d = json.loads(line)
            if not d.get("strategy"):
                logged[(d["sym"], d["tf"], d["signal_close"], d["type"])] = d
    rows = []
    for sym in syms:
        m1 = hist[sym]
        b = LV.frame(m1, "9m")
        b5 = LV.frame(m1, "5m")
        today = b[b.index.normalize() == day]
        n = 5
        for pos in range(len(today)):
            i = b.index.get_loc(today.index[pos])
            if i < n + 14 or i + look >= len(b):
                continue
            win_h, win_l = b.high.iloc[i - n:i + n + 1], b.low.iloc[i - n:i + n + 1]
            t = b.index[i]
            now = b.closes_at.iloc[i]
            mst = (now - pd.Timedelta(hours=2))
            if not (pd.Timedelta(hours=10) <= now - now.normalize() <= pd.Timedelta(hours=15, minutes=30)):
                continue
            a5 = float(b5[b5.closes_at <= now].atr.iloc[-1])
            kind = 0
            if b.high.iloc[i] >= win_h.max() and b.low.iloc[i + 1:i + look + 1].min() <= b.high.iloc[i] - move_atr * a5:
                kind = -1
            elif b.low.iloc[i] <= win_l.min() and b.high.iloc[i + 1:i + look + 1].max() >= b.low.iloc[i] + move_atr * a5:
                kind = 1
            if not kind:
                continue
            o, h, l, c = (float(b[k].iloc[i]) for k in ("open", "high", "low", "close"))
            rng = h - l
            up, dn, body = h - max(o, c), min(o, c) - l, abs(c - o)
            done = b.iloc[:i + 1]
            rv = float(vpa.relvol_tod(done).iat[-1])
            det = vpa.detect(done, done.atr)
            det = det[(det.index == t)]
            types = sorted(set(det.type) & LV.PREMIER_TYPES)
            pw = pivot_wick(done)
            eng = LV.Engine(cfg, hist, daily)
            m = m1[m1.index < now]
            gaps = eng._gaps(sym, m, now)
            wick = h if kind < 0 else l
            gap = eng._at_gap(gaps, wick, kind, a5)
            # what the scanner's mechanics would have made
            p = eng._plan(sym, "9m", "review", "pivot", kind, now, h, l, wick, gap)
            pnl, how = np.nan, "no valid plan"
            if p:
                eng.plans.append(p)
                for tt, bar in m1[m1.index >= now].iterrows():
                    eng.manage_sim(sym, bar, tt)
                    if p.status in ("closed", "cancelled"):
                        break
                how = p.exit_reason or p.status
                if p.status == "closed":
                    pnl = (p.exit - p.fill) * p.side * p.qty
            seen = [d for (s_, tf_, sc, ty), d in logged.items() if s_ == sym and (d["side"] > 0) == (kind > 0)
                    and abs(pd.Timestamp(sc) - now) <= pd.Timedelta(minutes=20)]
            rows.append(dict(time=f"{mst:%H:%M}", sym=sym, kind="top" if kind < 0 else "bottom", up=up / rng if rng else 0, dn=dn / rng if rng else 0,
                             body=body / rng if rng else 0, rvol=rv, rng_atr=rng / a5, premier=",".join(types) or "-", pivot_wick=pw == kind,
                             gap=gap, signalled=("yes: " + seen[0]["type"] + " " + seen[0]["tf"]) if seen else "no", scanner_would=pnl, how=how))
    if not rows:
        print("no pivots found")
        return
    df = pd.DataFrame(rows).sort_values(["time", "sym"])
    pd.set_option("display.width", 250)
    out = df.assign(**{"wick up": (df.up * 100).round(0).astype(int).astype(str) + "%", "wick dn": (df.dn * 100).round(0).astype(int).astype(str) + "%",
                       "body": (df.body * 100).round(0).astype(int).astype(str) + "%", "vol x": df.rvol.round(1), "size ATR": df.rng_atr.round(1),
                       "scanner P&L": df.scanner_would.round(0)})
    print(out[["time", "sym", "kind", "wick up", "wick dn", "body", "vol x", "size ATR", "premier", "pivot_wick", "gap", "signalled", "scanner P&L", "how"]].to_string(index=False))
    print(f"\n{len(df)} pivots; signalled {int((df.signalled != 'no').sum())}; pivot-wick shape {int(df.pivot_wick.sum())}; "
          f"at a 1h/4h/D gap {int((df.gap != '-').sum())}; volume >= 3x {int((df.rvol >= 3).sum())}")
    df.to_pickle(f"/tmp/claude-0/-home-user-VPA-Trading/a203c510-4723-5621-b130-f64d09a5febe/scratchpad/day_review_{day:%Y%m%d}.pkl")


if __name__ == "__main__":
    main()
