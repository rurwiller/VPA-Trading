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


def test_terrashade_parse_alert_post():
    m = {"content": "", "embeds": [{"title": "TSLA · Alert", "description": "**TSLA** moved below put wall **375.00**. Spot **374.97**."}]}
    assert parse(m, {"TSLA"}) == {"TSLA": {"put wall": 375.0, "alert": "moved below put wall 375", "spot": 374.97}}


def _ctx_days(n=260):
    """n sessions of 1m bars (premarket 08:00-09:30 and the regular session) on a slow uptrend with a daily wiggle."""
    from vpa_trading import keylevels as K
    days = pd.bdate_range("2025-01-02", periods=n)
    idx = pd.DatetimeIndex([d + pd.Timedelta(minutes=480 + i) for d in days for i in range(0, 480, 5)])
    k = np.arange(len(idx))
    px = 100 + 0.002 * k + 2 * np.sin(k / 37.0)
    m = pd.DataFrame({"open": px, "high": px + 0.3, "low": px - 0.3, "close": px, "volume": 1000.0, "vwap": px}, index=idx)
    return K, m, days


def test_key_levels_use_nothing_from_the_day_itself():
    """Levels for a day must not change when that day's regular-session bars (and every later day) are removed."""
    K, m, days = _ctx_days()
    d = days[230]
    full = K.Context(m)
    cut = m[(m.index < d + pd.Timedelta(hours=9, minutes=30))]                # history + that day's premarket only
    part = K.Context(cut, today=d)
    a = sorted(full.raw(full.index_of(d), opening_range=False))
    b = sorted(part.raw(part.index_of(d), opening_range=False))
    drop = lambda xs: [(round(p, 4), k) for p, k in xs if not k.startswith("round")]   # round numbers hang off the reference price
    assert drop(a) == drop(b) and len(a) > 20


def test_key_level_basics_and_zone_scoring():
    K, m, days = _ctx_days()
    c = K.Context(m)
    i = c.index_of(days[230])
    raw = dict((k, p) for p, k in c.raw(i))
    rth = m[(m.index.time >= pd.Timestamp("09:30").time())]
    y = rth[rth.index.normalize() == days[229]]
    assert raw["pd_high"] == y.high.max() and raw["pd_low"] == y.low.min() and raw["pd_close"] == y.close.iloc[-1]
    pre = m[(m.index.normalize() == days[230]) & (m.index.time < pd.Timestamp("09:30").time())]
    assert raw["premkt_high"] == pre.high.max()
    z = K.cluster([(100.0, "pd_high"), (100.05, "pw_high"), (100.08, "round"), (103.0, "ema9"), (103.02, "ema21")], tol=0.1)
    assert len(z) == 2 and z[0].score == 3.0 + 4.0 + 2.0 + 0.5 * 2           # three families stack
    assert z[1].score == 2.0                                                 # two averages are one family: the best one counts
    assert K.at(z, 100.2, 0.15) is z[0] and K.at(z, 101.5, 0.15) is None
    up, dn = K.select(z, 101.0, adr=2.0)
    assert [x.mid for x in up] == [z[1].mid] and [x.mid for x in dn] == [z[0].mid]


def test_zone_at_from_the_sheet_adds_the_live_opening_range():
    from vpa_trading import keylevels as K
    sheet = pd.DataFrame([dict(sym="TSLA", price=384.0, kind="pw_low", tol=0.5, adr=13.0, spot=380.0),
                          dict(sym="TSLA", price=384.2, kind="gap_edge", tol=0.5, adr=13.0, spot=380.0),
                          dict(sym="TSLA", price=377.0, kind="or_high", tol=0.5, adr=13.0, spot=380.0)])
    assert K.zone_at(sheet, "TSLA", 384.3) .families == ["gap", "week"]
    assert K.zone_at(sheet, "TSLA", 377.0) is None                           # the sheet's own (stale) opening range is ignored
    assert K.zone_at(sheet, "TSLA", 379.1, opening_range=(379.0, 372.0)).kinds == ["or_high"]
    assert K.zone_at(sheet, "AAPL", 384.0) is None and K.zone_at(None, "TSLA", 384.0) is None


def test_key_zone_trade_needs_volume_and_a_strong_zone(monkeypatch):
    from vpa_trading import live as L
    e = eng()
    e.key_sheet = pd.DataFrame([dict(sym="X", price=p, kind=k, tol=0.05, adr=2.0, spot=100.0) for p, k in
                                ((100.0, "pw_high"), (100.02, "pd_high"), (100.03, "round"), (98.0, "pd_low"))])
    m = pd.DataFrame({"open": 99.0, "high": 99.5, "low": 98.5, "close": 99.0, "volume": 1.0},
                     index=pd.date_range("2026-11-10 09:30", periods=60, freq="min"))
    now = pd.Timestamp("2026-11-10 10:30")
    monkeypatch.setattr(L.vpa, "relvol_tod", lambda b: pd.Series([2.5]))
    z = e._at_key("X", m, now, "15m", 100.01, m)
    assert z is not None and z.score >= 7                      # three families stack at 100: 4 + 3 + 2 + 1
    assert e._at_key("X", m, now, "15m", 98.0, m) is None      # a lone prior-day low scores 3: too weak
    monkeypatch.setattr(L.vpa, "relvol_tod", lambda b: pd.Series([1.5]))
    assert e._at_key("X", m, now, "15m", 100.01, m) is None    # volume under 2x
    e.cfg.key_risk_usd = 0
    monkeypatch.setattr(L.vpa, "relvol_tod", lambda b: pd.Series([2.5]))
    assert e._at_key("X", m, now, "15m", 100.01, m) is None    # turned off
