"""Tests for the chain registry / high-level toggle."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot import chains


def test_base_is_fully_capable():
    b = chains.get("base")
    assert b.kind == "evm" and b.can_discover and b.can_screen and b.can_execute
    assert b.primary_vehicle == "CBBTC" and b.screen_chainid == "8453"


def test_solana_fully_integrated():
    s = chains.get("solana")
    assert s.enabled and s.kind == "svm"
    assert s.can_discover is True            # GeckoTerminal has solana
    assert s.can_screen is True              # SPL mint-authority screen
    assert s.can_execute is True             # Jupiter wired + SOL vehicle
    assert s.primary_vehicle == "SOL" and s.vehicle_coin == "SOL"
    assert s.exec_venue == "jupiter"


def test_active_defaults_to_base(monkeypatch):
    monkeypatch.delenv("CHAIN", raising=False)
    assert chains.active().id == "base"


def test_active_honors_env_toggle(monkeypatch):
    monkeypatch.setenv("CHAIN", "solana")
    assert chains.active().id == "solana"


def test_active_falls_back_when_disabled_or_unknown(monkeypatch):
    monkeypatch.setenv("CHAIN", "ethereum")   # present but enabled=False
    assert chains.active().id == "base"
    monkeypatch.setenv("CHAIN", "nope")       # unknown
    assert chains.active().id == "base"


def test_enabled_lists_only_toggled_chains():
    ids = {c.id for c in chains.enabled()}
    assert "base" in ids and "solana" in ids and "ethereum" not in ids


def test_rpc_url_reads_env(monkeypatch):
    monkeypatch.setenv("SOLANA_RPC_URL", "https://sol.example/x")
    assert chains.get("solana").rpc_url == "https://sol.example/x"


def test_avalanche_fully_wired():
    a = chains.get("avalanche")
    assert a.enabled and a.kind == "evm"
    assert a.can_discover and a.can_screen and a.can_execute
    assert a.gt_network == "avax" and a.screen_chainid == "43114"
    assert a.primary_vehicle == "BTCB" and a.vehicle_coin == "BTC" and a.exec_venue == "cow"
