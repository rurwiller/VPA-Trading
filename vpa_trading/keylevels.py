"""Key price levels, the way a chart reader marks them, computed the same way live and in the 5-year test.

For a trading day, using only what is known before that day's open (plus today's premarket; the opening range counts from
10:00 ET), every level of these families is collected:

  session   prior day's high / low / close
  week      prior week's high / low / close            month   prior month's high / low
  year      52-week high / low
  premkt    today's premarket high / low (04:00-09:30 ET)
  or        today's opening range high / low (first 30 minutes; usable from 10:00)
  swing     daily swing highs / lows of the last 120 sessions (3 bars each side); swings within 0.5% are one level and
            every extra touch adds weight
  gap       unfilled daily gaps of the last 60 sessions: the edge that fills the gap and the gap day's own extreme
  profile   volume profile of the last 20 sessions (point of control, value area high / low) and yesterday's point of control
  avwap     VWAP anchored at the 60-session high, the 60-session low and the biggest gap-on-volume day of the last 90
            sessions (a stand-in for earnings), as of yesterday's close
  ma        daily EMA 9 / 21 / 50 and the 200-day average, as of yesterday's close
  round     the nearest round numbers ($10s under $250, $50s above; half steps count less)
  gamma     our call / put walls and gamma flip (live only)     posted   hand-entered levels, e.g. Banks (live only)

Levels closer together than about 5% of the stock's average daily range are merged into one ZONE. A zone's score is the
sum of its best level per family plus half a point per extra family: levels of different kinds stacking at one price is
what makes a level "key". The sheet keeps the 4 highest-scoring zones above and below the price, within 3 daily ranges.

Weights are a starting point from experience, not a fitted result. What the 5-year test says (reports/keylevels.md,
9 tickers): on a first touch these levels hold barely more often than a random price nearby (29% vs 29%); only the VWAP
anchored at the 60-session low beat its controls in both halves of the data (+8 and +11 points). A pivot candle at a zone
did no better than one elsewhere (-0.09R after costs either way), and the oscillator being at its extreme did not help.
One combination was positive after Nov 2024, a candle on volume 2x usual at a zone scoring 7+ (+0.11R, 105 trades), but it
was -0.05R before, so it is a lead to watch, not a rule. So: the sheet is a map for reading the chart and for tagging
signals; it is not evidence that these prices turn the market.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

WEIGHT = {"pd_high": 3.0, "pd_low": 3.0, "pd_close": 2.0, "pw_high": 4.0, "pw_low": 4.0, "pw_close": 2.0, "pm_high": 4.5,
          "pm_low": 4.5, "52w_high": 4.5, "52w_low": 4.5, "premkt_high": 2.5, "premkt_low": 2.5, "or_high": 2.0, "or_low": 2.0,
          "swing_high": 2.0, "swing_low": 2.0, "gap_fill": 3.0, "gap_edge": 2.0, "poc_20d": 3.0, "vah_20d": 2.5,
          "val_20d": 2.5, "poc_1d": 2.0, "avwap_high": 3.0, "avwap_low": 3.0, "avwap_event": 3.0, "ema9": 1.5, "ema21": 2.0,
          "ema50": 2.5, "sma200": 3.5, "round": 2.0, "round_half": 1.0, "call_wall": 3.0, "put_wall": 3.0, "gamma_flip": 2.0,
          "posted": 3.0}
FAMILY = {"pd_high": "session", "pd_low": "session", "pd_close": "session", "pw_high": "week", "pw_low": "week",
          "pw_close": "week", "pm_high": "month", "pm_low": "month", "52w_high": "year", "52w_low": "year",
          "premkt_high": "premkt", "premkt_low": "premkt", "or_high": "or", "or_low": "or", "swing_high": "swing",
          "swing_low": "swing", "gap_fill": "gap", "gap_edge": "gap", "poc_20d": "profile", "vah_20d": "profile",
          "val_20d": "profile", "poc_1d": "profile", "avwap_high": "avwap", "avwap_low": "avwap", "avwap_event": "avwap",
          "ema9": "ma", "ema21": "ma", "ema50": "ma", "sma200": "ma", "round": "round", "round_half": "round",
          "call_wall": "gamma", "put_wall": "gamma", "gamma_flip": "gamma", "posted": "posted"}
NAME = {"pd_high": "prior day high", "pd_low": "prior day low", "pd_close": "prior close", "pw_high": "prior week high",
        "pw_low": "prior week low", "pw_close": "prior week close", "pm_high": "prior month high", "pm_low": "prior month low",
        "52w_high": "52-week high", "52w_low": "52-week low", "premkt_high": "premarket high", "premkt_low": "premarket low",
        "or_high": "opening range high", "or_low": "opening range low", "swing_high": "swing high", "swing_low": "swing low",
        "gap_fill": "gap fill", "gap_edge": "gap edge", "poc_20d": "20-day volume peak", "vah_20d": "20-day value high",
        "val_20d": "20-day value low", "poc_1d": "yesterday's volume peak", "avwap_high": "VWAP from the high",
        "avwap_low": "VWAP from the low", "avwap_event": "VWAP from the gap day", "ema9": "daily EMA 9", "ema21": "daily EMA 21",
        "ema50": "daily EMA 50", "sma200": "200-day average", "round": "round number", "round_half": "half round number",
        "call_wall": "call wall", "put_wall": "put wall", "gamma_flip": "gamma flip", "posted": "posted level"}
SHEET_DIR = Path("logs/keylevels")       # the morning sheet (scripts/key_levels.py) writes <date>.csv here
BIN = 0.001          # volume profile bins: 0.1% of price
RTH0, RTH1 = pd.Timestamp("09:30").time(), pd.Timestamp("16:00").time()


def _daily_from_minutes(m: pd.DataFrame) -> pd.DataFrame:
    g = m.groupby(m.index.normalize())
    return pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                         "volume": g.volume.sum()})


@dataclass
class Zone:
    lo: float
    hi: float
    score: float
    kinds: list

    @property
    def mid(self) -> float:
        return (self.lo + self.hi) / 2

    @property
    def families(self) -> list:
        return sorted({FAMILY[k] for k in self.kinds})

    def label(self, n: int = 3) -> str:
        ks = sorted(set(self.kinds), key=lambda k: -WEIGHT[k])
        return " + ".join(NAME[k] for k in ks[:n]) + (f" +{len(ks) - n} more" if len(ks) > n else "")

    def price(self) -> str:
        return f"{self.lo:.2f}" if self.hi - self.lo < 0.005 else f"{self.lo:.2f}-{self.hi:.2f}"


class Context:
    """Everything needed to list a symbol's levels for any session: build once, then call raw(day) / zones(day)."""

    def __init__(self, m1_ext: pd.DataFrame, daily: pd.DataFrame | None = None, today: pd.Timestamp | None = None):
        t = m1_ext.index.time
        rth = m1_ext[(t >= RTH0) & (t < RTH1)]
        pre = m1_ext[t < RTH0]
        d = daily.copy() if daily is not None else _daily_from_minutes(rth)
        d = d[["open", "high", "low", "close", "volume"]].astype(float)
        if today is not None and today.normalize() not in d.index:          # live before the open: today has no bar yet
            d.loc[today.normalize()] = np.nan
        d = d.sort_index()
        self.days = d.index
        self.d = d
        o, h, l, c, v = (d[k].to_numpy() for k in ("open", "high", "low", "close", "volume"))
        self.o, self.h, self.l, self.c, self.v = o, h, l, c, v
        cs = pd.Series(c)
        self.adr = ((pd.Series(h) - pd.Series(l)).rolling(14, min_periods=5).mean().shift(1)).to_numpy()   # $ per day, prior days
        self.ema = {n: cs.ewm(span=n, adjust=False, min_periods=n).mean().shift(1).to_numpy() for n in (9, 21, 50)}
        self.sma200 = cs.rolling(200).mean().shift(1).to_numpy()
        self.v20 = pd.Series(v).rolling(20, min_periods=5).mean().shift(1).to_numpy()
        # prior week / month extremes
        wk = pd.Series(self.days.to_period("W-FRI"), index=self.days)
        mo = pd.Series(self.days.to_period("M"), index=self.days)
        self.pw = self._prior(d, wk)
        self.pm = self._prior(d, mo)
        # premarket and opening range of each day
        pg = pre.groupby(pre.index.normalize())
        self.pre_hi = pg.high.max().reindex(self.days).to_numpy()
        self.pre_lo = pg.low.min().reindex(self.days).to_numpy()
        self.pre_last = pg.close.last().reindex(self.days).to_numpy()
        first30 = rth[rth.index.time < pd.Timestamp("10:00").time()]
        og = first30.groupby(first30.index.normalize())
        self.or_hi = og.high.max().reindex(self.days).to_numpy()
        self.or_lo = og.low.min().reindex(self.days).to_numpy()
        # 1m arrays for the volume profile and anchored VWAPs
        px = (rth.vwap.fillna(rth.close) if "vwap" in rth else rth.close).to_numpy()
        vol = rth.volume.to_numpy()
        self.m_bin = np.floor(np.log(np.maximum(px, 0.01)) / BIN).astype(np.int64)
        self.m_vol = vol
        self.cpv, self.cv = np.r_[0.0, np.cumsum(px * vol)], np.r_[0.0, np.cumsum(vol)]
        pos = self.days.searchsorted(rth.index.normalize())
        self.m_start = np.searchsorted(pos, np.arange(len(self.days)), "left")     # first 1m bar of each session
        self.m_end = np.searchsorted(pos, np.arange(len(self.days)), "right")      # one past its last bar
        # daily swings (3 bars each side), known 3 sessions later
        hs, ls = pd.Series(h), pd.Series(l)
        self.sw_hi = np.flatnonzero((hs == hs.rolling(7, center=True).max()).to_numpy())
        self.sw_lo = np.flatnonzero((ls == ls.rolling(7, center=True).min()).to_numpy())

    @staticmethod
    def _prior(d: pd.DataFrame, per: pd.Series) -> pd.DataFrame:
        g = d.groupby(per.to_numpy())
        agg = pd.DataFrame({"high": g.high.max(), "low": g.low.min(), "close": g.close.last()}).shift(1)
        return agg.reindex(per.to_numpy()).set_axis(d.index)

    # ------------------------------------------------------------------ raw levels
    def index_of(self, day) -> int:
        return int(self.days.get_loc(pd.Timestamp(day).normalize()))

    def spot(self, i: int) -> float:
        """A reference price for day i before it trades: its open if known, else the last premarket print, else prior close."""
        for x in (self.o[i], self.pre_last[i], self.c[i - 1] if i else np.nan):
            if x == x:
                return float(x)
        return float("nan")

    def raw(self, i: int, opening_range: bool = True) -> list[tuple[float, str]]:
        """(price, kind) for session number i, from data before its open (plus its premarket and opening range)."""
        out: list[tuple[float, str]] = []
        if i < 1:
            return out
        h, l, c = self.h, self.l, self.c
        add = lambda p, k: out.append((float(p), k)) if p == p and p > 0 else None  # noqa: E731
        add(h[i - 1], "pd_high"); add(l[i - 1], "pd_low"); add(c[i - 1], "pd_close")
        add(self.pw.high.iat[i], "pw_high"); add(self.pw.low.iat[i], "pw_low"); add(self.pw.close.iat[i], "pw_close")
        add(self.pm.high.iat[i], "pm_high"); add(self.pm.low.iat[i], "pm_low")
        a = max(0, i - 252)
        if i - a >= 120:
            add(np.nanmax(h[a:i]), "52w_high"); add(np.nanmin(l[a:i]), "52w_low")
        add(self.pre_hi[i], "premkt_high"); add(self.pre_lo[i], "premkt_low")
        if opening_range:
            add(self.or_hi[i], "or_high"); add(self.or_lo[i], "or_low")
        # swings: confirmed (3 sessions later) within the last 120 sessions; cluster within 0.5%
        for idx, arr, kind in ((self.sw_hi, h, "swing_high"), (self.sw_lo, l, "swing_low")):
            js = idx[(idx >= i - 120) & (idx <= i - 4)]
            ps = np.sort(arr[js])
            k = 0
            while k < len(ps):
                e = k
                while e + 1 < len(ps) and ps[e + 1] <= ps[k] * 1.005:
                    e += 1
                for _ in range(min(e - k + 1, 4)):       # one entry per touch (up to 4): more touches, more weight
                    out.append((float(ps[k:e + 1].mean()), kind))
                k = e + 1
        # unfilled daily gaps of the last 60 sessions (a true gap: open beyond the prior day's range by 0.3%+)
        for j in range(max(2, i - 60), i):
            if self.o[j] > h[j - 1] * 1.003 and np.nanmin(l[j:i]) > h[j - 1]:
                add(h[j - 1], "gap_fill"); add(np.nanmin(l[j:i]), "gap_edge")
            elif self.o[j] < l[j - 1] * 0.997 and np.nanmax(h[j:i]) < l[j - 1]:
                add(l[j - 1], "gap_fill"); add(np.nanmax(h[j:i]), "gap_edge")
        # volume profile: last 20 sessions and yesterday
        for n, tag in ((20, "20d"), (1, "1d")):
            s, e = self.m_start[max(0, i - n)], self.m_end[i - 1]
            if e - s < 200:
                continue
            b, w = self.m_bin[s:e], self.m_vol[s:e]
            b0 = b.min()
            hist = np.bincount(b - b0, weights=w)
            sm = np.convolve(hist, [0.25, 0.5, 0.25], "same")
            p = int(sm.argmax())
            price = lambda k: float(np.exp((k + b0 + 0.5) * BIN))  # noqa: E731
            add(price(p), "poc_" + tag)
            if n == 20:
                lo_i = hi_i = p
                tot, acc = hist.sum(), hist[p]
                while acc < 0.7 * tot and (lo_i > 0 or hi_i < len(hist) - 1):
                    up = hist[hi_i + 1] if hi_i < len(hist) - 1 else -1
                    dn = hist[lo_i - 1] if lo_i > 0 else -1
                    if up >= dn:
                        hi_i += 1; acc += up
                    else:
                        lo_i -= 1; acc += dn
                add(price(hi_i), "vah_20d"); add(price(lo_i), "val_20d")
        # anchored VWAPs, value at yesterday's close
        e = self.m_end[i - 1]
        a60 = max(0, i - 60)
        if i - a60 >= 20:
            gap = np.abs(self.o[1:i] / c[:i - 1] - 1) * (self.v[1:i] / self.v20[1:i])
            a90 = max(1, i - 90)
            gz = gap[a90 - 1:]
            ev = a90 + int(np.nanargmax(gz)) if np.isfinite(gz).any() else None
            for j, kind in ((a60 + int(np.nanargmax(h[a60:i])), "avwap_high"), (a60 + int(np.nanargmin(l[a60:i])), "avwap_low"),
                            (ev, "avwap_event")):
                if j is None or j >= i - 1:
                    continue                     # anchored yesterday: no history yet
                s = self.m_start[j]
                if e > s and self.cv[e] > self.cv[s]:
                    add((self.cpv[e] - self.cpv[s]) / (self.cv[e] - self.cv[s]), kind)
        for n in (9, 21, 50):
            add(self.ema[n][i], f"ema{n}")
        add(self.sma200[i], "sma200")
        ref = self.spot(i)
        if ref == ref:
            step = 10.0 if ref < 250 else 50.0
            for k in (np.floor(ref / step), np.floor(ref / step) + 1):
                add(k * step, "round")
            half = (np.floor(ref / step) + 0.5) * step
            add(half, "round_half")
        return out

    def tol(self, i: int) -> float:
        """Merge / match distance in dollars: 5% of the average daily range, at least 0.05% of price."""
        ref = self.spot(i)
        adr = self.adr[i] if self.adr[i] == self.adr[i] else 0.02 * ref
        return max(0.05 * adr, 0.0005 * ref)

    def zones(self, i: int, extra: list[tuple[float, str]] | None = None, opening_range: bool = True) -> list[Zone]:
        return cluster(self.raw(i, opening_range) + (extra or []), self.tol(i))


