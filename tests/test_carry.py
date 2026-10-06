"""Offline tests for the carry monitor (pure math; network injected)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.carry import (CarryConfig, CarryRow, annualize, net_apr, realized,
                            is_attractive, build_row, rank, fetch_carry)


def test_annualize_8h():
    # 0.0001 (1bp) every 8h -> 3/day -> *365 -> 10.95%
    assert abs(annualize(0.0001, 3) - 10.95) < 1e-9


def test_net_apr_subtracts_fee_drag():
    assert net_apr(10.0, CarryConfig(fee_drag_apr=1.9)) == 8.1


def test_realized_summary():
    rates = [0.0001, 0.0002, -0.0001, 0.0001]   # 3 of 4 positive
    s = realized(rates, CarryConfig(periods_per_day=3, fee_drag_apr=1.9))
    assert s["n"] == 4 and s["pct_positive"] == 0.75
    assert s["gross_apr"] > 0 and s["net_apr"] == round(s["gross_apr"] - 1.9, 2)


def test_realized_empty():
    s = realized([])
    assert s == {"gross_apr": 0.0, "net_apr": 0.0, "pct_positive": 0.0, "n": 0}


def test_is_attractive_requires_yield_and_persistence():
    cfg = CarryConfig(min_net_apr=3.0, min_pct_positive=0.70)
    assert is_attractive(5.0, 0.9, cfg) is True
    assert is_attractive(2.0, 0.9, cfg) is False     # yield too low
    assert is_attractive(5.0, 0.5, cfg) is False     # not persistent


def test_build_row_flags_and_notes():
    cfg = CarryConfig(periods_per_day=3, fee_drag_apr=1.9, min_net_apr=3.0, min_pct_positive=0.7)
    # strong, persistent -> attractive
    strong = build_row("BTC", [0.0003] * 50, cfg=cfg)
    assert strong.attractive is True and strong.note == "" and strong.coin == "BTC"
    # positive but tiny yield -> below threshold
    weak = build_row("SOL", [0.00001] * 50, cfg=cfg)
    assert weak.attractive is False and weak.note == "yield below threshold"
    # decent average but flips sign often -> not persistent
    choppy = build_row("DOGE", [0.002, -0.0019] * 25, cfg=cfg)
    assert choppy.attractive is False and choppy.note == "not persistent"
    # no data
    empty = build_row("XRP", [], cfg=cfg)
    assert empty.n == 0 and empty.note == "no data" and empty.attractive is False


def test_rank_orders_by_net_apr_dataless_last():
    rows = [CarryRow("A", "okx", 2, 0.1, 0.8, 50, False),
            CarryRow("B", "okx", 10, 8.1, 0.9, 50, True),
            CarryRow("C", "okx", 0, 0, 0, 0, False)]
    r = rank(rows)
    assert [x.coin for x in r] == ["B", "A", "C"]     # B best, C (no data) last


def test_fetch_carry_injected_and_resilient():
    data = {"BTC": [0.0003] * 40, "ETH": [0.0002] * 40, "BAD": None}
    def hist(sym):
        if data.get(sym) is None:
            raise RuntimeError("venue down")
        return data[sym]
    rows = fetch_carry(["BTC", "ETH", "BAD"], history_fn=hist)
    by = {r.coin: r for r in rows}
    assert by["BTC"].net_apr > by["ETH"].net_apr      # BTC higher funding
    assert by["BAD"].n == 0 and by["BAD"].note == "no data"   # failure didn't break it
    assert rows[0].coin == "BTC"                      # ranked best-first
