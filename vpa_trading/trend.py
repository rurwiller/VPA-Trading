"""QQQ 200-day trend sleeve (paper), approved by the user on Nov 25 2026.

Rule (as tested in scripts/daily_trend_test.py): hold while QQQ closes above its 200-day average, otherwise cash.
Checked once a day 15 minutes before the close; the order is a market-on-close order, so the position changes at
the same close the signal uses (the tested assumption). The last price stands in for today's close in the average.
Traded in QQQM (same Nasdaq-100 index, a different ticker) so it never nets against the intraday QQQ breakout in the
same account. The flatten keeps QQQM overnight (live.KEEP_OVERNIGHT). Orders: client_order_id "trend-QQQM-<date>".
Every decision is appended to logs/trend/decisions.csv; logs/trend/done_<date> stops a second run the same day.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from . import live as LV

SIGNAL, TRADE_SYM = "QQQ", "QQQM"
LOG_DIR = Path("logs/trend")
DATA_LATEST = "https://data.alpaca.markets/v2/stocks/{sym}/trades/latest"


def inside(prior_closes: pd.Series, last_px: float) -> tuple[bool, float]:
    """True when last_px is above the 200-day average of the 199 prior closes plus last_px."""
    window = pd.concat([prior_closes.tail(199), pd.Series([last_px])], ignore_index=True)
    sma = float(window.mean())
    return (len(window) == 200 and last_px > sma), sma


def _latest(sym: str) -> float:
    j = requests.get(DATA_LATEST.format(sym=sym), headers=LV.headers(), params={"feed": "iex"}, timeout=30).json()
    return float(j["trade"]["p"])


def _held(sym: str) -> int:
    r = requests.get(LV.TRADE + f"/positions/{sym}", headers=LV.headers(), timeout=30)
    return int(float(r.json()["qty"])) if r.ok else 0


def rebalance(notional: float, now: pd.Timestamp, paper: bool = True) -> str:
    """Run once a day near the close. Returns a one-line description of what it did."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    done = LOG_DIR / f"done_{now:%Y-%m-%d}"
    if done.exists():
        return ""
    daily = LV.fetch_bars([SIGNAL], now - pd.Timedelta(days=420), now - pd.Timedelta(minutes=20), tf="1Day", feed="sip")
    c = daily[SIGNAL].close
    c = c[c.index.normalize() < now.normalize()]
    px = _latest(SIGNAL)
    up, sma = inside(c, px)
    tpx = _latest(TRADE_SYM)
    held = _held(TRADE_SYM) if paper else 0
    target = int(notional // tpx) if up else 0
    diff = target - held
    action = "hold" if diff == 0 else ("buy" if diff > 0 else "sell")
    note = ""
    if diff and paper:
        body = {"symbol": TRADE_SYM, "qty": str(abs(diff)), "side": "buy" if diff > 0 else "sell", "type": "market",
                "time_in_force": "cls", "client_order_id": f"trend-{TRADE_SYM}-{now:%Y%m%d}"}
        r = requests.post(LV.TRADE + "/orders", headers=LV.headers(), json=body, timeout=30)
        if not r.ok:                                   # market-on-close refused (e.g. past the cut-off): plain market
            body.update(time_in_force="day", client_order_id=f"trend-{TRADE_SYM}-{now:%Y%m%d}-mkt")
            r2 = requests.post(LV.TRADE + "/orders", headers=LV.headers(), json=body, timeout=30)
            note = f"close order refused ({r.text[:80]}); market order {'sent' if r2.ok else 'refused: ' + r2.text[:80]}"
        else:
            note = "market-on-close order sent"
    line = (f"QQQ {px:.2f} vs 200-day {sma:.2f} -> {'IN' if up else 'OUT'}; {TRADE_SYM} held {held}, target {target}: "
            f"{action} {abs(diff) if diff else ''} {note}").strip()
    row = pd.DataFrame([{"time": now, "qqq": px, "sma200": round(sma, 2), "inside": up, "qqqm": tpx, "held": held,
                         "target": target, "order": action, "note": note}])
    f = LOG_DIR / "decisions.csv"
    row.to_csv(f, mode="a", header=not f.exists(), index=False)
    if paper:
        done.write_text(line + "\n")
    return line
