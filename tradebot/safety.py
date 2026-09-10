"""Token safety / rug-screen from on-chain contract facts (Etherscan free tier).

Before you ever hold a token, the cheapest edge is knowing what the contract can
DO to you. Etherscan's free tier exposes the verified source + ABI, the creation
record, and gas — enough to flag the classic honeypot/rug patterns:

  * UNVERIFIED source           -> you can't audit it; treat as opaque.
  * blacklist / blocklist       -> owner can freeze YOUR ability to sell (honeypot).
  * mutable fee / tax setters    -> owner can raise sell tax toward 100% (honeypot).
  * owner-only mint              -> supply can be diluted out from under you.
  * pause / trading gates        -> setRule / maxTx / maxHolding can trap holders.
  * upgradeable PROXY            -> the logic you audited can be swapped later.
  * owner NOT renounced          -> the privileged powers above are live, not dead.
  * very new contract            -> little history, higher rug base-rate.

This is READ-ONLY public chain data — no keys, no signing. It informs; it does not
auto-trade. Majors (BTC/ETH via canonical contracts) will show benign; the screen
earns its keep on the long tail of new tokens.

Honest limits: source-pattern matching flags CAPABILITY, not intent — a benign
project can have a pauser; a scam can hide logic in a proxy or an external call.
Top-holder concentration (a strong rug signal) is Etherscan Pro-gated, so it is
NOT part of the free-tier screen. Use this as one input, never the only one.

Key: reads ``ETHERSCAN_API_KEY`` from the environment (a repo secret for the
autonomous runner). Without it, contract calls are skipped and the report says so.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_UA = "Mozilla/5.0 tradebot-safety/0.1"
_ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"
_RPCS = ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"]
_ZERO = "0x0000000000000000000000000000000000000000"
_DEAD = "0x000000000000000000000000000000000000dead"

# Well-known majors: canonical, audited, immutable enough that the pattern scan
# would only produce noise. We short-circuit these to a clean bill.
KNOWN_SAFE = {
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK",
}

# Capability patterns matched against ABI function names (authoritative) and,
# as a fallback, the raw verified source. Each: (flag key, human note, regex).
_PATTERNS = [
    ("blacklist", "owner can blacklist addresses (can freeze your sells — honeypot)",
     re.compile(r"blacklist|blocklist|_isblacklisted|denylist|addbot|setbots?\b", re.I)),
    ("mutable_fee", "owner can change fees/taxes (can raise sell tax — honeypot)",
     re.compile(r"set(fee|fees|tax|taxes|sellfee|buyfee|maxfee)\b|updatefee", re.I)),
    ("owner_mint", "owner-callable mint (supply can be diluted)",
     re.compile(r"\bmint\b", re.I)),
    ("pausable", "trading can be paused/gated (pause / setRule / maxTx / maxHolding)",
     re.compile(r"\bpause\b|setrule|enabletrading|maxtx|maxwallet|maxholding|tradingactive", re.I)),
]


def _http(url: str, tries: int = 3, timeout: int = 25):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.8 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def _etherscan(params: Dict[str, str]) -> Optional[dict]:
    key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
    if not key:
        return None
    q = dict(params)
    q.setdefault("chainid", "1")
    q["apikey"] = key
    try:
        return _http(f"{_ETHERSCAN_V2}?{urllib.parse.urlencode(q)}")
    except Exception:  # noqa: BLE001
        return None


def _eth_call(to: str, data: str) -> Optional[str]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": data}, "latest"]}).encode()
    for url in _RPCS:
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
                if d.get("result"):
                    return d["result"]
        except Exception:  # noqa: BLE001
            continue
    return None


@dataclass
class SafetyReport:
    address: str
    name: Optional[str] = None
    verified: Optional[bool] = None          # source published on Etherscan?
    is_proxy: Optional[bool] = None          # upgradeable logic?
    owner_renounced: Optional[bool] = None   # owner() == 0x0/dead ?
    owner: Optional[str] = None
    age_days: Optional[int] = None
    flags: List[str] = field(default_factory=list)      # capability warnings
    notes: Dict[str, str] = field(default_factory=dict)  # what couldn't be checked

    @property
    def risk_score(self) -> int:
        """Coarse 0 (clean) .. 100 (avoid). Capability flags + structural risk."""
        s = 0
        if self.verified is False:
            s += 45                          # opaque code is the biggest single flag
        s += 12 * len(self.flags)            # each live capability
        if self.is_proxy:
            s += 20                          # logic can be swapped
        if self.owner_renounced is False and self.flags:
            s += 15                          # powers are live, not dead
        if self.age_days is not None and self.age_days < 30:
            s += 10                          # very new
        return min(s, 100)

    @property
    def verdict(self) -> str:
        # Never reassure on missing data: if we couldn't even confirm the source
        # (no key / rate limit / non-contract), the honest answer is UNKNOWN.
        if self.verified is None:
            return "UNKNOWN"
        s = self.risk_score
        return "AVOID" if s >= 60 else ("CAUTION" if s >= 25 else "OK")

    def summary(self) -> str:
        score = "" if self.verdict == "UNKNOWN" else f" (risk {self.risk_score}/100)"
        lines = [f"{self.name or '?'} {self.address}  ->  {self.verdict}{score}"]
        v = {True: "yes", False: "NO", None: "?"}
        lines.append(f"  verified source: {v[self.verified]}   proxy(upgradeable): {v[self.is_proxy]}"
                     f"   owner renounced: {v[self.owner_renounced]}"
                     + (f"   age: {self.age_days}d" if self.age_days is not None else ""))
        for f in self.flags:
            lines.append(f"  ⚠ {f}")
        for k, msg in self.notes.items():
            lines.append(f"  · {k}: {msg}")
        return "\n".join(lines)


# Small symbol -> mainnet address book so the CLI can take --symbol PEPE, etc.
# (Majors resolve into KNOWN_SAFE and short-circuit; the long tail gets scanned.)
TOKENS = {
    "WETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "WBTC": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    "DAI": "0x6b175474e89094c44da98b954eedeac495271d0f",
    "LINK": "0x514910771af9ca656af840dff83e8264ecf986ca",
    "UNI": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
    "AAVE": "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
    "PEPE": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
    "SHIB": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce",
    "AMPL": "0xd46ba6d942050d489dbd938a2c909a5d5039a161",
    "SPOT": "0xc1f33e0cf7e40a67375007104b929e49a581bafe",
}


def resolve(symbol_or_addr: str) -> str:
    """Accept a 0x… address or a known symbol; return a normalized address."""
    s = (symbol_or_addr or "").strip()
    if s.upper() in TOKENS:
        return TOKENS[s.upper()]
    return _norm(s)


def _norm(addr: str) -> str:
    a = (addr or "").strip().lower()
    if not re.fullmatch(r"0x[0-9a-f]{40}", a):
        raise ValueError("expected a 0x… 40-hex-char contract address, or a known symbol")
    return a


def _scan_capabilities(abi_json: str, source: str) -> List[str]:
    """Prefer ABI function names (authoritative); fall back to raw source text."""
    names = ""
    try:
        for item in json.loads(abi_json) if abi_json and abi_json[0] == "[" else []:
            if item.get("type") == "function" and item.get("name"):
                names += item["name"] + "\n"
    except Exception:  # noqa: BLE001
        names = ""
    haystack = names if names else source
    flags: List[str] = []
    for _key, note, rx in _PATTERNS:
        if rx.search(haystack):
            flags.append(note)
    return flags


def check(address: str) -> SafetyReport:
    """Build a safety report for an ERC-20/contract address from free-tier data."""
    addr = _norm(address)
    rep = SafetyReport(address=addr)

    if addr in KNOWN_SAFE:
        rep.name = KNOWN_SAFE[addr]
        rep.verified = True
        rep.is_proxy = False
        rep.owner_renounced = True
        rep.notes["known"] = "canonical major — short-circuited to a clean bill"
        return rep

    if not os.environ.get("ETHERSCAN_API_KEY", "").strip():
        rep.notes["etherscan"] = "no ETHERSCAN_API_KEY set — contract audit skipped"
        return rep

    src = _etherscan({"module": "contract", "action": "getsourcecode", "address": addr})
    if src and src.get("status") == "1" and src.get("result"):
        row = src["result"][0]
        source_code = row.get("SourceCode") or ""
        rep.name = row.get("ContractName") or None
        rep.verified = bool(source_code.strip())
        rep.is_proxy = str(row.get("Proxy", "0")) == "1"
        if rep.verified:
            rep.flags = _scan_capabilities(row.get("ABI") or "", source_code)
        else:
            rep.notes["source"] = "contract source is NOT verified — cannot audit behavior"
    else:
        rep.notes["source"] = "Etherscan returned no source (bad key, rate limit, or non-contract)"

    # Ownership: owner() (0x8da5cb5b). 0x0 / dead == renounced.
    owner_res = _eth_call(addr, "0x8da5cb5b")
    if owner_res and len(owner_res) >= 42:
        owner = "0x" + owner_res[-40:]
        rep.owner = owner
        rep.owner_renounced = owner.lower() in (_ZERO, _DEAD)
    else:
        rep.notes["owner"] = "no owner() function found (may be ownerless by design)"

    # Age from the creation record.
    created = _etherscan({"module": "contract", "action": "getcontractcreation",
                          "contractaddresses": addr})
    if created and created.get("status") == "1" and created.get("result"):
        row = created["result"][0]
        ts = row.get("timestamp") or row.get("blockTimestamp")
        if ts:
            try:
                rep.age_days = int((time.time() - int(ts)) / 86400)
            except (TypeError, ValueError):
                pass
    return rep


def gas_oracle() -> Dict[str, Optional[float]]:
    """Current gas from Etherscan's gas tracker; falls back to RPC eth_gasPrice.

    Returns gwei figures: {safe, propose, fast, base}. High gas often coincides
    with frothy/congested conditions — useful context, not a trade trigger.
    """
    out: Dict[str, Optional[float]] = {"safe": None, "propose": None, "fast": None, "base": None}
    d = _etherscan({"module": "gastracker", "action": "gasoracle"})
    if d and d.get("status") == "1" and isinstance(d.get("result"), dict):
        r = d["result"]
        _f = lambda k: float(r[k]) if r.get(k) not in (None, "") else None
        out.update(safe=_f("SafeGasPrice"), propose=_f("ProposeGasPrice"),
                   fast=_f("FastGasPrice"), base=_f("suggestBaseFee"))
        return out
    # Fallback: raw RPC gas price (no key needed).
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_gasPrice", "params": []}).encode()
    for url in _RPCS:
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                out["propose"] = int(json.loads(r.read())["result"], 16) / 1e9
                break
        except Exception:  # noqa: BLE001
            continue
    return out
