"""Compare my own calls (data/my_calls.csv) with what the live scanner did, and say why a call was missed.

  python scripts/compare_calls.py                 # every call in the file
  python scripts/compare_calls.py --date 2026-11-04

For each call with a time and a timeframe (time_mst = the START of the candle on a chart in MST):
  - was there a scanner signal on that symbol and side within 15 minutes of the candle's close?
  - if not: did the candle have a premier shape (shooting star / hammer), did the context rule pass,
    was it at an unfilled 1h / 4h / D gap, and would the short trend filter have blocked it?
  - what a trade on it would have done with the scanner's own entry / stop / 1R target rules (simulated on 1m bars).
Calls without a time or timeframe are only listed (add them to the csv once known). Uses IEX bars like the live scanner.
Append new calls to data/my_calls.csv: date,time_mst,symbol,tf,side(long|short),note
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from vpa_trading import live as LV, vpa  # noqa: E402


def scanner_signals(day: str) -> list[dict]:
    p = ROOT / "logs/live" / f"{day}.jsonl"
    if not p.exists():
        return []
    return [d for d in map(json.loads, p.read_text().splitlines()) if d["kind"] == "signal"]


def shapes(b: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    rng = b.high - b.low
    top, bot = b[["open", "close"]].max(axis=1), b[["open", "close"]].min(axis=1)
    body, upw, low_w = (b.close - b.open).abs(), b.high - top, bot - b.low
    star = (upw >= 2 * body) & (upw >= 0.5 * rng) & (low_w <= 0.15 * rng) & (top <= b.low + rng / 3)
    ham = (low_w >= 2 * body) & (low_w >= 0.5 * rng) & (upw <= 0.15 * rng) & (bot >= b.high - rng / 3)
    return star, ham


def diagnose(sym: str, tf: str, side: int, start_et: pd.Timestamp, hist, daily) -> None:
    step = pd.Timedelta(tf.replace("m", "min"))
    close = start_et + step
    b = LV.frame(hist, tf)
    if start_et not in b.index:
        print("   no candle at that time in the data")
        return
    r = b.loc[start_et]
    rng = r.high - r.low
    star, ham = shapes(b)
    c = vpa.context(b, b.atr).loc[start_et]
    print(f"   candle O {r.open:.2f} H {r.high:.2f} L {r.low:.2f} C {r.close:.2f}  range {rng / r.atr:.2f} ATR")
    shape = bool(star[start_et]) if side < 0 else bool(ham[start_et])
    print(f"   premier shape ({'shooting star' if side < 0 else 'hammer'}): {'yes' if shape else 'NO'}")
    print(f"   context: trend {int(c.trend)}, near_high {bool(c.near_high)}, near_low {bool(c.near_low)} -> "
          f"{'passes' if ((side < 0 and (c.trend == 1 or c.near_high)) or (side > 0 and (c.trend == -1 or c.near_low))) else 'FAILS the context rule (needs a prior rise / at highs for a star, prior fall / at lows for a hammer)'}")
    eng = LV.Engine(LV.Config(symbols=[sym], risk_usd=1000.0, target="1R"), {sym: hist}, daily)  # same settings as the live run
    m = hist[hist.index + pd.Timedelta(minutes=1) <= close]
    a5 = float(LV.frame(m, "5m").atr.iloc[-1])
    wick = float(r.high if side < 0 else r.low)
    gap = eng._at_gap(eng._gaps(sym, m, close), wick, side, a5)
    print(f"   at a 1h/4h/D fair value gap: {gap if gap != '-' else 'NO'}")
    if side < 0:
        why = eng._uptrend(m, LV.frame(m, "5m"), close)
        print(f"   short trend filter: {'would block (' + why + ')' if why else 'passes'}")
    p = eng._plan(sym, tf, "manual", "my call", side, close, float(r.high), float(r.low), wick, gap)
    if not p:
        print("   no valid plan (stop too tight)")
        return
    eng.plans.append(p)
    for t, bar in hist[(hist.index >= close) & (hist.index < close.normalize() + pd.Timedelta(hours=15, minutes=50))].iterrows():
        eng.manage_sim(sym, bar, t)
        if p.status in ("closed", "cancelled"):
            break
    print(f"   scanner rules on this candle: entry {p.entry:.2f} stop {p.stop:.2f} target {p.target:.2f} qty {p.qty} -> {p.status}"
          + (f" ({p.exit_reason})" if p.exit_reason else "")
          + (f", {'+' if (p.exit - p.fill) * p.side * p.qty >= 0 else '-'}${abs((p.exit - p.fill) * p.side * p.qty):,.0f}" if p.status == "closed" else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--file", default=str(ROOT / "data/my_calls.csv"))
    a = ap.parse_args()
    calls = pd.read_csv(a.file, dtype=str).fillna("")
    if a.date:
        calls = calls[calls.date == a.date]
    cache: dict = {}
    for _, c in calls.iterrows():
        side = 1 if c.side.lower().startswith("l") else -1
        print(f"\n{c.date} {c.time_mst or '--:--'} MST  {c.symbol} {c.tf or '?'} {c.side.upper()}  ({c.note})")
        if not c.time_mst or not c.tf:
            print("   no time/timeframe recorded: not compared")
            continue
        step = pd.Timedelta(c.tf.replace("m", "min"))
        start_et = pd.Timestamp(f"{c.date} {c.time_mst}") + pd.Timedelta(hours=2)
        sigs = [s for s in scanner_signals(c.date) if s["sym"] == c.symbol and s["side"] == side
                and abs(pd.Timestamp(s["signal_close"]) - (start_et + step)) <= pd.Timedelta(minutes=15)]
        if sigs:
            for s in sigs:
                print(f"   SCANNER CAUGHT IT: {s['tf']} {s['type']} at {(pd.Timestamp(s['signal_close']) - pd.Timedelta(hours=2)):%H:%M} MST, status {s['status']}")
            continue
        print("   scanner did NOT signal. Why:")
        key = (c.symbol, c.date)
        if key not in cache:
            d = pd.Timestamp(c.date)
            h = LV.fetch_bars([c.symbol], d - pd.Timedelta(days=45), d + pd.Timedelta(days=1), feed="iex")[c.symbol]
            dl = LV.fetch_bars([c.symbol], d - pd.Timedelta(days=500), d, tf="1Day", feed="sip")
            cache[key] = (h, dl)
        diagnose(c.symbol, c.tf, side, start_et, *cache[key])


if __name__ == "__main__":
    main()
