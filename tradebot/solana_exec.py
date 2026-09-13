"""Solana execution via Jupiter — non-custodial propose-and-sign (analog of CoW).

Same contract as tradebot.execution: this NEVER holds a key, signs, or broadcasts. It
turns an intended trade into an order proposal the UI hands to the user's Solana wallet
(Phantom / Backpack) to review and sign. Two safety layers before any signature:

  * KILL SWITCH (SolanaExecPolicy.enabled, default False) — until you turn it on every
    proposal is preview-only (ok=False) and no swap transaction is built.
  * HARD GUARDRAILS — token not on the allowlist, notional over the per-order cap, or
    slippage out of bounds are REFUSED (PolicyError), not clamped.

Amounts are an estimate from our price oracle; the BINDING quote comes from Jupiter at
build time (`quote()` / `build_swap_tx()`), which also returns the min-out floor, price
impact, and the route. `build_swap_tx` POSTs to Jupiter with the user's pubkey and
returns an UNSIGNED base64 transaction — the wallet signs it, funds move only then.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .execution import PolicyError                     # reuse the guardrail error type

_UA = "Mozilla/5.0 tradebot-soljup/0.1"
_JUP = "https://lite-api.jup.ag/swap/v1"               # free tier; swap into a Pro host later

# Vetted Solana token registry: SYMBOL -> (mint, decimals). Discovered tokens can be
# merged via register_tokens (never overriding a hand-vetted entry).
SOLANA_TOKENS: Dict[str, tuple] = {
    "USDC":  ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),
    "USDT":  ("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", 6),
    "SOL":   ("So11111111111111111111111111111111111111112", 9),   # wrapped SOL
    "CBBTC": ("cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij", 8),
    "JUP":   ("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 6),
}


def register_tokens(mapping: Dict[str, tuple]) -> None:
    for sym, (mint, dec) in mapping.items():
        SOLANA_TOKENS.setdefault(sym.upper(), (mint, int(dec)))


@dataclass
class SolanaExecPolicy:
    enabled: bool = False                 # KILL SWITCH — must be on to build a signable tx
    venue: str = "jupiter"
    max_notional_usd: float = 100.0
    max_slippage_bps: int = 50
    min_slippage_bps: int = 5
    allowed_tokens: tuple = ("USDC", "SOL", "CBBTC")


@dataclass
class SolanaOrderProposal:
    owner: str
    venue: str
    chain: str
    sell_symbol: str
    buy_symbol: str
    sell_mint: str
    buy_mint: str
    sell_amount: float
    sell_amount_raw: str
    price_usd: Dict[str, float]
    notional_usd: float
    est_buy_amount: float
    min_buy_amount: float
    slippage_bps: int
    price_impact_pct: Optional[float]
    route: List[str]
    expiry_ts: int
    summary: str
    ok: bool
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _http_json(url: str, data: Optional[bytes] = None, timeout: int = 20) -> dict:
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def quote(input_mint: str, output_mint: str, amount_raw: str, slippage_bps: int,
          fetch: Optional[Callable] = None) -> Optional[dict]:
    """Binding Jupiter quote for an exact-in swap. `fetch(url)` injectable for tests."""
    url = (f"{_JUP}/quote?inputMint={input_mint}&outputMint={output_mint}"
           f"&amount={amount_raw}&slippageBps={slippage_bps}")
    try:
        return (fetch or _http_json)(url)
    except Exception:  # noqa: BLE001
        return None


def build_swap_tx(quote_response: dict, owner_pubkey: str,
                  fetch: Optional[Callable] = None) -> Optional[str]:
    """POST the quote to Jupiter and return an UNSIGNED base64 swap transaction for the
    user's wallet to sign. Never signs or sends. `fetch(url, data)` injectable."""
    body = json.dumps({"quoteResponse": quote_response, "userPublicKey": owner_pubkey,
                       "wrapAndUnwrapSol": True, "dynamicComputeUnitLimit": True}).encode()
    try:
        res = (fetch or _http_json)(f"{_JUP}/swap", body)
        return res.get("swapTransaction")
    except Exception:  # noqa: BLE001
        return None


def _raw(amount: float, decimals: int) -> str:
    return str(int(round(amount * (10 ** decimals))))


