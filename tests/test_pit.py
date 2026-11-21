"""The point-in-time guards catch look-ahead (including the Nov 21 2026 gap bug) and pass honest signals."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from vpa_trading import pit  # noqa: E402
from vpa_trading.willard_osc import willard_osc  # noqa: E402
from osc_oversold_v2 import at_gap, bull_gaps  # noqa: E402


def bars(n=400, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    o = c * np.exp(rng.normal(0, 0.005, n))
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.02, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.02, n))
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": rng.uniform(1e6, 2e6, n)}, index=idx)


def test_catches_peeking_at_tomorrow():
    with pytest.raises(pit.LookAheadError):
        pit.assert_no_lookahead(lambda d: d.close.shift(-1), bars())


def test_passes_honest_signals():
    assert pit.assert_no_lookahead(lambda d: d.close.rolling(20).mean(), bars()) > 0
    assert pit.assert_no_lookahead(lambda d: willard_osc(d)["osc"], bars(), n=15) > 0


def _gap_signal(check):
    def fn(d):
        lows, closes, gaps = d.low.to_numpy(), d.close.to_numpy(), bull_gaps(d)
        return pd.Series([float(check(lows, closes, gaps, np.int64(i))) for i in range(len(d))], index=d.index)
    return fn


def old_at_gap(lows, closes, gaps, k):
    """The buggy version: a numpy-int k made it slice lows[i+1:], i.e. include the future."""
    for i, bot, top in gaps:
        if not i < k:
            continue
        prior = lows[i + 1:k] if isinstance(k, int) else lows[i + 1:]
        if len(prior) and prior.min() < bot:
            continue
        if lows[k] <= top and closes[k] >= bot:
            return True
    return False


def test_catches_the_gap_bug_and_passes_the_fix():
    d = bars(600, seed=3)
    with pytest.raises(pit.LookAheadError):
        pit.assert_no_lookahead(_gap_signal(old_at_gap), d, n=80)
    fixed = _gap_signal(lambda lo, c, g, k: at_gap(lo, c, g, k, lambda a, b: a < b))
    assert pit.assert_no_lookahead(fixed, d, n=80) > 0


def test_holdout_and_required_t():
    d = pd.DataFrame({"x": 1}, index=pd.date_range("2026-01-01", "2026-11-20"))
    assert pit.holdout(d).index.max() < pit.HOLDOUT_START
    assert pit.holdout(d, final=True).index.min() >= pit.HOLDOUT_START
    assert 1.9 < pit.required_t(1) < 2.0
    assert pit.required_t(100) > 3.4
