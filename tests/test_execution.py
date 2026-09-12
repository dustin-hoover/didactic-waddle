"""Tests for the propose-and-sign execution layer — guardrails are the point."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tradebot.execution import (ExecutionPolicy, OrderProposal, PolicyError,
                                 propose, proposal_for_signal)

PRICES = {"USDC": 1.0, "WETH": 2000.0, "WBTC": 60000.0, "PEPE": 0.00001}


def test_preview_when_kill_switch_off():
    pr = propose("b1", "0xabc", "USDC", "WETH", 100.0, PRICES)  # default policy: disabled
    assert isinstance(pr, OrderProposal)
    assert pr.ok is False                              # cannot be signed
    assert any("kill switch is OFF" in w for w in pr.warnings)
    assert abs(pr.sell_amount - 100.0) < 1e-9          # 100 USDC
    assert abs(pr.est_buy_amount - 0.05) < 1e-9        # 0.05 WETH @ $2000
    assert pr.min_buy_amount < pr.est_buy_amount       # slippage applied


def test_ok_only_when_enabled():
    pol = ExecutionPolicy(enabled=True, max_notional_usd=100)
    pr = propose("b1", "0xabc", "USDC", "WETH", 100.0, PRICES, pol)
    assert pr.ok is True and not any("kill switch" in w for w in pr.warnings)


def test_notional_cap_refused():
    pol = ExecutionPolicy(enabled=True, max_notional_usd=100)
    with pytest.raises(PolicyError):
        propose("b1", "0xabc", "USDC", "WETH", 250.0, PRICES, pol)


def test_token_allowlist_enforced():
    pol = ExecutionPolicy(enabled=True, allowed_tokens=("USDC", "WETH"))
    with pytest.raises(PolicyError):
        propose("b1", "0xabc", "USDC", "PEPE", 50.0, PRICES, pol)


def test_same_token_refused():
    with pytest.raises(PolicyError):
        propose("b1", "0xabc", "USDC", "USDC", 50.0, PRICES, ExecutionPolicy(enabled=True))


def test_unknown_token_on_chain_refused():
    # WBTC is not in the base registry
    pol = ExecutionPolicy(enabled=True, chain="base", allowed_tokens=("USDC", "WBTC"))
    with pytest.raises(PolicyError):
        propose("b1", "0xabc", "USDC", "WBTC", 50.0, PRICES, pol)


def test_missing_price_refused():
    with pytest.raises(PolicyError):
        propose("b1", "0xabc", "USDC", "WETH", 50.0, {"USDC": 1.0}, ExecutionPolicy(enabled=True))


def test_raw_amounts_use_decimals():
    pol = ExecutionPolicy(enabled=True, max_notional_usd=1000)
    pr = propose("b1", "0xabc", "USDC", "WETH", 100.0, PRICES, pol)
    assert pr.sell_amount_raw == str(100 * 10 ** 6)     # USDC 6 decimals
    assert pr.buy_token.startswith("0x") and pr.spender.startswith("0x")


def test_slippage_min_bound():
    pr = propose("b1", "0xabc", "USDC", "WETH", 50.0, PRICES,
                 ExecutionPolicy(enabled=True, max_slippage_bps=30))
    assert pr.slippage_bps == 30
    expected_min = (50.0 / 2000.0) * (1 - 30 / 10_000)
    assert abs(pr.min_buy_amount - expected_min) < 1e-9


def test_proposal_for_signal_buy_and_sell():
    pol = ExecutionPolicy(enabled=True, max_notional_usd=1000)
    # increase exposure 0.0 -> 0.5 of $200 equity -> buy $100 of WETH with USDC
    buy = proposal_for_signal("b1", "0xabc", 0.5, 0.0, 200.0, "WETH", PRICES, pol)
    assert buy.sell_symbol == "USDC" and buy.buy_symbol == "WETH"
    assert abs(buy.notional_usd - 100.0) < 1e-6
    # decrease exposure 0.5 -> 0.0 -> sell WETH back to USDC
    sell = proposal_for_signal("b1", "0xabc", 0.0, 0.5, 200.0, "WETH", PRICES, pol)
    assert sell.sell_symbol == "WETH" and sell.buy_symbol == "USDC"


def test_proposal_for_signal_dust_is_noop():
    pol = ExecutionPolicy(enabled=True)
    assert proposal_for_signal("b1", "0xabc", 0.5001, 0.5, 100.0, "WETH", PRICES, pol) is None


def test_proposal_for_signal_respects_cap():
    pol = ExecutionPolicy(enabled=True, max_notional_usd=100)
    # a huge move gets clamped to the cap, not refused
    pr = proposal_for_signal("b1", "0xabc", 1.0, 0.0, 10_000.0, "WETH", PRICES, pol)
    assert pr is not None and pr.notional_usd == 100.0


def test_cbbtc_tradeable_on_base():
    # cbBTC is the Base-native BTC vehicle the regime gate is validated on.
    pol = ExecutionPolicy(enabled=True, chain="base", allowed_tokens=("USDC", "CBBTC"),
                          max_notional_usd=100)
    pr = propose("b1", "0xabc", "USDC", "CBBTC", 100.0,
                 {"USDC": 1.0, "CBBTC": 77000.0}, pol)
    assert pr.ok is True
    assert pr.buy_token == "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
    # 8-decimal token: ~100/77000 cbBTC in raw base units
    assert pr.min_buy_raw.isdigit() and int(pr.min_buy_raw) > 0
