"""Live / replay engine: premier candles and climaxes at 1h / 4h / daily fair value gaps -> Alpaca paper bracket orders.

Signal (closed candles only, on each signal timeframe):
  a premier candle (docs/vpa-detection-spec.md shapes, vpa.detect) or a climax (multi-bar climaxes, stopping volume,
  topping-out volume, single-bar climax candidates) whose wick reaches an unfilled 1h / 4h / daily fair value gap on its
  side (bearish signal at a bear gap = resistance, bullish at a bull gap = support), within 0.25 ATR(5m).
Order: bracket, entry = stop order one cent beyond the signal candle's opposite extreme (short below its low, long above
  its high), stop = one cent beyond the wick (+0.02%), target = +0.3% from the entry level (or 2R). Size = risk $ / stop
  distance. Cancelled if not filled within 2 signal candles or if price takes out the wick first. Entries 10:00-15:30 ET,
  one position per symbol; everything is cancelled and flattened at 15:50 ET.
Half at +0.5R (Config.half_at, 0 = off): once the entry fills, the bracket's two legs are swapped for two OCO exit orders,
  half the shares with a limit at +0.5R, the rest with the original target, both with the original stop (client ids
  <entry id>-h1 / -h2). When -h1 takes its profit, -h2 is replaced by -h3 with its stop at the entry fill (breakeven).
  Stateless (read back from Alpaca every minute), so it keeps working across restarts. 5-year test (reports/trim_test.md):
  same expectancy as all-at-1R, profitable trades 49% -> 65%.
Volume (relative volume, climaxes) uses the same feed for history and today, so the IEX feed is used live
(real-time on the free plan); replay uses SIP history.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import indicators as ind
from . import vpa
from .alpaca import to_session_frame
from .data import resample_bars

DATA = "https://data.alpaca.markets/v2/stocks/bars"
TRADE = "https://paper-api.alpaca.markets/v2"
PART = ("-h1", "-h2", "-h3", "-hm")      # suffixes of the half-at-+0.5R exit orders (hm = closed at market)
OPEN = {"new", "accepted", "held", "pending_new", "partially_filled", "pending_replace", "accepted_for_bidding"}
GAP_SESSIONS = {"1h": 5, "4h": 20, "D": 60}
CLIMAX_TYPES = {"SELLING_CLIMAX", "BUYING_CLIMAX", "STOPPING_VOLUME", "TOPPING_OUT_VOLUME"}
PREMIER_TYPES = {"SHOOTING_STAR", "SHOOTING_STAR_IN_DOWNTREND", "HAMMER", "HANGING_MAN", "HANGING_MAN_SHOOTING_STAR"}


def headers() -> dict:
    return {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]}


def _get(url: str, params: dict | None = None) -> dict:
    for k in range(6):
        r = requests.get(url, headers=headers(), params=params, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 + 2 ** k)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def fetch_bars(symbols: list[str], start, end, tf: str = "1Min", feed: str = "iex") -> dict[str, pd.DataFrame]:
    def ts(x):
        x = pd.Timestamp(x)
        return (x.tz_localize("America/New_York") if x.tzinfo is None else x).isoformat()
    params = {"symbols": ",".join(symbols), "timeframe": tf, "start": ts(start), "end": ts(end), "feed": feed,
              "adjustment": "split", "limit": 10000}
    rows: dict[str, list] = {s: [] for s in symbols}
    while True:
        j = _get(DATA, params)
        for s, bs in (j.get("bars") or {}).items():
            rows[s] += bs
        if not j.get("next_page_token"):
            break
        params["page_token"] = j["next_page_token"]
    if tf == "1Min":
        return {s: to_session_frame(r) for s, r in rows.items()}
    out = {}
    for s, r in rows.items():
        d = pd.DataFrame(r).rename(columns={"t": "date", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        if len(d):
            d.index = pd.to_datetime(d.pop("date"), utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
            out[s] = d[["open", "high", "low", "close", "volume"]].astype(float)
    return out


def frame(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    step = pd.Timedelta(tf.replace("m", "min")) if tf.endswith("m") else pd.Timedelta(tf)
    b = resample_bars(m1, tf)
    b["closes_at"] = np.minimum((b.index + step).values, (b.index.normalize() + pd.Timedelta(hours=16)).values)
    b["atr"] = ind.atr(b)
    return b


def live_gaps(b: pd.DataFrame, m1: pd.DataFrame, sessions: int, now: pd.Timestamp) -> pd.DataFrame:
    """Unfilled 3-bar gaps of frame b as of `now` (filled = a later 1m low / high through the far edge)."""
    if len(b) < 20:
        return pd.DataFrame(columns=["dir", "bottom", "top"])
    g = ind.fvgs(b, b.atr, b.volume / b.volume.rolling(20).mean(), b.closes_at, intraday_only=False)
    g = g[(g.formed_at <= now) & (g.formed_at >= now - pd.Timedelta(days=int(sessions * 1.45) + 1))]
    keep = []
    after_all = m1[m1.index + pd.Timedelta(minutes=1) <= now]
    for _, r in g.iterrows():
        a = after_all[after_all.index >= r.formed_at]
        filled = (a.low <= r.bottom).any() if r.dir > 0 else (a.high >= r.top).any()
        keep.append(not filled)
    return g[np.array(keep, bool)] if len(g) else g


def climaxes(b: pd.DataFrame) -> pd.DataFrame:
    det = vpa.detect(b, b.atr)
    det = det[det.type.isin(CLIMAX_TYPES)][["type", "bias"]]
    rv = ind.rvol(b)
    c = ind.climaxes(b, ind.candles(b, b.atr), rv, min_rvol=2.0, min_wick=0.4)
    rows = [det]
    for col, bias, name in (("buy_climax", -1, "single-bar climax top"), ("sell_climax", 1, "single-bar climax bottom")):
        m = c[col].fillna(False)
        rows.append(pd.DataFrame({"type": name, "bias": bias}, index=b.index[m]))
    return pd.concat(rows)


@dataclass
class Config:
    symbols: list[str]
    tfs: tuple = ("9m", "15m")
    families: tuple = ("premier", "climax")
    risk_usd: float = 50.0
    max_notional: float = 100_000.0  # never more than this much stock per position (tight stops would oversize)
    target: str = "0.3%"            # "0.3%" style percent, or k x the stop distance like "1R" / "2R"
    require_gap: bool = True
    require_pivot: bool = True      # the signal candle's wick must be the extreme of the last `pivot_bars` candles
    pivot_bars: int = 12
    long_min_rvol: float = 3.0      # bullish signals only on extremely high volume (time-of-day relative volume)
    max_adds: int = 1               # extra positions on a symbol that is already in a trade (same direction only)
    add_risk_usd: float = 0.0       # risk of an add in dollars; 0 = the same as risk_usd
    half_at: float = 0.5            # take half off at this many R, then the rest goes to breakeven; 0 = all at the target
    short_trend_filter: bool = False   # off: it blocks pivot-high shorts at the top of up-moves (user's choice 2026-11-04)  # shorts only when price is below session VWAP and the 5m EMA9 is below EMA21
    log_dir: Path = Path("logs/live")


@dataclass
class Plan:
    sym: str
    tf: str
    family: str
    type: str
    side: int                        # +1 long, -1 short
    signal_close: pd.Timestamp
    entry: float
    stop: float
    target: float
    wick: float
    qty: int
    valid_until: pd.Timestamp
    gap: str
    order_id: str | None = None
    status: str = "planned"          # planned -> submitted -> filled -> closed | cancelled
    fill: float | None = None
    fill_time: pd.Timestamp | None = None
    exit: float | None = None
    exit_time: pd.Timestamp | None = None
    exit_reason: str = ""
    gex: dict = field(default_factory=dict)   # our gamma levels at signal time (logged, not used as a filter)
    tags: dict = field(default_factory=dict)  # EMA / gap confluence at signal time (logged, not used as a filter)
    extra: dict = field(default_factory=dict)


class Engine:
    exits: dict = {}      # entry client id -> [(qty, px, why)] from the half-at-+0.5R exit orders (shared by both engines)

    def __init__(self, cfg: Config, history: dict[str, pd.DataFrame], daily: dict[str, pd.DataFrame]):
        self.cfg, self.history, self.daily = cfg, history, daily
        self.plans: list[Plan] = []
        self.seen: set = set()
        self.busy: set[str] = set()          # symbols with an open position / order at Alpaca (restart safety)
        self.external: dict[str, int] = {}   # symbols held by another strategy (the breakout) -> its direction

    # ---------------------------------------------------------------- signals
    def signals(self, sym: str, m1: pd.DataFrame, now: pd.Timestamp) -> list[Plan]:
        """Signals whose candle closed exactly at `now` (a 1m boundary)."""
        out = []
        minute = (now - now.normalize()) / pd.Timedelta(minutes=1) - 570
        if not 30 <= minute <= 360:
            return out
        active = [p for p in self.plans if p.sym == sym and p.status in ("planned", "submitted", "filled")]
        filled = [p for p in active if p.status == "filled"]
        ext = self.external.get(sym, 0)
        if len(active) > len(filled) or (sym in self.busy and not ext):
            return out                       # an unfilled order is waiting, or something unknown holds the symbol
        add_dir = None                       # None: no position yet, any direction. Otherwise only adds in this direction
        if filled or ext:
            dirs = {p.side for p in filled} | ({ext} if ext else set())
            if len(filled) + (1 if ext else 0) > self.cfg.max_adds or len(dirs) != 1:
                return out
            add_dir = dirs.pop()
        b5 = frame(m1, "5m")
        a5 = float(b5[b5.closes_at <= now].atr.iloc[-1])
        gaps = None
        for tf in self.cfg.tfs:
            b = frame(m1, tf)
            done = b[b.closes_at <= now]
            if not len(done) or done.closes_at.iloc[-1] != now:
                continue
            t = done.index[-1]
            found = []
            if "premier" in self.cfg.families:
                det = vpa.detect(done, done.atr)
                for _, r in det[(det.index == t) & det.type.isin(PREMIER_TYPES)].iterrows():
                    found.append(("premier", r.type, int(r.bias)))
                # the user's pivot candle: a clear rejection wick (>= 40% of the range and at least the body),
                # small opposite wick. Hammer-shaped candles are no longer traded as shorts (HANGING_MAN).
                o_, h_, l_, c_ = (float(done[k].iat[-1]) for k in ("open", "high", "low", "close"))
                rng = h_ - l_
                if rng > 0:
                    up, dn, body = h_ - max(o_, c_), min(o_, c_) - l_, abs(c_ - o_)
                    if up >= 0.4 * rng and up >= body and dn <= 0.3 * rng and not any(b < 0 for _, _, b in found):
                        found.append(("premier", "PIVOT_WICK_TOP", -1))
                    if dn >= 0.4 * rng and dn >= body and up <= 0.3 * rng and not any(b > 0 for _, _, b in found):
                        found.append(("premier", "PIVOT_WICK_BOTTOM", 1))
                found = [f for f in found if f[1] != "HANGING_MAN"]
            if "climax" in self.cfg.families:
                cl = climaxes(done)
                for _, r in cl[cl.index == t].iterrows():
                    found.append(("climax", r.type, int(r.bias)))
            for fam, typ, bias in found:
                if add_dir is not None and bias != add_dir:
                    continue                 # an opposite signal would only net against the open position
                key = (sym, tf, t, typ)
                if key in self.seen:
                    continue
                self.seen.add(key)
                hi, lo = float(done.high.iat[-1]), float(done.low.iat[-1])
                wick = max(hi, float(done.high.iloc[-3:].max())) if (fam == "climax" and bias < 0) else hi
                if bias > 0:
                    wick = min(lo, float(done.low.iloc[-3:].min())) if fam == "climax" else lo
                if self.cfg.require_pivot:
                    n = self.cfg.pivot_bars
                    if (bias < 0 and wick < float(done.high.iloc[-n:].max())) or (bias > 0 and wick > float(done.low.iloc[-n:].min())):
                        continue        # not the top / bottom of the move: no pivot
                if bias > 0 and self.cfg.long_min_rvol > 0:
                    rv = float(vpa.relvol_tod(done).iat[-1])
                    if not rv >= self.cfg.long_min_rvol:
                        continue        # bullish only on extremely high volume
                if gaps is None:
                    gaps = self._gaps(sym, m1, now)
                gap = self._at_gap(gaps, wick, bias, a5)
                if self.cfg.require_gap and gap == "-":
                    continue
                if bias < 0 and self.cfg.short_trend_filter:
                    why = self._uptrend(m1, b5, now)
                    if why:
                        print(f"[{(now - pd.Timedelta(hours=2)).strftime('%H:%M')} MST] {sym} {tf} {typ} short skipped: {why}", flush=True)
                        continue
                p = self._plan(sym, tf, fam, typ, bias, now, hi, lo, wick, gap,
                               risk_usd=(self.cfg.add_risk_usd or self.cfg.risk_usd) if add_dir is not None else None)
                if p:
                    p.tags = self._tags(sym, m1, now, wick, bias, a5, gaps)
                    if add_dir is not None:
                        p.tags["add"] = True
                        p.extra["add"] = True
                    out.append(p)
        return out[:1]          # one order per symbol: the same candle can count as two signal types

    @staticmethod
    def _uptrend(m1: pd.DataFrame, b5: pd.DataFrame, now: pd.Timestamp) -> str:
        """Reason a short should be skipped (price above VWAP, or 5m EMA9 above EMA21), else ''."""
        px, vw = float(m1.close.iloc[-1]), float(ind.session_vwap(m1).iloc[-1])
        c = b5[b5.closes_at <= now].close
        e9, e21 = float(c.ewm(span=9, adjust=False).mean().iloc[-1]), float(c.ewm(span=21, adjust=False).mean().iloc[-1])
        if px > vw:
            return f"price {px:.2f} above VWAP {vw:.2f}"
        if e9 > e21:
            return f"5m EMA9 {e9:.2f} above EMA21 {e21:.2f}"
        return ""

    def _tags(self, sym: str, m1: pd.DataFrame, now: pd.Timestamp, wick: float, bias: int, a5: float, gaps: dict) -> dict:
        """Which daily / 1h EMAs the wick sits on (within 0.25 ATR(5m)) and which unfilled gaps (15m / 1h / 4h / D) it is in."""
        try:
            lv: dict[str, float] = {}
            d = self.daily.get(sym)
            if d is not None and len(d):
                dc = d[d.index < now.normalize()].close
                px = float(m1.close.iloc[-1])
                for n in (9, 21):      # daily EMA including the current price, as TradingView draws it
                    k = 2 / (n + 1)
                    lv[f"dEMA{n}"] = k * px + (1 - k) * float(dc.ewm(span=n, adjust=False).mean().iloc[-1])
            b1 = frame(m1, "60m")
            c1 = b1[b1.closes_at <= now].close
            for n in (9, 21):
                lv[f"hEMA{n}"] = float(c1.ewm(span=n, adjust=False).mean().iloc[-1])
            near = [k for k, v in lv.items() if abs(wick - v) <= 0.25 * a5]
            buf = 0.25 * a5
            gtf = []
            for tf in ("15m", "1h", "4h", "D"):
                g = gaps.get(tf)
                if g is None or not len(g):
                    continue
                g = g[g.dir == bias]
                if ((wick >= g.bottom - buf) & (wick <= g.top + buf)).any():
                    gtf.append(tf)
            return {"near_ema": near, "gap_tfs": gtf, "confluence": bool(near and gtf),
                    "levels": {k: round(v, 2) for k, v in lv.items()}}
        except Exception as e:      # tags are informational: never block a signal
            return {"error": str(e)[:80]}

    def _gaps(self, sym: str, m1: pd.DataFrame, now: pd.Timestamp) -> dict:
        g = {"15m": live_gaps(frame(m1, "15m"), m1, 3, now), "1h": live_gaps(frame(m1, "60m"), m1, GAP_SESSIONS["1h"], now),
             "4h": live_gaps(frame(m1, "4h"), m1, GAP_SESSIONS["4h"], now)}
        d = self.daily.get(sym)
        if d is not None and len(d):
            d = d[d.index < now.normalize()].copy()
            d["closes_at"] = d.index + pd.Timedelta(hours=16)
            d["atr"] = ind.atr(d)
            g["D"] = live_gaps(d, m1, GAP_SESSIONS["D"], now)
        return g

    @staticmethod
    def _at_gap(gaps: dict, px: float, bias: int, a5: float) -> str:
        for tf in ("D", "4h", "1h"):
            g = gaps.get(tf)
            if g is None or not len(g):
                continue
            g = g[g.dir == bias]
            buf = 0.25 * a5
            if ((px >= g.bottom - buf) & (px <= g.top + buf)).any():
                return tf
        return "-"

    def _plan(self, sym, tf, fam, typ, bias, now, hi, lo, wick, gap, risk_usd: float | None = None) -> Plan | None:
        side = bias
        if side < 0:
            entry = round(lo - 0.01, 2)
            stop = math.ceil(wick * 1.0002 * 100 + 1) / 100
        else:
            entry = round(hi + 0.01, 2)
            stop = math.floor(wick * 0.9998 * 100 - 1) / 100
        risk = abs(stop - entry)
        if risk <= 0.0005 * entry:
            return None
        if self.cfg.target.upper().endswith("R"):                 # k x the stop distance, e.g. 1R, 1.5R, 2R
            target = round(entry + side * float(self.cfg.target[:-1]) * risk, 2)
        else:
            target = round(entry * (1 + side * float(self.cfg.target.rstrip("%")) / 100), 2)
        qty = int(min((risk_usd or self.cfg.risk_usd) // risk, self.cfg.max_notional // entry))
        if qty < 1:
            return None
        step = pd.Timedelta(tf.replace("m", "min"))
        return Plan(sym, tf, fam, typ, side, now, entry, stop, target, wick, qty, now + 2 * step, gap)

    # ---------------------------------------------------------------- simulated management (replay)
    def manage_sim(self, sym: str, bar: pd.Series, t: pd.Timestamp) -> None:
        """Advance planned / filled plans of `sym` with the 1m bar starting at t (same bar = stop first)."""
        for p in self.plans:
            if p.sym != sym or p.status not in ("planned", "filled"):
                continue
            if p.status == "planned":
                if (p.side < 0 and bar.high > p.wick) or (p.side > 0 and bar.low < p.wick) or t + pd.Timedelta(minutes=1) > p.valid_until:
                    p.status, p.exit_reason = "cancelled", "wick taken first" if t + pd.Timedelta(minutes=1) <= p.valid_until else "not triggered in time"
                    continue
                hit = bar.low <= p.entry if p.side < 0 else bar.high >= p.entry
                if hit:
                    p.status, p.fill_time = "filled", t
                    p.fill = min(bar.open, p.entry) if p.side < 0 else max(bar.open, p.entry)
                    # same-minute stop check (conservative)
                    if (p.side < 0 and bar.high >= p.stop) or (p.side > 0 and bar.low <= p.stop):
                        self._close(p, p.stop, t, "stop (same minute)")
                    continue
            if p.status == "filled" and t > p.fill_time:
                h = self.cfg.half_at
                if h > 0 and p.qty >= 2 and "half_px" not in p.extra:
                    p.extra["half_px"] = round(p.fill + p.side * h * abs(p.fill - p.stop), 2)
                if h > 0 and p.qty >= 2 and not p.extra.get("half_done") and \
                        ((p.side > 0 and bar.high >= p.extra["half_px"]) or (p.side < 0 and bar.low <= p.extra["half_px"])):
                    p.extra["half_done"], p.stop = True, round(p.fill, 2)
                if (p.side < 0 and bar.high >= p.stop) or (p.side > 0 and bar.low <= p.stop):
                    self._close(p, p.stop, t, "breakeven stop" if p.extra.get("half_done") else "stop")
                elif (p.side < 0 and bar.low <= p.target) or (p.side > 0 and bar.high >= p.target):
                    self._close(p, p.target, t, "target")
                elif (t - t.normalize()) >= pd.Timedelta(hours=15, minutes=50):
                    self._close(p, bar.close, t, "flat 15:50 ET")

    @staticmethod
    def _close(p: Plan, px: float, t: pd.Timestamp, why: str) -> None:
        if p.extra.get("half_done") and why != "stop (same minute)":      # replay: half was taken at +0.5R
            q1 = p.qty // 2
            px, why = (q1 * p.extra["half_px"] + (p.qty - q1) * px) / p.qty, f"half at +0.5R, rest: {why}"
        p.status, p.exit, p.exit_time, p.exit_reason = "closed", float(px), t, why

    # ---------------------------------------------------------------- paper orders (live)
    def submit(self, p: Plan) -> None:
        body = {"symbol": p.sym, "qty": str(p.qty), "side": "buy" if p.side > 0 else "sell", "type": "stop",
                "stop_price": f"{p.entry:.2f}", "time_in_force": "day", "order_class": "bracket",
                "take_profit": {"limit_price": f"{p.target:.2f}"}, "stop_loss": {"stop_price": f"{p.stop:.2f}"},
                "client_order_id": f"{p.extra.get('prefix', 'vpa')}-{p.sym}-{p.tf}-{p.signal_close:%Y%m%d%H%M}"}
        r = requests.post(TRADE + "/orders", headers=headers(), json=body, timeout=30)
        if not r.ok and "stop price must be" in r.text:
            # price is already through the trigger: enter at market if it is still within half the stop distance
            try:
                mp = float(r.json().get("market_price"))
            except (TypeError, ValueError):
                mp = float("nan")
            risk = abs(p.entry - p.stop)
            past = (p.entry - mp) * (-p.side)          # how far price went beyond the trigger in the trade's direction
            if mp == mp and 0 <= past <= 0.5 * risk:
                body.pop("stop_price")
                body["type"] = "market"
                body["client_order_id"] += "-mkt"
                r = requests.post(TRADE + "/orders", headers=headers(), json=body, timeout=30)
                p.extra["market_fallback"] = mp
            else:
                p.status, p.exit_reason = "cancelled", f"price {mp} already {past:.2f} past the trigger (> half the stop distance)"
                return
        if r.ok:
            p.order_id, p.status = r.json()["id"], "submitted"
        else:
            p.status, p.exit_reason = "cancelled", f"rejected: {r.text[:200]}"

    def poll(self, p: Plan, last_bar: pd.Series | None, now: pd.Timestamp) -> None:
        o = requests.get(TRADE + f"/orders/{p.order_id}", headers=headers(), params={"nested": "true"}, timeout=30).json()
        if p.status == "submitted":
            if o.get("status") == "filled":
                p.status, p.fill = "filled", float(o["filled_avg_price"])
                p.fill_time = pd.Timestamp(o["filled_at"]).tz_convert("America/New_York").tz_localize(None)
            elif o.get("status") in ("canceled", "expired", "rejected"):
                p.status, p.exit_reason = "cancelled", o.get("status")
            else:
                wick_taken = last_bar is not None and ((p.side < 0 and last_bar.high > p.wick) or (p.side > 0 and last_bar.low < p.wick))
                if wick_taken or now >= p.valid_until:
                    why = "wick taken first" if wick_taken else "not triggered in time"
                    requests.delete(TRADE + f"/orders/{p.order_id}", headers=headers(), timeout=30)
                    time.sleep(1.0)
                    o = requests.get(TRADE + f"/orders/{p.order_id}", headers=headers(), params={"nested": "true"}, timeout=30).json()
                    fq = int(float(o.get("filled_qty") or 0))
                    if o.get("status") == "filled":
                        # filled before the cancel landed: the bracket legs are live, manage it normally
                        p.status, p.fill = "filled", float(o["filled_avg_price"])
                        p.fill_time = pd.Timestamp(o["filled_at"]).tz_convert("America/New_York").tz_localize(None)
                    elif fq > 0:
                        # partial fill: cancelling the parent also cancels its stop/target legs,
                        # so close the filled shares at market right away instead of leaving them unprotected
                        p.qty, p.fill = fq, float(o["filled_avg_price"])
                        p.fill_time = now
                        px = self._market_exit(p.sym, fq, p.side)
                        self._close(p, px if px is not None else p.fill, now, f"partial fill {fq}, {why}, closed at market")
                    else:
                        p.status, p.exit_reason = "cancelled", why
        if p.status == "filled":
            for leg in o.get("legs") or []:
                if leg.get("status") == "filled":
                    why = "target" if leg.get("type") == "limit" else "stop"
                    t = pd.Timestamp(leg["filled_at"]).tz_convert("America/New_York").tz_localize(None)
                    self._close(p, float(leg["filled_avg_price"]), t, why)
                    return
            ex = Engine.exits.get(o.get("client_order_id"), [])
            done = sum(q for q, _, _ in ex)
            if ex and done >= p.qty:
                px = sum(q * x for q, x, _ in ex) / done
                why = ", ".join(dict.fromkeys(w for _, _, w in ex))
                self._close(p, px, now, why)

    @staticmethod
    def _market_exit(sym: str, qty: int, side: int, cid: str | None = None) -> float | None:
        """Close `qty` shares of a position opened on `side` with a market order; returns the fill price if known."""
        body = {"symbol": sym, "qty": str(qty), "side": "sell" if side > 0 else "buy", "type": "market", "time_in_force": "day"}
        if cid:
            body["client_order_id"] = cid
        r = requests.post(TRADE + "/orders", headers=headers(), json=body, timeout=30)
        if not r.ok:
            print(f"!! could not close {qty} {sym}: {r.text[:200]}", flush=True)
            return None
        oid = r.json()["id"]
        for _ in range(10):
            time.sleep(1.0)
            o = requests.get(TRADE + f"/orders/{oid}", headers=headers(), timeout=30).json()
            if o.get("status") == "filled":
                return float(o["filled_avg_price"])
        return None

    def refresh_busy(self) -> None:
        """Symbols that already have a position or a working order at Alpaca (e.g. from before a restart)."""
        pos = requests.get(TRADE + "/positions", headers=headers(), timeout=30).json()
        orders = requests.get(TRADE + "/orders", headers=headers(), params={"status": "open"}, timeout=30).json()
        mine = {p.sym for p in self.plans if p.status in ("submitted", "filled")}
        self.busy = ({x["symbol"] for x in pos} | {x["symbol"] for x in orders}) - mine

    @staticmethod
    def flatten() -> None:
        """Cancel every order, then close every position, retrying until Alpaca shows none (closes finish a moment later)."""
        import time
        requests.delete(TRADE + "/orders", headers=headers(), timeout=30)
        time.sleep(3)
        for _ in range(6):
            requests.delete(TRADE + "/positions", headers=headers(), params={"cancel_orders": "true"}, timeout=30)
            time.sleep(4)
            if not requests.get(TRADE + "/positions", headers=headers(), timeout=30).json():
                break

    @staticmethod
    def cancel_stale_entries() -> int:
        """At startup: cancel unfilled entry orders from an earlier run of the scanner (it no longer tracks them, so they
        would never be cancelled when their window ends and could fill hours later). Filled positions keep their brackets."""
        n = 0
        for o in requests.get(TRADE + "/orders", headers=headers(), params={"status": "open"}, timeout=30).json():
            if o["client_order_id"].startswith(("vpa-", "alert-")) and not o["client_order_id"].endswith(PART) \
                    and o.get("order_class") != "oco" and o.get("filled_qty") in (None, "0"):
                requests.delete(TRADE + f"/orders/{o['id']}", headers=headers(), timeout=30)
                n += 1
        return n

    # ---------------------------------------------------------------- half at +0.5R (live)
    @staticmethod
    def _oco(sym: str, side: int, qty: int, limit: float, stop: float, cid: str) -> bool:
        body = {"symbol": sym, "qty": str(qty), "side": "sell" if side > 0 else "buy", "type": "limit", "time_in_force": "day",
                "order_class": "oco", "take_profit": {"limit_price": f"{limit:.2f}"}, "stop_loss": {"stop_price": f"{stop:.2f}"},
                "client_order_id": cid}
        r = requests.post(TRADE + "/orders", headers=headers(), json=body, timeout=30)
        if not r.ok:
            print(f"!! {cid}: exit order rejected ({r.text[:150]}), closing {qty} {sym} at market", flush=True)
        return r.ok

    @staticmethod
    def _order(oid: str) -> dict:
        return requests.get(TRADE + f"/orders/{oid}", headers=headers(), params={"nested": "true"}, timeout=30).json()

    @classmethod
    def manage_partials(cls, half_at: float) -> None:
        """Call once a minute (paper). Splits filled candle / alert brackets into the two half exits, moves the second half
        to breakeven once the first has taken its profit, and records the exit fills in Engine.exits for poll()."""
        if half_at <= 0:
            return
        start = pd.Timestamp.now(tz="America/New_York").normalize()
        r = requests.get(TRADE + "/orders", headers=headers(), timeout=30,
                         params={"status": "all", "after": start.isoformat(), "limit": 500, "nested": "true", "direction": "asc"})
        if not r.ok:
            return
        orders = r.json()
        by = {o["client_order_id"]: o for o in orders}
        for o in orders:
            cid = o["client_order_id"]
            if not cid.startswith(("vpa-", "alert-")) or cid.endswith(PART) or o.get("order_class") != "bracket" \
                    or o.get("status") != "filled":
                continue
            try:
                cls._manage_one(o, by, half_at)
            except Exception as e:          # never let this stop the scanner
                print(f"!! half exits {cid}: {e}", flush=True)

    @classmethod
    def _manage_one(cls, o: dict, by: dict, half_at: float) -> None:
        cid, sym = o["client_order_id"], o["symbol"]
        side = 1 if o["side"] == "buy" else -1
        fill, qty = float(o["filled_avg_price"]), int(float(o["filled_qty"]))
        legs = o.get("legs") or []
        h1, h2, h3 = (by.get(cid + x) for x in PART[:3])
        if h1 is None:
            if qty < 2 or not legs or not all(lg["status"] in OPEN for lg in legs):
                return                      # a leg already closed it (or one share: keep the plain bracket)
            stop = float(next(lg for lg in legs if lg["type"] in ("stop", "stop_limit"))["stop_price"])
            target = float(next(lg for lg in legs if lg["type"] == "limit")["limit_price"])
            half_px = round(fill + side * half_at * abs(fill - stop), 2)
            for lg in legs:
                requests.delete(TRADE + f"/orders/{lg['id']}", headers=headers(), timeout=30)
            time.sleep(1.5)
            legs = cls._order(o["id"]).get("legs") or []
            if any(lg["status"] == "filled" for lg in legs) or any(lg["status"] in OPEN for lg in legs):
                return                      # closed by the bracket in the meantime, or the cancel has not landed yet
            q1 = qty // 2
            for x, q, lim in (("-h1", q1, half_px), ("-h2", qty - q1, target)):
                if not cls._oco(sym, side, q, lim, stop, cid + x):
                    cls._market_exit(sym, q, side, cid + "-hm" + x[-1])
            print(f"[half exits] {sym} {cid}: {q1} at {half_px:.2f} (+{half_at:g}R), {qty - q1} at {target:.2f}, stop {stop:.2f}", flush=True)
            return
        # record exit fills so poll() can close the plan
        ex = []
        for k, h in ((x, by.get(cid + x)) for x in PART[:3]):
            for y in [h] + ((h or {}).get("legs") or []) if h else []:
                q = int(float(y.get("filled_qty") or 0))
                if q:
                    why = ("half at +%gR" % half_at if k == "-h1" else "target") if y["type"] == "limit" else \
                          ("breakeven stop" if k == "-h3" else "stop")
                    ex.append((q, float(y["filled_avg_price"]), why))
        for x in ("-hm1", "-hm2", "-hm3"):
            y = by.get(cid + x)
            if y and float(y.get("filled_qty") or 0):
                ex.append((int(float(y["filled_qty"])), float(y["filled_avg_price"]), "closed at market"))
        cls.exits[cid] = ex
        # first half took its profit and the second half still has its original stop: move it to breakeven
        if h1.get("status") == "filled" and h2 is not None and h2.get("status") in OPEN and h3 is None:
            be = round(fill, 2)
            requests.delete(TRADE + f"/orders/{h2['id']}", headers=headers(), timeout=30)
            time.sleep(1.5)
            h2 = cls._order(h2["id"])
            if h2.get("status") in OPEN or h2.get("status") == "filled" or \
                    any(lg.get("status") == "filled" for lg in h2.get("legs") or []):
                return
            q2 = int(float(h2["qty"])) - int(float(h2.get("filled_qty") or 0))
            if q2 > 0 and not cls._oco(sym, side, q2, float(h2["limit_price"]), be, cid + "-h3"):
                cls._market_exit(sym, q2, side, cid + "-hm3")
            print(f"[half exits] {sym} {cid}: first half filled, stop on the other {q2} moved to breakeven {be:.2f}", flush=True)

    # ---------------------------------------------------------------- logging
    def log(self, kind: str, p: Plan) -> None:
        self.cfg.log_dir.mkdir(parents=True, exist_ok=True)
        rec = {"kind": kind, **{k: (str(v) if isinstance(v, pd.Timestamp) else v) for k, v in p.__dict__.items() if k != "extra"}}
        with open(self.cfg.log_dir / f"{p.signal_close:%Y-%m-%d}.jsonl", "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def summary(self) -> pd.DataFrame:
        rows = []
        for p in self.plans:
            pnl = (p.exit - p.fill) * p.side * p.qty if p.status == "closed" else np.nan
            slip = (p.fill - p.entry) * p.side if p.fill is not None else np.nan      # + = worse than the trigger level
            rows.append(dict(sym=p.sym, tf=p.tf, family=p.family, type=p.type, side="long" if p.side > 0 else "short",
                             signal_MST=(p.signal_close - pd.Timedelta(hours=2)).strftime("%H:%M"), gap=p.gap,
                             entry=p.entry, stop=p.stop, target=p.target, qty=p.qty, status=p.status,
                             fill=p.fill, slippage=round(slip, 3) if slip == slip else np.nan,
                             exit=p.exit, why=p.exit_reason, pnl_usd=round(pnl, 2) if pnl == pnl else np.nan,
                             near_ema="+".join(p.tags.get("near_ema", [])), gap_tfs="+".join(p.tags.get("gap_tfs", [])),
                             confluence=bool(p.tags.get("confluence", False))))
        return pd.DataFrame(rows)
