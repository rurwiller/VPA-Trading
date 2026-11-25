"""The paper-order plumbing against a fake Alpaca: half exits, their recovery, breakout conflicts, flatten, loss stop."""
import numpy as np
import pandas as pd
import pytest

from fake_alpaca import FakeAlpaca
from vpa_trading import live as LV, noise_band as NBM
from vpa_trading.noise_band import NoiseBand


@pytest.fixture
def api(monkeypatch):
    f = FakeAlpaca()
    for mod in (LV, NBM):
        monkeypatch.setattr(mod.requests, "get", f.get)
        monkeypatch.setattr(mod.requests, "post", f.post)
        monkeypatch.setattr(mod.requests, "delete", f.delete)
    monkeypatch.setattr(LV.time, "sleep", lambda s: None)
    LV.Engine.exits, LV.Engine.nb_net = {}, {}
    return f


CID = "vpa-TSLA-15m-202611101015"


def open_qty(api, sym="TSLA"):
    """Shares covered by a working stop order."""
    return sum(int(o["qty"]) for o in api.orders.values() if o["type"] == "stop" and o["status"] in ("new", "held"))


def test_split_into_two_halves(api):
    api.bracket(CID, "TSLA", "sell", 101, 380.0, 381.0, 379.0)
    LV.Engine.manage_partials(0.5)
    h1, h2 = api.by_cid(CID + "-h1"), api.by_cid(CID + "-h2")
    assert (h1["qty"], h1["limit_price"], h1["legs"][0]["stop_price"]) == ("50", "379.50", "381.00")
    assert (h2["qty"], h2["limit_price"], h2["legs"][0]["stop_price"]) == ("51", "379.00", "381.00")
    assert open_qty(api) == 101                          # every share has a stop
    LV.Engine.manage_partials(0.5)                       # a second pass changes nothing
    assert len(api.parents()) == 3


def test_first_half_filled_moves_the_rest_to_breakeven(api):
    api.bracket(CID, "TSLA", "sell", 100, 380.0, 381.0, 379.0)
    LV.Engine.manage_partials(0.5)
    api.fill(api.by_cid(CID + "-h1"), 379.5)
    api.by_cid(CID + "-h1")["legs"][0]["status"] = "canceled"
    LV.Engine.manage_partials(0.5)
    h3 = api.by_cid(CID + "-h3")
    assert h3["qty"] == "50" and h3["legs"][0]["stop_price"] == "380.00" and h3["limit_price"] == "379.00"
    assert api.by_cid(CID + "-h2")["status"] == "canceled" and open_qty(api) == 50
    assert LV.Engine.exits[CID] == [(50, 379.5, "half at +0.5R")]


def test_recovers_when_the_cancel_lands_late(api):
    """The old code gave up for good if the legs' cancel had not landed within 1.5 s: the position then had no stop."""
    api.bracket(CID, "TSLA", "buy", 100, 380.0, 379.0, 381.0)
    api.cancel_lands = False
    LV.Engine.manage_partials(0.5)
    assert api.by_cid(CID + "-h1") is None               # not yet: the legs still show as open (and still protect)
    for lg in api.by_cid(CID)["legs"]:                   # ... the cancel lands after we stopped waiting
        lg["status"] = "canceled"
    assert open_qty(api) == 0                            # nothing protects the shares now
    LV.Engine.manage_partials(0.5)                       # next minute (or after a restart)
    assert api.by_cid(CID + "-h1") and api.by_cid(CID + "-h2") and open_qty(api) == 100


def test_recovers_a_missing_second_exit(api):
    """Killed between the two exit orders (the scanner is restarted every two hours): the second half gets its order."""
    o = api.bracket(CID, "TSLA", "buy", 100, 380.0, 379.0, 381.0)
    for lg in o["legs"]:
        lg["status"] = "canceled"
    LV.Engine._oco("TSLA", 1, 50, 380.5, 379.0, CID + "-h1")
    LV.Engine.manage_partials(0.5)
    h2 = api.by_cid(CID + "-h2")
    assert h2["qty"] == "50" and h2["limit_price"] == "381.00" and open_qty(api) == 100


