"""Offline tests for the opportunity screener (pure scoring; network injected)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.fundamentals import (CoinMetrics, ScoreWeights, rank, fetch_universe,
                                    _pct_ranks)


def _coin(sym, rank_=10, vol=5e7, mcap=1e9, tvl=None, fees=None, trend=None, safety=None):
    return CoinMetrics(symbol=sym, coingecko_id=sym.lower(), mcap_rank=rank_, mcap_usd=mcap,
                       vol24_usd=vol, tvl_usd=tvl, fees24_usd=fees, trend_strength=trend,
                       safety_verdict=safety)


def test_pct_ranks_basic_and_ties():
    r = _pct_ranks([10.0, 20.0, 30.0])
    assert r == [0.0, 0.5, 1.0]
    # None gets 0; ties share the average rank
    r2 = _pct_ranks([5.0, 5.0, None, 9.0])
    assert r2[2] == 0.0                       # missing -> 0
    assert r2[0] == r2[1] and r2[3] == 1.0    # the two 5.0s tie below the 9.0


def test_excludes_stables_and_wrapped():
    coins = [_coin("USDT"), _coin("WBTC"), _coin("WETH"), _coin("AAVE", tvl=1e9)]
    out = rank(coins, min_vol_usd=0)
    syms = {r["symbol"] for r in out}
    assert syms == {"AAVE"}                    # stables/wrapped dropped


def test_mcap_rank_and_volume_filters():
    coins = [_coin("AAA", rank_=200, tvl=1e9),         # too deep in the rank
             _coin("BBB", rank_=10, vol=1e5, tvl=1e9),  # too illiquid
             _coin("CCC", rank_=10, vol=5e7, tvl=1e9)]  # ok
    out = rank(coins, max_rank=150, min_vol_usd=5e6)
    assert [r["symbol"] for r in out] == ["CCC"]


def test_drops_avoid_safety():
    coins = [_coin("GOOD", tvl=1e9, safety="OK"), _coin("RUG", tvl=5e9, safety="AVOID")]
    out = rank(coins, min_vol_usd=0)
    assert [r["symbol"] for r in out] == ["GOOD"]      # AVOID dropped despite higher TVL


def test_usage_dominates_when_weighted():
    # Same liquidity/trend; higher TVL+fees should rank first under usage weight.
    hi = _coin("HI", vol=5e7, tvl=5e9, fees=5e6, trend=0.0)
    lo = _coin("LO", vol=5e7, tvl=1e7, fees=1e4, trend=0.0)
    out = rank([hi, lo], weights=ScoreWeights(usage=1.0, liquidity=0.0, trend=0.0), min_vol_usd=0)
    assert out[0]["symbol"] == "HI" and out[0]["usage_score"] > out[1]["usage_score"]


def test_trend_breaks_ties_when_weighted():
    up = _coin("UP", vol=5e7, tvl=1e9, trend=0.9)
    dn = _coin("DN", vol=5e7, tvl=1e9, trend=-0.9)
    out = rank([up, dn], weights=ScoreWeights(usage=0.0, liquidity=0.0, trend=1.0), min_vol_usd=0)
    assert out[0]["symbol"] == "UP" and out[0]["trend_score"] > out[1]["trend_score"]


def test_missing_trend_is_neutral_not_penalized():
    c = _coin("X", vol=5e7, tvl=1e9, trend=None)
    out = rank([c], min_vol_usd=0)
    assert out[0]["trend_score"] == 0.5        # neutral, not 0


def test_no_usage_data_gets_no_usage_credit():
    c = _coin("NOUSE", vol=5e7, tvl=None, fees=None)
    out = rank([c], min_vol_usd=0)
    assert out[0]["usage_score"] == 0.0


def test_top_n_limits_output():
    coins = [_coin(f"C{i}", vol=5e7, tvl=float(i + 1) * 1e8) for i in range(10)]
    out = rank(coins, top_n=3, min_vol_usd=0)
    assert len(out) == 3


def test_rows_sorted_by_score_desc():
    coins = [_coin(f"C{i}", vol=(i + 1) * 1e7, tvl=(i + 1) * 1e8, trend=0.0) for i in range(6)]
    out = rank(coins, min_vol_usd=0, top_n=99)
    scores = [r["score"] for r in out]
    assert scores == sorted(scores, reverse=True)


def test_fetch_universe_merges_injected_sources():
    markets = [{"id": "aave", "symbol": "aave", "market_cap_rank": 30,
                "market_cap": 2e9, "total_volume": 1e8},
               {"id": "uniswap", "symbol": "uni", "market_cap_rank": 25,
                "market_cap": 5e9, "total_volume": 2e8}]
    tvl = {"aave": 2.0e10, "uniswap": 4.0e9}
    fees = {"aave": 1.2e6, "uniswap": 2.5e6}
    coins = fetch_universe(markets_fn=lambda: markets, tvl_fn=lambda: tvl, fees_fn=lambda: fees)
    by = {c.symbol: c for c in coins}
    assert by["AAVE"].tvl_usd == 2.0e10 and by["UNI"].fees24_usd == 2.5e6
    assert by["AAVE"].mcap_rank == 30
