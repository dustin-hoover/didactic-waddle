"""Offline tests for the on-chain tape reader (Uniswap V3 Swap decoding + scoring)."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tradebot.tape as tp
from tradebot.tape import Block, PoolMeta, decode_swap, rank_universe, score_blocks


def _word(signed_int: int) -> str:
    """Encode an int as a 32-byte, two's-complement hex word (no 0x)."""
    return f"{signed_int & (2**256 - 1):064x}"


def _swap_log(amount0: int, amount1: int, sqrt_p: int, block: int = 100) -> dict:
    data = "0x" + _word(amount0) + _word(amount1) + _word(sqrt_p) + _word(0) + _word(0)
    return {"data": data, "blockNumber": hex(block), "transactionHash": "0xabc"}


def test_decode_usd_pool_buy():
    # ETH-style pool: token0 = USDC (quote), token1 = WETH (base). ETH ≈ $2000.
    meta = PoolMeta("0xpool", base_is_token0=False, base_dec=18, quote_dec=6, quote="USD")
    # price_in_quote(base in USD)=2000 -> t0_in_t1=1/2000 = p*10^(6-18) -> p=5e8
    sqrt_p = int(math.sqrt(5e8) * 2 ** 96)
    # taker BUYS 1 WETH: USDC in (+2000e6), WETH out (-1e18)
    b = decode_swap(meta, _swap_log(2000 * 10 ** 6, -(10 ** 18), sqrt_p))
    assert b.side == "BUY"
    assert abs(b.price - 2000) / 2000 < 0.01
    assert abs(b.usd_size - 2000) < 1.0


def test_decode_usd_pool_sell():
    meta = PoolMeta("0xpool", base_is_token0=False, base_dec=18, quote_dec=6, quote="USD")
    sqrt_p = int(math.sqrt(5e8) * 2 ** 96)
    # taker SELLS 1 WETH: WETH in (+1e18), USDC out (-2000e6)
    b = decode_swap(meta, _swap_log(-(2000 * 10 ** 6), 10 ** 18, sqrt_p))
    assert b.side == "SELL"
    assert abs(b.usd_size - 2000) < 1.0


def test_decode_weth_pool_priced_through_eth():
    # UNI-style pool: token0 = UNI (base), token1 = WETH (quote). UNI ≈ $10, ETH=$2000.
    meta = PoolMeta("0xpool", base_is_token0=True, base_dec=18, quote_dec=18, quote="WETH")
    # price_in_quote(UNI in WETH)=0.005 -> t0_in_t1=p=0.005
    sqrt_p = int(math.sqrt(0.005) * 2 ** 96)
    # taker BUYS UNI: UNI out (-X), WETH in (+0.5e18) -> 0.5 WETH * $2000 = $1000
    b = decode_swap(meta, _swap_log(-(50 * 10 ** 18), 5 * 10 ** 17, sqrt_p), eth_price=2000.0)
    assert b.side == "BUY"
    assert abs(b.price - 10) / 10 < 0.01
    assert abs(b.usd_size - 1000) < 5.0


def test_decode_weth_pool_needs_eth_price():
    meta = PoolMeta("0xpool", base_is_token0=True, base_dec=18, quote_dec=18, quote="WETH")
    sqrt_p = int(math.sqrt(0.005) * 2 ** 96)
    assert decode_swap(meta, _swap_log(-(10 ** 18), 10 ** 17, sqrt_p), eth_price=0.0) is None


def test_decode_rejects_short_data():
    meta = PoolMeta("0xpool", base_is_token0=True, base_dec=18, quote_dec=6, quote="USD")
    assert decode_swap(meta, {"data": "0x1234", "blockNumber": "0x1"}) is None


def test_score_blocks_cvd_and_bias():
    blocks = [
        Block(1, "0x1", 100_000, "BUY", 10.0),
        Block(2, "0x2", 300_000, "BUY", 10.1),    # whale buy
        Block(3, "0x3", 50_000, "SELL", 10.05),
    ]
    s = score_blocks("UNI", "0xpool", blocks, whale_usd=250_000)
    assert s.buy_usd == 400_000 and s.sell_usd == 50_000
    assert abs(s.net_usd - 350_000) < 1e-6
    assert s.whale_usd == 300_000                 # only the 300k print
    assert s.largest.usd_size == 300_000
    assert s.score > 0.15 and s.bias == "ACCUMULATION"
    # price impact filled vs previous print
    assert abs(blocks[1].price_impact - (10.1 - 10.0) / 10.0 * 100) < 1e-6


def test_score_blocks_distribution():
    blocks = [Block(1, "0x1", 500_000, "SELL", 10.0), Block(2, "0x2", 100_000, "BUY", 9.9)]
    s = score_blocks("UNI", "0xpool", blocks, whale_usd=250_000)
    assert s.score < -0.15 and s.bias == "DISTRIBUTION" and s.net_usd < 0


def test_score_blocks_empty():
    s = score_blocks("UNI", "0xpool", [])
    assert s.n_prints == 0 and s.score == 0.0 and s.bias == "balanced"


def test_to_signed():
    assert tp._to_signed(1) == 1
    assert tp._to_signed(2 ** 256 - 1) == -1
    assert tp._to_signed((1 << 255)) == -(1 << 255)


def test_rank_universe_orders_by_conviction(monkeypatch):
    def fake_read(sym, blocks=7200, whale_usd=tp.DEFAULT_WHALE_USD):
        table = {
            "AAA": score_blocks("AAA", "0xa", [Block(1, "0x", 900_000, "BUY", 1.0)], whale_usd=1),
            "BBB": score_blocks("BBB", "0xb", [Block(1, "0x", 900_000, "SELL", 1.0),
                                               Block(2, "0x", 100_000, "BUY", 1.0)], whale_usd=1),
            "CCC": score_blocks("CCC", "0xc", [Block(1, "0x", 100_000, "BUY", 1.0),
                                               Block(2, "0x", 90_000, "SELL", 1.0)], whale_usd=999_999),
        }
        return table[sym]

    monkeypatch.setattr(tp, "read_tape", fake_read)
    ranked = rank_universe(["AAA", "BBB", "CCC"], top=3)
    assert [r.symbol for r in ranked][:2] == ["AAA", "BBB"]   # strongest |score| first
    assert ranked[-1].symbol == "CCC"                          # near-balanced last
