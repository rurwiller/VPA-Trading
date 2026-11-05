"""Live noise-area (trend-day) breakout, same rules as scripts/intraday_momentum_test.py (Zarattini, Aziz, Barbon 2024).

  sigma_t   average |close_t / open - 1| at the same minute over the previous 14 sessions
  bands     upper = max(open, prior close) x (1 + sigma_t), lower = min(open, prior close) x (1 - sigma_t)
  checks    only at 10:00, 10:30, ..., 15:30 ET, on the close of the minute that ends there
  rules     above upper -> long, below lower -> short; a long exits when price is below max(upper, VWAP), a short
            when above min(lower, VWAP), then may reverse at the same check; flat at the scanner's 15:50 flatten
            (the backtest held to 16:00)
  orders    market orders sized to a fixed notional, plus a protective stop 2.5% away (not in the backtest: a guard
            for moves between checks); client_order_id prefix "nb-"
State (position, qty, protective stop id) is kept in logs/live/nb_<SYM>_<date>.json so a restart picks it up.
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
        self.done: set[int] = set()

    # ------------------------------------------------------------ state
    def _state_path(self) -> Path:
        return self.log_dir / f"nb_{self.sym}_{self.day:%Y-%m-%d}.json"

    def _save(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._state_path().write_text(json.dumps({"pos": self.pos, "qty": self.qty, "entry": self.entry,
                                                  "guard_id": self.guard_id, "done": sorted(self.done)}))

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
        if self.paper and self.pos:
            self._sync()

    def _sync(self) -> None:
        """If the protective stop filled (or the position is gone), go flat."""
        r = requests.get(TRADE + f"/positions/{self.sym}", headers=headers(), timeout=30)
        have = int(float(r.json()["qty"])) if r.status_code == 200 else 0
        if self.pos and np.sign(have) != self.pos:
            self._log("guard stop hit / position gone", time=pd.Timestamp.now(tz="America/New_York").tz_localize(None))
            self.pos, self.qty, self.guard_id = 0, 0, None
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
            self._sync()
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

    def _cancel_guard(self) -> None:
        if self.guard_id:
            requests.delete(TRADE + f"/orders/{self.guard_id}", headers=headers(), timeout=30)
            self.guard_id = None

    def _trade(self, want: int, px: float, now: pd.Timestamp) -> None:
        if self.pos != 0:
            if self.paper:
                self._cancel_guard()
                fill, q = self._wait_fill(self._order("sell" if self.pos > 0 else "buy", self.qty, "exit"))
                if q < self.qty:      # exit not (fully) done: keep the rest tracked and retry at the next check
                    self.qty -= q
                    g = self._order("sell" if self.pos > 0 else "buy", self.qty, "guard", type="stop",
                                    stop_price=f"{round(self.entry * (1 - self.pos * GUARD), 2):.2f}")
                    self.guard_id = g["id"] if g else None
                    self._log("exit incomplete", time=now, filled=q, still_open=self.qty)
                    return
                px = fill
            pnl = (px - self.entry) * self.pos * self.qty
            self._log("exit", time=now, px=px, qty=self.qty, side="long" if self.pos > 0 else "short",
                      entry=self.entry, approx_pnl=round(pnl, 2), bands=self.last_bands)
            self.pos, self.qty = 0, 0
        if want != 0:
            qty = int(self.notional // px)
            if self.paper:
                fill, q = self._wait_fill(self._order("buy" if want > 0 else "sell", qty, "entry"))
                if not q:
                    self._log("entry not filled (cancelled)", time=now, px=px, qty=qty)
                    return
                px, qty = fill, q     # adopt whatever filled, even partly
                guard = round(px * (1 - want * GUARD), 2)
                g = self._order("sell" if want > 0 else "buy", qty, "guard", type="stop", stop_price=f"{guard:.2f}")
                self.guard_id = g["id"] if g else None
            self.pos, self.qty, self.entry = want, qty, px
            self._log("entry", time=now, px=px, qty=qty, side="long" if want > 0 else "short", bands=self.last_bands)
