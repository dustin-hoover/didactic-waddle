"""Solana chain helpers + SPL token rug-screen (the non-EVM analog of safety.py).

Solana has no Etherscan, but the SPL mint account itself exposes the facts that
matter most to a trader, readable from any RPC (your Alchemy endpoint via
SOLANA_RPC_URL, or a public node):

  * FREEZE AUTHORITY — if set, that key can FREEZE your token account, i.e. stop you
    from ever selling. This is the Solana honeypot signature; the scariest single flag.
  * MINT AUTHORITY — if set, the supply can be inflated out from under you (dilution).
  * initialized / decimals / supply — basic sanity.

A token whose freeze AND mint authorities are both null is "immutable" in the ways
that can trap or dilute a holder — the Solana equivalent of a renounced owner. Known
majors (wSOL, USDC, USDT, cbBTC) legitimately keep authorities (Circle can freeze
USDC), so those short-circuit to a clean bill instead of being flagged.

This is READ-ONLY RPC — no keys, no signing. Reports expose .verdict / .risk_score /
.summary so they drop straight into universe.screen_vetted() like the EVM screen.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_UA = "Mozilla/5.0 tradebot-solana/0.1"
_PUBLIC_RPC = ["https://api.mainnet-beta.solana.com",
               "https://solana-rpc.publicnode.com"]

# Canonical Solana majors — keep authorities by design; short-circuit to a clean bill.
KNOWN_SAFE_SOLANA = {
    "So11111111111111111111111111111111111111112": "wSOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "cbBTC",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "wBTC",
}


def _rpc_urls() -> List[str]:
    env = os.environ.get("SOLANA_RPC_URL", "").strip()
    return ([env] if env else []) + _PUBLIC_RPC


def _rpc(method: str, params: list, timeout: int = 20) -> Optional[dict]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for url in _rpc_urls():
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
                if "result" in d:
                    return d["result"]
        except Exception:  # noqa: BLE001
            continue
    return None


@dataclass
class MintInfo:
    mint: str
    decimals: Optional[int] = None
    mint_authority: Optional[str] = None
    freeze_authority: Optional[str] = None
    supply: Optional[int] = None
    initialized: Optional[bool] = None


def mint_info(mint: str, rpc=None) -> Optional[MintInfo]:
    """Read an SPL mint account (jsonParsed). `rpc` injectable for tests."""
    call = rpc or (lambda m, p: _rpc(m, p))
    res = call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    try:
        info = res["value"]["data"]["parsed"]["info"]
    except (TypeError, KeyError):
        return None
    return MintInfo(
        mint=mint,
        decimals=info.get("decimals"),
        mint_authority=info.get("mintAuthority"),
        freeze_authority=info.get("freezeAuthority"),
        supply=int(info["supply"]) if str(info.get("supply", "")).isdigit() else None,
        initialized=info.get("isInitialized"))


@dataclass
class SolanaSafetyReport:
    mint: str
    name: Optional[str] = None
    freeze_authority: Optional[str] = None
    mint_authority: Optional[str] = None
    decimals: Optional[int] = None
    flags: List[str] = field(default_factory=list)
    notes: Dict[str, str] = field(default_factory=dict)
    _known: bool = False
    _readable: bool = True

    @property
    def risk_score(self) -> int:
        if self._known:
            return 0
        s = 0
        if self.freeze_authority:
            s += 60                       # can freeze your account (can't sell) — AVOID on its own
        if self.mint_authority:
            s += 25                       # supply can be inflated
        return min(s, 100)

    @property
    def verdict(self) -> str:
        if self._known:
            return "OK"
        if not self._readable:
            return "UNKNOWN"              # couldn't read the mint — never a clean bill
        s = self.risk_score
        return "AVOID" if s >= 60 else ("CAUTION" if s >= 25 else "OK")

    def summary(self) -> str:
        v = {True: "yes", False: "no", None: "?"}
        head = f"{self.name or '?'} {self.mint}  ->  {self.verdict}"
        head += "" if self.verdict == "UNKNOWN" else f" (risk {self.risk_score}/100)"
        line = (f"  freeze authority: {v[bool(self.freeze_authority) if self._readable else None]}"
                f"   mint authority: {v[bool(self.mint_authority) if self._readable else None]}")
        out = [head, line] + [f"  ⚠ {f}" for f in self.flags]
        out += [f"  · {k}: {m}" for k, m in self.notes.items()]
        return "\n".join(out)


def check(mint: str, rpc=None) -> SolanaSafetyReport:
    """Rug-screen an SPL token from its mint authorities. Drop-in for screen_vetted."""
    rep = SolanaSafetyReport(mint=mint)
    if mint in KNOWN_SAFE_SOLANA:
        rep.name = KNOWN_SAFE_SOLANA[mint]
        rep._known = True
        rep.notes["known"] = "canonical Solana major — short-circuited to a clean bill"
        return rep

    mi = mint_info(mint, rpc=rpc)
    if mi is None:
        rep._readable = False
        rep.notes["rpc"] = "could not read the mint account (RPC/unavailable) — not audited"
        return rep

    rep.decimals = mi.decimals
    rep.freeze_authority = mi.freeze_authority
    rep.mint_authority = mi.mint_authority
    if mi.initialized is False:
        rep._readable = True
        rep.flags.append("mint not initialized")
    if mi.freeze_authority:
        rep.flags.append("freeze authority set (owner can freeze your token account — can't sell)")
    if mi.mint_authority:
        rep.flags.append("mint authority set (supply can be inflated)")
    return rep
