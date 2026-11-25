"""The trend-day breakout traded as options instead of stock (step 4 of the overhaul), TSLA and QQQ, Feb 2024 on
(Alpaca's historical option bars start then).

1. Every breakout trade is rebuilt minute by minute with the live rules: checks every 30 minutes from 10:00, entry
   above / below the noise band, thirds sold at +1% and +2% with the stop moved to breakeven after the first, a
   2.5% protective stop, the 15m-oscillator trim of half at 80/20, exit when price is back inside the band (or VWAP),
   out by the close. (Not modelled: the live exit on an opposite high-volume candle.)
2. Each trade is priced as three option choices, bought at the entry minute and sold piece by piece at the stock's
   exit minutes (same fractions): calls for longs, puts for shorts.
     nearest ATM     the nearest expiry (0DTE on most days for QQQ), strike closest to the entry price
     ~1 week ITM     the first expiry at least 5 days out, one strike in the money
     ~2 weeks ATM    the first expiry at least 10 days out, at the money
   Price = the option's last trade at or before the minute (at most 15 minutes old; otherwise the trade is skipped).
3. Costs: Alpaca's history has trades, not quotes, so a round-trip spread is assumed (QQQ 2% nearest / 1% later
   expiries; TSLA 3% / 1.5%, of the option's price), and results are also shown before it.
Comparison at equal risk: the stock is sized by volatility ($1,700 of a typical day's move), the option spends
$1,700 of premium (the most it can lose). Holdout = 2026-05-21 on.

  python scripts/breakout_options.py   -> results/breakout_options.csv, reports/breakout_options.md
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import live as LV, pit, research as R  # noqa: E402
from vpa_trading.alpaca import _headers, load_bars_file  # noqa: E402
import trim_test as T  # noqa: E402
from midcap_test import cost_bps  # noqa: E402

START = pd.Timestamp("2024-02-01")
DATA = "https://data.alpaca.markets/v1beta1/options"
CACHE = Path("results/options_cache")
SPREAD = {("QQQ", "nearest"): 0.02, ("QQQ", "week"): 0.01, ("QQQ", "two_weeks"): 0.01,
          ("TSLA", "nearest"): 0.03, ("TSLA", "week"): 0.015, ("TSLA", "two_weeks"): 0.015}
BUDGET = 1_700.0
GUARD = 0.025
S = requests.Session()


def get(url, params):
    for a in range(6):
        r = S.get(url, headers=_headers(), params=params, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (a + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def contracts(sym, day):
    p = CACHE / f"bc_{sym}_{day:%Y-%m-%d}.pkl"
    if p.exists():
        return pd.read_pickle(p)
    rows = []
    for status in ("inactive", "active"):
        tok = None
        while True:
            params = {"underlying_symbols": sym, "expiration_date_gte": f"{day:%Y-%m-%d}",
                      "expiration_date_lte": f"{day + pd.Timedelta(days=21):%Y-%m-%d}", "status": status, "limit": 10000}
            if tok:
                params["page_token"] = tok
            j = get(LV.TRADE + "/options/contracts", params)
            rows += j.get("option_contracts") or []
            tok = j.get("next_page_token")
            if not tok:
                break
    df = pd.DataFrame([{"occ": c["symbol"], "type": c["type"], "exp": pd.Timestamp(c["expiration_date"]),
                        "strike": float(c["strike_price"])} for c in rows])
    df = df.drop_duplicates("occ") if len(df) else df
    if len(df):
        df = df[df.occ.str.match(rf"^{sym}\d{{6}}[CP]\d{{8}}$")]      # standard contracts only (no adjusted "1TSLA...")
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_pickle(p)
    return df


def bars(occ, day):
    p = CACHE / f"bars_{occ}_{day:%Y-%m-%d}.pkl"
    if p.exists():
        return pd.read_pickle(p)
    try:
        j = get(DATA + "/bars", {"symbols": occ, "timeframe": "1Min", "start": f"{day:%Y-%m-%d}T13:00:00Z",
                                 "end": f"{day:%Y-%m-%d}T21:30:00Z", "limit": 10000})
    except requests.HTTPError:
        j = {}
    b = pd.DataFrame((j.get("bars") or {}).get(occ, []))
    if len(b):
        b["t"] = pd.to_datetime(b.t, utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        b = b.set_index("t")
    b.to_pickle(p)
    return b


def px_at(b, t):
    if not len(b):
        return np.nan
    x = b[b.index <= t]
    if not len(x) or t - x.index[-1] > pd.Timedelta(minutes=15):
        return np.nan
    return float(x.c.iat[-1])


def pick(ch, kind, spot, day, choice):
    if not len(ch):
        return None
    c = ch[ch.type == kind]
    min_exp = {"nearest": day, "week": day + pd.Timedelta(days=5), "two_weeks": day + pd.Timedelta(days=10)}[choice]
    c = c[c.exp >= min_exp]
    if not len(c):
        return None
    c = c[c.exp == c.exp.min()]
    ks = np.sort(c.strike.unique())
    i = int(np.argmin(np.abs(ks - spot)))
    if choice == "week":                                    # one strike in the money
        i = i - 1 if kind == "call" else i + 1
        if not 0 <= i < len(ks):
            return None
    return c[c.strike == ks[i]].occ.iat[0]


def trades(sym):
    """Live breakout rules, minute by minute, recording every exit piece."""
    s = R.prepare(sym, load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False))
    C, O, VW, Hh, Ll, OS = T.matrices(s)
    c, o, vw = C.to_numpy(), O.to_numpy(), VW.to_numpy()
    prev = C.attrs["prev_close"]
    sigma = pd.DataFrame(np.abs(c / o[:, None] - 1)).rolling(14).mean().shift(1).to_numpy()
    cost = cost_bps(sym) / 1e4
    ub0, lb0 = np.fmax(o, prev), np.fmin(o, prev)
    out = []
    for k, day in enumerate(C.index):
        if day < START or np.isnan(sigma[k, T.CHECKS[0]]) or np.isnan(prev[k]):
            continue
        tm = lambda m: day + pd.Timedelta(minutes=570 + m + 1)       # noqa: E731  minute index -> bar close time
        st = None

        def close_piece(m, px, frac):
            st["legs"].append((tm(m), px, frac))
            st["rem"] -= frac

        def finish():
            if st and st["legs"]:
                ret = sum(f * (st["pos"] * (px / st["entry"] - 1)) for _, px, f in st["legs"]) - cost
                out.append({"sym": sym, "day": day, "side": st["pos"], "entry_t": st["t"], "entry": st["entry"],
                            "legs": st["legs"], "stock_ret": ret})
        for ci, t in enumerate(T.CHECKS):
            px = c[k, t]
            ub, lb = ub0[k] * (1 + sigma[k, t]), lb0[k] * (1 - sigma[k, t])
            pos = st["pos"] if st else 0
            want = pos
            if pos == 1 and px < max(ub, vw[k, t]):
                want = 0
            elif pos == -1 and px > min(lb, vw[k, t]):
                want = 0
            if want == 0:
                want = 1 if px > ub else (-1 if px < lb else 0)
            if want != pos:
                if st:
                    close_piece(t, px, st["rem"])
                    finish()
                    st = None
                if want:
                    st = {"pos": want, "entry": px, "t": tm(t), "rem": 1.0, "legs": [],
                          "targets": [px * (1 + want * 0.01), px * (1 + want * 0.02)], "be": False, "armed": False, "trim": False}
            if not st:
                continue
            end = T.CHECKS[ci + 1] if ci + 1 < len(T.CHECKS) else 389
            for b in range(t + 1, end + 1):
                p_, e = st["pos"], st["entry"]
                stop = e if st["be"] else e * (1 - p_ * GUARD)
                if (p_ > 0 and Ll[k, b] <= stop) or (p_ < 0 and Hh[k, b] >= stop):
                    close_piece(b, stop, st["rem"])
                    finish()
                    st = None
                    break
                while st["targets"] and ((Hh[k, b] >= st["targets"][0]) if p_ > 0 else (Ll[k, b] <= st["targets"][0])):
                    close_piece(b, st["targets"].pop(0), min(1 / 3, st["rem"]))
                    st["be"] = True
                v = OS[k, b]
                against = (p_ > 0 and v >= 80) or (p_ < 0 and v <= 20)
                if not against:
                    st["armed"] = True
                elif st["armed"] and not st["trim"] and (c[k, b] - e) * p_ > 0 and st["rem"] > 1e-9:
                    close_piece(b, c[k, b], min(0.5, st["rem"]))
                    st["trim"], st["be"] = True, True
                    if st["targets"]:
                        st["targets"].pop(0)
                if st["rem"] <= 1e-9:
                    finish()
                    st = None
                    break
            if st is None:
                continue
        if st:
            close_piece(389, c[k, 389], st["rem"])
            finish()
    return pd.DataFrame(out)


def price_options(tr):
    rows = []
    for n, r in enumerate(tr.itertuples()):
        day = pd.Timestamp(r.day)
        kind = "call" if r.side > 0 else "put"
        row = {"sym": r.sym, "day": day, "side": r.side, "stock_ret": r.stock_ret,
               "hold_min": sum(f * (t - r.entry_t).total_seconds() / 60 for t, _, f in r.legs)}
        try:
            ch = contracts(r.sym, day)
        except Exception as e:                                # noqa: BLE001
            print("contracts failed", r.sym, day, e, flush=True)
            rows.append(row)
            continue
        for choice in ("nearest", "week", "two_weeks"):
            occ = pick(ch, kind, r.entry, day, choice)
            if not occ:
                continue
            b = bars(occ, day)
            p0 = px_at(b, r.entry_t)
            exits = [(px_at(b, t), f) for t, _, f in r.legs]
            if not p0 == p0 or p0 <= 0 or any(not x == x for x, _ in exits):
                continue
            gross = sum(f * (x / p0 - 1) for x, f in exits)
            row[f"{choice}_gross"] = gross
            row[f"{choice}"] = gross - SPREAD[(r.sym, choice)]
            row[f"{choice}_dte"] = (pd.Timestamp(occ[len(r.sym):len(r.sym) + 6], ) - day).days if False else np.nan
        rows.append(row)
        if n % 50 == 0:
            print(f"{n}/{len(tr)} priced", flush=True)
    return pd.DataFrame(rows)


def vol20(sym):
    from osc_oversold_test import daily
    c = daily(sym).close
    return np.log(c).diff().rolling(20).std().shift(1)


def main():
    out = Path("results/breakout_options.csv")
    if "--cached" in sys.argv and out.exists():
        res = pd.read_csv(out, parse_dates=["day"])
    else:
        tp = Path("results/breakout_trades.pkl")
        tr = pd.read_pickle(tp) if tp.exists() else pd.concat([trades(s) for s in ("TSLA", "QQQ")], ignore_index=True)
        tr.to_pickle(tp)
        print(len(tr), "breakout trades since", START.date(), flush=True)
        res = price_options(tr)
        res.to_csv(out, index=False)
    vols = {s: vol20(s) for s in ("TSLA", "QQQ")}
    res["notional"] = [min(BUDGET / vols[s].get(d, np.nan), 150_000) if vols[s].get(d, np.nan) == vols[s].get(d, np.nan)
                       else 75_000 for s, d in zip(res.sym, res.day)]
    res["stock_usd"] = res.stock_ret * res.notional
    L = ["# The trend-day breakout as options\n", __doc__.split("\n\n")[0], "", __doc__.split("\n\n")[1], "",
         f"{len(res)} trades, {res.day.min():%Y-%m-%d} to {res.day.max():%Y-%m-%d}. Median holding time "
         f"{res.hold_min.median():.0f} minutes.\n"]
    for nm, part in (("All trades", res), ("Before the holdout", res[res.day < pit.HOLDOUT_START]),
                     ("Holdout (2026-05-21 on)", res[res.day >= pit.HOLDOUT_START])):
        L += [f"\n## {nm}\n", "| Instrument | Trades priced | Avg per trade | Before spread | Won | $ per trade at equal risk | Total $ |",
              "|---|--:|--:|--:|--:|--:|--:|"]
        s_ = part.stock_usd.dropna()
        L.append(f"| Stock, vol-sized | {len(s_)} | {part.stock_ret.mean() * 100:+.2f}% of notional | | "
                 f"{(part.stock_ret > 0).mean() * 100:.0f}% | {s_.mean():+.0f} | {s_.sum():+,.0f} |")
        for ch, lab in (("nearest", "Nearest expiry, ATM"), ("week", "~1 week, 1 strike ITM"), ("two_weeks", "~2 weeks, ATM")):
            if ch not in part:
                continue
            x = part[ch].dropna()
            L.append(f"| {lab} | {len(x)} | {x.mean() * 100:+.1f}% of premium | {part[ch + '_gross'].dropna().mean() * 100:+.1f}% | "
                     f"{(x > 0).mean() * 100:.0f}% | {x.mean() * BUDGET:+.0f} | {x.sum() * BUDGET:+,.0f} |")
            both = part.dropna(subset=[ch])
            L.append(f"| (stock on the same {len(both)} trades) | | | | | {both.stock_usd.mean():+.0f} | {both.stock_usd.sum():+,.0f} |")
    for s in ("TSLA", "QQQ"):
        p = res[res.sym == s]
        L += [f"\n### {s}\n", "| Instrument | Trades | Avg per trade | Won | $ per trade at equal risk |", "|---|--:|--:|--:|--:|",
              f"| Stock | {len(p)} | {p.stock_ret.mean() * 100:+.2f}% | {(p.stock_ret > 0).mean() * 100:.0f}% | {p.stock_usd.mean():+.0f} |"]
        for ch in ("nearest", "week", "two_weeks"):
            if ch in p:
                x = p[ch].dropna()
                L.append(f"| {ch} | {len(x)} | {x.mean() * 100:+.1f}% | {(x > 0).mean() * 100:.0f}% | {x.mean() * BUDGET:+.0f} |")
    pit.log_trial("breakout_options", "3 option choices x TSLA/QQQ", len(res), float("nan"), float("nan"))
    Path("reports/breakout_options.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
