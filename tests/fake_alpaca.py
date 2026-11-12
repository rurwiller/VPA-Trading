"""A tiny in-memory stand-in for Alpaca's paper trading API: enough to test the order plumbing without a network.
Orders never fill by themselves; tests fill them by hand with fill()."""
from __future__ import annotations

import itertools


class Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code, self.ok, self.text = data, code, code < 300, str(data)

    def json(self):
        return self._d

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.text)


class FakeAlpaca:
    def __init__(self):
        self.orders: dict[str, dict] = {}      # id -> order (parents and legs)
        self.pos: dict[str, int] = {}
        self.n = itertools.count(1)
        self.reject_oco = False
        self.cancel_lands = True
        self.slow_close = False                # True: DELETE /positions leaves a working close order instead of closing
        self.bp = None                         # buying power; None = unlimited               # False: a cancel is accepted but the order still shows as open
        self.log: list[tuple] = []

    # ---- helpers for tests
    def _new(self, **kw):
        o = {"id": f"o{next(self.n)}", "status": "new", "filled_qty": "0", "filled_avg_price": None, "legs": [],
             "filled_at": None, "order_class": "", **kw}
        self.orders[o["id"]] = o
        return o

    def bracket(self, cid, sym, side, qty, fill, stop, target):
        """A filled bracket entry with its two resting exit legs."""
        ex = "sell" if side == "buy" else "buy"
        o = self._new(client_order_id=cid, symbol=sym, side=side, qty=str(qty), type="stop", order_class="bracket",
                      status="filled", filled_qty=str(qty), filled_avg_price=str(fill), filled_at="2026-11-10T15:00:00Z")
        o["legs"] = [self._new(client_order_id=cid + "-tp", symbol=sym, side=ex, qty=str(qty), type="limit",
                               limit_price=str(target), status="new"),
                     self._new(client_order_id=cid + "-sl", symbol=sym, side=ex, qty=str(qty), type="stop",
                               stop_price=str(stop), status="held")]
        self.pos[sym] = self.pos.get(sym, 0) + (qty if side == "buy" else -qty)
        return o

    def fill(self, o, px):
        o["status"], o["filled_qty"], o["filled_avg_price"], o["filled_at"] = "filled", o["qty"], str(px), "2026-11-10T15:05:00Z"
        q = int(o["qty"])
        self.pos[o["symbol"]] = self.pos.get(o["symbol"], 0) + (q if o["side"] == "buy" else -q)

    def by_cid(self, cid):
        return next((o for o in self.orders.values() if o["client_order_id"] == cid), None)

    def parents(self):
        legs = {lg["id"] for o in self.orders.values() for lg in o["legs"]}
        return [o for o in self.orders.values() if o["id"] not in legs]

    # ---- the requests API
    def get(self, url, headers=None, params=None, timeout=None):
        path = url.split("/v2", 1)[1]
        if path == "/orders":
            st = (params or {}).get("status")
            out = [o for o in self.parents() if st != "open" or o["status"] in ("new", "held", "accepted")]
            return Resp(out)
        if path.startswith("/orders/"):
            return Resp(self.orders[path.split("/")[2]])
        if path == "/positions":
            return Resp([{"symbol": s, "qty": str(q)} for s, q in self.pos.items() if q])
        if path.startswith("/positions/"):
            q = self.pos.get(path.split("/")[2], 0)
            return Resp({"qty": str(q), "current_price": "100"}) if q else Resp({"message": "position does not exist"}, 404)
        if path == "/account":
            return Resp({"equity": "100000", "last_equity": "100000"})
        raise AssertionError(path)

    def post(self, url, headers=None, json=None, timeout=None):
        b = dict(json)
        self.log.append(("post", b.get("client_order_id"), b.get("type"), b.get("qty")))
        if b.get("order_class") == "oco":
            if self.reject_oco:
                return Resp({"message": "rejected"}, 422)
            o = self._new(client_order_id=b["client_order_id"], symbol=b["symbol"], side=b["side"], qty=b["qty"], type="limit",
                          limit_price=b["take_profit"]["limit_price"], order_class="oco")
            o["legs"] = [self._new(client_order_id=b["client_order_id"] + "-sl", symbol=b["symbol"], side=b["side"], qty=b["qty"],
                                   type="stop", stop_price=b["stop_loss"]["stop_price"], status="held")]
            return Resp(o)
        px = float(b.get("stop_price") or 100.0)
        entry = b.get("order_class") == "bracket" or "-entry-" in (b.get("client_order_id") or "")
        if self.bp is not None and entry and int(b["qty"]) * px * 1.03 > self.bp:
            return Resp({"buying_power": f"{self.bp:.2f}", "code": 40310000, "cost_basis": f"{int(b['qty']) * px * 1.03:.2f}",
                         "message": "insufficient buying power"}, 403)
        o = self._new(client_order_id=b.get("client_order_id", f"x{next(self.n)}"), symbol=b["symbol"], side=b["side"],
                      qty=b["qty"], type=b["type"], stop_price=b.get("stop_price"))
        if b["type"] == "market":
            self.fill(o, 100.0)
        return Resp(o)

    def delete(self, url, headers=None, params=None, timeout=None):
        path = url.split("/v2", 1)[1]
        self.log.append(("delete", path))
        if path.startswith("/orders/"):
            o = self.orders[path.split("/")[2]]
            if o["status"] in ("new", "held", "accepted") and self.cancel_lands:
                o["status"] = "canceled"
                for lg in o["legs"]:
                    if lg["status"] in ("new", "held"):
                        lg["status"] = "canceled"
        elif path == "/orders":
            for o in self.orders.values():
                if o["status"] in ("new", "held", "accepted"):
                    o["status"] = "canceled"
        elif path == "/positions":
            self.log.append(("close_all", dict(params or {})))
            if self.slow_close:              # the close is a market order that has not filled yet
                for s_, q in list(self.pos.items()):
                    if q:
                        self._new(client_order_id=f"close-{s_}", symbol=s_, side="buy" if q < 0 else "sell", qty=str(abs(q)), type="market")
            else:
                self.pos.clear()
        elif path.startswith("/positions/"):
            self.log.append(("close_one", path))
            self.pos.pop(path.split("/")[2], None)
        return Resp({}, 204)
