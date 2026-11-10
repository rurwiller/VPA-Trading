"""TerraShade levels from the user's own Discord server (read-only bot), never from the TerraShade site itself.

TerraShade's terms ban scraping the site and its API, but they offer a Discord bot that posts a levels card after the open
and after the close (`/autopost`). The TerraShade bot posts into two channels in the user's server; our own read-only bot
(token stored as a network secret for discord.com, injected by the proxy) reads those channels:
  #terrashade-heatmap   morning and close options cards
  #terrashade-alerts    levels for TSLA, AAPL and QQQ
The scanner reads both channels every 10 minutes (two small requests), keeps every new post raw in logs/terrashade/<date>.jsonl
and tags each signal with the latest levels for its ticker. Logged only, never a filter.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import requests

API = "https://discord.com/api/v10"
CHANNELS = {"heatmap": "1569544610664022159", "alerts": "1569545328733065356"}
TICKER = re.compile(r"\b([A-Z]{1,5}[WP]?)\b")
NUM = r"\$?(-?\d[\d,]*\.?\d*)"
# "Call wall: 400", "Put Wall 380", "Gamma flip — 383.0", "Zero gamma: 381", "Max pain: 390", "Vanna wall ..." etc.
LEVEL = re.compile(r"([A-Za-z][A-Za-z +/\-]{1,30}?)\s*[:=—–\-|]\s*" + NUM)


def _text(m: dict) -> list[str]:
    parts = [m.get("content") or ""]
    for e in m.get("embeds") or []:
        parts += [e.get("title") or "", e.get("description") or ""]
        parts += [f"{f.get('name', '')}: {f.get('value', '')}" for f in e.get("fields") or []]
    return [p for p in parts if p]


def parse(m: dict, known: set[str]) -> dict[str, dict]:
    """{ticker: {label: value}} from one post. Tickers are the ones we trade (`known`); labels are kept as written."""
    out: dict[str, dict] = {}
    cur = None
    for part in _text(m):
        for line in part.replace("**", "").replace("`", "").splitlines():
            hits = [t for t in TICKER.findall(line) if t in known]
            if hits:
                cur = hits[0]
            if cur is None:
                continue
            for lab, val in LEVEL.findall(line):
                lab = lab.strip().lower()
                if lab in {t.lower() for t in known}:
                    continue
                try:
                    out.setdefault(cur, {})[lab] = float(val.replace(",", ""))
                except ValueError:
                    pass
    return out


class TerraShadeFeed:
    def __init__(self, symbols: list[str], log_dir: Path = Path("logs/terrashade"), every_min: int = 10):
        self.known = set(symbols) | {"SPY", "QQQ", "SPX", "SPXW", "NDX", "IWM"}
        self.log_dir, self.every = log_dir, pd.Timedelta(minutes=every_min)
        self.after: dict[str, str] = {}
        self.levels: dict[str, dict] = {}          # ticker -> {label: value, "asof": time, "channel": name}
        self.at = None
        self.ok = True

    def refresh(self, now: pd.Timestamp) -> int:
        """Read new posts if it is time. Returns how many new posts were read."""
        if not self.ok or (self.at is not None and now - self.at < self.every):
            return 0
        self.at = now
        n = 0
        day = now.normalize()
        for name, cid in CHANNELS.items():
            params = {"limit": 50}
            if cid in self.after:
                params["after"] = self.after[cid]
            r = requests.get(f"{API}/channels/{cid}/messages", params=params, timeout=20)
            if r.status_code in (401, 403):
                print(f"TerraShade #{name}: no access ({r.status_code}); Discord feed off for today", flush=True)
                self.ok = False
                return n
            if not r.ok:
                continue
            msgs = sorted(r.json(), key=lambda m: int(m["id"]))
            if not msgs:
                continue
            self.after[cid] = msgs[-1]["id"]
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_dir / f"{day:%Y-%m-%d}.jsonl", "a") as f:
                for m in msgs:
                    f.write(json.dumps({"channel": name, **m}) + "\n")
            for m in msgs:
                t = pd.Timestamp(m["timestamp"]).tz_convert("America/New_York").tz_localize(None)
                if t.normalize() != day and "after" in params:
                    continue
                for sym, lv in parse(m, self.known).items():
                    self.levels[sym] = {**lv, "asof": str(t), "channel": name}
                    n += 1
        return n

    def tag(self, sym: str) -> dict:
        return dict(self.levels.get(sym, {}))
