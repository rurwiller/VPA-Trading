"""Run the point-in-time guard over the signal code the live scanner and the research scripts rely on.

Each signal is computed on a month of real TSLA bars, then recomputed with the future cut off at 40 random bars;
any value that changes is look-ahead. Prints PASS / FAIL per signal.

  python scripts/lookahead_audit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import indicators as ind, pit, vpa  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
from vpa_trading.live import climaxes, frame  # noqa: E402
from vpa_trading.willard_osc import willard_osc  # noqa: E402
from osc_oversold_test import daily  # noqa: E402
from osc_oversold_v2 import at_gap, bull_gaps  # noqa: E402


def code(det, index):
    """Detections -> one number per bar (which types fired, signed by bias)."""
    out = pd.Series(0.0, index=index)
    for t, r in det.iterrows():
        out[t] += r.bias * (1 + (sum(map(ord, str(r.type))) % 997))
    return out


def gaps_formed(b):
    g = ind.fvgs(b, b.atr, b.volume / b.volume.rolling(20).mean(), b.closes_at, intraday_only=False)
    out = pd.Series(0.0, index=b.index)
    for _, r in g.iterrows():
        k = b.index[b.closes_at == r.formed_at]
        if len(k):
            out[k[0]] += r.dir * (1 + round(r.bottom, 2))
    return out


def main():
    m1 = load_bars_file("data/alpaca/TSLA-1m-ext.csv.gz")
    m1 = m1[m1.index >= m1.index.max() - pd.Timedelta(days=45)]
    tests = {}
    for tf in ("9m", "15m"):
        b = frame(m1, tf)
        tests[f"{tf} premier/climax detection (vpa.detect)"] = (lambda d: code(vpa.detect(d, d.atr), d.index), b)
        tests[f"{tf} climax list used live (live.climaxes)"] = (lambda d: code(climaxes(d), d.index), b)
        tests[f"{tf} time-of-day relative volume"] = (lambda d: vpa.relvol_tod(d), b)
        tests[f"{tf} trend context"] = (lambda d: vpa.context(d, d.atr).astype(float), b)
        tests[f"{tf} 3-bar gaps (indicators.fvgs)"] = (gaps_formed, b)
        tests[f"{tf} Willard oscillator"] = (lambda d: willard_osc(d)["osc"], b)
    dd = daily("AAPL")[["open", "high", "low", "close", "volume"]]
    tests["daily unfilled-gap check (fixed)"] = (
        lambda d: pd.Series([float(at_gap(d.low.to_numpy(), d.close.to_numpy(), bull_gaps(d), int(i), lambda a, k: a < k))
                             for i in range(len(d))], index=d.index), dd.iloc[-700:])
    bad = 0
    for name, (fn, b) in tests.items():
        try:
            n = pit.assert_no_lookahead(fn, b, n=40, warmup=min(150, len(b) // 3))
            print(f"PASS  {name}  ({n} bars checked)")
        except pit.LookAheadError as e:
            bad += 1
            print(f"FAIL  {name}: {e}")
    print(f"\n{bad} failing signal(s)")


if __name__ == "__main__":
    main()
