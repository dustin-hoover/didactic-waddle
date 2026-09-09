"""Offline tests for the on-chain data path (Chainlink + DefiLlama, no CEX)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tradebot.onchain_feed as oc
from tradebot.ohlcv import ExchangeFeed, get_feed
from tradebot.onchain_feed import OnChainFeed


def test_chainlink_price(monkeypatch):
    monkeypatch.setattr(oc, "_eth_call", lambda to, data: hex(50000 * 10 ** 8))
    assert abs(oc.chainlink_price("BTC") - 50000) < 1e-6


def test_chainlink_unknown_symbol_no_network():
    # no feed address -> None, without any RPC call
    assert oc.chainlink_price("NOTACOIN") is None


def test_defillama_history_parses(monkeypatch):
    coin = "coingecko:bitcoin"
    payload = {"coins": {coin: {"prices": [
        {"timestamp": 1_700_000_000, "price": 10.0},
        {"timestamp": 1_700_086_400, "price": 11.0}]}}}
    monkeypatch.setattr(oc, "_http_json", lambda *a, **k: payload)
    bars = oc.defillama_history("BTC", 10)
    assert len(bars) == 2
    assert bars[0].close == 10.0 and bars[0].volume == 0.0


def test_onchain_feed_is_daily_only():
    raised = False
    try:
        OnChainFeed().history("BTC", "4h", 10)
    except ValueError:
        raised = True
    assert raised


def test_get_feed_factory():
    assert isinstance(get_feed("onchain"), OnChainFeed)
    assert isinstance(get_feed("cex"), ExchangeFeed)
    assert isinstance(get_feed("auto"), ExchangeFeed)


def test_get_feed_env(monkeypatch):
    monkeypatch.setenv("TB_DATA_SOURCE", "onchain")
    assert isinstance(get_feed(), OnChainFeed)
