"""Live / replay engine: premier candles and climaxes at 1h / 4h / daily fair value gaps -> Alpaca paper bracket orders.

Signal (closed candles only, on each signal timeframe):
  a premier candle (docs/vpa-detection-spec.md shapes, vpa.detect) or a climax (multi-bar climaxes, stopping volume,
  topping-out volume, single-bar climax candidates) whose wick reaches an unfilled 1h / 4h / daily fair value gap on its
  side (bearish signal at a bear gap = resistance, bullish at a bull gap = support), within 0.25 ATR(5m).
Order: bracket, entry = stop order one cent beyond the signal candle's opposite extreme (short below its low, long above
  its high), stop = one cent beyond the wick (+0.02%), target = +0.3% from the entry level (or 2R). Size = risk $ / stop
  distance. Cancelled if not filled within 2 signal candles or if price takes out the wick first. Entries 10:00-15:30 ET,
  one position per symbol; everything is cancelled and flattened at 15:50 ET.
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
    tfs: tuple = ("5m", "9m", "15m")
    families: tuple = ("premier", "climax")
    risk_usd: float = 50.0
    max_notional: float = 100_000.0  # never more than this much stock per position (tight stops would oversize)
    target: str = "0.3%"            # "0.3%" style percent, or k x the stop distance like "1R" / "2R"
    require_gap: bool = True
    short_trend_filter: bool = True  # shorts only when price is below session VWAP and the 5m EMA9 is below EMA21
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
    extra: dict = field(default_factory=dict)


class Engine:
    def __init__(self, cfg: Config, history: dict[str, pd.DataFrame], daily: dict[str, pd.DataFrame]):
        self.cfg, self.history, self.daily = cfg, history, daily
        self.plans: list[Plan] = []
        self.seen: set = set()
        self.busy: set[str] = set()          # symbols with an open position / order at Alpaca (restart safety)

    # ---------------------------------------------------------------- signals
    def signals(self, sym: str, m1: pd.DataFrame, now: pd.Timestamp) -> list[Plan]:
        """Signals whose candle closed exactly at `now` (a 1m boundary)."""
        out = []
        minute = (now - now.normalize()) / pd.Timedelta(minutes=1) - 570
        if not 30 <= minute <= 360 or sym in self.busy or \
                any(p.sym == sym and p.status in ("planned", "submitted", "filled") for p in self.plans):
            return out
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
            if "climax" in self.cfg.families:
                cl = climaxes(done)
                for _, r in cl[cl.index == t].iterrows():
                    found.append(("climax", r.type, int(r.bias)))
            for fam, typ, bias in found:
                key = (sym, tf, t, typ)
                if key in self.seen:
                    continue
                self.seen.add(key)
                hi, lo = float(done.high.iat[-1]), float(done.low.iat[-1])
                wick = max(hi, float(done.high.iloc[-3:].max())) if (fam == "climax" and bias < 0) else hi
                if bias > 0:
                    wick = min(lo, float(done.low.iloc[-3:].min())) if fam == "climax" else lo
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
                p = self._plan(sym, tf, fam, typ, bias, now, hi, lo, wick, gap)
                if p:
                    out.append(p)
        return out

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

    def _gaps(self, sym: str, m1: pd.DataFrame, now: pd.Timestamp) -> dict:
        g = {"1h": live_gaps(frame(m1, "60m"), m1, GAP_SESSIONS["1h"], now),
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

    def _plan(self, sym, tf, fam, typ, bias, now, hi, lo, wick, gap) -> Plan | None:
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
        qty = int(min(self.cfg.risk_usd // risk, self.cfg.max_notional // entry))
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
                if (p.side < 0 and bar.high >= p.stop) or (p.side > 0 and bar.low <= p.stop):
                    self._close(p, p.stop, t, "stop")
                elif (p.side < 0 and bar.low <= p.target) or (p.side > 0 and bar.high >= p.target):
                    self._close(p, p.target, t, "target")
                elif (t - t.normalize()) >= pd.Timedelta(hours=15, minutes=50):
                    self._close(p, bar.close, t, "flat 15:50 ET")

    @staticmethod
    def _close(p: Plan, px: float, t: pd.Timestamp, why: str) -> None:
        p.status, p.exit, p.exit_time, p.exit_reason = "closed", float(px), t, why

    # ---------------------------------------------------------------- paper orders (live)
    def submit(self, p: Plan) -> None:
        body = {"symbol": p.sym, "qty": str(p.qty), "side": "buy" if p.side > 0 else "sell", "type": "stop",
                "stop_price": f"{p.entry:.2f}", "time_in_force": "day", "order_class": "bracket",
                "take_profit": {"limit_price": f"{p.target:.2f}"}, "stop_loss": {"stop_price": f"{p.stop:.2f}"},
                "client_order_id": f"vpa-{p.sym}-{p.tf}-{p.signal_close:%Y%m%d%H%M}"}
        r = requests.post(TRADE + "/orders", headers=headers(), json=body, timeout=30)
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

    @staticmethod
    def _market_exit(sym: str, qty: int, side: int) -> float | None:
        """Close `qty` shares of a position opened on `side` with a market order; returns the fill price if known."""
        body = {"symbol": sym, "qty": str(qty), "side": "sell" if side > 0 else "buy", "type": "market", "time_in_force": "day"}
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
        requests.delete(TRADE + "/orders", headers=headers(), timeout=30)
        requests.delete(TRADE + "/positions", headers=headers(), timeout=30)

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
                             exit=p.exit, why=p.exit_reason, pnl_usd=round(pnl, 2) if pnl == pnl else np.nan))
        return pd.DataFrame(rows)
