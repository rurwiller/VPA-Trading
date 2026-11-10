"""Premier candles and climaxes at 1h / 4h / daily fair value gaps: live paper trading, or replay of a past day.

  Replay a past day (no orders sent; SIP data):
    python scripts/live_signals.py --replay 2026-11-03 --symbols TSLA
  Live alerts only (no orders), real-time IEX data, run during market hours:
    python scripts/live_signals.py --symbols TSLA NVDA AAPL
  Live with Alpaca PAPER bracket orders (needs ALPACA_API_KEY / ALPACA_SECRET_KEY for the paper account):
    python scripts/live_signals.py --paper --symbols TSLA NVDA AAPL --risk 50 --target 0.3%

Options: --tfs 9m 15m (default)   --families premier climax   --target 0.3% | 1R | 2R (R = the candle-based stop distance)   --risk <dollars per trade>
         --max-notional <max dollars of stock per position, default 100000>
         --no-gap (do not require a 1h/4h/D gap)
         --breakout TSLA (trend-day noise-band breakout, default TSLA; --breakout with nothing after it disables it)
         --breakout-notional 100000
         --trend-filter (skip shorts when price is above session VWAP or the 5m EMA9 is above EMA21; off by default)
Every signal, order, fill and exit is appended to logs/live/<date>.jsonl; a summary prints at the end of the day.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import gex as GX, live as LV  # noqa: E402
from vpa_trading.alert import AlertMode  # noqa: E402
from vpa_trading.noise_band import NoiseBand  # noqa: E402

MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


def mst(t: pd.Timestamp) -> str:
    return (t - pd.Timedelta(hours=2)).strftime("%H:%M")


def announce(p: LV.Plan) -> None:
    side = "SHORT below" if p.side < 0 else "LONG above"
    print(f"[{mst(p.signal_close)} MST] {p.sym} {p.tf} {p.type} at {p.gap} gap -> {side} {p.entry:.2f}, "
          f"stop {p.stop:.2f}, target {p.target:.2f}, qty {p.qty} (valid until {mst(p.valid_until)})"
          + (" | ADD to the open position" if p.extra.get("add") else "")
          + (f" | tags: EMA {'+'.join(p.tags['near_ema']) or '-'}, gaps {'+'.join(p.tags['gap_tfs']) or '-'}"
             + (" CONFLUENCE" if p.tags.get("confluence") else "") if p.tags and "near_ema" in p.tags else "")
          + (f" | GEX: {p.gex['near'] or 'no level'}, call wall {p.gex['call_wall']:g}, put wall {p.gex['put_wall']:g}, flip {p.gex['flip']}"
             if p.gex else ""), flush=True)


def announce_alert(p: LV.Plan, order: str) -> None:
    t = p.tags
    print(f"[{mst(p.signal_close)} MST] ALERT {p.sym} {p.tf} pivot wick {'TOP' if p.side < 0 else 'BOTTOM'} -> "
          f"{'SHORT below' if p.side < 0 else 'LONG above'} {p.entry:.2f} | stop {p.stop:.2f} target {p.target:.2f} "
          f"qty {p.qty} (${abs(p.entry - p.stop) * p.qty:,.0f} risk) | volume {t['rvol']}x usual, oscillators "
          f"5m {t['osc']['5m']:g} / 9m {t['osc']['9m']:g} / 15m {t['osc']['15m']:g}, wick {t['stretch_atr']} ATR "
          f"{'above' if p.side < 0 else 'below'} the 15m EMA 9 ({t['ema15_9']}) | gap {p.gap} | order: {order}", flush=True)


def alert_order_ok(p: LV.Plan, eng: LV.Engine, aeng: LV.Engine) -> tuple[bool, str]:
    """May an alert-mode order go in? Never opposite to an open trade, never on top of the scanner's own order."""
    reg = [q for q in eng.plans if q.sym == p.sym and q.status in ("planned", "submitted", "filled")]
    if any(q.side != p.side for q in reg):
        return False, "not placed: opposite to an open scanner trade"
    if any(q.signal_close == p.signal_close for q in reg):
        return False, "not placed: the regular scanner has this candle"
    ext = eng.external.get(p.sym, 0)
    if ext and ext != p.side:
        return False, "not placed: opposite to the open breakout / alert position"
    if any(q.sym == p.sym and q.status in ("planned", "submitted", "filled") for q in aeng.plans):
        return False, "not placed: already in an alert-mode trade on it"
    if p.sym in eng.busy and not ext and not reg:
        return False, "not placed: the symbol is busy at Alpaca"
    return True, "placed"


