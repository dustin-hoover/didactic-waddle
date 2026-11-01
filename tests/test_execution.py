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


def test_btcb_tradeable_on_avalanche():
    pol = ExecutionPolicy(enabled=True, chain="avalanche", allowed_tokens=("USDC", "BTCB"),
                          max_notional_usd=100)
    pr = propose("b1", "0xabc", "USDC", "BTCB", 100.0, {"USDC": 1.0, "BTCB": 100000.0}, pol)
    assert pr.ok is True
    assert pr.buy_token == "0x152b9d0fdc40c096757f570a51e494bd4b943e50"
    assert pr.spender == "0xc92e8bdf79f0507f65a392b0ab4667716bfe0110"   # CoW relayer


def test_wbtc_tradeable_on_arbitrum():
    pol = ExecutionPolicy(enabled=True, chain="arbitrum", allowed_tokens=("USDC", "WBTC"),
                          max_notional_usd=100)
    pr = propose("b1", "0xabc", "USDC", "WBTC", 100.0, {"USDC": 1.0, "WBTC": 100000.0}, pol)
    assert pr.ok is True and pr.buy_token == "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"


# ---- Phase 0.4: live path refuses tokens that aren't safety-OK -----------------

def test_live_refuses_discovered_unknown_token(tmp_path):
    from tradebot import execution as ex
    # A discovered token with an UNKNOWN verdict: registered for addresses, NOT live.
    ex.register_tokens("base", {"SKETCH": ("0x" + "9" * 40, 18)},
                       safety={"SKETCH": "UNKNOWN"})
    prices = {"USDC": 1.0, "SKETCH": 0.5}
    pol_live = ExecutionPolicy(enabled=True, chain="base",
                               allowed_tokens=("USDC", "SKETCH"), max_notional_usd=100)
    with pytest.raises(PolicyError, match="not live-eligible"):
        propose("b1", "0xabc", "USDC", "SKETCH", 100.0, prices, pol_live)
    # Dry-run (kill switch off) still builds a preview for research/UX.
    pol_dry = ExecutionPolicy(enabled=False, chain="base",
                              allowed_tokens=("USDC", "SKETCH"), max_notional_usd=100)
    pr = propose("b1", "0xabc", "USDC", "SKETCH", 100.0, prices, pol_dry)
    assert pr.ok is False


def test_live_allows_discovered_ok_token():
    from tradebot import execution as ex
    ex.register_tokens("base", {"CLEAN": ("0x" + "a" * 40, 18)}, safety={"CLEAN": "OK"})
    pol = ExecutionPolicy(enabled=True, chain="base",
                          allowed_tokens=("USDC", "CLEAN"), max_notional_usd=100)
    pr = propose("b1", "0xabc", "USDC", "CLEAN", 100.0, {"USDC": 1.0, "CLEAN": 2.0}, pol)
    assert pr.ok is True


def test_live_allows_hand_vetted_core_without_a_verdict():
    # CBBTC is hand-audited (TRUSTED), so it is live-eligible with no recorded verdict.
    pol = ExecutionPolicy(enabled=True, chain="base", allowed_tokens=("USDC", "CBBTC"),
                          max_notional_usd=100)
    pr = propose("b1", "0xabc", "USDC", "CBBTC", 100.0, {"USDC": 1.0, "CBBTC": 77000.0}, pol)
    assert pr.ok is True


def test_live_refuses_caution_and_avoid():
    from tradebot import execution as ex
    ex.register_tokens("base", {"MEH": ("0x" + "b" * 40, 18),
                                "BAD": ("0x" + "c" * 40, 18)},
                       safety={"MEH": "CAUTION", "BAD": "AVOID"})
    for sym, price in (("MEH", 1.0), ("BAD", 1.0)):
        pol = ExecutionPolicy(enabled=True, chain="base",
                              allowed_tokens=("USDC", sym), max_notional_usd=100)
        with pytest.raises(PolicyError, match="not live-eligible"):
            propose("b1", "0xabc", "USDC", sym, 100.0, {"USDC": 1.0, sym: price}, pol)