def test_same_test_on_the_old_code_leaves_it_naked(api):
    """Documents the bug on the pre-audit logic: legs cancelled, nothing re-placed."""
    o = api.bracket(CID, "TSLA", "buy", 100, 380.0, 379.0, 381.0)
    for lg in o["legs"]:
        lg["status"] = "canceled"
    legs = o["legs"]
    old_would_return = not all(lg["status"] in LV.OPEN for lg in legs)      # the pre-audit early return
    assert old_would_return and open_qty(api) == 0


def test_no_exit_orders_for_shares_that_are_gone(api):
    """Bracket legs cancelled and the position closed elsewhere (a flatten): never sell shares we no longer hold."""
    o = api.bracket(CID, "TSLA", "buy", 100, 380.0, 379.0, 381.0)
    for lg in o["legs"]:
        lg["status"] = "canceled"
    api.pos["TSLA"] = 0
    LV.Engine.manage_partials(0.5)
    assert len(api.parents()) == 1


def test_never_protects_the_breakouts_shares(api):
    o = api.bracket(CID, "TSLA", "buy", 100, 380.0, 379.0, 381.0)
    for lg in o["legs"]:
        lg["status"] = "canceled"
    api.pos["TSLA"] = 0
    nb = api._new(client_order_id="nb-TSLA-entry-1", symbol="TSLA", side="buy", qty="190", type="market")
    api.fill(nb, 380.0)                                  # only the breakout is long now
    LV.Engine.manage_partials(0.5)
    assert api.by_cid(CID + "-h1") is None


def test_rejected_exit_order_closes_at_market(api):
    api.bracket(CID, "TSLA", "buy", 100, 380.0, 379.0, 381.0)
    api.reject_oco = True
    LV.Engine.manage_partials(0.5)
    assert api.pos["TSLA"] == 0 and api.by_cid(CID + "-hm1")["status"] == "filled"


def test_one_share_keeps_its_plain_bracket(api):
    api.bracket(CID, "TSLA", "buy", 1, 380.0, 379.0, 381.0)
    LV.Engine.manage_partials(0.5)
    assert all(lg["status"] in ("new", "held") for lg in api.by_cid(CID)["legs"])


def test_stale_entry_cleanup_leaves_exit_orders_alone(api):
    api.bracket(CID, "TSLA", "buy", 100, 380.0, 379.0, 381.0)
    LV.Engine.manage_partials(0.5)
    api._new(client_order_id="vpa-AAPL-9m-202611101000", symbol="AAPL", side="buy", qty="10", type="stop", order_class="bracket")
    assert LV.Engine.cancel_stale_entries() == 1 and open_qty(api) == 100