def refresh_gex(cfg: LV.Config, levels: dict, now: pd.Timestamp) -> None:
    """Our own GEX levels from Alpaca options data, appended to logs/gex/<date>.csv (refreshed every 30 min)."""
    rows = []
    for sym in cfg.symbols:
        try:
            levels[sym] = GX.levels(sym, now)
            rows.append({k: v for k, v in levels[sym].items() if not isinstance(v, list)})
        except Exception as e:  # options data is optional: never stop the scanner for it
            print(f"GEX {sym} failed: {e}", flush=True)
    if rows:
        out = Path("logs/gex") / f"{now:%Y-%m-%d}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out, mode="a", header=not out.exists(), index=False)


def tag_gex(p: LV.Plan, levels: dict, m: pd.DataFrame) -> None:
    lv = levels.get(p.sym)
    if not lv or "call_wall" not in lv:
        return
    a5 = float(LV.frame(m, "5m").atr.iloc[-1])
    p.gex = {"near": GX.near(lv, p.wick, a5), "call_wall": lv["call_wall"], "put_wall": lv["put_wall"],
             "flip": lv["flip"], "net_gex_musd": lv["net_gex_musd"], "spot": lv["spot"], "asof": lv["time"]}


def replay(cfg: LV.Config, day: str, breakout: list[str], notional: float, alert_risk: float = 0.0, breakout_exit: bool = True, osc_trim: tuple | None = (80.0, 0.5)) -> None:
    d = pd.Timestamp(day)
    syms = sorted(set(cfg.symbols) | set(breakout))
    end = min(d + pd.Timedelta(days=1), pd.Timestamp.now(tz="America/New_York").tz_localize(None) - pd.Timedelta(minutes=20))
    hist = LV.fetch_bars(syms, d - pd.Timedelta(days=45), end, feed="sip")   # free plan: no SIP from the last 15 min
    daily = LV.fetch_bars(cfg.symbols, d - pd.Timedelta(days=500), d, tf="1Day", feed="sip")
    for sym in breakout:
        nb = NoiseBand(sym, notional, Path("logs/replay"), paper=False, exit_opposite=breakout_exit, osc_trim=osc_trim)
        nb.start_day(hist[sym], None, d)
        today = hist[sym][(hist[sym].index.normalize() == d) & (hist[sym].index.time < pd.Timestamp("16:00").time())]
        for t in today.index:
            nb.on_minute(today[today.index <= t], t + pd.Timedelta(minutes=1), blocked=False, full=hist[sym][hist[sym].index <= t])
        if nb.pos:
            px = float(today.close.iat[-1])
            print(f"NB {sym} still {'long' if nb.pos > 0 else 'short'} at the close {px:.2f}: approx P&L "
                  f"{(px - nb.entry) * nb.pos * nb.qty:+.2f}")
    eng = LV.Engine(cfg, hist, daily)
    aeng = LV.Engine(replace(cfg, risk_usd=alert_risk, families=("premier",), require_gap=False), hist, daily) if alert_risk else None
    alert = AlertMode(aeng) if aeng else None
    for sym in cfg.symbols:
        m = hist[sym]
        today = m[m.index.normalize() == d]
        for t, bar in today.iterrows():
            eng.manage_sim(sym, bar, t)
            if aeng:
                aeng.manage_sim(sym, bar, t)
            now = t + pd.Timedelta(minutes=1)
            for p in eng.signals(sym, m[m.index < now], now):
                eng.plans.append(p)
                announce(p)
            if alert:
                for p in alert.signals(sym, m[m.index < now], now):
                    ok, why = alert_order_ok(p, eng, aeng)
                    announce_alert(p, why.replace("placed", "simulated"))
                    if ok:
                        aeng.plans.append(p)
    s = eng.summary()
    print("\nReplay summary (simulated fills at the trigger level or the bar's open if it gapped through):")
    print(s.to_string(index=False) if len(s) else "no signals")
    if aeng:
        sa = aeng.summary()
        print("\nAlert mode (simulated, half risk):")
        print(sa.to_string(index=False) if len(sa) else "no alerts")


