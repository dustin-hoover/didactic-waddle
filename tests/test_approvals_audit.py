"""Tests for scripts/approvals_audit.py — the 'zero unlimited approvals' gate (0.2)."""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HERE = os.path.dirname(os.path.abspath(__file__))
_AA = os.path.join(os.path.dirname(_HERE), "scripts", "approvals_audit.py")
_spec = importlib.util.spec_from_file_location("approvals_audit", _AA)
aa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(aa)


def test_classify_unlimited_detects_max_uint():
    assert aa.classify_allowance(aa.MAX_UINT256, 6) == "unlimited"
    assert aa.classify_allowance(1 << 255, 18) == "unlimited"


def test_classify_bounded_none_and_excessive():
    assert aa.classify_allowance(0, 6) == "none"
    # 100 USDC (6 decimals) bounded under a 1000-unit cap.
    assert aa.classify_allowance(100 * 10**6, 6, cap_units=1000) == "bounded"
    # 5000 USDC over a 1000-unit cap.
    assert aa.classify_allowance(5000 * 10**6, 6, cap_units=1000) == "excessive"
    # No cap given: a large-but-finite approval is merely 'bounded'.
    assert aa.classify_allowance(5000 * 10**6, 6) == "bounded"


def test_audit_ok_only_when_no_flags():
    good = [{"symbol": "USDC", "raw": 0, "decimals": 6, "spender": "0xsp"},
            {"symbol": "USDC", "raw": 100 * 10**6, "decimals": 6, "spender": "0xsp"}]
    assert aa.audit(good)["ok"] is True
    bad = good + [{"symbol": "WETH", "raw": aa.MAX_UINT256, "decimals": 18, "spender": "0xsp"}]
    rep = aa.audit(bad)
    assert rep["ok"] is False and rep["n_flagged"] == 1
    assert any(f["verdict"] == "unlimited" for f in rep["findings"])


def test_fetch_allowance_encodes_call_and_parses_hex():
    seen = {}
    def fake(rpc, to, data):
        seen["to"] = to; seen["data"] = data
        return 0x64                                   # 100
    val = aa.fetch_allowance("http://rpc", "0xToken", "0xOwnerAddr", "0xSpenderAddr", fetch=fake)
    assert val == 100
    assert seen["to"] == "0xToken"
    assert seen["data"].startswith(aa._ALLOWANCE_SELECTOR)
    assert len(seen["data"]) == len(aa._ALLOWANCE_SELECTOR) + 128   # two 32-byte args


def test_main_without_wallet_is_setup_gap_not_pass(monkeypatch):
    monkeypatch.delenv("TB_WALLET", raising=False)
    monkeypatch.delenv("ETH_RPC_URL", raising=False)
    assert aa.main(["approvals_audit.py"]) == 2       # not 0 — missing config is not a pass