def test_flatten_survives_a_network_error(api, monkeypatch):
    api.bracket(CID, "TSLA", "buy", 100, 380.0, 379.0, 381.0)
    real, calls = api.delete, {"n": 0}

    def flaky(url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LV.requests.ConnectionError("boom")
        return real(url, **kw)
    monkeypatch.setattr(LV.requests, "delete", flaky)
    LV.Engine.flatten()
    assert not any(api.pos.values())


def nb_at_check(tmp_path, pos):
    nb = NoiseBand("TSLA", 75_000, tmp_path, paper=True)
    nb.day = pd.Timestamp("2026-11-10")
    nb.sigma, nb.prev_close, nb.open = pd.Series(0.001, index=range(1, 391)), 100.0, 100.0
    nb.pos, nb.qty, nb.entry, nb.orig_qty = pos, (100 if pos else 0), 99.0, (100 if pos else 0)
    nb.tranches = [{"qty": 100, "target": None, "open": True}] if pos else []
    nb._wait_fill = staticmethod(lambda o, tries=60: (float(o["filled_avg_price"]), int(o["filled_qty"])) if o else (None, 0))
    idx = pd.date_range("2026-11-10 09:30", periods=30, freq="min")
    up = pd.DataFrame({"open": 101.0, "high": 101.0, "low": 101.0, "close": 101.0, "volume": 100.0}, index=idx)
    return nb, up, pd.Timestamp("2026-11-10 10:00")


def test_breakout_stays_out_when_the_scanner_is_short(api, tmp_path, monkeypatch):
    monkeypatch.setattr(NBM.pd.Timestamp, "now", classmethod(lambda cls, tz=None: pd.Timestamp("2026-11-10 10:00:01", tz=tz)), raising=False)
    api.bracket("alert-TSLA-5m-202611100955", "TSLA", "sell", 50, 101.0, 102.0, 100.0)     # alert mode is short 50
    nb, up, t = nb_at_check(tmp_path, 0)
    nb.on_minute(up, t, blocked=False)               # blocked=False: e.g. after a restart the plan objects are gone
    assert nb.pos == 0 and api.pos["TSLA"] == -50    # the old code bought here and netted against the short


def test_breakout_exits_but_does_not_reverse_into_the_scanners_add(api, tmp_path):
    mine = api._new(client_order_id="nb-TSLA-entry-1", symbol="TSLA", side="sell", qty="100", type="market")
    api.fill(mine, 99.0)                             # the breakout is short 100 ...
    api.bracket("vpa-TSLA-9m-202611100945", "TSLA", "sell", 40, 99.5, 100.5, 98.5)          # ... and the scanner added 40 short
    nb, up, t = nb_at_check(tmp_path, -1)
    nb.on_minute(up, t, blocked=True)                # price is now above the upper band: the rule says long
    assert nb.pos == 0 and api.pos["TSLA"] == -40    # our 100 are covered, the scanner's 40 short are untouched


def test_level_trades_get_the_half_exits_too(api):
    cid = "lvl-TSLA-9m-202611101015"
    api.bracket(cid, "TSLA", "buy", 100, 376.0, 375.0, 377.0)
    LV.Engine.manage_partials(0.5)
    assert api.by_cid(cid + "-h1")["limit_price"] == "376.50" and api.by_cid(cid + "-h2")["qty"] == "50"


def entry_plan(qty=264):
    e = LV.Engine(LV.Config(symbols=["TSLA"], risk_usd=1000, target="1R"), {}, {})
    p = LV.Plan("TSLA", "9m", "premier", "PIVOT_WICK_TOP", -1, pd.Timestamp("2026-11-10 14:54"), 378.13, 379.40, 376.86,
                379.37, qty, pd.Timestamp("2026-11-10 15:12"), "D")
    return e, p


def test_shrinks_to_fit_the_buying_power(api):
    api.bp = 57_091.98                                     # what Alpaca had left at 13:00 MST on Nov 10
    e, p = entry_plan()
    e.submit(p)
    assert p.status == "submitted" and p.extra["shrunk_from"] == 264
    assert p.qty * 378.13 * 1.03 <= api.bp and p.qty >= 140   # 143 of 264 shares fit
    assert api.by_cid("vpa-TSLA-9m-202611101454-fit")["qty"] == str(p.qty)


def test_skips_when_almost_nothing_fits(api):
    api.bp = 11_496.38                                     # 12:54 MST: 28 of 264 shares would fit, under a quarter
    e, p = entry_plan()
    e.submit(p)
    assert p.status == "cancelled" and "not enough buying power" in p.exit_reason and len(api.parents()) == 0


def test_full_size_when_it_fits(api):
    api.bp = 400_000
    e, p = entry_plan()
    e.submit(p)
    assert p.status == "submitted" and p.qty == 264 and "shrunk_from" not in p.extra


def test_breakout_entry_shrinks_to_fit(api, tmp_path):
    api.bp = 40_000                                  # room for about 380 of the planned 742 shares
    nb, up, t = nb_at_check(tmp_path, 0)
    nb.on_minute(up, t, blocked=False)               # price is above the band: the rule says long
    o = next(o for o in api.parents() if o["client_order_id"].endswith("-entry-" + o["client_order_id"].split("-entry-")[1])
             and o["client_order_id"].endswith("-fit"))
    assert nb.pos == 1 and nb.qty == nb.orig_qty == int(o["qty"]) == api.pos["TSLA"]
    assert 300 < nb.qty < 400
    assert open_qty(api) == nb.qty                   # every share bought is protected


def test_breakout_entry_skipped_when_almost_nothing_fits(api, tmp_path):
    api.bp = 10_000
    nb, up, t = nb_at_check(tmp_path, 0)
    nb.on_minute(up, t, blocked=False)
    assert nb.pos == 0 and not any(api.pos.values())


def test_key_level_trades_get_the_half_exits_too(api):
    cid = "key-TSLA-15m-202611101500"
    api.bracket(cid, "TSLA", "sell", 60, 384.0, 389.0, 379.0)
    LV.Engine.manage_partials(0.5)
    assert api.by_cid(cid + "-h1")["limit_price"] == "381.50" and api.by_cid(cid + "-h2")["qty"] == "30"


def test_flatten_waits_for_a_slow_close_and_never_cancels_it(api, monkeypatch):
    """Nov 12: retries cancelled the previous attempt's closing order while it filled."""
    api.pos["TSLA"] = -234
    api.slow_close = True
    calls = {"n": 0}
    real_get = api.get

    def get(url, **kw):
        if url.endswith("/positions"):
            calls["n"] += 1
            if calls["n"] == 3:                  # the close fills on the third look
                close = api.by_cid("close-TSLA")
                if close and close["status"] == "new":
                    api.fill(close, 397.40)
        return real_get(url, **kw)
    monkeypatch.setattr(LV.requests, "get", get)
    LV.Engine.flatten()
    assert api.pos["TSLA"] == 0
    assert api.by_cid("close-TSLA")["status"] == "filled"                 # never cancelled
    assert [x for x in api.log if x[0] == "close_all"] == [("close_all", {})]   # one close-all, no cancel_orders retries


def _resting_entry(api, cid, sym="AAPL", side="buy", stop=99.0):
    o = api._new(client_order_id=cid, symbol=sym, side=side, qty="10", type="stop", stop_price="101", order_class="bracket")
    o["legs"] = [api._new(client_order_id=cid + "-sl", symbol=sym, side="sell" if side == "buy" else "buy", qty="10",
                          type="stop", stop_price=str(stop), status="held")]
    return o


def test_restart_keeps_an_entry_inside_its_window_then_cancels_it(api):
    LV.Engine.adopted = {}
    o = _resting_entry(api, "vpa-AAPL-9m-202611231000")          # valid until 10:18
    assert LV.Engine.cancel_stale_entries(pd.Timestamp("2026-11-23 10:05")) == 0
    assert o["status"] == "new" and o["id"] in LV.Engine.adopted
    assert LV.Engine.expire_adopted(pd.Timestamp("2026-11-23 10:10")) == [] and o["status"] == "new"
    gone = LV.Engine.expire_adopted(pd.Timestamp("2026-11-23 10:18"))
    assert o["status"] == "canceled" and gone and "window ended" in gone[0] and not LV.Engine.adopted


def test_kept_entry_is_cancelled_when_price_hits_its_stop_first(api):
    LV.Engine.adopted = {}
    o = _resting_entry(api, "alert-AAPL-5m-202611231000", stop=99.0)
    LV.Engine.cancel_stale_entries(pd.Timestamp("2026-11-23 10:02"))
    LV.Engine.expire_adopted(pd.Timestamp("2026-11-23 10:03"), {"AAPL": {"low": 98.9, "high": 100.0}})
    assert o["status"] == "canceled"


def test_kept_entry_that_fills_is_left_to_the_normal_exit_handling(api):
    LV.Engine.adopted = {}
    o = _resting_entry(api, "vpa-AAPL-15m-202611231000")
    LV.Engine.cancel_stale_entries(pd.Timestamp("2026-11-23 10:05"))
    api.fill(o, 101.0)
    LV.Engine.expire_adopted(pd.Timestamp("2026-11-23 10:40"))
    assert o["status"] == "filled" and not LV.Engine.adopted


def test_restart_still_cancels_entries_past_their_window_and_market_ids(api):
    LV.Engine.adopted = {}
    late = _resting_entry(api, "vpa-AAPL-9m-202611230900")
    odd = _resting_entry(api, "vpa-MSFT-9m-202611231000-mkt", sym="MSFT")
    assert LV.Engine.cancel_stale_entries(pd.Timestamp("2026-11-23 10:05")) == 2
    assert late["status"] == odd["status"] == "canceled" and not LV.Engine.adopted


def test_breakout_exit_waits_for_its_protection_cancels_to_land(api, tmp_path, monkeypatch):
    """Nov 25: cancels of the breakout's stop / profit orders landed slowly, the exit was sent while the shares were still
    held for those orders and Alpaca rejected it, leaving the position with no stop. The exit must wait for the cancels."""
    mine = api._new(client_order_id="nb-TSLA-entry-1", symbol="TSLA", side="sell", qty="100", type="market")
    api.fill(mine, 99.0)
    stop = api._new(client_order_id="nb-TSLA-stop3-1", symbol="TSLA", side="buy", qty="100", type="stop", stop_price="101.5")
    pending, polls = [], {"n": 0}
    real_delete, real_get, real_post = api.delete, api.get, api.post

    def slow_delete(url, **kw):                      # the cancel is accepted but lands a few polls later
        if "/orders/" in url:
            pending.append(url)
            return __import__("fake_alpaca").Resp({})
        return real_delete(url, **kw)

    def get(url, **kw):
        if url.endswith("/orders") and pending:
            polls["n"] += 1
            if polls["n"] >= 3:
                for u in pending:
                    real_delete(u)
                pending.clear()
        return real_get(url, **kw)

    def post(url, json=None, **kw):
        if (json or {}).get("client_order_id", "").startswith("nb-TSLA-exit"):
            assert stop["status"] == "canceled", "exit sent while the stop still held the shares"
        return real_post(url, json=json, **kw)
    for name, fn in (("delete", slow_delete), ("get", get), ("post", post)):
        monkeypatch.setattr(NBM.requests, name, fn)
    monkeypatch.setattr(NBM.time if hasattr(NBM, "time") else __import__("time"), "sleep", lambda s: None)
    nb, up, t = nb_at_check(tmp_path, -1)
    nb._trade(0, 101.0, t)
    assert nb.pos == 0 and api.pos["TSLA"] == 0


def _plan(sym, side=-1):
    t = pd.Timestamp("2026-11-25 11:00")
    return LV.Plan(sym, "9m", "premier", "PIVOT_WICK_TOP", side, t, 100.0, 101.0 if side < 0 else 99.0,
                   99.0 if side < 0 else 101.0, 100.9, 10, t + pd.Timedelta(minutes=18), "1h")


def test_short_cap_blocks_a_third_short_stock(api):
    eng = LV.Engine.__new__(LV.Engine)
    eng.cfg = LV.Config(symbols=["AAPL"], max_shorts=2)
    api.bracket("vpa-MSFT-9m-202611251100", "MSFT", "sell", 10, 490.0, 492.0, 488.0)      # short MSFT (filled)
    api._new(client_order_id="vpa-AMZN-9m-202611251100", symbol="AMZN", side="sell", qty="10", type="stop",
             stop_price="243", order_class="bracket")                                       # short AMZN entry waiting
    p = _plan("META")
    eng.submit(p)
    assert p.status == "cancelled" and "short cap" in p.exit_reason and api.by_cid("vpa-META-9m-202611251100") is None


def test_short_cap_allows_longs_adds_and_ignores_the_breakout(api):
    eng = LV.Engine.__new__(LV.Engine)
    eng.cfg = LV.Config(symbols=["AAPL"], max_shorts=2)
    api.bracket("vpa-MSFT-9m-202611251100", "MSFT", "sell", 10, 490.0, 492.0, 488.0)
    mine = api._new(client_order_id="nb-QQQ-entry-1", symbol="QQQ", side="sell", qty="100", type="market")
    api.fill(mine, 610.0)
    LV.Engine.nb_net = {"QQQ": -100}                          # the breakout's short does not count
    p = _plan("AMZN")
    eng.submit(p)
    assert p.status != "cancelled" or "short cap" not in (p.exit_reason or "")
    long_ = _plan("META", side=1)
    eng.submit(long_)
    assert "short cap" not in (long_.exit_reason or "")


def test_breakout_vol_sizing_uses_prior_closes_and_the_cap(tmp_path):
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2026-10-01", periods=30)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(days))))
    idx = [d + pd.Timedelta(hours=15, minutes=59) for d in days]
    hist = pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1.0}, index=idx)
    day = days[-1] + pd.Timedelta(days=1)
    v = float(np.log(pd.Series(closes)).diff().tail(20).std())
    nb = NoiseBand("TSLA", 75_000, tmp_path, paper=False, vol_budget=1_000)
    nb.start_day(hist, None, day, resume=False)
    assert abs(nb.day_notional - min(1_000 / v, 150_000)) < 1
    nb2 = NoiseBand("QQQ", 75_000, tmp_path, paper=False, vol_budget=1_000_000)
    nb2.start_day(hist, None, day, resume=False)
    assert nb2.day_notional == 150_000
    nb3 = NoiseBand("QQQ", 75_000, tmp_path, paper=False)
    nb3.start_day(hist, None, day, resume=False)
    assert nb3.day_notional == 75_000


