"""Offline tests for the Solana SPL rug-screen (mint authorities)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot import solana as sol


def _rpc_returning(info):
    """Fake getAccountInfo RPC returning the given parsed mint info (or None)."""
    def rpc(method, params):
        if info is None:
            return {"value": None}
        return {"value": {"data": {"parsed": {"info": info, "type": "mint"}}}}
    return rpc


def test_known_safe_short_circuits_no_rpc():
    # A canonical major must not need the network.
    def boom(*a, **k):
        raise AssertionError("should not hit RPC for a known-safe mint")
    r = sol.check("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", rpc=boom)
    assert r.verdict == "OK" and r.risk_score == 0 and r.name == "USDC"


def test_clean_token_both_authorities_null_is_ok():
    info = {"decimals": 6, "mintAuthority": None, "freezeAuthority": None,
            "supply": "1000", "isInitialized": True}
    r = sol.check("Mint1111111111111111111111111111111111111111", rpc=_rpc_returning(info))
    assert r.verdict == "OK" and r.risk_score == 0


def test_freeze_authority_alone_is_avoid():
    info = {"decimals": 6, "mintAuthority": None, "freezeAuthority": "Frz1111",
            "supply": "1000", "isInitialized": True}
    r = sol.check("Mint2", rpc=_rpc_returning(info))
    assert r.verdict == "AVOID" and r.risk_score >= 60
    assert any("freeze" in f.lower() for f in r.flags)


def test_mint_authority_alone_is_caution():
    info = {"decimals": 9, "mintAuthority": "Mnt111", "freezeAuthority": None,
            "supply": "1000", "isInitialized": True}
    r = sol.check("Mint3", rpc=_rpc_returning(info))
    assert r.verdict == "CAUTION" and 25 <= r.risk_score < 60


def test_unreadable_mint_is_unknown_not_clean():
    r = sol.check("Mint4", rpc=_rpc_returning(None))
    assert r.verdict == "UNKNOWN" and "rpc" in r.notes


def test_mint_info_parses_fields():
    info = {"decimals": 8, "mintAuthority": "A", "freezeAuthority": "B",
            "supply": "42", "isInitialized": True}
    mi = sol.mint_info("MintX", rpc=_rpc_returning(info))
    assert mi.decimals == 8 and mi.supply == 42 and mi.freeze_authority == "B"