def cluster(raw: list[tuple[float, str]], tol: float) -> list[Zone]:
    """Merge levels within `tol` of each other (a zone never grows wider than 3 x tol) and score each zone."""
    out: list[Zone] = []
    cur: list[tuple[float, str]] = []
    for p, k in sorted(raw):
        if cur and (p - cur[-1][0] > tol or p - cur[0][0] > 3 * tol):
            out.append(_zone(cur))
            cur = []
        cur.append((p, k))
    if cur:
        out.append(_zone(cur))
    return out


def _zone(items: list[tuple[float, str]]) -> Zone:
    fam: dict[str, float] = {}
    for _, k in items:
        w = WEIGHT[k]
        if FAMILY[k] == "swing":                    # each extra touch of a swing level adds a point (up to 3)
            fam["swing"] = min(fam.get("swing", w - 1) + 1, w + 3)
        else:
            fam[FAMILY[k]] = max(fam.get(FAMILY[k], 0), w)
    score = sum(fam.values()) + 0.5 * (len(fam) - 1)
    return Zone(min(p for p, _ in items), max(p for p, _ in items), round(score, 1), [k for _, k in items])


def select(zones: list[Zone], spot: float, adr: float, n: int = 4, reach: float = 3.0) -> tuple[list[Zone], list[Zone]]:
    """The n highest-scoring zones above and below `spot` within `reach` daily ranges (a zone holding the price counts
    on the side its middle is). Returned nearest first."""
    near = [z for z in zones if abs(z.mid - spot) <= reach * adr]
    above = sorted([z for z in near if z.mid >= spot], key=lambda z: -z.score)[:n]
    below = sorted([z for z in near if z.mid < spot], key=lambda z: -z.score)[:n]
    return sorted(above, key=lambda z: z.mid), sorted(below, key=lambda z: -z.mid)


