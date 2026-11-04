"""Premier candles and climaxes at 1h / 4h / daily fair value gaps: live paper trading, or replay of a past day.

  Replay a past day (no orders sent; SIP data):
    python scripts/live_signals.py --replay 2026-11-03 --symbols TSLA
  Live alerts only (no orders), real-time IEX data, run during market hours:
    python scripts/live_signals.py --symbols TSLA NVDA AAPL
  Live with Alpaca PAPER bracket orders (needs ALPACA_API_KEY / ALPACA_SECRET_KEY for the paper account):
    python scripts/live_signals.py --paper --symbols TSLA NVDA AAPL --risk 50 --target 0.3%

Options: --tfs 2m 5m 9m 15m   --families premier climax   --target 0.3% | 1R | 2R (R = the candle-based stop distance)   --risk <dollars per trade>
         --max-notional <max dollars of stock per position, default 100000>
         --no-gap (do not require a 1h/4h/D gap)
         --no-trend-filter (shorts are skipped by default when price is above session VWAP or the 5m EMA9 is above EMA21)
Every signal, order, fill and exit is appended to logs/live/<date>.jsonl; a summary prints at the end of the day.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import live as LV  # noqa: E402

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


def mst(t: pd.Timestamp) -> str:
    return (t - pd.Timedelta(hours=2)).strftime("%H:%M")


def announce(p: LV.Plan) -> None:
    side = "SHORT below" if p.side < 0 else "LONG above"
    print(f"[{mst(p.signal_close)} MST] {p.sym} {p.tf} {p.type} at {p.gap} gap -> {side} {p.entry:.2f}, "
          f"stop {p.stop:.2f}, target {p.target:.2f}, qty {p.qty} (valid until {mst(p.valid_until)})", flush=True)


def replay(cfg: LV.Config, day: str) -> None:
    d = pd.Timestamp(day)
    hist = LV.fetch_bars(cfg.symbols, d - pd.Timedelta(days=45), d + pd.Timedelta(days=1), feed="sip")
    daily = LV.fetch_bars(cfg.symbols, d - pd.Timedelta(days=500), d, tf="1Day", feed="sip")
    eng = LV.Engine(cfg, hist, daily)
    for sym in cfg.symbols:
        m = hist[sym]
        today = m[m.index.normalize() == d]
        for t, bar in today.iterrows():
            eng.manage_sim(sym, bar, t)
            now = t + pd.Timedelta(minutes=1)
            for p in eng.signals(sym, m[m.index < now], now):
                eng.plans.append(p)
                announce(p)
    s = eng.summary()
    print("\nReplay summary (simulated fills at the trigger level or the bar's open if it gapped through):")
    print(s.to_string(index=False) if len(s) else "no signals")


def live(cfg: LV.Config, paper: bool) -> None:
    clock = requests.get(LV.TRADE + "/clock", headers=LV.headers(), timeout=30).json()
    if not clock.get("is_open"):
        print(f"Market closed. Next open: {clock.get('next_open')}")
        return
    now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    hist = LV.fetch_bars(cfg.symbols, now - pd.Timedelta(days=45), now, feed="iex")
    daily = LV.fetch_bars(cfg.symbols, now - pd.Timedelta(days=500), now - pd.Timedelta(minutes=20), tf="1Day", feed="sip")
    eng = LV.Engine(cfg, hist, daily)
    print(f"Watching {', '.join(cfg.symbols)} on {', '.join(cfg.tfs)} ({'PAPER ORDERS' if paper else 'alerts only'})", flush=True)
    while True:
        now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
        boundary = now.floor("min")
        if boundary - boundary.normalize() >= pd.Timedelta(hours=15, minutes=50):
            if paper:
                LV.Engine.flatten()
            break
        today = LV.fetch_bars(cfg.symbols, boundary.normalize() + pd.Timedelta(hours=9, minutes=30), boundary, feed="iex")
        if paper:
            eng.refresh_busy()               # never double up after a restart
        for sym in cfg.symbols:
            m = pd.concat([hist[sym][hist[sym].index.normalize() < boundary.normalize()], today.get(sym, pd.DataFrame())])
            m = m[m.index < boundary]
            last_bar = m.iloc[-1] if len(m) else None
            for p in eng.plans:
                if paper and p.sym == sym and p.status in ("submitted", "filled"):
                    before = p.status
                    eng.poll(p, last_bar, boundary)
                    if p.status != before:
                        eng.log(p.status, p)
                        px = p.exit if p.status == "closed" else p.fill
                        print(f"[{mst(boundary)} MST] {p.sym} {p.status} {f'{px:.2f}' if px else ''} {p.exit_reason}", flush=True)
            for p in eng.signals(sym, m, boundary):
                eng.plans.append(p)
                announce(p)
                if paper:
                    eng.submit(p)
                eng.log("signal", p)
        time.sleep(max(1.0, 65 - (pd.Timestamp.now(tz="America/New_York").tz_localize(None) - boundary).total_seconds()))
    s = eng.summary()
    print("\nEnd of day summary:")
    print(s.to_string(index=False) if len(s) else "no signals")
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    s.to_csv(cfg.log_dir / f"{boundary:%Y-%m-%d}_summary.csv", index=False)


def flatten_and_report(day: str | None) -> None:
    """Safety net: cancel every open order, close every position, print the day's log."""
    LV.Engine.flatten()
    d = day or pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")
    p = Path("logs/live") / f"{d}.jsonl"
    print(f"Flattened. Log {p}: " + (p.read_text() if p.exists() else "no entries today"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=MAG7)
    ap.add_argument("--tfs", nargs="+", default=["2m", "5m", "9m", "15m"])
    ap.add_argument("--families", nargs="+", default=["premier", "climax"])
    ap.add_argument("--risk", type=float, default=50.0, help="dollars risked per trade")
    ap.add_argument("--max-notional", type=float, default=100_000.0, help="max dollars of stock per position")
    ap.add_argument("--target", default="0.3%", help="0.3%% style percent from the entry, or a multiple of the stop distance like 1R / 2R")
    ap.add_argument("--no-gap", action="store_true", help="do not require a 1h/4h/D fair value gap")
    ap.add_argument("--no-trend-filter", action="store_true", help="allow shorts even when price is above VWAP or 5m EMA9 > EMA21")
    ap.add_argument("--paper", action="store_true", help="place Alpaca PAPER bracket orders")
    ap.add_argument("--replay", help="YYYY-MM-DD: replay a past day, no orders")
    ap.add_argument("--flatten", action="store_true", help="cancel all paper orders, close all positions, print today's log")
    a = ap.parse_args()
    cfg = LV.Config(symbols=[s.upper() for s in a.symbols], tfs=tuple(a.tfs), families=tuple(a.families),
                    risk_usd=a.risk, max_notional=a.max_notional, target=a.target, require_gap=not a.no_gap, short_trend_filter=not a.no_trend_filter)
    if a.flatten:
        flatten_and_report(None)
    elif a.replay:
        replay(cfg, a.replay)
    else:
        live(cfg, a.paper)


if __name__ == "__main__":
    main()
