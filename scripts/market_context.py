"""Daily market context: the chart reads from the weekly video call, as numbers, for any watchlist.

  python scripts/market_context.py                      # default watchlist, key low = July 2026
  python scripts/market_context.py TSLA NVDA --key-low 2026-07
  python scripts/market_context.py --md > reports/context_today.md

What it reads for each ticker (closed daily bars, SIP):
  trend       above / below the 200-day SMA and whether the 200-day is rising or falling (50-day vs 200-day)
  levels      200-day SMA, 50-day SMA, daily 9 EMA, and the low of a reference month (the "July lows")
  the day     change, gap, close vs open (did it fade?), volume vs its 20-day average
  momentum    RSI(14), distance from the 52-week high
Flags (each with the 10-year evidence where we have it, see reports/market_context.md):
  testing the 200-day from below / reclaimed it / rejected at it
  light-volume up day (the "low-volume walk-up") vs strong up day
  sharp rally into the 200-day (6%+ off the 5-day low and within 2% of it)
  back above / still below the reference low, rejected at it
  rejected at the daily 9 EMA, RSI oversold (not a short) / overbought
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading import live as LV  # noqa: E402

DEFAULT = ["QQQ", "SPY", "IWM", "RSP", "SMH", "MAGS", "TSLA", "NVDA", "AAPL", "AMD", "META", "GOOGL", "MSFT", "AMZN", "MU", "PLTR", "HOOD", "USO"]


def rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def read(sym: str, x: pd.DataFrame, key_low: str) -> dict:
    x = x.copy()
    c = x.close
    x["sma200"], x["sma50"] = c.rolling(200).mean(), c.rolling(50).mean()
    x["ema9"] = c.ewm(span=9, adjust=False).mean()
    x["v20"] = x.volume.rolling(20).mean().shift(1)
    x["rsi"] = rsi(c)
    t, p = x.iloc[-1], x.iloc[-2]
    km = x[x.index.strftime("%Y-%m") == key_low]
    klow = float(km.low.min()) if len(km) else np.nan
    chg = t.close / p.close - 1
    vol = t.volume / t.v20
    vs200 = t.close / t.sma200 - 1
    up3 = t.close / x.close.iloc[-5:].min() - 1          # rally off the lowest close of the last 5 sessions
    flags = []
    rising = t.sma50 > t.sma200
    flags.append(("above" if vs200 > 0 else "below") + (" a rising" if rising else " a falling") + " 200-day")
    if p.close < p.sma200 <= t.close:
        flags.append("reclaimed the 200-day today")
    elif t.high >= t.sma200 > t.close:
        flags.append("tagged the 200-day and closed under it (rejected)")
    elif -0.015 <= vs200 < 0:
        flags.append("testing the 200-day from below")
    if up3 > 0.06 and abs(vs200) <= 0.02:
        flags.append(f"sharp rally ({up3:+.1%} off its 5-day low) into the 200-day")
    if chg > 0 and vol < 0.9:
        flags.append(f"light-volume up day ({vol:.2f}x)")
    elif chg > 0 and vol >= 1.5:
        flags.append(f"strong-volume up day ({vol:.2f}x)")
    elif chg < 0 and vol >= 1.5:
        flags.append(f"heavy-volume down day ({vol:.2f}x)")
    if chg > 0 and t.close < t.open and t.open > p.close:
        flags.append("gapped up and faded (closed under its open)")
    if klow == klow:
        if p.close < klow <= t.close:
            flags.append(f"back above the {key_low} low")
        elif t.high >= klow > t.close:
            flags.append(f"rejected at the {key_low} low")
        elif t.close < klow:
            flags.append(f"still below the {key_low} low")
    if t.high > t.ema9 > t.close and t.close < t.open:
        flags.append("rejected at the daily 9 EMA")
    if t.rsi < 30:
        flags.append("RSI oversold: a poor short")
    elif t.rsi > 70:
        flags.append("RSI overbought")
    return dict(sym=sym, close=t.close, chg=chg, gap=t.open / p.close - 1, vol=vol, sma200=t.sma200, vs200=vs200,
                sma50=t.sma50, ema9=t.ema9, klow=klow, rsi=t.rsi, off_high=t.close / x.high.iloc[-252:].max() - 1,
                flags=flags, date=x.index[-1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--key-low", default="2026-07", help="YYYY-MM: the month whose low is the reference level (default July 2026)")
    ap.add_argument("--md", action="store_true", help="markdown only (for a report file)")
    a = ap.parse_args()
    syms = [s.upper() for s in a.symbols] or DEFAULT
    now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    d = LV.fetch_bars(syms, now - pd.Timedelta(days=500), now - pd.Timedelta(minutes=20), tf="1Day", feed="sip")
    rows = [read(s, d[s], a.key_low) for s in syms if s in d and len(d[s]) > 210]
    day = rows[0]["date"]
    print(f"# Market context, close of {day:%a %b %d %Y}\n")
    print(f"| Ticker | Close | Day | Volume | vs 200-day | 200-day | 50-day | Daily 9 EMA | {a.key_low} low | RSI | Off 52w high |")
    print("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for r in rows:
        print(f"| {r['sym']} | {r['close']:.2f} | {r['chg']:+.1%} | {r['vol']:.2f}x | {r['vs200']:+.1%} | {r['sma200']:.2f} | {r['sma50']:.2f} | "
              f"{r['ema9']:.2f} | {r['klow']:.2f} | {r['rsi']:.0f} | {r['off_high']:+.1%} |")
    print("\n## What each chart is doing\n")
    for r in rows:
        print(f"- **{r['sym']}**: " + "; ".join(r["flags"]) + ".")
    print("\nVolume is the day's volume over its 20-day average. The 10-year evidence behind the flags is in reports/market_context.md.")


if __name__ == "__main__":
    main()
