"""Load the Kronos forecasting model (vendored as a git submodule) from Hugging Face.

Kronos source: https://github.com/shiyu-coder/Kronos (third_party/Kronos)
Weights:       https://huggingface.co/NeoQuasar/Kronos-small
Tokenizer:     https://huggingface.co/NeoQuasar/Kronos-Tokenizer-base
"""
from __future__ import annotations

import sys
from pathlib import Path

KRONOS_DIR = Path(__file__).resolve().parent.parent / "third_party" / "Kronos"

if not (KRONOS_DIR / "model" / "kronos.py").exists():
    raise ImportError(
        f"Kronos source not found at {KRONOS_DIR}. Run: git submodule update --init"
    )
if str(KRONOS_DIR) not in sys.path:
    sys.path.insert(0, str(KRONOS_DIR))

from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402

MODEL_ID = "NeoQuasar/Kronos-small"
TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
MAX_CONTEXT = 512  # max sequence length for Kronos-small


def load_kronos_small(device: str | None = None, max_context: int = MAX_CONTEXT) -> KronosPredictor:
    """Download (or reuse cached) Kronos-small + its tokenizer and wrap them in a KronosPredictor.

    device: "cuda:0", "mps", "cpu", or None to auto-detect.
    """
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_ID)
    model = Kronos.from_pretrained(MODEL_ID)
    tokenizer.eval()
    model.eval()
    return KronosPredictor(model, tokenizer, device=device, max_context=max_context)


__all__ = ["Kronos", "KronosPredictor", "KronosTokenizer", "load_kronos_small", "MODEL_ID", "TOKENIZER_ID"]
