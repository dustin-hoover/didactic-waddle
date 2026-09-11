"""Tests for tax lot tracking (FIFO/HIFO), summary, estimate, sweep proposal."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tradebot import tax

DAY = 86400


def _t(ts, side, amount, px, sym="ETH"):
    return {"ts": ts, "symbol": sym, "side": side, "amount": amount, "price_usd": px}


def test_fifo_matches_oldest_first():
    trades = [_t(0, "buy", 1, 100), _t(DAY, "buy", 1, 200), _t(2*DAY, "sell", 1, 300)]
    d = tax.compute_realized(trades, "fifo")
    assert len(d) == 1
    assert d[0].cost_basis_usd == 100 and d[0].proceeds_usd == 300  # sold the $100 lot
    assert d[0].gain_usd == 200


def test_hifo_matches_highest_cost_first():
    trades = [_t(0, "buy", 1, 100), _t(DAY, "buy", 1, 200), _t(2*DAY, "sell", 1, 300)]
    d = tax.compute_realized(trades, "hifo")
    assert d[0].cost_basis_usd == 200 and d[0].gain_usd == 100  # sold the $200 lot


def test_partial_lot_consumption():
    trades = [_t(0, "buy", 2, 100), _t(DAY, "sell", 0.5, 150)]
    d = tax.compute_realized(trades, "fifo")
    assert len(d) == 1 and abs(d[0].amount - 0.5) < 1e-9
    assert abs(d[0].cost_basis_usd - 50) < 1e-9 and abs(d[0].gain_usd - 25) < 1e-9


def test_long_vs_short_term():
    trades = [_t(0, "buy", 1, 100), _t(2*DAY, "sell", 1, 120),         # short
              _t(0, "buy", 1, 100, "BTC"), _t(400*DAY, "sell", 1, 120, "BTC")]  # long
    d = tax.compute_realized(trades, "fifo")
    eth = next(x for x in d if x.symbol == "ETH"); btc = next(x for x in d if x.symbol == "BTC")
    assert eth.long_term is False and btc.long_term is True


def test_summary_and_estimate():
    trades = [_t(0, "buy", 1, 100), _t(2*DAY, "sell", 1, 200),            # +100 short
              _t(0, "buy", 1, 100, "BTC"), _t(400*DAY, "sell", 1, 300, "BTC")]  # +200 long
    s = tax.summarize(tax.compute_realized(trades, "fifo"))
    assert abs(s.short_gain_usd - 100) < 1e-9 and abs(s.long_gain_usd - 200) < 1e-9
    est = tax.estimate_tax(s, short_rate=0.35, long_rate=0.15)
    assert abs(est["short_tax"] - 35) < 1e-6 and abs(est["long_tax"] - 30) < 1e-6
    assert abs(est["total_tax"] - 65) < 1e-6


def test_net_loss_no_tax():
    trades = [_t(0, "buy", 1, 200), _t(2*DAY, "sell", 1, 100)]  # -100 short
    s = tax.summarize(tax.compute_realized(trades, "fifo"))
    assert s.short_gain_usd == -100
    assert tax.estimate_tax(s)["total_tax"] == 0.0     # no credit for a loss


def test_sell_without_basis_is_zero_basis():
    d = tax.compute_realized([_t(0, "sell", 1, 100)], "fifo")
    assert d[0].cost_basis_usd == 0.0 and d[0].gain_usd == 100


def test_sweep_proposal_builds_transfer():
    p = tax.sweep_proposal(50.0, "0x1111111111111111111111111111111111111111", "base", "USDC")
    assert p["amount_raw"] == str(50 * 10**6)                 # USDC 6 decimals
    assert p["calldata"].startswith("0xa9059cbb")             # ERC-20 transfer selector
    assert "0x1111111111111111111111111111111111111111"[2:] in p["calldata"]


def test_sweep_rejects_bad_address():
    with pytest.raises(ValueError):
        tax.sweep_proposal(50.0, "not-an-address")


def test_trades_from_fills_converts_ms():
    class F:  # mimic portfolio.Fill
        def __init__(s, ts, side, units, price): s.ts=ts; s.side=side; s.units=units; s.price=price
    fills = [F(1_700_000_000_000, "buy", 2.0, 100.0)]   # ms timestamp
    tr = tax.trades_from_fills(fills, "ETH")
    assert tr[0]["ts"] == 1_700_000_000 and tr[0]["amount"] == 2.0   # converted to seconds
