"""Offline tests for the NEAR Intents (1Click) cross-chain quote adapter.

No network: the 1Click POST is injected via `post_fn`, so these lock the
request we build, the guardrails, and the honest net-cost math.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tradebot import near_intents as ni

PRICES = {"USDC": 1.0, "SOL": 150.0, "CBBTC": 64000.0}


def _canned(amount_out="0.6", out_usd="99.0", deposit="near-deposit-abc", dry_echo=None):
    """A fake /v0/quote responder that also captures the request body."""
    seen = {}

    def post(path, body, jwt=""):
        seen["path"] = path
        seen["body"] = body
        seen["jwt"] = jwt
        return {"quote": {
            "amountInFormatted": "100",
            "amountInUsd": "100.0",
            "amountOutFormatted": amount_out,
            "amountOutUsd": out_usd,
            "minAmountOut": "590000000",           # raw, 9dp -> 0.59 (fallback path)
            "timeEstimate": 12,
            # a dry quote returns no deposit address; a live one does
            "depositAddress": "" if body.get("dry") else deposit,
        }}
    return post, seen


def test_asset_id_matches_documented_example():
    # The canonical documented example: arbitrum USDC.
    got = ni.asset_id("arbitrum", "0xaf88d065e77c8cc2239327c5edb3a432268e5831")
    assert got == "nep141:arb-0xaf88d065e77c8cc2239327c5edb3a432268e5831.omft.near"


def test_asset_id_lowercases_and_maps_chain():
    got = ni.asset_id("base", "0xCBB7C0000AB88B473B1F5AFD9EF808440EED33BF")
    assert got == "nep141:base-0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf.omft.near"


def test_resolve_asset_prefers_canonical_list():
    tokens = [{"blockchain": "sol", "symbol": "USDC", "assetId": "nep141:sol-REAL.omft.near"},
              {"blockchain": "base", "symbol": "USDC", "assetId": "nep141:base-x.omft.near"}]
    assert ni.resolve_asset(tokens, "solana", "USDC") == "nep141:sol-REAL.omft.near"
    assert ni.resolve_asset(tokens, "arbitrum", "USDC") is None   # not in the list


def test_dry_by_default_not_executable():
    post, seen = _canned()
    q = ni.quote("base", "solana", "USDC", "SOL", 100.0, price_usd=PRICES, post_fn=post)
    assert seen["body"]["dry"] is True             # kill switch off => dry
    assert q.dry is True and q.ok is False
    assert any("kill switch is OFF" in w for w in q.warnings)
    assert q.deposit_address == ""                 # dry => no route


def test_request_body_is_well_formed():
    post, seen = _canned()
    pol = ni.IntentsPolicy(slippage_bps=75, deadline_seconds=600)
    ni.quote("base", "solana", "USDC", "SOL", 100.0, recipient="Recip1",
             refund_to="0xrefund", policy=pol, price_usd=PRICES, post_fn=post)
    b = seen["body"]
    assert b["swapType"] == "EXACT_INPUT"
    assert b["depositType"] == "ORIGIN_CHAIN" and b["recipientType"] == "DESTINATION_CHAIN"
    assert b["refundType"] == "ORIGIN_CHAIN"
    assert b["slippageTolerance"] == 75
    assert b["originAsset"].startswith("nep141:base-") and b["destinationAsset"].startswith("nep141:sol-")
    assert b["amount"] == "100000000"              # 100 USDC @ $1, 6 decimals
    assert b["recipient"] == "Recip1" and b["refundTo"] == "0xrefund"
    assert b["deadline"].endswith("Z")


def test_amount_scales_with_price_and_decimals():
    post, seen = _canned()
    # $150 of SOL @ $150 => 1.0 SOL, 9 decimals => 1e9 raw
    ni.quote("solana", "base", "SOL", "USDC", 150.0, price_usd=PRICES, post_fn=post,
             policy=ni.IntentsPolicy(max_notional_usd=200))
    assert seen["body"]["amount"] == "1000000000"


def test_honest_cost_is_in_minus_out_usd():
    post, _ = _canned(amount_out="0.6", out_usd="97.5")
    q = ni.quote("base", "solana", "USDC", "SOL", 100.0, price_usd=PRICES, post_fn=post)
    assert q.amount_in_usd == 100.0 and q.amount_out_usd == 97.5
    assert q.cost_usd == 2.5                        # 100 - 97.5, all fees folded in
    assert q.cost_bps == 250.0                      # 2.5 / 100 * 10_000
    assert q.amount_out == 0.6


def test_live_quote_executable_when_armed():
    post, seen = _canned()
    pol = ni.IntentsPolicy(enabled=True, max_notional_usd=100)
    q = ni.quote("base", "solana", "USDC", "SOL", 100.0, recipient="Recip1",
                 policy=pol, price_usd=PRICES, post_fn=post)
    assert seen["body"]["dry"] is False
    assert q.dry is False and q.ok is True          # armed + deposit address present
    assert q.deposit_address == "near-deposit-abc"


def test_jwt_forwarded_when_present():
    post, seen = _canned()
    ni.quote("base", "solana", "USDC", "SOL", 100.0, price_usd=PRICES, post_fn=post, jwt="tok123")
    assert seen["jwt"] == "tok123"


def test_min_amount_out_fallback_from_raw():
    # No formatted min field -> derive from raw minAmountOut using dest decimals (SOL=9).
    post, _ = _canned()
    q = ni.quote("base", "solana", "USDC", "SOL", 100.0, price_usd=PRICES, post_fn=post)
    assert q.min_amount_out == 0.59                 # 590000000 / 1e9


def test_formula_fallback_warns_without_token_list():
    post, _ = _canned()
    q = ni.quote("base", "solana", "USDC", "SOL", 100.0, price_usd=PRICES, post_fn=post)
    assert any("verify against GET /v0/tokens" in w for w in q.warnings)


def test_canonical_list_used_when_supplied():
    post, seen = _canned()
    tokens = [{"blockchain": "base", "symbol": "USDC", "assetId": "nep141:base-CANON.omft.near"},
              {"blockchain": "sol", "symbol": "SOL", "assetId": "nep141:sol-CANON.omft.near"}]
    q = ni.quote("base", "solana", "USDC", "SOL", 100.0, price_usd=PRICES, post_fn=post, tokens=tokens)
    assert seen["body"]["originAsset"] == "nep141:base-CANON.omft.near"
    assert seen["body"]["destinationAsset"] == "nep141:sol-CANON.omft.near"
    assert not any("verify against" in w for w in q.warnings)


# ---- guardrails: refuse, never clamp ----

def test_dry_uses_chain_appropriate_placeholder_recipient():
    post, seen = _canned()
    ni.quote("base", "solana", "USDC", "SOL", 50.0, price_usd=PRICES, post_fn=post)
    # destination is Solana -> a base58 placeholder, not an 0x address
    assert seen["body"]["recipient"] == ni._PLACEHOLDER["solana"]
    assert not seen["body"]["recipient"].startswith("0x")


def test_live_quote_requires_real_recipient():
    post, _ = _canned()
    pol = ni.IntentsPolicy(enabled=True)
    with pytest.raises(ni.IntentsError):
        ni.quote("base", "solana", "USDC", "SOL", 50.0, policy=pol, price_usd=PRICES, post_fn=post)


def test_rejects_chain_off_allowlist():
    post, _ = _canned()
    with pytest.raises(ni.IntentsError):
        ni.quote("base", "ethereum", "USDC", "USDC", 50.0, price_usd=PRICES, post_fn=post)


def test_rejects_over_cap():
    post, _ = _canned()
    with pytest.raises(ni.IntentsError):
        ni.quote("base", "solana", "USDC", "SOL", 100_000.0, price_usd=PRICES, post_fn=post)


def test_rejects_identical_asset():
    post, _ = _canned()
    with pytest.raises(ni.IntentsError):
        ni.quote("base", "base", "USDC", "USDC", 50.0, price_usd=PRICES, post_fn=post)


def test_rejects_unknown_asset():
    post, _ = _canned()
    with pytest.raises(ni.IntentsError):
        ni.quote("base", "solana", "USDC", "PEPE", 50.0, price_usd=PRICES, post_fn=post)


def test_rejects_missing_price():
    post, _ = _canned()
    with pytest.raises(ni.IntentsError):
        ni.quote("base", "solana", "USDC", "SOL", 50.0, price_usd={}, post_fn=post)


def test_bridge_cost_bps_stable_relocation():
    post, seen = _canned(amount_out="49.9", out_usd="49.85")
    bps = ni.bridge_cost_bps("USDC", "base", "arbitrum", notional_usd=50.0, post_fn=post)
    # in_usd defaults to notional 50 (no amountInUsd override here -> uses notional)
    assert seen["body"]["originAsset"].startswith("nep141:base-")
    assert seen["body"]["destinationAsset"].startswith("nep141:arb-")
    assert bps is not None and bps > 0                    # 50 - 49.85 = 0.15 -> 30 bps


def test_bridge_cost_bps_unknown_asset_returns_none():
    post, _ = _canned()
    assert ni.bridge_cost_bps("PEPE", "base", "solana", post_fn=post) is None


def test_bridge_cost_bps_non_stable_without_price_none():
    post, _ = _canned()
    # SOL is a known asset but no price supplied -> cannot size -> None (not a crash)
    assert ni.bridge_cost_bps("SOL", "solana", "base", post_fn=post) is None


def test_bridge_cost_bps_swallows_errors():
    def boom(path, body, jwt=""): raise RuntimeError("down")
    assert ni.bridge_cost_bps("USDC", "base", "arbitrum", post_fn=boom) is None


def test_fetch_tokens_uses_injected_getter():
    def get(path, jwt=""):
        assert path == "/v0/tokens"
        return [{"blockchain": "base", "symbol": "USDC", "assetId": "x"}]
    assert ni.fetch_tokens(get_fn=get)[0]["symbol"] == "USDC"
