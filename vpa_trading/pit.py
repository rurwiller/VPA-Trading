"""Point-in-time research guards: make it hard for a backtest to fool us.

Why this exists: on Nov 21 2026 a one-line slip (slicing lows[i+1:] instead of lows[i+1:k]) let a "gap still
unfilled" filter peek at future prices and turned a useless filter into a fake +6% edge. These helpers catch that
class of mistake mechanically instead of by luck.

  assert_no_lookahead(fn, df)   run a signal function on the full history and on history cut off at sampled bars;
                                any bar whose value changes when the future is removed is look-ahead -> raises.
  holdout(frame, final=False)   the most recent months are kept for one final check; research code gets only the
                                part before HOLDOUT_START unless it explicitly asks for the final test.
  log_trial(...)                every variant tried is appended to results/trials.csv, so a winner can be judged
                                against how many tries it took (required_t grows with the number of trials).
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HOLDOUT_START = pd.Timestamp("2026-05-21")       # last 6 months at the time this was set up (Nov 21 2026)
TRIALS = Path("results/trials.csv")


class LookAheadError(AssertionError):
    pass


def _value_at(out, i):
    if isinstance(out, pd.DataFrame):
        return out.iloc[i].to_numpy(dtype=float)
    if isinstance(out, pd.Series):
        return np.array([float(out.iloc[i])])
    return np.array([float(np.asarray(out, dtype=float)[i])])


def assert_no_lookahead(fn, df: pd.DataFrame, n: int = 40, warmup: int = 100, seed: int = 0,
                        atol: float = 1e-7) -> int:
    """fn(df) must return values aligned with df's rows. Checks n random bars after `warmup`.

    For each sampled bar i: fn(df.iloc[:i+1]) at its last row must equal fn(df) at row i. Returns the number of bars
    checked; raises LookAheadError naming the first bar that changed.
    """
    full = fn(df)
    rng = np.random.default_rng(seed)
    idx = sorted(rng.choice(np.arange(warmup, len(df)), size=min(n, len(df) - warmup), replace=False))
    for i in idx:
        cut = fn(df.iloc[:i + 1])
        a, b = _value_at(full, i), _value_at(cut, len(df.iloc[:i + 1]) - 1)
        same = np.isclose(a, b, atol=atol, equal_nan=True)
        if not same.all():
            raise LookAheadError(f"value at {df.index[i]} is {a} with the full history but {b} without the future")
    return len(idx)


def holdout(frame, date_col: str | None = None, final: bool = False):
    """Research view: rows before HOLDOUT_START. final=True returns only the holdout rows (use once, at the end)."""
    d = frame[date_col] if date_col else frame.index
    d = pd.to_datetime(pd.Series(d, index=frame.index))
    return frame[(d >= HOLDOUT_START).to_numpy()] if final else frame[(d < HOLDOUT_START).to_numpy()]


def required_t(n_trials: int, alpha: float = 0.05) -> float:
    """t needed for one result to be significant after trying n_trials variants (Bonferroni, two-sided, normal)."""
    from statistics import NormalDist
    return NormalDist().inv_cdf(1 - alpha / (2 * max(1, n_trials)))


def tstat(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.mean() / (x.std() / math.sqrt(len(x)))) if len(x) > 2 and x.std() > 0 else float("nan")


def log_trial(study: str, variant: str, n: int, mean: float, t: float, unit: str = "", note: str = "") -> None:
    TRIALS.parent.mkdir(exist_ok=True)
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["logged_utc", "study", "variant", "n", "mean", "t", "unit", "note"])
        w.writerow([datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), study, variant, n,
                    f"{mean:.4f}", f"{t:.2f}", unit, note])


def trials_so_far(study: str | None = None) -> int:
    if not TRIALS.exists():
        return 0
    t = pd.read_csv(TRIALS)
    return int(len(t) if study is None else (t.study == study).sum())
