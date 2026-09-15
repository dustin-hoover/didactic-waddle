"""NEAR Intents — cross-chain execution via the 1Click API (read-only by default).

Why this exists: our doctrine allows a bag to *spawn into another chain when
conditions are opportunistic*, and to arbitrage. Today moving capital between
chains means stitching bridges together, and `tradebot/arbitrage.py` shows the
bridge cost/risk is usually what kills the trade. NEAR Intents is an
intent-based cross-chain settlement layer (the same family as CoW, which we
already sign against on EVM): you express "send X of asset A on chain 1, receive
asset B on chain 2," and a network of solvers competes to fill it — no bridge to
operate, one quote, one deposit address.

This module is the honest first step: a **quote adapter**. It NEVER signs, holds
a key, or moves funds. By default every quote is a `dry` quote — a price with no
deposit commitment — so we can measure the real cross-chain economics (net of
solver + withdraw + refund fees, read straight off the quote's USD in/out)
before deciding whether the spawn/arb is worth it. Live execution stays gated
behind a kill switch, exactly like `execution.py` and `solana_exec.py`.

Design notes kept deliberately honest:
  * Asset identifiers use NEP-141 form, e.g. arbitrum USDC is
    `nep141:arb-0xaf88d065e77c8cc2239327c5edb3a432268e5831.omft.near`. We can
    BUILD that string by formula for EVM tokens (verified against the documented
    example), but the canonical source is the live `GET /v0/tokens` list — the
    live path should resolve against it rather than trust the formula.
  * The 1Click `/quote` endpoint may require a JWT for non-dry (real) quotes.
    We pass `NEAR_INTENTS_JWT` as a bearer token when present; dry quotes for
    price discovery generally do not need it.
  * "Cost" is reported as amountInUsd - amountOutUsd (what the round actually
    costs you, all fees folded in), never a rosy mid-price.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

BASE_URL = "https://1click.chaindefuser.com"

# Our chain ids -> the 1Click `blockchain` enum value. Every one of these is in
# the live enum (near, eth, base, arb, btc, sol, avax, … , hood). Robinhood
# ("hood") and native BTC are listed too, so the same rail reaches them once we
# have verified vehicle assets there.
NEAR_BLOCKCHAIN: Dict[str, str] = {
    "base": "base", "solana": "sol", "arbitrum": "arb", "avalanche": "avax",
    "ethereum": "eth", "robinhood": "hood", "bitcoin": "btc",
}

# Vetted vehicle/stable assets per chain: (SYMBOL) -> (contract, decimals).
# Addresses mirror tradebot/execution.py + tradebot/solana_exec.py (all verified
# via CoinGecko). Used to build NEP-141 asset ids by formula for EVM chains and
# to size raw amounts. Solana entries are resolved against the live token list on
# the live path (native/SPL encoding is canonical there), never guessed blindly.
ASSET_TOKENS: Dict[Tuple[str, str], Tuple[str, int]] = {
    ("base", "USDC"):  ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
    ("base", "CBBTC"): ("0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf", 8),
    ("arbitrum", "USDC"): ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", 6),
    ("arbitrum", "WBTC"): ("0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f", 8),
    ("avalanche", "USDC"): ("0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e", 6),
    ("avalanche", "BTCB"): ("0x152b9d0fdc40c096757f570a51e494bd4b943e50", 8),
    ("solana", "USDC"): ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),
    ("solana", "SOL"):  ("So11111111111111111111111111111111111111112", 9),  # wSOL mint
}


# Even a dry (price-only) quote is validated by the API against a real
# destination-chain address. When the caller gives none (pure price discovery),
# we substitute a syntactically valid, chain-appropriate placeholder AND warn.
# A live (non-dry) quote never uses a placeholder — it must route to your address.
_PLACEHOLDER: Dict[str, str] = {
    "solana": "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH",   # valid base58 pubkey
    "_evm":   "0x0000000000000000000000000000000000000001",
}


def _placeholder(chain: str) -> str:
    return _PLACEHOLDER.get(chain, _PLACEHOLDER["_evm"])


class IntentsError(Exception):
    """A cross-chain quote breaks a hard guardrail and must not be built."""


@dataclass
class IntentsPolicy:
    enabled: bool = False              # KILL SWITCH — off => every quote is dry (price only)
    max_notional_usd: float = 100.0    # per-move cap (canary-sized by default)
    slippage_bps: int = 100            # 1% — sent as slippageTolerance
    deadline_seconds: int = 300        # how long the quote/route stays valid
    allowed_chains: Tuple[str, ...] = ("base", "solana", "arbitrum", "avalanche")


@dataclass
class CrossChainQuote:
    origin_chain: str
    dest_chain: str
    origin_asset: str                  # NEP-141 asset id
    dest_asset: str
    amount_in: float
    amount_in_usd: float
    amount_out: float                  # in destination-asset units
    amount_out_usd: float
    min_amount_out: float
    deposit_address: str               # where funds are sent to start the intent ("" for dry)
    time_estimate_s: float
    cost_usd: float                    # amountInUsd - amountOutUsd (all fees folded in)
    cost_bps: float                    # cost as a fraction of amount_in_usd
    dry: bool
    ok: bool                           # signable/executable? (kill switch on AND guardrails passed)
    summary: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def asset_id(chain: str, contract: str) -> str:
    """Build a NEP-141 asset id for an EVM token, e.g.
    asset_id("arbitrum", "0xaf88…5831") -> "nep141:arb-0xaf88…5831.omft.near".

    Matches the documented 1Click example exactly. For the live path, prefer
    `resolve_asset` against GET /v0/tokens — that is the canonical source and it
    also covers native/SPL forms this formula does not.
    """
    prefix = NEAR_BLOCKCHAIN.get(chain)
    if not prefix:
        raise IntentsError(f"chain '{chain}' has no NEAR Intents blockchain mapping")
    return f"nep141:{prefix}-{contract.lower()}.omft.near"


def resolve_asset(tokens: List[dict], chain: str, symbol: str) -> Optional[str]:
    """Find the canonical assetId for (chain, symbol) in a GET /v0/tokens list."""
    prefix = NEAR_BLOCKCHAIN.get(chain)
    if not prefix:
        return None
    sym = symbol.upper()
    for t in tokens or []:
        if str(t.get("blockchain", "")).lower() == prefix and str(t.get("symbol", "")).upper() == sym:
            return t.get("assetId")
    return None


def _raw(amount: float, decimals: int) -> str:
    return str(int(round(amount * (10 ** decimals))))


# A browser-ish User-Agent: the endpoint sits behind Cloudflare, which 403s the
# default python-urllib agent. (curl's own UA passes, so this is UA-gating, not auth.)
_UA = "Mozilla/5.0 (compatible; saatgut-bot/1.0; +https://github.com)"


def _ssl_ctx():
    import ssl
    ca = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
    return ssl.create_default_context(cafile=ca) if os.path.exists(ca) else None


def _default_post(path: str, body: dict, jwt: str = "") -> dict:
    """POST JSON to the 1Click API using urllib (proxy + custom CA aware)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE_URL + path, data=data, method="POST",
                                 headers={"content-type": "application/json", "user-agent": _UA,
                                          "accept": "application/json"})
    if jwt:
        req.add_header("authorization", f"Bearer {jwt}")
    with urllib.request.urlopen(req, timeout=20, context=_ssl_ctx()) as r:
        return json.loads(r.read().decode())


