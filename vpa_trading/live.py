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
  Stateless (read back from Alpaca every minute), so it keeps working across restarts. If a step is interrupted (a slow
  cancel, a restart between two orders) the next minute finishes it: shares are never left without a stop, and exit
  orders are never placed for more shares than the scanner still holds. 5-year test (reports/trim_test.md): same
  expectancy as all-at-1R, profitable trades 49% -> 65%.
Session times come from Alpaca's calendar (close_minute): last entry 30 minutes before the close, flat 10 minutes before,
  so a 13:00 half day is handled (12:30 / 12:50).
Key levels (Nov 10, the user's call, $300 risk): a PREMIER candle on volume 2x usual or more whose wick is at a zone of the
  morning key-levels sheet (logs/keylevels/, vpa_trading/keylevels.py) scoring 7 or more is traded even with no gap and
  no Banks level. Marked: prefix "key-", printed as "KEY LEVEL ALERT", strategy "Key level" in the report. Evidence is
  thin: +0.11R a trade since Nov 2024 (105 trades) but -0.05R before (reports/keylevels.md). A signal at a gap or a
  Banks level stays that kind of trade (with the key zone as a tag).
Buying power (Nov 10, the user's call): an entry Alpaca refuses for buying power is sent again at the size that fits
  (same stop and target, so less at risk); skipped if under a quarter of the planned size fits. Logged as shrunk_from.
Banks levels (Nov 10, the user's call): a PREMIER candle whose wick is at a posted level (data/levels/, within 0.25 ATR(5m))
  is traded even with no 1h / 4h / D gap, if the level fits the direction: a bottom candle at support / long trigger /
  downside target, a top candle at resistance / short trigger / upside target. Every other filter still applies (pivot,
  volume for longs), same risk and exits. Marked: client id prefix "lvl-", printed as "LEVEL ALERT", strategy
  "Banks level" in the end-of-day report. Untested: there is no history of these levels yet.
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
    r = None
    for k in range(6):
        try:
            r = requests.get(url, headers=headers(), params=params, timeout=60)
        except requests.RequestException:      # a dropped connection or timeout: retry like a server error
            if k == 5:
                raise
            time.sleep(2 + 2 ** k)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 + 2 ** k)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def close_minute(day=None) -> int:
    """Minutes from 9:30 ET to the session close on `day` (default today): 390 on a normal day, 210 on a 13:00 half day.
    From Alpaca's calendar; 390 if it cannot be read. Entries stop 30 minutes before it, the flatten is 10 minutes before."""
    try:
        d = pd.Timestamp(day if day is not None else pd.Timestamp.now(tz="America/New_York")).strftime("%Y-%m-%d")
        cal = _get(TRADE + "/calendar", {"start": d, "end": d})
        if cal and cal[0]["date"] == d:
            h, m = map(int, cal[0]["close"].split(":"))
            return h * 60 + m - 570
    except Exception as e:
        print(f"!! could not read the market calendar ({e}); assuming a 16:00 close", flush=True)
    return 390


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
    key_risk_usd: float = 300.0     # risk on a trade taken only because of a key-levels zone (0 = off)
    key_min_score: float = 7.0
    key_min_rvol: float = 2.0
    max_adds: int = 1               # extra positions on a symbol that is already in a trade (same direction only)
    add_risk_usd: float = 0.0       # risk of an add in dollars; 0 = the same as risk_usd
    half_at: float = 0.5            # take half off at this many R, then the rest goes to breakeven; 0 = all at the target
    close_min: int = 390            # minutes from 9:30 to today's close (210 on a half day); see close_minute()
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
    nb_net: dict = {}     # symbol -> signed shares the breakout holds (its own "nb-" orders today); never ours to protect

    def __init__(self, cfg: Config, history: dict[str, pd.DataFrame], daily: dict[str, pd.DataFrame]):
        self.cfg, self.history, self.daily = cfg, history, daily
        self.plans: list[Plan] = []
        self.seen: set = set()
        self.busy: set[str] = set()          # symbols with an open position / order at Alpaca (restart safety)
        self.external: dict[str, int] = {}   # symbols held by another strategy (the breakout) -> its direction
        self.levels: pd.DataFrame | None = None   # posted levels (vpa_trading.levels.load); premier candles at one may trade
        self.key_sheet: pd.DataFrame | None = None  # the morning key-levels sheet (keylevels.load_sheet)

    # ---------------------------------------------------------------- signals
    def signals(self, sym: str, m1: pd.DataFrame, now: pd.Timestamp) -> list[Plan]:
        """Signals whose candle closed exactly at `now` (a 1m boundary)."""
        out = []
        minute = (now - now.normalize()) / pd.Timedelta(minutes=1) - 570
        if not 30 <= minute <= self.cfg.close_min - 30:
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
                lvl = self._at_level(sym, wick, bias, a5) if gap == "-" and fam == "premier" else None
                key = self._at_key(sym, m1, now, tf, wick, done) if gap == "-" and lvl is None and fam == "premier" else None
                if self.cfg.require_gap and gap == "-" and lvl is None and key is None:
                    continue
                if bias < 0 and self.cfg.short_trend_filter:
                    why = self._uptrend(m1, b5, now)
                    if why:
                        print(f"[{(now - pd.Timedelta(hours=2)).strftime('%H:%M')} MST] {sym} {tf} {typ} short skipped: {why}", flush=True)
                        continue
                risk_usd = (self.cfg.add_risk_usd or self.cfg.risk_usd) if add_dir is not None else None
                if key is not None:
                    risk_usd = self.cfg.key_risk_usd
                p = self._plan(sym, tf, fam, typ, bias, now, hi, lo, wick, gap, risk_usd=risk_usd)
                if p:
                    p.tags = self._tags(sym, m1, now, wick, bias, a5, gaps)
                    if lvl:                  # traded only because of a posted level: marked as its own strategy
                        p.gap, p.extra["prefix"], p.tags["banks_level"] = "level", "lvl", lvl
                    elif key is not None:    # traded only because of a key-levels zone
                        p.gap, p.extra["prefix"] = "key", "key"
                        p.tags["key_level"] = {"zone": key.price(), "score": key.score, "what": key.label(4)}
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

    def _at_key(self, sym: str, m1: pd.DataFrame, now: pd.Timestamp, tf: str, wick: float, done: pd.DataFrame):
        """The key-levels zone (score >= key_min_score) at the wick, if the candle's volume is >= key_min_rvol x usual."""
        if self.key_sheet is None or not self.cfg.key_risk_usd:
            return None
        if not float(vpa.relvol_tod(done).iat[-1]) >= self.cfg.key_min_rvol:
            return None
        from .keylevels import zone_at
        day = m1[m1.index.normalize() == now.normalize()]
        f30 = day[day.index.time < pd.Timestamp("10:00").time()]
        late = now - pd.Timedelta(tf.replace("m", "min")) >= now.normalize() + pd.Timedelta(hours=10)
        z = zone_at(self.key_sheet, sym, wick, (float(f30.high.max()), float(f30.low.min())) if late and len(f30) else None)
        return z if z is not None and z.score >= self.cfg.key_min_score else None

    LONG_ROLES = ("support", "long_trigger", "target_down")
    SHORT_ROLES = ("resistance", "short_trigger", "target_up")

    def _at_level(self, sym: str, px: float, bias: int, a5: float) -> str | None:
        """Label of the closest posted level at the wick that fits the direction, else None."""
        if self.levels is None or not len(self.levels):
            return None
        from .levels import near
        roles = self.LONG_ROLES if bias > 0 else self.SHORT_ROLES
        hits = [h for h in near(self.levels, sym, px, 0.25 * a5) if h["role"] in roles]
        return f"{hits[0]['source']} {hits[0]['role'].replace('_', ' ')} {hits[0]['level']}" if hits else None

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
                hit = bar.low <= p.entry if p.side < 0 else bar.high >= p.entry
                late = t + pd.Timedelta(minutes=1) > p.valid_until
                took = (p.side < 0 and bar.high > p.wick) or (p.side > 0 and bar.low < p.wick)
                # a minute that both triggers the entry and takes the wick: the order is unknown, so count the bad
                # one (filled, then stopped if the stop was reached) instead of quietly cancelling the trade
                if late or (took and not hit):
                    p.status, p.exit_reason = "cancelled", "not triggered in time" if late else "wick taken first"
                    continue
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
                elif (t - t.normalize()) >= pd.Timedelta(hours=9, minutes=30 + self.cfg.close_min - 10):
                    self._close(p, bar.close, t, "flat 10 min before the close")

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
        if not r.ok and "insufficient buying power" in r.text:
            r = self._shrink_to_fit(p, body, r)
        if r is not None and r.ok:
            p.order_id, p.status = r.json()["id"], "submitted"
        elif r is not None:
            p.status, p.exit_reason = "cancelled", f"rejected: {r.text[:200]}"

    MIN_FIT = 0.25      # shrink-to-fit: skip the trade if less than a quarter of the planned size fits

    def _shrink_to_fit(self, p: Plan, body: dict, r):
        """Alpaca refused the order for buying power: resend it at the size that fits (user's choice, Nov 10). Alpaca
        reserves a little more than the order's value (about 3% on stop and market orders), so the size uses the
        reserve it reported, with 2% to spare. Same stop and target: the dollars at risk shrink with the size."""
        try:
            j = r.json()
            bp, cost = float(j["buying_power"]), float(j["cost_basis"])
        except (ValueError, KeyError, TypeError):
            return r
        per_share = cost / p.qty                            # what Alpaca reserves per share of this order
        q = int(0.98 * bp // per_share)
        if q < max(1, math.ceil(self.MIN_FIT * p.qty)):
            p.status, p.exit_reason = "cancelled", f"not enough buying power (only {max(q, 0)} of {p.qty} shares fit)"
            return None
        planned = p.qty
        body = dict(body, qty=str(q), client_order_id=body["client_order_id"] + "-fit")
        r2 = requests.post(TRADE + "/orders", headers=headers(), json=body, timeout=30)
        if r2.ok:
            p.qty = q
            p.extra["shrunk_from"] = planned
            print(f"    buying power: {p.sym} shrunk to fit, {q} of {planned} shares "
                  f"(${abs(p.entry - p.stop) * q:,.0f} risk instead of ${abs(p.entry - p.stop) * planned:,.0f})", flush=True)
        return r2

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
        for k in range(8):                    # a network error here must not leave positions open: keep trying
            try:
                if k == 0:
                    requests.delete(TRADE + "/orders", headers=headers(), timeout=30)
                    time.sleep(3)
                requests.delete(TRADE + "/positions", headers=headers(), params={"cancel_orders": "true"}, timeout=30)
                time.sleep(4)
                if requests.get(TRADE + "/positions", headers=headers(), timeout=30).json() == []:
                    return
            except requests.RequestException as e:
                print(f"!! flatten attempt {k + 1} failed: {e}", flush=True)
                time.sleep(5)
        print("!! FLATTEN DID NOT CONFIRM: positions may still be open at Alpaca", flush=True)

    @staticmethod
    def cancel_stale_entries() -> int:
        """At startup: cancel unfilled entry orders from an earlier run of the scanner (it no longer tracks them, so they
        would never be cancelled when their window ends and could fill hours later). Filled positions keep their brackets."""
        n = 0
        for o in requests.get(TRADE + "/orders", headers=headers(), params={"status": "open"}, timeout=30).json():
            if o["client_order_id"].startswith(("vpa-", "alert-", "lvl-", "key-")) and not o["client_order_id"].endswith(PART) \
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
        net: dict = {}
        for o in orders:
            if o["client_order_id"].startswith("nb-"):
                for y in [o] + (o.get("legs") or []):
                    q = float(y.get("filled_qty") or 0)
                    net[o["symbol"]] = net.get(o["symbol"], 0) + (q if y["side"] == "buy" else -q)
        cls.nb_net = {k: int(round(v)) for k, v in net.items()}
        for o in orders:
            cid = o["client_order_id"]
            if not cid.startswith(("vpa-", "alert-", "lvl-", "key-")) or cid.endswith(PART) or o.get("order_class") != "bracket" \
                    or o.get("status") != "filled":
                continue
            try:
                cls._manage_one(o, by, half_at)
            except Exception as e:          # never let this stop the scanner
                print(f"!! half exits {cid}: {e}", flush=True)

    @staticmethod
    def _position(sym: str) -> int:
        """Signed shares held in `sym` at Alpaca (0 if none)."""
        r = requests.get(TRADE + f"/positions/{sym}", headers=headers(), timeout=30)
        return int(float(r.json().get("qty") or 0)) if r.status_code == 200 else 0

    @classmethod
    def _cancel_wait(cls, ids: list[str], parent_id: str, tries: int = 10) -> dict:
        """Cancel orders and wait until Alpaca shows none of them open (up to `tries` seconds). Returns the parent re-read."""
        for i in ids:
            requests.delete(TRADE + f"/orders/{i}", headers=headers(), timeout=30)
        o = {}
        for _ in range(tries):
            time.sleep(1.0)
            o = cls._order(parent_id)
            if not any(y.get("status") in OPEN for y in [o] + (o.get("legs") or []) if y["id"] in ids):
                break
        return o

    @classmethod
    def _exit_pair(cls, sym: str, side: int, q: int, limit: float, stop: float, cid: str, fallback_cid: str) -> None:
        """An OCO exit (limit + stop) for q shares. Never more than the account still holds on that side; if Alpaca
        refuses the OCO, those shares are closed at market so they are never left without a stop."""
        q = min(q, max((cls._position(sym) - cls.nb_net.get(sym, 0)) * side, 0))
        if q <= 0:
            print(f"!! {cid}: no shares left to protect in {sym} (already closed)", flush=True)
            return
        if not cls._oco(sym, side, q, limit, stop, cid):
            cls._market_exit(sym, q, side, fallback_cid)

    @classmethod
    def _manage_one(cls, o: dict, by: dict, half_at: float) -> None:
        cid, sym = o["client_order_id"], o["symbol"]
        side = 1 if o["side"] == "buy" else -1
        fill, qty = float(o["filled_avg_price"]), int(float(o["filled_qty"]))
        legs = o.get("legs") or []
        h1, h2, h3 = (by.get(cid + x) for x in PART[:3])
        hm = {x: by.get(cid + "-hm" + x) for x in "123"}
        if h1 is None and hm["1"] is None:
            if qty < 2 or not legs or any(lg["status"] == "filled" for lg in legs):
                return                      # the bracket closed it, or one share: keep the plain bracket
            stop = float(next(lg for lg in legs if lg["type"] in ("stop", "stop_limit"))["stop_price"])
            target = float(next(lg for lg in legs if lg["type"] == "limit")["limit_price"])
            open_ids = [lg["id"] for lg in legs if lg["status"] in OPEN]
            if open_ids:
                legs = cls._cancel_wait(open_ids, o["id"]).get("legs") or []
                if any(lg["status"] == "filled" for lg in legs) or any(lg["status"] in OPEN for lg in legs):
                    return                  # closed by the bracket meanwhile, or the cancel has not landed: retried next minute
            else:
                print(f"!! {cid}: {sym} bracket legs are cancelled and no exit orders exist: re-placing them", flush=True)
            # here the legs are cancelled and nothing protects the shares: place the two exits now
            # (also reached on a later minute / after a restart if the first attempt was interrupted)
            left = qty - sum(int(float(lg.get("filled_qty") or 0)) for lg in legs)
            q1 = min(qty // 2, left)
            half_px = round(fill + side * half_at * abs(fill - stop), 2)
            cls._exit_pair(sym, side, q1, half_px, stop, cid + "-h1", cid + "-hm1")
            if h2 is None and hm["2"] is None:
                cls._exit_pair(sym, side, left - q1, target, stop, cid + "-h2", cid + "-hm2")
            print(f"[half exits] {sym} {cid}: {q1} at {half_px:.2f} (+{half_at:g}R), {left - q1} at {target:.2f}, stop {stop:.2f}", flush=True)
            return
        if h2 is None and hm["2"] is None and h3 is None and hm["3"] is None and h1 is not None:
            # interrupted between the two exit orders: the second half has no protection yet
            lg = (h1.get("legs") or [{}])[0]
            stop, target = float(lg.get("stop_price") or 0), None
            for y in o.get("legs") or []:
                if y["type"] == "limit":
                    target = float(y["limit_price"])
            q2 = qty - int(float(h1["qty"]))
            if stop and target and q2 > 0:
                print(f"!! {cid}: second exit order missing for {q2} {sym}: placing it", flush=True)
                cls._exit_pair(sym, side, q2, target, stop, cid + "-h2", cid + "-hm2")
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
        for y in hm.values():
            if y and float(y.get("filled_qty") or 0):
                ex.append((int(float(y["filled_qty"])), float(y["filled_avg_price"]), "closed at market"))
        cls.exits[cid] = ex
        # first half took its profit: the second half's stop moves to breakeven (h2 -> h3)
        if h1 is not None and h1.get("status") == "filled" and h2 is not None and h3 is None and hm["3"] is None:
            h2_legs = h2.get("legs") or []
            if h2.get("status") == "filled" or any(lg.get("status") == "filled" for lg in h2_legs):
                return                      # the second half already ended at its target or stop
            open_ids = [y["id"] for y in [h2] + h2_legs if y.get("status") in OPEN]
            if open_ids:
                h2 = cls._cancel_wait(open_ids, h2["id"])
                h2_legs = h2.get("legs") or []
                if h2.get("status") in OPEN or h2.get("status") == "filled" or \
                        any(lg.get("status") in OPEN or lg.get("status") == "filled" for lg in h2_legs):
                    return                  # retried next minute
            be = round(fill, 2)
            q2 = int(float(h2["qty"])) - int(float(h2.get("filled_qty") or 0)) - \
                sum(int(float(lg.get("filled_qty") or 0)) for lg in h2_legs)
            if q2 > 0:
                cls._exit_pair(sym, side, q2, float(h2["limit_price"]), be, cid + "-h3", cid + "-hm3")
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
