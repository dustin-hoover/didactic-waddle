"""Offline tests for the CoinGecko data-source integration (no network)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tradebot.ohlcv as o


def test_resolve_curated_map():
    assert o.cg_resolve_id("BTC") == "bitcoin"
    assert o.cg_resolve_id("eth") == "ethereum"


def test_resolve_search_fallback(monkeypatch):
    o._cg_id_cache.clear()
    monkeypatch.setattr(o, "_cg_get", lambda path, params: {
        "coins": [{"symbol": "zzz", "id": "other"}, {"symbol": "XYZ", "id": "xyz-token"}]})
    assert o.cg_resolve_id("XYZ") == "xyz-token"


def test_daily_bars_dedupe_and_volume(monkeypatch):
    day = 86_400_000
    payload = {"prices": [[day, 10.0], [day + 3_600_000, 11.0], [2 * day, 12.0]],
               "total_volumes": [[day, 100.0], [2 * day, 200.0]]}
    monkeypatch.setattr(o, "_cg_get", lambda path, params: payload)
    bars = o.ExchangeFeed()._coingecko("BTC", "1d", 10, None)
    assert len(bars) == 2                 # two distinct UTC days
    assert bars[0].close == 11.0          # last obs of day 1 kept
    assert bars[0].volume == 100.0
    assert bars[1].close == 12.0
    assert bars[0].open == bars[0].high == bars[0].low == bars[0].close  # close-based


def test_intraday_ohlc(monkeypatch):
    monkeypatch.setattr(o, "_cg_get", lambda path, params: [[1000, 1.0, 2.0, 0.5, 1.5]])
    bars = o.ExchangeFeed()._coingecko("BTC", "4h", 10, None)
    assert bars[0].high == 2.0 and bars[0].low == 0.5 and bars[0].close == 1.5


def test_markets_context(monkeypatch):
    monkeypatch.setattr(o, "_cg_get", lambda path, params: [
        {"id": "bitcoin", "symbol": "btc", "current_price": 50000, "market_cap": 1e12,
         "market_cap_rank": 1, "total_volume": 3e10, "price_change_percentage_24h": 1.5}])
    mk = o.coingecko_markets(["BTC"])
    assert mk["BTC"]["rank"] == 1 and mk["BTC"]["price"] == 50000


def test_unresolvable_symbol_returns_empty(monkeypatch):
    o._cg_id_cache.clear()
    monkeypatch.setattr(o, "_cg_get", lambda path, params: {"coins": []})
    assert o.ExchangeFeed()._coingecko("NOTACOIN", "1d", 10, None) == []