def propose(owner: str, sell_symbol: str, buy_symbol: str, notional_usd: float,
            price_usd: Dict[str, float], policy: Optional[SolanaExecPolicy] = None,
            quote_fn: Optional[Callable] = None, ttl_seconds: int = 60) -> SolanaOrderProposal:
    """Build a compliant Solana order proposal (no signing). Raises PolicyError on a
    hard-guardrail violation. Enriches with a live Jupiter quote when `quote_fn` (or the
    default network) is available; otherwise estimates from the price oracle."""
    p = policy or SolanaExecPolicy()
    ss, bs = sell_symbol.upper(), buy_symbol.upper()

    if ss == bs:
        raise PolicyError("sell and buy tokens are the same")
    for sym in (ss, bs):
        if sym not in p.allowed_tokens:
            raise PolicyError(f"{sym} is not on the Solana execution allowlist")
        if sym not in SOLANA_TOKENS:
            raise PolicyError(f"{sym} has no known Solana mint")
        if price_usd.get(sym, 0) <= 0:
            raise PolicyError(f"no positive USD price for {sym}")
    if notional_usd <= 0:
        raise PolicyError("notional must be positive")
    if notional_usd > p.max_notional_usd:
        raise PolicyError(f"notional ${notional_usd:,.2f} exceeds the per-order cap "
                          f"${p.max_notional_usd:,.2f}")
    if not (p.min_slippage_bps <= p.max_slippage_bps <= 500):
        raise PolicyError("slippage bounds are misconfigured")
    if p.venue != "jupiter":
        raise PolicyError(f"unknown venue '{p.venue}'")

    sell_mint, sell_dec = SOLANA_TOKENS[ss]
    buy_mint, buy_dec = SOLANA_TOKENS[bs]
    slippage = p.max_slippage_bps
    sell_amount = notional_usd / price_usd[ss]
    sell_raw = _raw(sell_amount, sell_dec)
    est_buy = notional_usd / price_usd[bs]
    min_buy = est_buy * (1 - slippage / 10_000)
    price_impact: Optional[float] = None
    route: List[str] = []
    warnings: List[str] = []

    q = quote(sell_mint, buy_mint, sell_raw, slippage, fetch=quote_fn) if quote_fn is not False else None
    if q and q.get("outAmount"):
        est_buy = int(q["outAmount"]) / (10 ** buy_dec)
        thr = q.get("otherAmountThreshold")
        if thr:
            min_buy = int(thr) / (10 ** buy_dec)
        try:
            price_impact = float(q.get("priceImpactPct")) * 100
        except (TypeError, ValueError):
            price_impact = None
        route = [rp.get("swapInfo", {}).get("label", "?") for rp in q.get("routePlan", [])]
    else:
        warnings.append("no live Jupiter quote — amounts are an oracle estimate")

    if not p.enabled:
        warnings.append("execution kill switch is OFF — preview only; cannot be signed")
    if notional_usd > 0.9 * p.max_notional_usd:
        warnings.append("near the per-order cap")
    if price_impact is not None and price_impact > 1.0:
        warnings.append(f"high price impact {price_impact:.2f}%")

    summary = (f"Sell {sell_amount:.6f} {ss} (~${notional_usd:,.2f}) for ~{est_buy:.6f} {bs} "
               f"(min {min_buy:.6f} at {slippage/100:.2f}% slippage) via Jupiter on Solana"
               + (f" · route {'>'.join(route)}" if route else ""))

    return SolanaOrderProposal(
        owner=owner, venue=p.venue, chain="solana", sell_symbol=ss, buy_symbol=bs,
        sell_mint=sell_mint, buy_mint=buy_mint, sell_amount=round(sell_amount, 9),
        sell_amount_raw=sell_raw, price_usd={ss: price_usd[ss], bs: price_usd[bs]},
        notional_usd=round(notional_usd, 2), est_buy_amount=round(est_buy, 9),
        min_buy_amount=round(min_buy, 9), slippage_bps=slippage, price_impact_pct=price_impact,
        route=route, expiry_ts=int(time.time()) + ttl_seconds, summary=summary,
        ok=bool(p.enabled), warnings=warnings)