def _default_get(path: str, jwt: str = "") -> list:
    req = urllib.request.Request(BASE_URL + path, method="GET",
                                 headers={"user-agent": _UA, "accept": "application/json"})
    if jwt:
        req.add_header("authorization", f"Bearer {jwt}")
    with urllib.request.urlopen(req, timeout=20, context=_ssl_ctx()) as r:
        return json.loads(r.read().decode())


def fetch_tokens(get_fn: Optional[Callable[[str, str], list]] = None, jwt: str = "") -> List[dict]:
    """GET /v0/tokens — the canonical asset registry (assetId, blockchain, symbol, …)."""
    get = get_fn or _default_get
    return get("/v0/tokens", jwt)


_STABLES = {"USDC", "USDT", "DAI", "USDG"}


def bridge_cost_bps(asset: str, origin_chain: str, dest_chain: str,
                    notional_usd: float = 50.0, price_usd: Optional[Dict[str, float]] = None,
                    tokens: Optional[List[dict]] = None,
                    post_fn: Optional[Callable[[str, dict, str], dict]] = None,
                    jwt: Optional[str] = None) -> Optional[float]:
    """Live cost (bps) of RELOCATING `asset` from one chain to another via a dry quote.

    Same symbol both sides — this is the "move it across" cost, exactly what the
    arbitrage scanner needs in place of a guessed bridge fee. Returns None if it
    can't be measured (unknown asset on a leg, no price, network hiccup) so callers
    fall back to their static assumption instead of dropping the opportunity.

    Designed to be handed to arbitrage.find_arbitrage as
    `bridge_bps_fn=lambda a, oc, dc: bridge_cost_bps(a, oc, dc, price_usd=..., tokens=...)`.
    """
    sym = asset.upper()
    px = dict(price_usd or {})
    if sym not in px:
        if sym in _STABLES:
            px[sym] = 1.0
        else:
            return None
    try:
        q = quote(origin_chain, dest_chain, sym, sym, notional_usd, price_usd=px,
                  tokens=tokens, post_fn=post_fn, jwt=jwt)
        return q.cost_bps
    except Exception:  # noqa: BLE001
        return None


