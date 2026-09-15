"""Tests for the honest arbitrage scanner."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.arbitrage import ArbConfig, find_arbitrage, scan_token


def test_needs_two_venues():
    o = find_arbitrage("SOL", [{"venue": "a", "price": 100}])
    assert o.tradeable is False and "need >=2" in o.reason


def test_small_spread_not_tradeable_after_costs():
    # 0.2% gross gap - two 0.3% fees - gas => deeply negative net
    o = find_arbitrage("X", [{"venue": "a", "price": 100.0}, {"venue": "b", "price": 100.2}])
    assert o.gross_bps == 20.0 and o.net_bps < 0 and o.tradeable is False


def test_large_spread_flags_net_positive():
    # 3% gross gap, custom low fees so net clears the bar
    cfg = ArbConfig(min_net_bps=10, default_fee_bps=10, gas_mev_bps=5)
    o = find_arbitrage("X", [{"venue": "cheap", "price": 100.0, "fee_bps": 10},
                             {"venue": "rich", "price": 103.0, "fee_bps": 10}], cfg)
    assert o.buy_venue == "cheap" and o.sell_venue == "rich"
    assert o.gross_bps == 300.0 and o.net_bps > 10 and o.tradeable is True


def test_cross_chain_adds_bridge_cost():
    cfg = ArbConfig(min_net_bps=10, default_fee_bps=10, gas_mev_bps=5, bridge_bps=100)
    same = find_arbitrage("X", [{"venue": "a", "price": 100, "chain": "base", "fee_bps": 10},
                                {"venue": "b", "price": 101.5, "chain": "base", "fee_bps": 10}], cfg)
    cross = find_arbitrage("X", [{"venue": "a", "price": 100, "chain": "base", "fee_bps": 10},
                                 {"venue": "b", "price": 101.5, "chain": "solana", "fee_bps": 10}], cfg)
    assert cross.net_bps == same.net_bps - 100     # bridge cost applied cross-chain


def test_no_spread():
    o = find_arbitrage("X", [{"venue": "a", "price": 100}, {"venue": "b", "price": 100}])
    assert o.tradeable is False and o.gross_bps == 0.0


def test_scan_token_uses_pool_prices_and_depth_filter():
    page = {"data": [
        {"attributes": {"name": "SOL / USDC", "base_token_price_usd": "100.0", "reserve_in_usd": "5000000"}},
        {"attributes": {"name": "SOL / USDT", "base_token_price_usd": "103.0", "reserve_in_usd": "2000000"}},
        {"attributes": {"name": "SOL / SCAM", "base_token_price_usd": "999.0", "reserve_in_usd": "5000"}},  # too thin -> ignored
    ]}
    cfg = ArbConfig(min_net_bps=10, default_fee_bps=10, gas_mev_bps=5)
    o = scan_token("SOL", "solana", "mint", cfg=cfg, fetch=lambda n, a: page, min_reserve_usd=100_000)
    assert o.buy_price == 100.0 and o.sell_price == 103.0    # thin $5k pool excluded
    assert o.tradeable is True


def test_scan_token_fetch_failure_is_safe():
    def boom(n, a):
        raise RuntimeError("gt down")
    o = scan_token("SOL", "solana", "mint", fetch=boom)
    assert o.tradeable is False and "fetch failed" in o.reason
