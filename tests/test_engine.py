"""Signal maths and the replay simulation of the candle scanner (no network)."""
import numpy as np
import pandas as pd
import pytest

from vpa_trading import levels as LVL, live as LV
from vpa_trading.alert import pivot_wick
from vpa_trading.noise_band import NoiseBand, sigma_curve
from vpa_trading.terrashade import parse

T0 = pd.Timestamp("2026-11-10 10:15")


def eng(**kw):
    return LV.Engine(LV.Config(symbols=["X"], risk_usd=1000, target="1R", **kw), {}, {})


def plan(e, side=-1, hi=100.5, lo=100.0, wick=None):
    wick = wick if wick is not None else (hi if side < 0 else lo)
    return e._plan("X", "15m", "premier", "T", side, T0, hi, lo, wick, "-")


def bar(o, h, l, c):
    return pd.Series({"open": o, "high": h, "low": l, "close": c, "volume": 1000.0})


def test_plan_short_prices_and_size():
    p = plan(eng())
    assert p.entry == 99.99                                   # one cent under the candle's low
    assert p.stop == pytest.approx(100.54, abs=0.011)         # just above the wick
    assert p.target == pytest.approx(p.entry - (p.stop - p.entry), abs=0.011)   # 1R
    assert p.qty == min(int(1000 // (p.stop - p.entry)), int(100_000 // p.entry))


def test_plan_notional_cap_cuts_the_real_risk():
    """A tight stop on a $1,000 risk hits the $100k cap, so the dollars at risk are far below $1,000."""
    p = plan(eng(), hi=100.10, lo=100.0)
    assert p.qty == int(100_000 // p.entry)
    assert (p.stop - p.entry) * p.qty < 250


def test_plan_minimum_stop_distance():
    """A candle with no range is refused (stop under 5 bps); anything with a real wick is planned, however tight."""
    assert plan(eng(), hi=100.0, lo=100.0) is None
    p = plan(eng(), hi=100.02, lo=100.0)
    assert 0.0005 < (p.stop - p.entry) / p.entry < 0.0008     # ~7 bps: costs of 2-3 bps are a third of this stop


def test_plan_long_mirror():
    p = plan(eng(), side=1)
    assert p.entry == 100.51 and p.stop < 100.0 and p.target > p.entry


def filled(e, half_at):
    e.cfg.half_at = half_at
    p = plan(e)
    e.plans.append(p)
    e.manage_sim("X", bar(100.1, 100.2, 99.9, 99.95), T0)                       # triggers the short at 99.99
    assert p.status == "filled" and p.fill == 99.99
    return p


def test_sim_stop_without_half():
    e = eng(); p = filled(e, 0)
    e.manage_sim("X", bar(100, 100.7, 99.9, 100.6), T0 + pd.Timedelta(minutes=1))
    assert p.status == "closed" and p.exit == p.stop and p.exit_reason == "stop"


def test_sim_half_then_breakeven():
    e = eng(); p = filled(e, 0.5)
    stop0, risk = p.stop, p.stop - p.fill
    e.manage_sim("X", bar(99.9, 99.95, 99.99 - 0.6 * risk, 99.8), T0 + pd.Timedelta(minutes=1))   # +0.5R reached
    assert p.status == "filled" and p.stop == p.fill
    e.manage_sim("X", bar(99.9, 100.2, 99.85, 100.1), T0 + pd.Timedelta(minutes=2))               # back to the entry
    assert p.status == "closed" and "half at +0.5R" in p.exit_reason and "breakeven" in p.exit_reason
    pnl_r = (p.fill - p.exit) / (stop0 - p.fill)
    assert pnl_r == pytest.approx(0.25, abs=0.03)             # half at +0.5R, half at zero


def test_sim_half_then_target():
    e = eng(); p = filled(e, 0.5)
    risk = p.stop - p.fill
    e.manage_sim("X", bar(99.9, 99.95, p.target - 0.01, p.target), T0 + pd.Timedelta(minutes=1))
    assert p.status == "closed" and (p.fill - p.exit) / risk == pytest.approx(0.75, abs=0.03)


def test_sim_same_bar_counts_the_stop_first():
    e = eng(); p = plan(e); e.plans.append(p)
    e.manage_sim("X", bar(100.1, 100.9, 99.9, 100.0), T0)     # trigger and stop inside one minute: order unknown
    assert p.status == "closed" and p.exit == p.stop          # (the old replay cancelled this trade: no loss counted)


def test_sim_cancelled_when_wick_is_taken_first():
    e = eng(); p = plan(e); e.plans.append(p)
    e.manage_sim("X", bar(100.3, 100.6, 100.2, 100.4), T0)
    assert p.status == "cancelled"


def test_half_day_flatten_time_and_entry_cutoff():
    e = eng(close_min=210)                                    # 13:00 close
    p = filled(e, 0)
    e.manage_sim("X", bar(99.9, 100.0, 99.8, 99.9), pd.Timestamp("2026-11-27 12:50"))
    assert p.status == "closed" and "before the close" in p.exit_reason
    m = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                     index=pd.date_range("2026-11-27 09:30", periods=200, freq="min"))
    assert e.signals("X", m, pd.Timestamp("2026-11-27 12:45")) == []          # after the last-entry time (12:30)


def candles(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"]).assign(volume=1.0)


def test_pivot_wick_top_and_bottom():
    base = [[10, 10.2, 9.9, 10.1]] * 14
    assert pivot_wick(candles(base + [[10.1, 10.9, 10.05, 10.15]])) == -1      # long upper wick at a new high
    assert pivot_wick(candles(base + [[10.1, 10.15, 9.3, 10.05]])) == 1
    assert pivot_wick(candles(base + [[10.1, 10.19, 10.05, 10.12]])) == 0      # wick, but not the high of the move
    assert pivot_wick(candles(base + [[10.0, 10.9, 9.95, 10.85]])) == 0        # big body, no rejection


def test_levels_near_label_and_age(tmp_path):
    pd.DataFrame([{"date": "2026-11-09", "source": "a", "sym": "TSLA", "lo": 374, "hi": 377, "role": "support", "note": ""},
                  {"date": "2026-11-09", "source": "a", "sym": "TSLA", "lo": 383, "hi": 383, "role": "long_trigger", "note": ""}]
                 ).to_csv(tmp_path / "2026-11-09_a.csv", index=False)
    lv = LVL.load(pd.Timestamp("2026-11-10"), tmp_path)
    hits = LVL.near(lv, "TSLA", 376.2, 0.5)
    assert [h["level"] for h in hits] == ["374-377"] and hits[0]["dist"] == 0
    assert LVL.near(lv, "TSLA", 382.7, 0.5)[0]["role"] == "long_trigger"
    assert LVL.near(lv, "AAPL", 376, 5) == []
    assert not len(LVL.load(pd.Timestamp("2026-11-08"), tmp_path))             # a post is never used before its date
    assert not len(LVL.load(pd.Timestamp("2026-11-20"), tmp_path))             # nor once it is more than a week old


def test_terrashade_parse():
    m = {"content": "", "embeds": [{"title": "TSLA levels", "description": "Call wall: 400\nPut Wall: 380\nGamma flip: 383.5",
                                    "fields": [{"name": "QQQ", "value": "Call wall: 520"}]}]}
    out = parse(m, {"TSLA", "QQQ"})
    assert out["TSLA"] == {"call wall": 400.0, "put wall": 380.0, "gamma flip": 383.5}
    assert out["QQQ"]["call wall"] == 520.0


def minute_bars(days, drift=0.0):
    idx = pd.DatetimeIndex([d + pd.Timedelta(minutes=570 + i) for d in days for i in range(390)])
    i = np.tile(np.arange(390), len(days))
    px = 100 * (1 + 0.0001 * i + drift)
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 100.0}, index=idx)


def test_sigma_uses_only_earlier_days_and_skips_half_days():
    days = list(pd.bdate_range("2026-10-01", periods=16))
    h = minute_bars(days)
    h = h[~((h.index.normalize() == days[5]) & (h.index.time >= pd.Timestamp("13:00").time()))]   # one half day
    s = sigma_curve(h, days[-1])
    assert len(s) == 390 and s.loc[390] == pytest.approx(0.0389, abs=1e-4)   # 0.0376 if the half day leaks in
    assert s.equals(sigma_curve(h[h.index.normalize() < days[-1]], days[-1]))   # today's bars change nothing
    assert sigma_curve(h, days[10]).empty                                       # not enough full sessions yet


def test_breakout_rule_matches_the_backtest_rule():
    nb = NoiseBand("X", 75_000, None, paper=False)
    nb.sigma, nb.prev_close, nb.open = pd.Series(0.01, index=range(1, 391)), 100.0, 101.0
    assert nb.decide(102.5, 101.5, 30) == 1          # above max(open, prior close) x 1.01
    assert nb.decide(101.9, 101.5, 30) == 0
    assert nb.decide(98.9, 100.0, 30) == -1          # below min(...) x 0.99
    nb.pos = 1
    assert nb.decide(102.5, 101.0, 60) == 1          # still above the band and VWAP: hold
    assert nb.decide(102.2, 102.4, 60) == 1          # above the band, under VWAP: out, and straight back in by the rule
    assert nb.decide(101.5, 101.0, 60) == 0          # back inside the band: out


def test_breakout_never_checks_in_the_last_half_hour_of_a_half_day(tmp_path):
    nb = NoiseBand("X", 75_000, tmp_path, paper=False, close_min=210)
    nb.day = pd.Timestamp("2026-11-27")
    nb.sigma, nb.prev_close = pd.Series(0.001, index=range(1, 391)), 100.0
    day = minute_bars([nb.day], drift=0.05)
    for minute in (180, 210, 240):                   # 12:30 is the last allowed check on a 13:00 close
        t = nb.day + pd.Timedelta(minutes=570 + minute)
        nb.pos, nb.done = 0, set()
        nb.on_minute(day[day.index < t], t, blocked=False)
        assert (nb.pos == 1) == (minute == 180)


def test_breakout_skips_a_check_on_stale_data(tmp_path):
    nb = NoiseBand("X", 75_000, tmp_path, paper=False)
    nb.day = pd.Timestamp("2026-11-10")
    nb.sigma, nb.prev_close = pd.Series(0.001, index=range(1, 391)), 100.0
    day = minute_bars([nb.day], drift=0.05)
    t = nb.day + pd.Timedelta(hours=10)
    nb.on_minute(day[day.index < t - pd.Timedelta(minutes=10)], t, blocked=False)
    assert nb.pos == 0


def test_level_must_fit_the_direction():
    e = eng()
    e.levels = pd.DataFrame([{"date": "2026-11-09", "source": "jgbanks", "sym": "TSLA", "lo": 374, "hi": 377, "role": "support", "note": ""},
                             {"date": "2026-11-09", "source": "jgbanks", "sym": "TSLA", "lo": 383, "hi": 383, "role": "resistance", "note": ""}])
    assert e._at_level("TSLA", 376.2, 1, 1.0) == "jgbanks support 374-377"      # bottom candle at support: yes
    assert e._at_level("TSLA", 376.2, -1, 1.0) is None                         # top candle at support: no
    assert e._at_level("TSLA", 383.2, -1, 1.0) == "jgbanks resistance 383"
    assert e._at_level("TSLA", 380.0, 1, 1.0) is None                          # nowhere near a level
    assert eng()._at_level("TSLA", 376.2, 1, 1.0) is None                      # no levels loaded


def test_terrashade_parse_real_autopost_card():
    """The first real card, Nov 10 9:45 ET (#terrashade-heatmap)."""
    m = {"content": "", "embeds": [{"title": "TSLA · Levels", "description":
         "**TSLA** · 9:45 AM ET\nSpot **374.92**\nKing Node **400.00** (+6.69% from spot)\nCall wall **400.00** (+6.69% from spot)\n"
         "Put wall **350.00** (-6.65% from spot)\nZero gamma **358.31** (-4.43% from spot)\n"
         "[Open TSLA on TerraShade](https://terrashade.onrender.com/?t=TSLA)"}]}
    assert parse(m, {"TSLA", "QQQ"}) == {"TSLA": {"spot": 374.92, "king node": 400.0, "call wall": 400.0,
                                                   "put wall": 350.0, "zero gamma": 358.31}}


def test_gex_walls_sit_on_the_right_side_of_price(monkeypatch):
    """NVDA Nov 10: spot 170 after a drop, big leftover put open interest at 190. The put wall must be below price."""
    from vpa_trading import gex as G
    now = pd.Timestamp("2026-11-10 11:00")
    rows = [("put", 190, 115_000), ("put", 170, 53_000), ("put", 165, 41_000), ("call", 200, 130_000), ("call", 175, 4_500),
            ("call", 160, 20_000)]
    c = pd.DataFrame([{"symbol": f"{t}{k}", "type": t, "strike": float(k), "expiry": pd.Timestamp("2026-11-20"), "oi": float(oi),
                       "iv": 0.72, "spot": 170.0} for t, k, oi in rows])
    monkeypatch.setattr(G, "chain", lambda sym, now, max_days=30: c)
    lv = G.levels("NVDA", now)
    assert lv["put_wall"] == 170.0 and lv["call_wall"] == 200.0
