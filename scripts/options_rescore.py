"""Re-score the paper account's real trades as the option you would buy instead of the stock (step 5).

For every position (same entry and exit minutes as the stock trade, half exits included piece by piece):
long -> call, short -> put; three expiries (nearest, about a week, about a month) x two strikes (at the money,
one strike out of the money). Prices = Alpaca's historical 1-minute option trade bars (last trade at or before the
minute, at most 15 minutes old; otherwise that contract is skipped). Costs: Alpaca's bars are trades, not quotes,
so a round-trip spread is charged from today's quoted spreads (indicative feed) for the same symbol / expiry / strike
bucket, i.e. half the spread on the way in and half on the way out.
Result per trade: % return on the premium paid. "Equal risk" compares with the stock: if you spend the trade's
planned risk on premium (so the most you can lose matches the stock stop), option P/L in R = % return on premium.

  python scripts/options_rescore.py   -> reports/options_rescore.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import live as LV  # noqa: E402
from vpa_trading.alpaca import _headers  # noqa: E402
import eod_report as E  # noqa: E402

DATA = "https://data.alpaca.markets/v1beta1/options"
CACHE = Path("results/options_cache")
RISK = {"Candle scanner": 1000, "Alert mode": 500, "Banks level": 1000, "Key level": 300}
S = requests.Session()


def contracts(sym, day):
    p = CACHE / f"contracts_{sym}_{day}.pkl"
    if p.exists():
        return pd.read_pickle(p)
    rows, tok = [], None
    d0 = pd.Timestamp(day)
    while True:
        params = {"underlying_symbols": sym, "expiration_date_gte": f"{d0:%Y-%m-%d}",
                  "expiration_date_lte": f"{d0 + pd.Timedelta(days=40):%Y-%m-%d}", "limit": 10000}
        if tok:
            params["page_token"] = tok
        out = []
        for status in ("active", "inactive"):
            params["status"] = status
            j = S.get(LV.TRADE + "/options/contracts", headers=_headers(), params=params, timeout=60).json()
            out += j.get("option_contracts") or []
        rows += out
        tok = None
        break
    df = pd.DataFrame([{"occ": c["symbol"], "type": c["type"], "exp": pd.Timestamp(c["expiration_date"]),
                        "strike": float(c["strike_price"])} for c in rows]).drop_duplicates("occ")
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_pickle(p)
    return df


def bars(occ, day):
    p = CACHE / f"bars_{occ}_{day}.pkl"
    if p.exists():
        return pd.read_pickle(p)
    j = S.get(DATA + "/bars", headers=_headers(), timeout=60,
              params={"symbols": occ, "timeframe": "1Min", "start": f"{day}T13:00:00Z", "end": f"{day}T21:30:00Z", "limit": 10000}).json()
    b = pd.DataFrame((j.get("bars") or {}).get(occ, []))
    if len(b):
        b["t"] = pd.to_datetime(b.t, utc=True)
        b = b.set_index("t")
    b.to_pickle(p)
    return b


def px_at(b, t):
    if not len(b):
        return np.nan
    x = b[b.index <= t + pd.Timedelta(seconds=59)]
    if not len(x) or t - x.index[-1] > pd.Timedelta(minutes=15):
        return np.nan
    return float(x.c.iat[-1])


def pick(ch, kind, spot, day, bucket, otm):
    d = pd.Timestamp(day)
    c = ch[ch.type == kind]
    min_exp = {"nearest": d, "week": d + pd.Timedelta(days=5), "month": d + pd.Timedelta(days=25)}[bucket]
    c = c[c.exp >= min_exp]
    if not len(c):
        return None
    c = c[c.exp == c.exp.min()]
    ks = np.sort(c.strike.unique())
    atm = ks[np.argmin(np.abs(ks - spot))]
    i = int(np.searchsorted(ks, atm))
    if otm:
        i = i + 1 if kind == "call" else i - 1
        if not 0 <= i < len(ks):
            return None
    return c[c.strike == ks[i]].occ.iat[0], (c.exp.iat[0] - d).days


def spreads():
    """Today's quoted spread (ask-bid)/mid by symbol x expiry bucket x moneyness, from the indicative snapshots."""
    out = {}
    for sym in ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]:
        spot = float(S.get(f"https://data.alpaca.markets/v2/stocks/{sym}/trades/latest", headers=_headers(), timeout=30).json()["trade"]["p"])
        day = pd.Timestamp.now().normalize()
        ch = contracts(sym, f"{day:%Y-%m-%d}")
        for bucket in ("nearest", "week", "month"):
            for otm in (False, True):
                vals = []
                for kind in ("call", "put"):
                    pk = pick(ch, kind, spot, f"{day:%Y-%m-%d}", bucket, otm)
                    if not pk:
                        continue
                    j = S.get(DATA + f"/snapshots/{sym}", headers=_headers(), timeout=30,
                              params={"feed": "indicative", "symbols": pk[0]} if False else {"feed": "indicative"}).json()
                    q = (j.get("snapshots") or {}).get(pk[0], {}).get("latestQuote")
                    if not q:
                        r = S.get(DATA + "/quotes/latest", headers=_headers(), timeout=30,
                                  params={"symbols": pk[0], "feed": "indicative"}).json()
                        q = (r.get("quotes") or {}).get(pk[0])
                    if q and q.get("ap") and q.get("bp") and q["ap"] > q["bp"] > 0:
                        vals.append((q["ap"] - q["bp"]) / ((q["ap"] + q["bp"]) / 2))
                out[(sym, bucket, otm)] = float(np.median(vals)) if vals else np.nan
    return out


