"""Offline tests for the Solana/Jupiter execution proposal layer."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tradebot.execution import PolicyError
from tradebot.solana_exec import (SolanaExecPolicy, propose, register_tokens,
                                   SOLANA_TOKENS)

PRICES = {"USDC": 1.0, "SOL": 200.0, "CBBTC": 100000.0}


def _fake_quote(out_amount, min_out, impact="0.001", label="Orca"):
    # Mimics a Jupiter /quote response.
    def fetch(url):
        return {"outAmount": str(out_amount), "otherAmountThreshold": str(min_out),
                "priceImpactPct": impact,
                "routePlan": [{"swapInfo": {"label": label}}]}
    return fetch


def test_preview_when_kill_switch_off():
    pr = propose("owner", "USDC", "SOL", 50.0, PRICES, quote_fn=False)  # default policy: disabled
    assert pr.ok is False
    assert any("kill switch" in w for w in pr.warnings)


def test_ok_and_amounts_from_live_quote():
    pol = SolanaExecPolicy(enabled=True, max_notional_usd=100)
    # $50 USDC -> SOL; quote says 0.25 SOL out (9 decimals), min 0.248
    q = _fake_quote(out_amount=250_000_000, min_out=248_000_000, impact="0.002")
    pr = propose("owner", "USDC", "SOL", 50.0, PRICES, pol, quote_fn=q)
    assert pr.ok is True
    assert abs(pr.est_buy_amount - 0.25) < 1e-9
    assert abs(pr.min_buy_amount - 0.248) < 1e-9
    assert pr.route == ["Orca"] and pr.sell_mint == SOLANA_TOKENS["USDC"][0]


def test_notional_cap_refused():
    pol = SolanaExecPolicy(enabled=True, max_notional_usd=100)
    with pytest.raises(PolicyError):
        propose("owner", "USDC", "SOL", 250.0, PRICES, pol, quote_fn=False)


def test_allowlist_enforced():
    pol = SolanaExecPolicy(enabled=True, allowed_tokens=("USDC", "SOL"))
    with pytest.raises(PolicyError):
        propose("owner", "USDC", "JUP", 20.0, {**PRICES, "JUP": 0.8}, pol, quote_fn=False)


def test_same_token_refused():
    with pytest.raises(PolicyError):
        propose("owner", "SOL", "SOL", 20.0, PRICES, SolanaExecPolicy(enabled=True), quote_fn=False)


def test_missing_price_refused():
    with pytest.raises(PolicyError):
        propose("owner", "USDC", "SOL", 20.0, {"USDC": 1.0}, SolanaExecPolicy(enabled=True), quote_fn=False)


def test_estimate_without_quote_warns():
    pol = SolanaExecPolicy(enabled=True)
    pr = propose("owner", "USDC", "SOL", 50.0, PRICES, pol, quote_fn=False)
    assert abs(pr.est_buy_amount - 0.25) < 1e-9          # 50 / 200
    assert any("oracle estimate" in w for w in pr.warnings)


def test_register_tokens_no_override():
    before = SOLANA_TOKENS["USDC"]
    register_tokens({"USDC": ("bad", 6), "WIF": ("WifMint111", 6)})
    assert SOLANA_TOKENS["USDC"] == before          # existing not overridden
    assert SOLANA_TOKENS["WIF"] == ("WifMint111", 6)
    del SOLANA_TOKENS["WIF"]                          # clean shared registry
