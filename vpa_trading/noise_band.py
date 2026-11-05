"""Live noise-area (trend-day) breakout, same rules as scripts/intraday_momentum_test.py (Zarattini, Aziz, Barbon 2024).

  sigma_t   average |close_t / open - 1| at the same minute over the previous 14 sessions
  bands     upper = max(open, prior close) x (1 + sigma_t), lower = min(open, prior close) x (1 - sigma_t)
  checks    only at 10:00, 10:30, ..., 15:30 ET, on the close of the minute that ends there
  rules     above upper -> long, below lower -> short; a long exits when price is below max(upper, VWAP), a short
            when above min(lower, VWAP), then may reverse at the same check; flat at the scanner's 15:50 flatten
            (the backtest held to 16:00)
  orders    market orders sized to a fixed notional; client_order_id prefix "nb-"
  scale out the position is split in thirds: the first third takes profit at 1% from the entry (a resting limit order),
            the second at 2%, and the last third runs with the rule above. Every third also has a protective stop
            2.5% from the entry (an OCO pair with its limit, a plain stop for the last third), not in the backtest:
            a guard for moves between checks. If price is already beyond a level when the orders are placed (for
            example after a restart), that third is taken at market right away.
            5-year TSLA test: more winning days (42% -> 48%) and a smaller worst day for a lower average gain.
  breakeven as soon as the first third has taken its profit, the stop on every remaining third moves to the entry price
            (the trade can no longer lose); stops are re-placed right then.
State (position, remaining qty, tranches) is kept in logs/live/nb_<SYM>_<date>.json so a restart picks it up.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .live import TRADE, headers

CHECK_MINUTES = list(range(30, 361, 30))   # minutes after 9:30 at which a check happens (10:00 ... 15:30)
GUARD = 0.025
SCALE_LEVELS = (0.01, 0.02)      # profit levels (fraction of the entry price) for the first and second third


def sigma_curve(hist: pd.DataFrame, day: pd.Timestamp, lookback: int = 14) -> pd.Series:
    """sigma by minute-after-open (1..390) from the previous `lookback` full sessions of 1m bars."""
    h = hist[hist.index.normalize() < day]
    h = h[(h.index.time >= pd.Timestamp("09:30").time()) & (h.index.time < pd.Timestamp("16:00").time())]
    rows = []
    for d, g in h.groupby(h.index.normalize()):
        mi = ((g.index - d) / pd.Timedelta(minutes=1)).astype(int) - 570 + 1   # minutes after open at the bar close
        c = pd.Series(g.close.to_numpy(), index=mi).reindex(range(1, 391)).ffill()
        if c.notna().sum() < 380:
            continue
        rows.append((c / float(g.open.iat[0]) - 1).abs())
    rows = rows[-lookback:]
    return pd.concat(rows, axis=1).mean(axis=1) if len(rows) == lookback else pd.Series(dtype=float)


class NoiseBand:
    def __init__(self, sym: str, notional: float, log_dir: Path, paper: bool):
        self.sym, self.notional, self.log_dir, self.paper = sym, notional, log_dir, paper
        self.day = None
        self.sigma = pd.Series(dtype=float)
        self.prev_close = self.open = np.nan
        self.pos, self.qty, self.entry, self.guard_id = 0, 0, np.nan, None
        self.tranches: list[dict] = []
        self.orig_qty, self.taken_levels, self.breakeven = 0, 0, False
        self.done: set[int] = set()
        self.last_bands = (np.nan, np.nan)

    # ------------------------------------------------------------ state
    def _state_path(self) -> Path:
        return self.log_dir / f"nb_{self.sym}_{self.day:%Y-%m-%d}.json"

    def _save(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._state_path().write_text(json.dumps({"pos": self.pos, "qty": self.qty, "entry": self.entry,
                                                  "guard_id": self.guard_id, "tranches": self.tranches,
                                                  "orig_qty": self.orig_qty, "taken_levels": self.taken_levels,
                                                  "breakeven": self.breakeven,
                                                  "done": sorted(self.done)}))

    @staticmethod
    def _now() -> pd.Timestamp:
        return pd.Timestamp.now(tz="America/New_York").tz_localize(None)

    def _log(self, kind: str, **kw) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        rec = {"kind": kind, "strategy": "noise_band", "sym": self.sym, **kw}
        with open(self.log_dir / f"{self.day:%Y-%m-%d}.jsonl", "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(f"[{(pd.Timestamp(kw.get('time', pd.Timestamp.now())) - pd.Timedelta(hours=2)):%H:%M} MST] NB {self.sym} {kind} "
              + " ".join(f"{k}={v}" for k, v in kw.items() if k != "time"), flush=True)

    def start_day(self, hist: pd.DataFrame, today: pd.DataFrame, day: pd.Timestamp) -> None:
        self.day = day
        self.sigma = sigma_curve(hist, day)
        prev = hist[hist.index.normalize() < day]
        prev = prev[prev.index.time < pd.Timestamp("16:00").time()]
        self.prev_close = float(prev.close.iat[-1]) if len(prev) else np.nan
        p = self._state_path()
        if p.exists():
            s = json.loads(p.read_text())
            self.pos, self.qty, self.entry, self.guard_id, self.done = s["pos"], s["qty"], s["entry"], s["guard_id"], set(s["done"])
            self.tranches = s.get("tranches", [])
            self.orig_qty = s.get("orig_qty") or (sum(t["qty"] for t in self.tranches) if self.tranches else self.qty)
            self.taken_levels, self.breakeven = s.get("taken_levels", 0), s.get("breakeven", False)
            if "breakeven" not in s and self.pos:      # state from before breakeven stops existed
                sz = [self.orig_qty // 3, self.orig_qty // 3, self.orig_qty - 2 * (self.orig_qty // 3)]
                self.taken_levels = next((k for k in (0, 1, 2) if self.qty >= sum(sz[k:]) - 1), 0)
                if self.taken_levels:
                    self.breakeven, self.tranches = True, []     # empty tranches = re-place the protection next minute
        if self.paper and self.pos:
            self._sync()

    def _sync(self, now: pd.Timestamp | None = None) -> None:
        """Compare with Alpaca: shares closed there (profit-taking limits or protective stops) reduce the tracked qty."""
        now = now or self._now()
        r = requests.get(TRADE + f"/positions/{self.sym}", headers=headers(), timeout=30)
        have = int(float(r.json()["qty"])) if r.status_code == 200 else 0
        if self.pos and np.sign(have) != self.pos:
            self._log("position closed at Alpaca (profit targets / protective stop)", time=now)
            self.pos, self.qty, self.guard_id, self.tranches = 0, 0, None, []
            self._save()
        elif self.pos and abs(have) < self.qty:
            closed = self.qty - abs(have)
            self._log("shares closed at Alpaca (profit target)", time=now, closed=closed, remaining=abs(have))
            self.qty = abs(have)
            if self.paper and self.taken_levels < 2:    # a partial close with the position still open = a profit limit filled
                self.taken_levels = min(2, self.taken_levels + max(1, round(closed / max(self.orig_qty / 3, 1))))
                self.breakeven = True
                px = float(r.json().get("current_price") or self.entry)
                self._attach(px, now)                   # re-place the protection with stops at breakeven
            self._save()

    # ------------------------------------------------------------ decisions
    def decide(self, px: float, vwap: float, minute: int) -> int:
        s = float(self.sigma.get(minute, np.nan))
        if np.isnan(s) or np.isnan(self.prev_close) or np.isnan(self.open):
            return self.pos
        ub = max(self.open, self.prev_close) * (1 + s)
        lb = min(self.open, self.prev_close) * (1 - s)
        want = self.pos
        if self.pos == 1 and px < max(ub, vwap):
            want = 0
        elif self.pos == -1 and px > min(lb, vwap):
            want = 0
        if want == 0:
            want = 1 if px > ub else (-1 if px < lb else 0)
        self.last_bands = (round(lb, 2), round(ub, 2))
        return want

    def on_minute(self, today: pd.DataFrame, now: pd.Timestamp, blocked: bool) -> None:
        """Call once per minute with today's 1m bars closed before `now`. blocked = the candle scanner holds this symbol."""
        if not len(today):
            return
        if np.isnan(self.open):
            self.open = float(today.open.iat[0])
        if self.paper and self.pos:
            self._sync(now)
            if self.pos and not self.tranches:       # position opened before scale-out existed (or after a restart)
                self._attach(float(today.close.iat[-1]), now)
        elif not self.paper and self.pos and self.tranches:
            self._sim_targets(today.iloc[-1], now)
        minute = int((now - now.normalize()) / pd.Timedelta(minutes=1)) - 570
        if minute not in CHECK_MINUTES or minute in self.done:
            return
        self.done.add(minute)
        px = float(today.close.iat[-1])
        pv = (today.vwap.fillna(today.close) if "vwap" in today else today.close) * today.volume
        vwap = float(pv.sum() / today.volume.sum()) if today.volume.sum() > 0 else px
        want = self.decide(px, vwap, minute)
        if want != self.pos and want != 0 and self.pos == 0 and blocked:
            self._log("entry skipped: candle scanner holds the symbol", time=now, px=px, want=want, bands=self.last_bands)
            self._save()
            return
        if want != self.pos:
            self._trade(want, px, now)
        self._save()

    # ------------------------------------------------------------ orders
    def _order(self, side: str, qty: int, tag: str, **extra) -> dict | None:
        body = {"symbol": self.sym, "qty": str(qty), "side": side, "time_in_force": "day",
                "client_order_id": f"nb-{self.sym}-{tag}-{pd.Timestamp.now():%Y%m%d%H%M%S}", **extra}
        body.setdefault("type", "market")
        r = requests.post(TRADE + "/orders", headers=headers(), json=body, timeout=30)
        if not r.ok:
            self._log("order rejected", side=side, qty=qty, why=r.text[:200])
            return None
        return r.json()

    @staticmethod
    def _wait_fill(o: dict | None, tries: int = 60) -> tuple[float | None, int]:
        """Poll a market order until it fills. If it is still open after `tries` seconds, cancel it and report
        whatever did fill, so a slow fill is never left untracked. Returns (avg fill price or None, filled qty)."""
        import time
        if not o:
            return None, 0
        r = o
        for _ in range(tries):
            r = requests.get(TRADE + f"/orders/{o['id']}", headers=headers(), timeout=30).json()
            if r.get("status") == "filled":
                return float(r["filled_avg_price"]), int(float(r["filled_qty"]))
            if r.get("status") in ("canceled", "rejected", "expired"):
                break
            time.sleep(1.0)
        if r.get("status") not in ("canceled", "rejected", "expired", "filled"):
            requests.delete(TRADE + f"/orders/{o['id']}", headers=headers(), timeout=30)
            time.sleep(2.0)
            r = requests.get(TRADE + f"/orders/{o['id']}", headers=headers(), timeout=30).json()
        q = int(float(r.get("filled_qty") or 0))
        return (float(r["filled_avg_price"]) if q else None), q

    def _cancel_protection(self) -> None:
        """Cancel every open order this strategy placed on the symbol (profit limits and stops)."""
        import time
        r = requests.get(TRADE + "/orders", headers=headers(), params={"status": "open", "symbols": self.sym}, timeout=30)
        n = 0
        for o in r.json() if r.ok else []:
            if o["client_order_id"].startswith("nb-"):
                requests.delete(TRADE + f"/orders/{o['id']}", headers=headers(), timeout=30)
                n += 1
        if n:
            time.sleep(1.5)
        self.guard_id = None

    def _protect(self, q: int, side: str, guard: float, tag: str, now: pd.Timestamp) -> None:
        """A plain stop for q shares; if the stop is invalid (price already through it) close those shares at market."""
        if q <= 0:
            return
        if self._order(side, q, tag, type="stop", stop_price=f"{guard:.2f}") is None:
            fill, f = self._wait_fill(self._order(side, q, tag + "mkt"))
            self._log("stop not valid (price already through it): closed at market", time=now, qty=f, px=fill)
            self.qty = max(self.qty - f, 0)

    def _attach(self, px_now: float, now: pd.Timestamp) -> None:
        """Set the protection for the shares still open: a limit + stop (OCO) for each remaining profit level, a stop for
        the last third. The stop is 2.5% from the entry, or the entry price itself (breakeven) once a level has been
        taken. A level that price is already beyond is taken at market."""
        side = "sell" if self.pos > 0 else "buy"
        guard = round(self.entry, 2) if self.breakeven else round(self.entry * (1 - self.pos * GUARD), 2)
        orig = self.orig_qty or self.qty
        sizes = [orig // 3, orig // 3, orig - 2 * (orig // 3)]
        if not self.paper:
            self.tranches = [{"qty": sizes[i], "target": round(self.entry * (1 + self.pos * lv), 2), "open": i >= self.taken_levels}
                             for i, lv in enumerate(SCALE_LEVELS)] + [{"qty": sizes[2], "target": None, "open": True}]
            return
        self._cancel_protection()
        r = requests.get(TRADE + f"/positions/{self.sym}", headers=headers(), timeout=30)
        have = abs(int(float(r.json()["qty"]))) if r.status_code == 200 else 0
        if have == 0:
            self.pos, self.qty, self.tranches = 0, 0, []
            return
        last_q = min(sizes[2], have)
        rest = have - last_q
        levels = list(range(self.taken_levels, len(SCALE_LEVELS)))
        qs = [rest] if len(levels) == 1 else ([rest // 2, rest - rest // 2] if len(levels) == 2 else [])
        if not levels:
            last_q = have
        self.tranches = []
        for i, q in zip(levels, qs):
            lv, target = SCALE_LEVELS[i], round(self.entry * (1 + self.pos * SCALE_LEVELS[i]), 2)
            if q <= 0:
                continue
            if (px_now - target) * self.pos >= 0:      # already past this level: take the profit now
                fill, f = self._wait_fill(self._order(side, q, f"take{i + 1}"))
                if f:
                    self._log("profit taken", time=now, level=f"{lv:.0%}", qty=f, px=fill, entry=round(self.entry, 2),
                              approx_pnl=round((fill - self.entry) * self.pos * f, 2))
                    self.taken_levels, self.breakeven, have = max(self.taken_levels, i + 1), True, have - f
                    self.tranches.append({"qty": f, "target": target, "open": False})
                    continue
            o = self._order(side, q, f"tp{i + 1}", type="limit", order_class="oco",
                            take_profit={"limit_price": f"{target:.2f}"}, stop_loss={"stop_price": f"{guard:.2f}"})
            if o is None:      # never leave shares unprotected
                self._protect(q, side, guard, f"stopfb{i + 1}", now)
            self.tranches.append({"qty": q, "target": target, "open": True})
        if self.breakeven and guard != round(self.entry, 2):   # a level was just taken at market: stops move to breakeven
            guard = round(self.entry, 2)
        self._protect(last_q, side, guard, "stop3", now)
        self.tranches.append({"qty": last_q, "target": None, "open": True})
        self.qty = max(have, 0)
        if self.qty <= 0:
            self.pos, self.qty, self.tranches = 0, 0, []
        self._log("protection set", time=now, remaining=self.qty, stop=guard, breakeven=self.breakeven,
                  targets=[t["target"] for t in self.tranches if t["target"] and t["open"]])
        self._save()

    def _sim_targets(self, bar: pd.Series, now: pd.Timestamp) -> None:
        """Replay only: a profit level counts as filled when a 1m bar reaches it."""
        if self.breakeven and self.qty > 0 and ((self.pos > 0 and bar.low <= self.entry) or (self.pos < 0 and bar.high >= self.entry)):
            self._log("breakeven stop", time=now, qty=self.qty, px=round(self.entry, 2))
            self.pos, self.qty, self.tranches = 0, 0, []
            return
        for t in self.tranches:
            if t["open"] and t["target"] and ((self.pos > 0 and bar.high >= t["target"]) or (self.pos < 0 and bar.low <= t["target"])):
                t["open"] = False
                self.taken_levels, self.breakeven = self.taken_levels + 1, True
                self.qty -= t["qty"]
                self.scaled_pnl = getattr(self, "scaled_pnl", 0.0) + (t["target"] - self.entry) * self.pos * t["qty"]
                self._log("profit taken", time=now, qty=t["qty"], px=t["target"], entry=round(self.entry, 2),
                          approx_pnl=round((t["target"] - self.entry) * self.pos * t["qty"], 2))

    def _trade(self, want: int, px: float, now: pd.Timestamp) -> None:
        if self.pos != 0:
            if self.paper:
                self._cancel_protection()
                self._sync(now)          # shares may have been closed by a profit limit a moment ago
                if not self.pos:
                    return
                fill, q = self._wait_fill(self._order("sell" if self.pos > 0 else "buy", self.qty, "exit"))
                if q < self.qty:      # exit not (fully) done: keep the rest tracked and retry at the next check
                    self.qty -= q
                    self._order("sell" if self.pos > 0 else "buy", self.qty, "guard", type="stop",
                                stop_price=f"{round(self.entry * (1 - self.pos * GUARD), 2):.2f}")
                    self._log("exit incomplete", time=now, filled=q, still_open=self.qty)
                    return
                px = fill
            pnl = (px - self.entry) * self.pos * self.qty
            self._log("exit", time=now, px=px, qty=self.qty, side="long" if self.pos > 0 else "short",
                      entry=self.entry, approx_pnl=round(pnl, 2), bands=self.last_bands)
            self.pos, self.qty, self.tranches = 0, 0, []
            self.orig_qty, self.taken_levels, self.breakeven = 0, 0, False
        if want != 0:
            qty = int(self.notional // px)
            if self.paper:
                fill, q = self._wait_fill(self._order("buy" if want > 0 else "sell", qty, "entry"))
                if not q:
                    self._log("entry not filled (cancelled)", time=now, px=px, qty=qty)
                    return
                px, qty = fill, q     # adopt whatever filled, even partly
            self.pos, self.qty, self.entry, self.tranches = want, qty, px, []
            self.orig_qty, self.taken_levels, self.breakeven = qty, 0, False
            self._log("entry", time=now, px=px, qty=qty, side="long" if want > 0 else "short", bands=self.last_bands)
            self._attach(px, now)
