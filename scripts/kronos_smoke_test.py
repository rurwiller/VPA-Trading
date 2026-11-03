"""Load Kronos-small from Hugging Face and forecast a synthetic OHLCV series.

Usage: python scripts/kronos_smoke_test.py [--device cpu]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vpa_trading.kronos_loader import load_kronos_small  # noqa: E402


def synthetic_ohlcv(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, n))
    volume = rng.uniform(1e3, 5e3, n)
    ts = pd.date_range("2025-01-02 09:30", periods=n, freq="5min")
    return pd.DataFrame({"timestamps": ts, "open": open_, "high": high, "low": low,
                         "close": close, "volume": volume, "amount": volume * close})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=None)
    ap.add_argument("--lookback", type=int, default=400)
    ap.add_argument("--pred-len", type=int, default=24)
    args = ap.parse_args()

    predictor = load_kronos_small(device=args.device)
    n_params = sum(p.numel() for p in predictor.model.parameters())
    print(f"Loaded Kronos-small on {predictor.device}: {n_params / 1e6:.1f}M params")

    df = synthetic_ohlcv(args.lookback + args.pred_len)
    x = df.iloc[: args.lookback]
    pred = predictor.predict(
        df=x[["open", "high", "low", "close", "volume", "amount"]],
        x_timestamp=x["timestamps"],
        y_timestamp=df["timestamps"].iloc[args.lookback:].reset_index(drop=True),
        pred_len=args.pred_len, T=1.0, top_p=0.9, sample_count=1, verbose=False,
    )
    print(pred.head())
    assert len(pred) == args.pred_len and np.isfinite(pred.values).all()
    print("OK")


if __name__ == "__main__":
    main()