def live(cfg: LV.Config, paper: bool, breakout: list[str], notional: float, alert_risk: float = 0.0, breakout_exit: bool = True, osc_trim: tuple | None = (80.0, 0.5)) -> None:
    clock = requests.get(LV.TRADE + "/clock", headers=LV.headers(), timeout=30).json()
    if not clock.get("is_open"):
        print(f"Market closed. Next open: {clock.get('next_open')}")
        return
    now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    hist = LV.fetch_bars(sorted(set(cfg.symbols) | set(breakout)), now - pd.Timedelta(days=45), now, feed="iex")
    daily = LV.fetch_bars(cfg.symbols, now - pd.Timedelta(days=500), now - pd.Timedelta(minutes=20), tf="1Day", feed="sip")
    eng = LV.Engine(cfg, hist, daily)
    aeng = LV.Engine(replace(cfg, risk_usd=alert_risk, families=("premier",), require_gap=False), hist, daily)
    alert = AlertMode(aeng) if alert_risk else None
    if paper:
        n_stale = LV.Engine.cancel_stale_entries()
        if n_stale:
            print(f"Cancelled {n_stale} unfilled entry order(s) left by an earlier run", flush=True)
    if alert:
        print(f"Candle alert mode on 5m/9m/15m: pivot wick + volume surge + stretch from the 15m EMA 9 + oscillators, "
              f"${alert_risk:,.0f} risk per trade", flush=True)
    nbs = []
    for sym in breakout:
        nb = NoiseBand(sym, notional, cfg.log_dir, paper, exit_opposite=breakout_exit, osc_trim=osc_trim)
        nb.start_day(hist[sym], None, now.normalize())
        nbs.append(nb)
        print(f"Trend-day breakout on {sym}: ${notional:,.0f} per trade, checks every 30 min 10:00-15:30 ET", flush=True)
    gex_levels: dict = {}
    gex_at = None
    print(f"Watching {', '.join(cfg.symbols)} on {', '.join(cfg.tfs)} ({'PAPER ORDERS' if paper else 'alerts only'})", flush=True)
    while True:
        now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
        boundary = now.floor("min")
        if boundary - boundary.normalize() >= pd.Timedelta(hours=15, minutes=50):
            if paper:
                LV.Engine.flatten()
            break
        if gex_at is None or boundary - gex_at >= pd.Timedelta(minutes=30):
            refresh_gex(cfg, gex_levels, boundary)
            gex_at = boundary
        today = LV.fetch_bars(sorted(set(cfg.symbols) | set(breakout)), boundary.normalize() + pd.Timedelta(hours=9, minutes=30), boundary, feed="iex")
        eng.external = {nb.sym: nb.pos for nb in nbs}   # the candle scanner may add to the breakout's direction, never oppose it
        for q in aeng.plans:
            if q.status == "filled":
                eng.external[q.sym] = q.side
        for nb in nbs:                        # before refresh_busy, so the candle scanner sees a new breakout position
            try:
                t = today.get(nb.sym, pd.DataFrame())
                t = t[t.index < boundary] if len(t) else t
                held = any(p.sym == nb.sym and p.status in ("submitted", "filled") for p in eng.plans)
                full = pd.concat([hist[nb.sym][hist[nb.sym].index.normalize() < boundary.normalize()], t]) if len(t) else None
                nb.on_minute(t, boundary, blocked=held, full=full)
            except Exception as e:      # never let the breakout stop the scanner
                print(f"NB {nb.sym} error: {e}", flush=True)
        if paper:
            eng.refresh_busy()               # never double up after a restart
            try:
                LV.Engine.manage_partials(cfg.half_at)     # half at +0.5R, then breakeven (candle and alert trades)
            except Exception as e:
                print(f"half exits error: {e}", flush=True)
        for sym in cfg.symbols:
            m = pd.concat([hist[sym][hist[sym].index.normalize() < boundary.normalize()], today.get(sym, pd.DataFrame())])
            m = m[m.index < boundary]
            last_bar = m.iloc[-1] if len(m) else None
            for e_ in (eng, aeng):
                for p in e_.plans:
                    if paper and p.sym == sym and p.status in ("submitted", "filled"):
                        before = p.status
                        e_.poll(p, last_bar, boundary)
                        if p.status != before:
                            e_.log(p.status, p)
                            px = p.exit if p.status == "closed" else p.fill
                            print(f"[{mst(boundary)} MST] {p.sym} {'(alert mode) ' if e_ is aeng else ''}{p.status} "
                                  f"{f'{px:.2f}' if px else ''} {p.exit_reason}", flush=True)
            for p in eng.signals(sym, m, boundary):
                eng.plans.append(p)
                tag_gex(p, gex_levels, m)
                announce(p)
                if paper:
                    eng.submit(p)
                eng.log("signal", p)
            for p in (alert.signals(sym, m, boundary) if alert else []):
                ok, why = alert_order_ok(p, eng, aeng)
                if ok and paper:
                    aeng.plans.append(p)
                    aeng.submit(p)
                    why = "placed" if p.status == "submitted" else f"not placed: {p.exit_reason}"
                elif ok:
                    why = "alert only"
                tag_gex(p, gex_levels, m)
                announce_alert(p, why)
                aeng.log("signal", p)
        time.sleep(max(1.0, 65 - (pd.Timestamp.now(tz="America/New_York").tz_localize(None) - boundary).total_seconds()))
    s = eng.summary()
    print("\nEnd of day summary:")
    print(s.to_string(index=False) if len(s) else "no signals")
    sa = aeng.summary()
    if len(sa):
        print("\nAlert mode:")
        print(sa.to_string(index=False))
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
    ap.add_argument("--tfs", nargs="+", default=["9m", "15m"])
    ap.add_argument("--families", nargs="+", default=["premier", "climax"])
    ap.add_argument("--risk", type=float, default=50.0, help="dollars risked per trade")
    ap.add_argument("--max-notional", type=float, default=100_000.0, help="max dollars of stock per position")
    ap.add_argument("--target", default="0.3%", help="0.3%% style percent from the entry, or a multiple of the stop distance like 1R / 2R")
    ap.add_argument("--no-gap", action="store_true", help="do not require a 1h/4h/D fair value gap")
    ap.add_argument("--trend-filter", action="store_true", help="skip shorts when price is above VWAP or the 5m EMA9 is above EMA21 (off by default)")
    ap.add_argument("--no-trend-filter", action="store_true", help=argparse.SUPPRESS)   # old flag, now the default
    ap.add_argument("--max-adds", type=int, default=1, help="extra same-direction positions allowed on a symbol already in a trade (0 = off)")
    ap.add_argument("--add-risk", type=float, default=0.0, help="dollars risked on an add (default: the same as --risk)")
    ap.add_argument("--alert-risk", type=float, default=500.0, help="candle alert mode: dollars risked per trade (0 turns the mode off)")
    ap.add_argument("--breakout", nargs="*", default=["TSLA"], help="symbols for the trend-day (noise band) breakout; none to disable")
    ap.add_argument("--no-breakout-exit", action="store_true", help="do not sell the breakout on an opposite high-volume pivot candle")
    ap.add_argument("--breakout-notional", type=float, default=100_000.0, help="dollars of stock per breakout trade")
    ap.add_argument("--half-at", type=float, default=0.5, help="candle and alert trades: take half off at this many R, then breakeven (0 = off)")
    ap.add_argument("--no-breakout-trim", action="store_true", help="breakout: no 15m oscillator trim (half when it crosses 80/20 against)")
    ap.add_argument("--paper", action="store_true", help="place Alpaca PAPER bracket orders")
    ap.add_argument("--replay", help="YYYY-MM-DD: replay a past day, no orders")
    ap.add_argument("--flatten", action="store_true", help="cancel all paper orders, close all positions, print today's log")
    a = ap.parse_args()
    cfg = LV.Config(symbols=[s.upper() for s in a.symbols], tfs=tuple(a.tfs), families=tuple(a.families),
                    risk_usd=a.risk, max_notional=a.max_notional, target=a.target, require_gap=not a.no_gap, short_trend_filter=a.trend_filter,
                    max_adds=a.max_adds, add_risk_usd=a.add_risk, half_at=a.half_at)
    if a.flatten:
        flatten_and_report(None)
    elif a.replay:
        replay(cfg, a.replay, [x.upper() for x in a.breakout], a.breakout_notional, a.alert_risk, not a.no_breakout_exit,
               None if a.no_breakout_trim else (80.0, 0.5))
    else:
        live(cfg, a.paper, [x.upper() for x in a.breakout], a.breakout_notional, a.alert_risk, not a.no_breakout_exit,
               None if a.no_breakout_trim else (80.0, 0.5))


if __name__ == "__main__":
    main()
