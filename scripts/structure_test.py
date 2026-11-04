"""Does adding market structure / divergence / volume / ADX confluence improve the 15m+9m+5m rule?

For every 15m+9m+5m stack event, five reversal-evidence items (all known at the bar close):
  retest     5m push comes within 0.5 ATR of the last confirmed 5m swing high (short) / low (long)
  rsi_div    5m push breaks that swing but RSI(14) is lower than at the swing (bearish), mirror bullish
  vol_fade   last six 5m bars: price moving with the stretch while volume falls (Coulling weak rally)
  adx_fade   ADX(15m) >= 25 and falling
  structure  15m swings no longer HH+HL (for a short) / LL+LH (for a long)
score = number of items present (0-5). Swing = 5-bar pivot, confirmed 2 bars later.

  python scripts/structure_test.py [SYM ...]   -> results/structure_events.pkl + reports/structure.md
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vpa_trading import research as R  # noqa: E402
from vpa_trading.alpaca import load_bars_file  # noqa: E402
from vpa_trading.vpa import _slope  # noqa: E402
from vpa_trading.willard_osc import _rsi  # noqa: E402
from research_run import DEFAULT  # noqa: E402

PIV = 2


def pivots(b: pd.DataFrame, col: str, kind: str) -> tuple[pd.Series, pd.Series]:
    """Pivot values placed at their confirmation bar (j + PIV), plus the bar position j."""
    x = b[col]
    roll = x.rolling(2 * PIV + 1, center=True)
    is_p = x == (roll.max() if kind == "high" else roll.min())
    val = x.where(is_p).shift(PIV)
    pos = pd.Series(np.where(is_p, np.arange(len(x)), np.nan), index=x.index).shift(PIV)
    return val, pos


def swing_feats(b: pd.DataFrame) -> pd.DataFrame:
    rsi = _rsi(b.close, 14)
    f = pd.DataFrame(index=b.index)
    for kind, sgn in (("high", 1), ("low", -1)):
        val, pos = pivots(b, kind, kind)
        rsi_at = pd.Series(np.nan, index=b.index)
        ok = pos.notna()
        rsi_at[ok] = rsi.to_numpy()[pos[ok].astype(int).to_numpy()]
        prev = val.shift(3).ffill()          # a swing confirmed before the current 3-bar push
        prev_rsi = rsi_at.shift(3).ffill()
        push = b[kind].rolling(3).max() if sgn > 0 else b[kind].rolling(3).min()
        push_rsi = rsi.rolling(3).max() if sgn > 0 else rsi.rolling(3).min()
        f[f"retest_{kind}"] = (push - prev).abs() <= 0.5 * b.atr
        f[f"div_{kind}"] = ((push - prev) * sgn > 0) & ((push_rsi - prev_rsi) * sgn < 0)
    vs, ps = _slope(b.volume, 6), _slope(b.close, 6)
    f["vol_fade_up"] = (vs < 0) & (ps > 0)
    f["vol_fade_dn"] = (vs < 0) & (ps < 0)
    return f.astype(float)


def structure_feats(b: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=b.index)
    for kind in ("high", "low"):
        val, _ = pivots(b, kind, kind)
        p = val.dropna()
        out[f"last_{kind}"] = p.reindex(b.index).ffill()
        out[f"prev_{kind}"] = p.shift().reindex(b.index).ffill()
    up = (out.last_high > out.prev_high) & (out.last_low > out.prev_low)
    dn = (out.last_high < out.prev_high) & (out.last_low < out.prev_low)
    return pd.DataFrame({"struct_up": up.astype(float), "struct_dn": dn.astype(float)}, index=b.index)


def run_symbol(sym: str) -> pd.DataFrame:
    m1 = load_bars_file(Path("data/alpaca") / f"{sym}-1m-ext.csv.gz", regular_only=False)
    s = R.prepare(sym, m1)
    b5, b15 = s.tf["5m"], s.tf["15m"]
    b5 = b5.join(swing_feats(b5))
    b15 = b15.join(structure_feats(b15))
    ev = pd.concat([R.stack_events(s, ["15m", "9m", "5m"], lv) for lv in (20, 25, 30)], ignore_index=True)
    ev = pd.concat([ev.reset_index(drop=True), R.outcomes(s, ev.reset_index(drop=True))], axis=1)
    t = s.clock[ev.i.to_numpy()]
    a5 = R.asof(b5, t, ["retest_high", "retest_low", "div_high", "div_low", "vol_fade_up", "vol_fade_dn"])
    a15 = R.asof(b15, t, ["struct_up", "struct_dn", "adx", "adx_slope"])
    up = ev.stretch.to_numpy() > 0
    ev["retest"] = np.where(up, a5.retest_high, a5.retest_low)
    ev["rsi_div"] = np.where(up, a5.div_high, a5.div_low)
    ev["vol_fade"] = np.where(up, a5.vol_fade_up, a5.vol_fade_dn)
    ev["adx_fade"] = ((a15.adx >= 25) & (a15.adx_slope < 0)).astype(float).to_numpy()
    ev["structure"] = np.where(up, 1 - a15.struct_up, 1 - a15.struct_dn)
    items = ["retest", "rsi_div", "vol_fade", "adx_fade", "structure"]
    ev[items] = ev[items].fillna(0)
    ev["score"] = ev[items].sum(axis=1).astype(int)
    ev["time"] = pd.to_datetime(t)
    return ev


def main() -> None:
    import research_report as rr
    syms = sys.argv[1:] or DEFAULT
    with ProcessPoolExecutor(max_workers=3) as ex:
        ev = pd.concat(list(ex.map(run_symbol, syms)), ignore_index=True)
    ev.to_pickle("results/structure_events.pkl")
    ev["period"] = np.where(ev.time < pd.Timestamp("2024-11-01"), "disc", "hold")
    cols = ["variant", "mode", "n_d", "win15_d", "r15_d", "pct_win_d", "atr_R_d", "2se_d",
            "n_h", "win15_h", "r15_h", "pct_win_h", "atr_R_h", "2se_h"]
    L = ["# Market structure confluence on the 15m+9m+5m rule\n",
         f"{len(ev)} trades, {', '.join(sorted(ev.sym.unique()))}. `_d` = before 2024-11-01, `_h` = after.",
         "fade = trade the reversal (the setup you trade); cont = the opposite. Costs 2 bps.\n"]
    for item in ["retest", "rsi_div", "vol_fade", "adx_fade", "structure"]:
        L.append(f"\n## {item} present (1) or not (0)\n")
        L.append(rr.md(rr.two_period(ev, ["variant", "mode", item])[["variant", "mode", item] + cols[2:]]))
    ev["score_band"] = np.where(ev.score >= 4, "4-5", ev.score.astype(str))
    L.append("\n## Confluence score (number of the five items present)\n")
    L.append(rr.md(rr.two_period(ev, ["variant", "mode", "score_band"])[["variant", "mode", "score_band"] + cols[2:]]))
    Path("reports/structure.md").write_text("\n".join(L) + "\n")
    print("wrote reports/structure.md")


if __name__ == "__main__":
    main()