def _fnum(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def quote(origin_chain: str, dest_chain: str, origin_symbol: str, dest_symbol: str,
          notional_usd: float, recipient: str = "", refund_to: str = "",
          policy: Optional[IntentsPolicy] = None, price_usd: Optional[Dict[str, float]] = None,
          tokens: Optional[List[dict]] = None,
          post_fn: Optional[Callable[[str, dict, str], dict]] = None,
          jwt: Optional[str] = None) -> CrossChainQuote:
    """Fetch a cross-chain quote (dry by default) and report honest net economics.

    Raises IntentsError on a hard-guardrail violation. The returned quote's `ok`
    is True only when the kill switch is on AND every rule passes; otherwise the
    request is forced `dry` and `ok` is False (price discovery, nothing signable).
    """
    p = policy or IntentsPolicy()
    oc, dc = origin_chain.lower(), dest_chain.lower()
    os_, ds = origin_symbol.upper(), dest_symbol.upper()

    # ---- hard guardrails (refuse, don't clamp) ----
    for ch in (oc, dc):
        if ch not in p.allowed_chains:
            raise IntentsError(f"chain '{ch}' is not on the NEAR Intents allowlist")
    if oc == dc and os_ == ds:
        raise IntentsError("origin and destination asset are identical — nothing to route")
    if notional_usd <= 0:
        raise IntentsError("notional must be positive")
    if notional_usd > p.max_notional_usd:
        raise IntentsError(f"notional ${notional_usd:,.2f} exceeds the per-move cap "
                           f"${p.max_notional_usd:,.2f}")
    if (oc, os_) not in ASSET_TOKENS:
        raise IntentsError(f"no known {os_} asset on '{oc}'")
    if (dc, ds) not in ASSET_TOKENS:
        raise IntentsError(f"no known {ds} asset on '{dc}'")

    # Resolve asset ids: canonical list first, formula fallback for EVM tokens.
    warnings: List[str] = []
    o_addr, o_dec = ASSET_TOKENS[(oc, os_)]
    origin_asset = resolve_asset(tokens or [], oc, os_) or asset_id(oc, o_addr)
    dest_asset = resolve_asset(tokens or [], dc, ds) or asset_id(dc, ASSET_TOKENS[(dc, ds)][0])
    if not tokens:
        warnings.append("asset ids built by formula — verify against GET /v0/tokens before live use")

    # Size the input in smallest units from a USD notional.
    px = (price_usd or {}).get(os_, 0.0)
    if px <= 0:
        raise IntentsError(f"no positive USD price for {os_} to size the input amount")
    amount_in = notional_usd / px
    amount_raw = _raw(amount_in, o_dec)

    dry = not p.enabled          # kill switch OFF => price-only, never a real route
    if dry:
        warnings.append("kill switch is OFF — dry quote (price only), cannot be executed")

    # Recipient (on dest chain) and refundTo (on origin chain) must be valid. A live
    # quote refuses to route to a placeholder; a dry quote may fill them in to discover a price.
    dest_recipient = recipient
    origin_refund = refund_to or recipient
    if not dest_recipient:
        if not dry:
            raise IntentsError("a live quote needs a real destination-chain recipient address")
        dest_recipient = _placeholder(dc)
        warnings.append("no recipient given — using a placeholder for the dry quote only")
    if not origin_refund:
        origin_refund = _placeholder(oc) if dry else dest_recipient

    deadline = (datetime.now(timezone.utc) + timedelta(seconds=p.deadline_seconds)) \
        .isoformat(timespec="seconds").replace("+00:00", "Z")
    body = {
        "dry": dry,
        "swapType": "EXACT_INPUT",
        "slippageTolerance": int(p.slippage_bps),
        "originAsset": origin_asset,
        "depositType": "ORIGIN_CHAIN",
        "destinationAsset": dest_asset,
        "amount": amount_raw,
        "refundTo": origin_refund,
        "refundType": "ORIGIN_CHAIN",
        "recipient": dest_recipient,
        "recipientType": "DESTINATION_CHAIN",
        "deadline": deadline,
    }

    post = post_fn or _default_post
    token = (jwt if jwt is not None else os.environ.get("NEAR_INTENTS_JWT", "")).strip()
    resp = post("/v0/quote", body, token) or {}
    q = resp.get("quote", resp) or {}

    _, d_dec = ASSET_TOKENS[(dc, ds)]
    amt_in = _fnum(q.get("amountInFormatted")) or amount_in
    amt_out = _fnum(q.get("amountOutFormatted"))
    min_out = _fnum(q.get("minAmountOutFormatted")) or (
        _fnum(q.get("minAmountOut")) / (10 ** d_dec) if q.get("minAmountOut") else 0.0)
    in_usd = _fnum(q.get("amountInUsd")) or notional_usd
    out_usd = _fnum(q.get("amountOutUsd"))
    cost_usd = in_usd - out_usd if out_usd else 0.0
    cost_bps = (cost_usd / in_usd * 10_000) if in_usd else 0.0
    if out_usd <= 0:                 # don't let a missing output price read as "free"
        warnings.append("output USD not returned — cost figures unavailable, not zero")

    ok = bool(p.enabled) and not dry and bool(q.get("depositAddress"))
    summary = (f"{amt_in:.6f} {os_}@{oc} -> {amt_out:.6f} {ds}@{dc} "
               f"(min {min_out:.6f}); cost ~${cost_usd:,.2f} ({cost_bps:.0f} bps), "
               f"~{_fnum(q.get('timeEstimate')):.0f}s via NEAR Intents"
               + ("  [DRY]" if dry else ""))

    return CrossChainQuote(
        origin_chain=oc, dest_chain=dc, origin_asset=origin_asset, dest_asset=dest_asset,
        amount_in=round(amt_in, 8), amount_in_usd=round(in_usd, 2),
        amount_out=round(amt_out, 8), amount_out_usd=round(out_usd, 2),
        min_amount_out=round(min_out, 8), deposit_address=str(q.get("depositAddress", "")),
        time_estimate_s=_fnum(q.get("timeEstimate")), cost_usd=round(cost_usd, 4),
        cost_bps=round(cost_bps, 2), dry=dry, ok=ok, summary=summary, warnings=warnings)
