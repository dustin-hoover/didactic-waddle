"""Propose-and-sign execution — non-custodial by construction.

This layer NEVER holds a key, signs, or broadcasts. It turns a bag's intended
trade into an **order proposal**: a fully specified, human-readable plan that the
UI hands to your own wallet (MetaMask / Coinbase / Base) to review and sign. Funds
only ever move when YOU approve in your wallet.

Two things keep this safe before a signature is ever requested:
  * A KILL SWITCH (`ExecutionPolicy.enabled`, default False). Until you turn it on,
    every proposal is preview-only (`ok=False`) and cannot be signed.
  * HARD GUARDRAILS. A proposal that breaks a rule — token not on the allowlist,
    notional over the per-order cap, slippage outside bounds — is refused
    (`PolicyError`), not clamped silently.

The proposal's amounts are an ESTIMATE from our own price oracle; the binding quote
comes from the venue (CoW / 1inch) at signing time. Start tiny: the default cap is
canary-sized ($100) and the kill switch is off.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Minimal, audited token registry per chain: symbol -> (address, decimals).
TOKENS: Dict[str, Dict[str, tuple]] = {
    "ethereum": {
        "USDC": ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
        "USDT": ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
        "DAI":  ("0x6b175474e89094c44da98b954eedeac495271d0f", 18),
        "WETH": ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
        "WBTC": ("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 8),
    },
    "base": {
        "USDC":  ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
        "WETH":  ("0x4200000000000000000000000000000000000006", 18),
        # cbBTC (key upper-cased like the rest) — Coinbase Wrapped BTC, Base-native,
        # ~$450M/day volume: the BTC vehicle the regime gate is validated on. Verified
        # via CoinGecko, 8 decimals.
        "CBBTC": ("0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf", 8),
    },
}

def register_tokens(chain: str, mapping: Dict[str, tuple]) -> None:
    """Merge a vetted token set (from tradebot.universe) into the registry at runtime.

    Keys are upper-cased to match the proposal layer's lookup. Existing hand-vetted
    entries win on conflict, so a discovered token can never silently override a
    known-good address. Values are (address, decimals).
    """
    reg = TOKENS.setdefault(chain, {})
    for sym, (addr, dec) in mapping.items():
        key = sym.upper()
        if key not in reg:
            reg[key] = (addr, int(dec))


# Where a one-time ERC-20 approval must point for each venue (the signing layer
# uses this later; recorded here so the whole execution contract lives in one file).
VENUE_SPENDER = {
    "ethereum": {"cow": "0xc92e8bdf79f0507f65a392b0ab4667716bfe0110",     # CoW vault relayer
                 "1inch": "0x111111125421ca6dc452d289314280a0f8842a65"},  # 1inch router v6
    "base": {"cow": "0xc92e8bdf79f0507f65a392b0ab4667716bfe0110",
             "1inch": "0x111111125421ca6dc452d289314280a0f8842a65"},
}


class PolicyError(Exception):
    """A proposed order breaks a hard guardrail and must not be built."""


@dataclass
class ExecutionPolicy:
    enabled: bool = False              # KILL SWITCH — must be explicitly turned on to sign
    venue: str = "cow"                 # "cow" (gasless, MEV-protected) | "1inch"
    chain: str = "ethereum"            # "ethereum" | "base"
    max_notional_usd: float = 100.0    # per-order cap (canary-sized by default)
    max_slippage_bps: int = 50         # 0.5% — proposals above this are refused
    min_slippage_bps: int = 5          # guard against 0-slippage self-harm
    allowed_tokens: tuple = ("USDC", "USDT", "DAI", "WETH", "WBTC")


@dataclass
class OrderProposal:
    bag_id: str
    wallet: str
    chain: str
    venue: str
    sell_symbol: str
    buy_symbol: str
    sell_token: str
    buy_token: str
    spender: str                        # approval target for this venue/chain
    sell_amount: float
    sell_amount_raw: str                # integer base units, as a string (may exceed JS ints)
    price_usd: Dict[str, float]         # {symbol: usd} used for the estimate
    notional_usd: float
    est_buy_amount: float
    min_buy_amount: float
    min_buy_raw: str
    slippage_bps: int
    expiry_ts: int
    summary: str
    ok: bool                            # signable? (kill switch on AND guardrails pass)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def _raw(amount: float, decimals: int) -> str:
    return str(int(round(amount * (10 ** decimals))))


def propose(bag_id: str, wallet: str, sell_symbol: str, buy_symbol: str,
            notional_usd: float, price_usd: Dict[str, float],
            policy: Optional[ExecutionPolicy] = None, ttl_seconds: int = 1200) -> OrderProposal:
    """Build a compliant, human-readable order proposal (no signing, no broadcast).

    Raises PolicyError on a hard-guardrail violation. Returns a proposal whose
    ``ok`` is True only when the kill switch is on AND every rule passes.
    """
    p = policy or ExecutionPolicy()
    chain = p.chain
    reg = TOKENS.get(chain, {})
    ss, bs = sell_symbol.upper(), buy_symbol.upper()

    # ---- hard guardrails (refuse, don't clamp) ----
    if ss == bs:
        raise PolicyError("sell and buy tokens are the same")
    for sym in (ss, bs):
        if sym not in p.allowed_tokens:
            raise PolicyError(f"{sym} is not on the execution allowlist")
        if sym not in reg:
            raise PolicyError(f"{sym} has no known address on chain '{chain}'")
    if notional_usd <= 0:
        raise PolicyError("notional must be positive")
    if notional_usd > p.max_notional_usd:
        raise PolicyError(f"notional ${notional_usd:,.2f} exceeds the per-order cap "
                          f"${p.max_notional_usd:,.2f}")
    if not (p.min_slippage_bps <= p.max_slippage_bps <= 500):
        raise PolicyError("slippage bounds are misconfigured")
    for sym in (ss, bs):
        if price_usd.get(sym, 0) <= 0:
            raise PolicyError(f"no positive USD price for {sym}")
    if p.venue not in ("cow", "1inch"):
        raise PolicyError(f"unknown venue '{p.venue}'")

    sell_addr, sell_dec = reg[ss]
    buy_addr, buy_dec = reg[bs]
    slippage = p.max_slippage_bps
    sell_amount = notional_usd / price_usd[ss]
    est_buy = notional_usd / price_usd[bs]
    min_buy = est_buy * (1 - slippage / 10_000)

    warnings: List[str] = []
    if not p.enabled:
        warnings.append("execution kill switch is OFF — this is a preview; it cannot be signed")
    if notional_usd > 0.9 * p.max_notional_usd:
        warnings.append("near the per-order cap")

    spender = VENUE_SPENDER.get(chain, {}).get(p.venue, "")
    summary = (f"Sell {sell_amount:.6f} {ss} (~${notional_usd:,.2f}) for ~{est_buy:.6f} {bs} "
               f"(min {min_buy:.6f} at {slippage/100:.2f}% slippage) via {p.venue} on {chain}")

    return OrderProposal(
        bag_id=bag_id, wallet=wallet, chain=chain, venue=p.venue,
        sell_symbol=ss, buy_symbol=bs, sell_token=sell_addr, buy_token=buy_addr,
        spender=spender, sell_amount=round(sell_amount, 8), sell_amount_raw=_raw(sell_amount, sell_dec),
        price_usd={ss: price_usd[ss], bs: price_usd[bs]}, notional_usd=round(notional_usd, 2),
        est_buy_amount=round(est_buy, 8), min_buy_amount=round(min_buy, 8),
        min_buy_raw=_raw(min_buy, buy_dec), slippage_bps=slippage,
        expiry_ts=int(time.time()) + ttl_seconds, summary=summary,
        ok=bool(p.enabled), warnings=warnings)


def proposal_for_signal(bag_id: str, wallet: str, target_exposure: float, current_exposure: float,
                        equity_usd: float, base_symbol: str, price_usd: Dict[str, float],
                        policy: Optional[ExecutionPolicy] = None,
                        stable: str = "USDC") -> Optional[OrderProposal]:
    """Translate a bag's model decision into an order proposal.

    Long/flat spot: increasing exposure buys the base with the stable; decreasing
    sells the base back to the stable. Returns None when the move is negligible.
    """
    p = policy or ExecutionPolicy()
    delta = target_exposure - current_exposure           # fraction of equity to shift
    notional = abs(delta) * equity_usd
    if notional < 1.0:                                    # dust / no-op
        return None
    notional = min(notional, p.max_notional_usd)          # respect the cap up front
    if delta > 0:
        return propose(bag_id, wallet, stable, base_symbol, notional, price_usd, p)
    return propose(bag_id, wallet, base_symbol, stable, notional, price_usd, p)