def at(zones: list[Zone], px: float, tol: float) -> Zone | None:
    """The best-scoring zone within `tol` of px, if any."""
    hits = [z for z in zones if z.lo - tol <= px <= z.hi + tol]
    return max(hits, key=lambda z: z.score) if hits else None


def load_sheet(day: pd.Timestamp, folder: Path = SHEET_DIR) -> pd.DataFrame | None:
    """Today's raw levels as written by the morning sheet (sym, price, kind, tol, adr, spot), or None if it was not made."""
    p = folder / f"{pd.Timestamp(day):%Y-%m-%d}.csv"
    return pd.read_csv(p) if p.exists() else None


def zone_at(sheet: pd.DataFrame | None, sym: str, px: float, opening_range: tuple[float, float] | None = None) -> Zone | None:
    """The zone of `sym` that price px sits at, from the morning sheet. The sheet is made before the open, so the opening
    range is passed in once it exists (after 10:00 ET); the sheet's own opening-range rows are ignored."""
    if sheet is None:
        return None
    x = sheet[sheet.sym == sym]
    if not len(x):
        return None
    raw = [(float(p), k) for p, k in zip(x.price, x.kind) if not k.startswith("or_")]
    if opening_range:
        raw += [(float(opening_range[0]), "or_high"), (float(opening_range[1]), "or_low")]
    tol = float(x.tol.iat[0])
    return at(cluster(raw, tol), px, 0.6 * tol)
