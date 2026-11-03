"""Sample many Kronos futures for one chart and race them to a stop and a target.

The stock KronosPredictor averages its samples into one line (sample_count=N).
For entries we want the opposite: keep every sampled path and count how many
reach the target before the stop. That count only means something next to a
baseline, so race() also reports what a driftless random walk would give for
the same stop and target.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .kronos_loader import KronosPredictor

COLS = ["open", "high", "low", "close", "volume", "amount"]
# Path array layout: (n_paths, pred_len, 6) in COLS order.
O, H, L, C, V, A = range(6)


# ---------------------------------------------------------------- timestamps
def us_session_bars(after: pd.Timestamp, n: int, freq: str = "5min",
                    open_: str = "09:30", close: str = "16:00") -> pd.Series:
    """The next n regular-session bar start times after `after` (New York time,
    tz-naive). Skips weekends; does not know exchange holidays."""
    step = pd.Timedelta(freq)
    o, c = pd.Timestamp(open_).time(), pd.Timestamp(close).time()
    out, t = [], pd.Timestamp(after) + step
    while len(out) < n:
        day_open = pd.Timestamp.combine(t.date(), o)
        day_close = pd.Timestamp.combine(t.date(), c)
        if t.weekday() >= 5 or t >= day_close:
            nxt = t.normalize() + pd.Timedelta(days=1)
            while nxt.weekday() >= 5:
                nxt += pd.Timedelta(days=1)
            t = pd.Timestamp.combine(nxt.date(), o)
            continue
        if t < day_open:
            t = day_open
        out.append(t)
        t += step
    return pd.Series(out)


def business_days(after: pd.Timestamp, n: int) -> pd.Series:
    return pd.Series(pd.bdate_range(pd.Timestamp(after).normalize() + pd.Timedelta(days=1), periods=n))


# ------------------------------------------------------------------ sampling
def sample_paths(predictor: KronosPredictor, df: pd.DataFrame, x_timestamp: pd.Series,
                 y_timestamp: pd.Series, n_paths: int = 100, T: float = 1.0,
                 top_p: float = 0.9, batch_size: int = 50, seed: int | None = None) -> np.ndarray:
    """Return every sampled future as an array (n_paths, pred_len, 6), columns COLS.

    Same preprocessing as KronosPredictor.predict (per-window z-score, clip),
    done once and repeated across the batch instead of once per path.
    """
    import torch

    from model.kronos import calc_time_stamps  # Kronos package (on sys.path via kronos_loader)

    if seed is not None:
        torch.manual_seed(seed)
        np.random.seed(seed)

    df = df.copy()
    if "volume" not in df:
        df["volume"] = 0.0
    if "amount" not in df:
        df["amount"] = df["volume"] * df[["open", "high", "low", "close"]].mean(axis=1)
    x = df[COLS].to_numpy(np.float32)
    if np.isnan(x).any():
        raise ValueError("input bars contain NaN")
    x_ts = pd.Series(pd.to_datetime(x_timestamp)).reset_index(drop=True)
    y_ts = pd.Series(pd.to_datetime(y_timestamp)).reset_index(drop=True)
    if len(x_ts) != len(x):
        raise ValueError("x_timestamp length must match df")
    pred_len = len(y_ts)

    mean, std = x.mean(axis=0), x.std(axis=0)
    x_norm = np.clip((x - mean) / (std + 1e-5), -predictor.clip, predictor.clip)
    x_stamp = calc_time_stamps(x_ts).to_numpy(np.float32)
    y_stamp = calc_time_stamps(y_ts).to_numpy(np.float32)

    out = []
    done = 0
    while done < n_paths:
        b = min(batch_size, n_paths - done)
        preds = predictor.generate(
            np.repeat(x_norm[None], b, axis=0), np.repeat(x_stamp[None], b, axis=0),
            np.repeat(y_stamp[None], b, axis=0), pred_len, T, 0, top_p, 1, False)
        out.append(preds * (std + 1e-5) + mean)
        done += b
    paths = np.concatenate(out, axis=0)
    # Decoded candles are not guaranteed to be internally consistent; enforce it.
    paths[..., H] = np.maximum(paths[..., H], paths[..., [O, C]].max(axis=-1))
    paths[..., L] = np.minimum(paths[..., L], paths[..., [O, C]].min(axis=-1))
    return paths


# --------------------------------------------------------------------- race
@dataclass
class RaceResult:
    side: str
    entry: float
    stop: float
    target: float
    n: int
    target_first: int
    stop_first: int
    neither: int
    random_walk_target_first: float  # driftless baseline, share of resolved paths
    mean_bars_to_resolve: float

    @property
    def p_target(self) -> float:
        """Share of all paths that hit the target first."""
        return self.target_first / self.n

    @property
    def p_target_resolved(self) -> float:
        """Share of paths that resolved (hit either level) that hit the target."""
        r = self.target_first + self.stop_first
        return self.target_first / r if r else float("nan")

    @property
    def edge_vs_random(self) -> float:
        return self.p_target_resolved - self.random_walk_target_first

    @property
    def reward_risk(self) -> float:
        return abs(self.target - self.entry) / abs(self.entry - self.stop)

    def expected_r(self, cost_r: float = 0.0, neither_r: float = 0.0) -> float:
        """Expected result in R (multiples of risk) per trade under the model.

        neither_r: assumed average R for paths that touch neither level
        (0 = flat at the close). cost_r: round-trip fees + slippage, in R.
        """
        return (self.target_first * self.reward_risk - self.stop_first
                + self.neither * neither_r) / self.n - cost_r

    def summary(self) -> str:
        return (
            f"{self.side.upper()} entry {self.entry:.2f}  stop {self.stop:.2f}  target {self.target:.2f}"
            f"  ({self.reward_risk:.1f}R)\n"
            f"  {self.n} paths: target first {self.target_first}, stop first {self.stop_first},"
            f" neither {self.neither}\n"
            f"  of resolved paths, target first {self.p_target_resolved:.1%}"
            f" vs random walk {self.random_walk_target_first:.1%}"
            f"  (edge {self.edge_vs_random:+.1%})\n"
            f"  model-implied expectancy {self.expected_r():+.2f}R before costs"
        )


def race(paths: np.ndarray, entry: float, stop: float, target: float) -> RaceResult:
    """Count, for each path, which level its bars touch first.

    If one bar touches both levels the stop is counted (conservative, since the
    bar's internal order is unknown).
    """
    long = target > entry
    if long and not stop < entry:
        raise ValueError("long trade needs stop < entry < target")
    if not long and not stop > entry > target:
        raise ValueError("short trade needs target < entry < stop")
    hi, lo = paths[..., H], paths[..., L]
    hit_t = hi >= target if long else lo <= target
    hit_s = lo <= stop if long else hi >= stop
    big = paths.shape[1] + 1
    t_idx = np.where(hit_t.any(1), hit_t.argmax(1), big)
    s_idx = np.where(hit_s.any(1), hit_s.argmax(1), big)
    tgt = (t_idx < s_idx)
    stp = (s_idx <= t_idx) & (s_idx < big)
    resolved = tgt | stp
    first = np.minimum(t_idx, s_idx)
    return RaceResult(
        side="long" if long else "short", entry=float(entry), stop=float(stop), target=float(target),
        n=len(paths), target_first=int(tgt.sum()), stop_first=int(stp.sum()),
        neither=int((~resolved).sum()),
        random_walk_target_first=abs(entry - stop) / abs(target - stop),
        mean_bars_to_resolve=float(first[resolved].mean() + 1) if resolved.any() else float("nan"),
    )


# --------------------------------------------------------------------- cone
def cone(paths: np.ndarray, timestamps: pd.Series, qs=(10, 50, 90)) -> pd.DataFrame:
    """Per-bar percentiles of the close across paths (for charting the fan)."""
    q = np.percentile(paths[..., C], qs, axis=0)
    return pd.DataFrame({f"p{x}": q[i] for i, x in enumerate(qs)},
                        index=pd.DatetimeIndex(timestamps, name="timestamps"))


def atr(df: pd.DataFrame, n: int = 14) -> float:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.tail(n).mean())
