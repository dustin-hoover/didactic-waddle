#!/usr/bin/env python3
"""approvals_audit.py — flag unlimited / excessive ERC-20 approvals (Phase 0.2).

A non-custodial wallet is only as safe as the token APPROVALS it has granted. An
"unlimited" approval (allowance == MAX_UINT256, the MetaMask default) lets a spender
move your entire balance of that token forever — exactly the blast radius we refuse.
This read-only audit reads the on-chain allowance of each (token, spender) pair and
reports anything that isn't a small, bounded, exact-amount approval.

It NEVER signs or sends — it only calls `allowance(owner, spender)` (eth_call). The
pure core (`classify_allowance` / `audit`) is offline-testable; the network wrapper
is injectable. Exit code is non-zero if any unlimited/excessive approval is found, so
CI / a pre-live check can gate on "zero unlimited approvals".

Usage:
    TB_WALLET=0x... ETH_RPC_URL=https://... python3 scripts/approvals_audit.py
    python3 scripts/approvals_audit.py --chain base --wallet 0x... --rpc https://...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.execution import TOKENS, VENUE_SPENDER  # noqa: E402

MAX_UINT256 = (1 << 256) - 1
# Anything in the top half of the uint256 range is "unlimited" by intent (covers
# MAX_UINT256 and the common 2**255 variants). No honest exact-amount approval is here.
UNLIMITED_FLOOR = 1 << 255
_ALLOWANCE_SELECTOR = "0xdd62ed3e"           # allowance(address,address)


def classify_allowance(raw: int, decimals: int, cap_units: float | None = None) -> str:
    """Classify one allowance. Pure.

    'unlimited'  -> top-half of uint256 (MAX_UINT256 / 2**255 style infinite approval)
    'excessive'  -> bounded, but above cap_units token units (when a cap is given)
    'none'       -> zero allowance (ideal between trades)
    'bounded'    -> a finite approval within the cap
    """
    if raw >= UNLIMITED_FLOOR:
        return "unlimited"
    if raw == 0:
        return "none"
    if cap_units is not None and decimals >= 0 and (raw / (10 ** decimals)) > cap_units:
        return "excessive"
    return "bounded"


def audit(rows: list[dict], cap_units: float | None = None) -> dict:
    """Classify a list of {token, spender, raw, decimals} rows.

    Returns {ok, n, findings}. ok is True only when NO approval is unlimited or
    excessive — that is the "zero unlimited approvals" acceptance bar."""
    findings = []
    bad = 0
    for r in rows:
        verdict = classify_allowance(int(r["raw"]), int(r.get("decimals", 18)), cap_units)
        row = {"token": r.get("token"), "symbol": r.get("symbol"),
               "spender": r.get("spender"), "raw": str(r["raw"]), "verdict": verdict}
        if verdict in ("unlimited", "excessive"):
            bad += 1
        findings.append(row)
    return {"ok": bad == 0, "n": len(rows), "n_flagged": bad, "findings": findings}


def _eth_call(rpc_url: str, to: str, data: str) -> int:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": data}, "latest"]}).encode()
    req = urllib.request.Request(rpc_url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read())
    hexval = (res.get("result") or "0x0")
    return int(hexval, 16) if hexval not in ("0x", "0x0", "") else 0


def fetch_allowance(rpc_url: str, token: str, owner: str, spender: str, fetch=None) -> int:
    """On-chain allowance(owner, spender) for an ERC-20. `fetch(rpc,to,data)` injectable."""
    def _pad(addr: str) -> str:
        return addr.lower().replace("0x", "").rjust(64, "0")
    data = _ALLOWANCE_SELECTOR + _pad(owner) + _pad(spender)
    return (fetch or _eth_call)(rpc_url, token, data)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chain", default=os.environ.get("TB_CHAIN", "base"))
    ap.add_argument("--wallet", default=os.environ.get("TB_WALLET", ""))
    ap.add_argument("--rpc", default=os.environ.get("ETH_RPC_URL", ""))
    ap.add_argument("--cap-units", type=float, default=None,
                    help="flag bounded approvals above this many token units as excessive")
    args = ap.parse_args(argv[1:])

    if not args.wallet or not args.rpc:
        print("approvals_audit: set --wallet and --rpc (or TB_WALLET / ETH_RPC_URL).")
        print("  Nothing audited — this is a setup gap, not a pass.", file=sys.stderr)
        return 2

    reg = TOKENS.get(args.chain, {})
    spenders = VENUE_SPENDER.get(args.chain, {})
    if not reg or not spenders:
        print(f"approvals_audit: no tokens/spenders known for chain '{args.chain}'.")
        return 2

    rows = []
    for sym, (addr, dec) in reg.items():
        for venue, spender in spenders.items():
            try:
                raw = fetch_allowance(args.rpc, addr, args.wallet, spender)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {sym} -> {venue}: allowance read failed ({str(e)[:60]})")
                continue
            rows.append({"token": addr, "symbol": sym, "spender": spender,
                         "raw": raw, "decimals": dec})

    rep = audit(rows, cap_units=args.cap_units)
    print(f"Approvals audit — chain {args.chain}, wallet {args.wallet[:10]}…  "
          f"({rep['n']} pairs, {rep['n_flagged']} flagged)")
    for f in rep["findings"]:
        mark = "OK " if f["verdict"] in ("none", "bounded") else "!! "
        print(f"  {mark}{f['symbol']:<6} -> {f['spender'][:10]}…  {f['verdict']}")
    if rep["ok"]:
        print("PASS: zero unlimited/excessive approvals.")
        return 0
    print("FAIL: revoke the flagged approvals (set allowance to 0, then approve exact amounts).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
