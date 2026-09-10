"""Offline tests for the token safety / rug-screen (Etherscan free-tier facts)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tradebot.safety as sf


# A trimmed ABI resembling the real PEPE contract (blacklist + owner-gated rules).
_PEPE_ABI = (
    '[{"type":"function","name":"blacklist","inputs":[]},'
    '{"type":"function","name":"setRule","inputs":[]},'
    '{"type":"function","name":"burn","inputs":[]},'
    '{"type":"function","name":"transfer","inputs":[]}]'
)


def test_resolve_symbol_and_address():
    assert sf.resolve("PEPE") == sf.TOKENS["PEPE"]
    assert sf.resolve("pepe") == sf.TOKENS["PEPE"]
    a = "0x1111111111111111111111111111111111111111"
    assert sf.resolve(a) == a


def test_norm_rejects_garbage():
    for bad in ["", "0x123", "notanaddress", "0x" + "z" * 40]:
        try:
            sf._norm(bad)
            assert False, f"expected ValueError for {bad!r}"
        except ValueError:
            pass


def test_scan_capabilities_from_abi():
    flags = sf._scan_capabilities(_PEPE_ABI, "")
    joined = " ".join(flags).lower()
    assert "blacklist" in joined         # freeze-your-sells honeypot flag
    assert "paused" in joined or "gated" in joined  # setRule trading gate


def test_scan_capabilities_clean_abi():
    clean = ('[{"type":"function","name":"transfer","inputs":[]},'
             '{"type":"function","name":"approve","inputs":[]}]')
    assert sf._scan_capabilities(clean, "") == []


def test_known_safe_short_circuits(monkeypatch):
    # Should not touch the network for a canonical major.
    def boom(*a, **k):
        raise AssertionError("network should not be called for a KNOWN_SAFE token")
    monkeypatch.setattr(sf, "_etherscan", boom)
    monkeypatch.setattr(sf, "_eth_call", boom)
    rep = sf.check(sf.TOKENS["WETH"])
    assert rep.verified is True and rep.verdict == "OK" and rep.risk_score == 0


def test_no_api_key_reports_skip(monkeypatch):
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    # a non-major address so it doesn't short-circuit
    rep = sf.check("0x2222222222222222222222222222222222222222")
    assert rep.verified is None
    assert "etherscan" in rep.notes
    # Must NOT reassure when it couldn't audit.
    assert rep.verdict == "UNKNOWN"
    assert "risk" not in rep.summary().splitlines()[0]


def test_full_report_flags_and_score(monkeypatch):
    monkeypatch.setenv("ETHERSCAN_API_KEY", "dummy")

    def fake_etherscan(params):
        if params["action"] == "getsourcecode":
            return {"status": "1", "result": [{
                "SourceCode": "contract PepeToken { function blacklist() {} }",
                "ABI": _PEPE_ABI, "ContractName": "PepeToken", "Proxy": "0"}]}
        if params["action"] == "getcontractcreation":
            return {"status": "1", "result": [{"timestamp": str(int(__import__("time").time()) - 5 * 86400)}]}
        return None

    # owner() returns a non-zero owner -> not renounced
    monkeypatch.setattr(sf, "_etherscan", fake_etherscan)
    monkeypatch.setattr(sf, "_eth_call",
                        lambda to, data: "0x" + "0" * 24 + "3333333333333333333333333333333333333333")
    rep = sf.check("0x4444444444444444444444444444444444444444")
    assert rep.verified is True
    assert rep.owner_renounced is False
    assert rep.age_days is not None and rep.age_days <= 6
    assert rep.flags                      # blacklist + setRule detected
    assert rep.verdict in ("CAUTION", "AVOID")
    assert rep.risk_score > 0


def test_unverified_source_is_high_risk(monkeypatch):
    monkeypatch.setenv("ETHERSCAN_API_KEY", "dummy")
    monkeypatch.setattr(sf, "_etherscan", lambda p: (
        {"status": "1", "result": [{"SourceCode": "", "ABI": "Contract source code not verified",
                                     "ContractName": "", "Proxy": "0"}]}
        if p["action"] == "getsourcecode" else None))
    monkeypatch.setattr(sf, "_eth_call", lambda to, data: None)
    rep = sf.check("0x5555555555555555555555555555555555555555")
    assert rep.verified is False
    assert rep.risk_score >= 45           # unverified alone is a major flag


def test_gas_oracle_fallback(monkeypatch):
    monkeypatch.setattr(sf, "_etherscan", lambda p: None)   # no Etherscan
    # RPC fallback path
    import tradebot.safety as s

    class FakeResp:
        def __init__(self, d): self._d = d
        def read(self): return self._d
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(s.urllib.request, "urlopen",
                        lambda *a, **k: FakeResp(b'{"result":"0x3b9aca00"}'))  # 1 gwei
    g = sf.gas_oracle()
    assert abs(g["propose"] - 1.0) < 1e-6
