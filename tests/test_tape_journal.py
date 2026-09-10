"""Tests for the forward-accumulating flow journal."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot import tape_journal as tj


def _row(sym, buy, sell, price):
    return {"symbol": sym, "buy_usd": buy, "sell_usd": sell,
            "net_usd": buy - sell, "score": 0.0, "price": price}


def test_record_computes_imbalance():
    j = tj.record({"days": {}}, [_row("ETH", 300, 100, 2000.0)], date="2026-01-01")
    rec = j["days"]["2026-01-01"]["ETH"]
    assert abs(rec["imb"] - 0.5) < 1e-6 and rec["price"] == 2000.0


def test_record_skips_errors_and_zero_price():
    j = tj.record({"days": {}}, [
        {"symbol": "X", "error": "boom", "price": 0},
        {"symbol": "Y", "buy_usd": 1, "sell_usd": 1, "price": 0},   # no price
    ], date="2026-01-01")
    assert j["days"]["2026-01-01"] == {}


def test_pairs_and_forward_return():
    j = {"days": {
        "2026-01-01": {"ETH": {"imb": 0.5, "net": 200, "price": 100.0}},
        "2026-01-02": {"ETH": {"imb": -0.3, "net": -50, "price": 110.0}},
    }}
    pairs = tj._pairs(j)
    assert "ETH" in pairs and len(pairs["ETH"]) == 1
    _, imb, fwd = pairs["ETH"][0]
    assert imb == 0.5 and abs(fwd - 0.10) < 1e-9   # +10% next day


def test_analyze_small_sample_is_honest():
    j = {"days": {"2026-01-01": {"ETH": {"imb": 0.5, "net": 1, "price": 100.0}}}}
    r = tj.analyze(j)
    assert r["n_pairs"] == 0
    assert "not enough data" in r["verdict"]


def test_analyze_does_not_overclaim_on_tiny_positive_sample():
    # A few perfectly-predictive days must NOT trigger a trade verdict (n<30 gate).
    days = {}
    price = 100.0
    for d in range(6):
        date = f"2026-01-0{d+1}"
        days[date] = {"ETH": {"imb": 0.4, "net": 1, "price": price}}
        price *= 1.02
    r = tj.analyze({"days": days})
    assert r["n_pairs"] >= 3
    assert "do not size positions" in r["verdict"]   # still gated on sample size


def test_date_days_ago():
    assert tj.date_days_ago(0, base="2026-09-10") == "2026-09-10"
    assert tj.date_days_ago(1, base="2026-09-10") == "2026-09-09"
    assert tj.date_days_ago(8, base="2026-09-10") == "2026-09-02"


def test_roundtrip_save_load(tmp_path):
    p = str(tmp_path / "journal.json")
    j = tj.record(tj.load(p), [_row("ETH", 300, 100, 2000.0)], date="2026-01-01")
    tj.save(p, j)
    reloaded = tj.load(p)
    assert reloaded["days"]["2026-01-01"]["ETH"]["price"] == 2000.0