def main():
    now = pd.Timestamp.now(tz="America/New_York")
    cal = requests.get(LV.TRADE + "/calendar", headers=LV.headers(), timeout=30,
                       params={"start": "2026-11-04", "end": f"{now:%Y-%m-%d}"}).json()
    pieces = []
    for c in cal:
        pc, _ = E.get_pieces(pd.Timestamp(c["date"]))
        pieces += [dict(p, day=c["date"]) for p in pc]
    pc = pd.DataFrame(pieces)
    pc = pc[pc.strat != "TSLA breakout"].copy() if False else pc
    sp = spreads()
    rows = []
    for (strat, sym, t_in, day), g in pc.groupby(["strat", "sym", "t_in", "day"]):
        kind = "call" if g.side.iat[0] == "long" else "put"
        spot = float(g.entry.iat[0])
        q = g.q.sum()
        stock_pnl = float(g.pnl.sum())
        r = {"day": day, "sym": sym, "strat": strat, "side": g.side.iat[0], "stock_pnl": stock_pnl,
             "stock_pct": float((g.pnl / (g.entry * g.q)).mul(g.q).sum() / q * 100),
             "minutes": float(((g.t_out - g.t_in).dt.total_seconds() / 60 * g.q).sum() / q)}
        ch = contracts(sym, day)
        for bucket in ("nearest", "week", "month"):
            for otm in (False, True):
                key = f"{bucket}_{'otm' if otm else 'atm'}"
                pk = pick(ch, kind, spot, day, bucket, otm)
                if not pk:
                    continue
                occ, dte = pk
                b = bars(occ, day)
                p0 = px_at(b, t_in)
                exits = [(px_at(b, t), n) for t, n in zip(g.t_out, g.q)]
                if not p0 == p0 or any(not e == e for e, _ in exits):
                    continue
                gross = sum((e / p0 - 1) * n for e, n in exits) / q * 100
                cost = sp.get((sym, bucket, otm), np.nan) * 100
                r[key] = gross - (cost if cost == cost else 0)
                r[key + "_gross"], r[key + "_dte"], r[key + "_prem"] = gross, dte, p0
        rows.append(r)
    t = pd.DataFrame(rows)
    t.to_csv("results/options_rescore.csv", index=False)
    risk = t.strat.map(RISK)
    t["stock_R"] = t.stock_pnl / risk
    L = ["# Paper trades re-scored as options\n", __doc__.split("\n\n")[1], "",
         f"{len(t)} positions, {t.day.min()} to {t.day.max()}. Median holding time {t.minutes.median():.0f} minutes.\n",
         "Today's quoted round-trip spread used as the cost (median of call and put, % of the option's mid):\n",
         "| Stock | Nearest ATM | Nearest OTM | Week ATM | Week OTM | Month ATM | Month OTM |", "|---|--:|--:|--:|--:|--:|--:|"]
    for sym in sorted({k[0] for k in sp}):
        L.append(f"| {sym} | " + " | ".join(f"{sp.get((sym, b, o), np.nan) * 100:.1f}%" for b in ("nearest", "week", "month") for o in (False, True)) + " |")
    L += ["\n## Average result per trade\n",
          "| Instrument | Trades priced | Avg % on premium (after spread) | Before spread | Won | Typical days to expiry |",
          "|---|--:|--:|--:|--:|--:|"]
    L.append(f"| Stock (what the account did), % of position | {len(t)} | {t.stock_pct.mean():+.2f}% | | {100 * (t.stock_pnl > 0).mean():.0f}% | |")
    for key, nm in (("nearest_atm", "Nearest expiry, at the money"), ("nearest_otm", "Nearest expiry, 1 strike out"),
                    ("week_atm", "About 1 week, at the money"), ("week_otm", "About 1 week, 1 strike out"),
                    ("month_atm", "About 1 month, at the money"), ("month_otm", "About 1 month, 1 strike out")):
        if key not in t:
            continue
        x = t[key].dropna()
        L.append(f"| {nm} | {len(x)} | {x.mean():+.1f}% | {t[key + '_gross'].dropna().mean():+.1f}% | "
                 f"{100 * (x > 0).mean():.0f}% | {t[key + '_dte'].median():.0f} |")
    e = t.dropna(subset=["stock_R"])
    L += ["\n## Equal risk: spend the trade's planned risk on premium\n",
          "Stock R = the account's P/L / planned risk ($1,000 scanner, $500 alert, $300 key level). Option R = % on premium / 100 "
          "(the premium is the most you can lose, like the stop). Breakout trades excluded (no fixed planned risk).\n",
          "| Instrument | Trades | Average R | Total R |", "|---|--:|--:|--:|",
          f"| Stock | {len(e)} | {e.stock_R.mean():+.3f} | {e.stock_R.sum():+.1f} |"]
    for key in ("nearest_atm", "nearest_otm", "week_atm", "week_otm", "month_atm", "month_otm"):
        if key in e:
            x = e[key].dropna() / 100
            L.append(f"| {key.replace('_', ' ')} | {len(x)} | {x.mean():+.3f} | {x.sum():+.1f} |")
    L += ["\n## By strategy (about 1 week, at the money, after spread)\n", "| Strategy | Trades | Stock % | Option % on premium | Option won |", "|---|--:|--:|--:|--:|"]
    for s, g in t.groupby("strat"):
        x = g.get("week_atm", pd.Series(dtype=float)).dropna()
        L.append(f"| {s} | {len(g)} | {g.stock_pct.mean():+.2f}% | {x.mean():+.1f}% | {100 * (x > 0).mean():.0f}% |")
    Path("reports/options_rescore.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