def test_flatten_keeps_the_trend_sleeve(api):
    api.bracket("vpa-TSLA-9m-202611271000", "TSLA", "buy", 10, 380.0, 379.0, 381.0)
    q = api._new(client_order_id="trend-QQQM-20261126", symbol="QQQM", side="buy", qty="200", type="market")
    api.fill(q, 250.0)
    moc = api._new(client_order_id="trend-QQQM-20261127", symbol="QQQM", side="sell", qty="200", type="market")
    LV.Engine.flatten()
    assert api.pos.get("TSLA", 0) == 0 and api.pos["QQQM"] == 200 and moc["status"] == "new"


def test_trend_rule_and_rebalance(api, monkeypatch, tmp_path):
    from vpa_trading import trend as TR
    assert TR.inside(pd.Series([100.0] * 199), 101.0)[0] and not TR.inside(pd.Series([100.0] * 199), 99.0)[0]
    assert not TR.inside(pd.Series([100.0] * 50), 101.0)[0]          # not enough history: stay out
    monkeypatch.setattr(TR, "LOG_DIR", tmp_path)
    monkeypatch.setattr(TR.requests, "get", api.get)
    monkeypatch.setattr(TR.requests, "post", api.post)
    days = pd.bdate_range("2026-01-01", periods=250)
    monkeypatch.setattr(TR.LV, "fetch_bars", lambda *a, **k: {"QQQ": pd.DataFrame({"close": 100.0}, index=days)})
    prices = {"QQQ": 110.0, "QQQM": 250.0}
    monkeypatch.setattr(TR, "_latest", lambda s: prices[s])
    now = pd.Timestamp("2026-12-21 15:45")
    msg = TR.rebalance(50_000, now)
    assert "IN" in msg and api.pos["QQQM"] == 200 and api.by_cid("trend-QQQM-20261221") is not None
    assert TR.rebalance(50_000, now) == ""                           # once a day
    prices["QQQ"] = 90.0
    msg = TR.rebalance(50_000, now + pd.Timedelta(days=1))
    assert "OUT" in msg and api.pos.get("QQQM", 0) == 0
