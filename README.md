# VPA-Trading

## Kronos setup

[Kronos](https://github.com/shiyu-coder/Kronos) (a foundation model for financial
candlestick/K-line data) is vendored as a git submodule at `third_party/Kronos`,
pinned to upstream commit `67b630e`.

```bash
git submodule update --init
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python scripts/kronos_smoke_test.py   # downloads NeoQuasar/Kronos-small + Kronos-Tokenizer-base
```

```python
from vpa_trading.kronos_loader import load_kronos_small
predictor = load_kronos_small()          # KronosPredictor, max_context=512
pred_df = predictor.predict(df=x_df, x_timestamp=x_ts, y_timestamp=y_ts, pred_len=24)
```

`x_df` needs `open, high, low, close` (and optionally `volume`, `amount`); keep
the lookback at or below 512 bars. Weights are cached in `~/.cache/huggingface`
(override with `HF_HOME`).
