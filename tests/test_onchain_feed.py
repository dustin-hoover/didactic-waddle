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


def test_v3_pool_price_direct_read(monkeypatch):
    # Synthetic USDC(token0)/WETH(token1) pool priced so ETH ≈ $2000.
    usdc = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    weth = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    P = (1 / 2000) * 10 ** 12               # from t0_in_t1 = P*10^(6-18) = 1/2000
    sqrt_p = int((P ** 0.5) * 2 ** 96)
    slot0 = "0x" + f"{sqrt_p:064x}"

    def fake(to, data):
        if data == "0x0dfe1681":
            return "0x" + "0" * 24 + usdc[2:]
        if data == "0xd21220a7":
            return "0x" + "0" * 24 + weth[2:]
        if data == "0x3850c7bd":
            return slot0
        return None

    monkeypatch.setattr(oc, "_eth_call", fake)
    price = oc._v3_pool_price_usd("0xpool")
    assert abs(price - 2000) / 2000 < 0.01   # direct pool read recovers ~$2000


def test_trustless_cross_check(monkeypatch):
    # agree within tolerance -> trust the direct pool read
    monkeypatch.setattr(oc, "v3_price_usd", lambda s: 100.0)
    monkeypatch.setattr(oc, "chainlink_price", lambda s: 101.0)
    assert oc.trustless_price("BTC") == 100.0
    # diverge -> fall back to the oracle (manipulation guard)
    monkeypatch.setattr(oc, "chainlink_price", lambda s: 200.0)
    assert oc.trustless_price("BTC") == 200.0
    # only oracle available
    monkeypatch.setattr(oc, "v3_price_usd", lambda s: None)
    assert oc.trustless_price("BTC") == 200.0


def test_v3_unconfigured_symbol_is_none():
    assert oc.v3_price_usd("NOTACOIN") is None
