"""End-of-day report: every trade in one readable table, straight from Alpaca's filled orders.

  python scripts/eod_report.py [YYYY-MM-DD]      (default: today)

One row per piece of a position (a breakout sold in thirds is three rows). Entries and exits are matched first-in-first-out per
symbol; strategy comes from the order id prefix (vpa- candle scanner, alert- alert mode, nb- TSLA breakout). Times are MST.
Also lists the signals that never traded (from logs/live/<date>.jsonl) and the account's equity change.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import live as LV  # noqa: E402

STRAT = {"vpa-": "Candle scanner", "alert-": "Alert mode", "nb-": "TSLA breakout"}
MST = "America/Denver"


def strat_of(cid: str) -> str | None:
    return next((v for k, v in STRAT.items() if cid.startswith(k)), None)


def how(kind: str, cid: str) -> str:
    if kind == "limit":
        return "half at +0.5R" if cid.endswith("-h1") else "profit target"
    if kind == "stop":
        return "breakeven stop" if cid.endswith("-h3") else "stop"
    for key, label in (("osctrim", "15m oscillator trim"), ("-hm", "closed at market (exit order rejected)"),
                       ("take", "profit taken at market"), ("manual", "sold by hand"), ("exit", "breakout exit rule"), ("fix-orphan", "duplicate order fixed")):
        if key in cid:
            return label
    return "closed at flatten"


def get_pieces(day: pd.Timestamp):
    """Every closed piece of a position on `day` (first-in-first-out per symbol) and the lots still open."""
    start = day.tz_localize("America/New_York")
    r = requests.get(LV.TRADE + "/orders", headers=LV.headers(), timeout=30,
                     params={"status": "all", "after": start.isoformat(), "until": (start + pd.Timedelta(days=1)).isoformat(),
                             "limit": 500, "nested": "true", "direction": "asc"})
    r.raise_for_status()
    fills = []
    for o in r.json():
        for y in [o] + (o.get("legs") or []):
            q = float(y.get("filled_qty") or 0)
            if q:
                fills.append(dict(t=pd.Timestamp(y["filled_at"]), sym=y["symbol"], side=1 if y["side"] == "buy" else -1, q=int(q),
                                  px=float(y["filled_avg_price"]), kind=y["type"], cid=o["client_order_id"],
                                  strat=strat_of(o["client_order_id"])))
    fills.sort(key=lambda f: f["t"])
    lots: dict[str, deque] = defaultdict(deque)
    rows = []
    for f in fills:
        book = lots[f["sym"]]
        qty = f["q"]
        while qty and book and book[0]["side"] == -f["side"]:
            lot = book[0]
            n = min(qty, lot["q"])
            pnl = (f["px"] - lot["px"]) * lot["side"] * n
            rows.append(dict(t_in=lot["t"], t_out=f["t"], sym=f["sym"], strat=lot["strat"] or "-", side="long" if lot["side"] > 0 else "short",
                             q=n, entry=lot["px"], exit=f["px"], pnl=pnl, how=how(f["kind"], f["cid"])))
            lot["q"] -= n
            qty -= n
            if lot["q"] == 0:
                book.popleft()
        if qty:
            book.append(dict(t=f["t"], side=f["side"], q=qty, px=f["px"], strat=f["strat"]))
    rows.sort(key=lambda x: (x["t_in"], x["t_out"]))
    return rows, [(s, l) for s, b in lots.items() for l in b]


def main() -> None:
    day = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.now(tz=MST).strftime("%Y-%m-%d"))
    rows, open_lots = get_pieces(day)
    a = requests.get(LV.TRADE + "/account", headers=LV.headers(), timeout=30).json()
    eq, last = float(a["equity"]), float(a["last_equity"])

    def t(ts):
        return ts.tz_convert(MST).strftime("%H:%M")
    print(f"# End of day report, {day:%a %b %d %Y}\n")
    if rows:
        print("| # | In | Out | Stock | Strategy | Side | Shares | Entry | Exit | $ P/L | How it ended |")
        print("|--:|----|-----|-------|----------|------|-------:|------:|-----:|----:|--------------|")
        for i, x in enumerate(rows, 1):
            print(f"| {i} | {t(x['t_in'])} | {t(x['t_out'])} | {x['sym']} | {x['strat']} | {x['side']} | {x['q']} | {x['entry']:.2f} | "
                  f"{x['exit']:.2f} | {'+' if x['pnl'] >= 0 else '-'}${abs(x['pnl']):,.0f} | {x['how']} |")
    else:
        print("No trades today.")
    for s, l in open_lots:
        print(f"\nSTILL OPEN: {s} {l['q']} shares {'long' if l['side'] > 0 else 'short'} from {l['px']:.2f}")
    print("\n## Totals\n")
    df = pd.DataFrame(rows)
    if len(df):
        # one trade = one position opened (a breakout sold in thirds counts once); it wins if it made money overall
        tr = df.groupby(["strat", "sym", "t_in"]).pnl.sum().reset_index()
        g = tr.groupby("strat").agg(trades=("pnl", "size"), wins=("pnl", lambda x: int((x > 0).sum())), pnl=("pnl", "sum"))
        print("| Strategy | Trades | Won | % win | $ P/L | % P/L |\n|----------|-------:|----:|------:|------:|------:|")
        for s, x in g.iterrows():
            print(f"| {s} | {int(x.trades)} | {int(x.wins)} | {x.wins / x.trades:.0%} | {'+' if x.pnl >= 0 else '-'}${abs(x.pnl):,.0f} | {x.pnl / last:+.2%} |")
        tot, nw = tr.pnl.sum(), int((tr.pnl > 0).sum())
        print(f"| **All trades** | {len(tr)} | {nw} | {nw / len(tr):.0%} | **{'+' if tot >= 0 else '-'}${abs(tot):,.0f}** | **{tot / last:+.2%}** |")
    print(f"\nAccount equity: ${last:,.2f} -> ${eq:,.2f} (**{'+' if eq >= last else '-'}${abs(eq - last):,.2f}**)")
    p = Path("logs/live") / f"{day:%Y-%m-%d}.jsonl"
    if p.exists():
        latest = {}
        for line in p.read_text().splitlines():
            d = json.loads(line)
            if not d.get("strategy"):
                latest[(d["sym"], d["tf"], d["signal_close"], d["type"])] = d
        skipped = [d for d in latest.values() if d["status"] not in ("closed", "filled")]
        if skipped:
            print("\n## Signals that never traded\n")
            print("| Signal (MST) | Stock | Candle | Side | Why not |\n|--------------|-------|--------|------|---------|")
            for d in skipped:
                why = (d.get("exit_reason") or d["status"])
                why = "not enough buying power" if "buying_power" in why else why[:45]
                print(f"| {(pd.Timestamp(d['signal_close']) - pd.Timedelta(hours=2)):%H:%M} | {d['sym']} | {d['tf']} {d['type'].replace('_', ' ').lower()} | "
                      f"{'long' if d['side'] > 0 else 'short'} | {why} |")


if __name__ == "__main__":
    main()
