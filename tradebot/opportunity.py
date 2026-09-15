"""Cross-chain opportunity scoring — where should the next bag be born?

When a bag reproduces, its child doesn't have to stay on the parent's chain. This
ranks the chains by how attractive each is RIGHT NOW, from honest, observable inputs:

  * executable    — can we actually trade there? (a chain we can't execute on scores 0)
  * regime_on     — is BTC's macro gate open? (risk-off => don't seed new bags anywhere)
  * breadth       — how many vetted, liquid tokens the chain's universe has (more real
                    opportunities to rotate through)
  * vehicle_trend — the chain's primary vehicle's own trend strength (0..1)
  * liquidity     — average pool depth (fills without slippage)

It is deliberately conservative: a chain must be BOTH executable AND in a confirmed
BTC bull to score above zero, so bags never spawn into a chain we can't trade or into
a macro downturn. Pure logic — no network, no keys; the runner feeds it live signals.

Honest limits: BTC's regime is market-wide, so it gates every chain equally; the real
differentiation is breadth + liquidity + the vehicle's trend. This ranks; it does not
promise the winner will outperform — it just sends new capital toward the strongest
*observable* conditions instead of a fixed chain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class OppConfig:
    w_breadth: float = 1.0
    w_trend: float = 1.0
    w_liquidity: float = 0.5
    require_executable: bool = True
    require_regime_on: bool = True


@dataclass
class ChainOpportunity:
    chain: str
    score: float
    tradeable: bool
    reason: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def score_chain(chain: str, *, executable: bool, regime_on: bool, universe_count: int = 0,
                vehicle_trend: float = 0.0, avg_liquidity_usd: float = 0.0,
                cfg: Optional[OppConfig] = None) -> ChainOpportunity:
    c = cfg or OppConfig()
    if c.require_executable and not executable:
        return ChainOpportunity(chain, 0.0, False, "not executable on this chain")
    if c.require_regime_on and not regime_on:
        return ChainOpportunity(chain, 0.0, False, "BTC regime off — macro risk-off")
    breadth = math.log1p(max(0, universe_count))
    liq = math.log1p(max(0.0, avg_liquidity_usd) / 1e6)
    trend = max(0.0, min(1.0, vehicle_trend))
    score = c.w_breadth * breadth + c.w_trend * trend + c.w_liquidity * liq
    reason = (f"breadth={universe_count} trend={trend:.2f} liq~${avg_liquidity_usd:,.0f}")
    return ChainOpportunity(chain, round(score, 4), True, reason)


def rank_chains(signals: Dict[str, dict], cfg: Optional[OppConfig] = None) -> List[ChainOpportunity]:
    """signals: {chain_id: {executable, regime_on, universe_count, vehicle_trend, avg_liquidity_usd}}."""
    out = [score_chain(cid, cfg=cfg, **sig) for cid, sig in signals.items()]
    out.sort(key=lambda o: o.score, reverse=True)
    return out


def best_chain(signals: Dict[str, dict], cfg: Optional[OppConfig] = None,
               default: str = "base") -> str:
    """The single most opportunistic *tradeable* chain, or `default` if none qualify."""
    ranked = rank_chains(signals, cfg)
    return ranked[0].chain if ranked and ranked[0].tradeable else default
