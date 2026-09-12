"""Tests for the Base universe-expander — the vetting bars are the point (offline)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.execution import TOKENS, register_tokens
from tradebot.universe import (TokenCandidate, discover_base, to_registry,
                               vet_candidates)


def _c(sym, addr="0x" + "1" * 40, dec=18, reserve=1e6, vol=5e6, n=2, cg="x"):
    return TokenCandidate(sym, addr, dec, reserve, vol, n, cg)


def test_liquidity_floor_enforced():
    cands = [_c("DEEP", reserve=2e6), _c("THIN", addr="0x" + "2" * 40, reserve=50_000)]
    out = vet_candidates(cands, min_reserve_usd=250_000)
    syms = [v.symbol for v in out]
    assert "DEEP" in syms and "THIN" not in syms


def test_unlisted_rejected_but_allowlist_forces_in():
    cands = [_c("GHOST", cg=None, reserve=2e6)]
    assert vet_candidates(cands, require_listed=True) == []
    forced = vet_candidates(cands, require_listed=True, allow=("GHOST",))
    assert [v.symbol for v in forced] == ["GHOST"]


def test_stablecoins_skipped():
    out = vet_candidates([_c("USDC", reserve=9e9), _c("WETH", addr="0x" + "3" * 40)])
    assert [v.symbol for v in out] == ["WETH"]


def test_blocklist_excludes():
    out = vet_candidates([_c("SCAM", reserve=9e9)], block=("SCAM",))
    assert out == []


def test_dedup_keeps_deepest_and_sorts_by_reserve():
    cands = [
        _c("AERO", addr="0x" + "a" * 40, reserve=1e6),
        _c("AERO", addr="0x" + "b" * 40, reserve=5e6),   # deeper dup wins
        _c("VIRTUAL", addr="0x" + "c" * 40, reserve=8e6),
    ]
    out = vet_candidates(cands)
    assert [v.symbol for v in out] == ["VIRTUAL", "AERO"]
    aero = next(v for v in out if v.symbol == "AERO")
    assert aero.address == "0x" + "b" * 40 and aero.reserve_usd == 5e6


def test_missing_decimals_skipped():
    out = vet_candidates([_c("NODEC", dec=None, reserve=9e6)])
    assert out == []


def test_discover_base_with_injected_fetch():
    # Two GeckoTerminal-shaped pages: a deep listed token + a thin one.
    page = {
        "data": [
            {"attributes": {"name": "AERO / USDC", "reserve_in_usd": "3000000",
                            "volume_usd": {"h24": "1000000"}},
             "relationships": {"base_token": {"data": {"id": "base_0xae"}}}},
            {"attributes": {"name": "THIN / WETH", "reserve_in_usd": "10000",
                            "volume_usd": {"h24": "5000"}},
             "relationships": {"base_token": {"data": {"id": "base_0xth"}}}},
        ],
        "included": [
            {"type": "token", "id": "base_0xae",
             "attributes": {"address": "0xAE", "symbol": "AERO", "decimals": 18, "coingecko_coin_id": "aerodrome"}},
            {"type": "token", "id": "base_0xth",
             "attributes": {"address": "0xTH", "symbol": "THIN", "decimals": 18, "coingecko_coin_id": None}},
        ],
    }
    out = discover_base(pages=1, min_reserve_usd=250_000, fetch=lambda p: page)
    assert [v.symbol for v in out] == ["AERO"]
    assert out[0].address == "0xae"       # lower-cased


def test_to_registry_and_register_merges_without_override():
    vetted = discover_base(pages=1, fetch=lambda p: {
        "data": [{"attributes": {"name": "AERO / USDC", "reserve_in_usd": "3000000",
                                 "volume_usd": {"h24": "1"}},
                  "relationships": {"base_token": {"data": {"id": "base_0xae"}}}}],
        "included": [{"type": "token", "id": "base_0xae",
                      "attributes": {"address": "0xAE", "symbol": "AERO", "decimals": 18,
                                     "coingecko_coin_id": "aerodrome"}}]})
    reg = to_registry(vetted)
    assert reg["AERO"] == ("0xae", 18)
    # register must NOT override the hand-vetted USDC entry
    original_usdc = TOKENS["base"]["USDC"]
    register_tokens("base", {**reg, "USDC": ("0xbad", 6)})
    assert TOKENS["base"]["USDC"] == original_usdc
    assert TOKENS["base"]["AERO"] == ("0xae", 18)
    del TOKENS["base"]["AERO"]             # clean up shared registry
