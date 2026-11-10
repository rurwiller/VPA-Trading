"""The paper-order plumbing against a fake Alpaca: half exits, their recovery, breakout conflicts, flatten, loss stop."""
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
