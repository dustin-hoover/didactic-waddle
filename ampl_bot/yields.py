"""Staking / yield helpers.

Ampleforth-adjacent yield has historically come from things like the Geyser
liquidity-mining program and providing liquidity in AMPL pairs. Because APRs and
programs change constantly, this module does NOT hard-code current rates or
auto-deposit anywhere. It provides transparent math so the operator can compare
"stake vs. hold" for a rate they supply, and the dashboard can surface it.

Never auto-move funds into a vault on inferred data. Yield decisions stay with
the operator until a specific, audited integration is added deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class YieldScenario:
    name: str
    apr: float  # Nominal annual rate the operator provides (e.g. 0.12 = 12%).
    compounds_per_year: int = 365
    impermanent_loss_frac: float = 0.0  # For LP positions; operator estimate.

    def apy(self) -> float:
        """Effective annual yield including compounding, net of IL estimate."""
        n = max(1, self.compounds_per_year)
        gross = (1.0 + self.apr / n) ** n - 1.0
        return gross - self.impermanent_loss_frac

    def projected_value(self, principal: float, years: float = 1.0) -> float:
        return principal * (1.0 + self.apy()) ** years


def compare(principal: float, scenarios: list[YieldScenario], years: float = 1.0) -> list[dict]:
    """Rank scenarios by projected value. Pure reporting, no side effects."""
    rows = [
        {
            "name": s.name,
            "apr": s.apr,
            "apy": s.apy(),
            "projected": s.projected_value(principal, years),
        }
        for s in scenarios
    ]
    return sorted(rows, key=lambda r: r["projected"], reverse=True)
