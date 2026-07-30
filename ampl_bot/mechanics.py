"""Ampleforth rebase mechanics.

Faithful (parameterised) model of the AMPL supply policy so the strategy and
backtester reason about the *actual* protocol behaviour rather than a generic
token.

Reference behaviour of Ampleforth's monetary policy:
  * There is a price target derived from the 2019 US CPI (nominal $1.00 in 2019
    dollars). We expose it as a configurable ``target_price``.
  * A rebase only occurs when |price - target| / target exceeds the
    ``deviation_threshold`` (historically 5%).
  * When it does, total supply changes by
        supplyDelta = totalSupply * (price - target) / target / rebase_lag
    where ``rebase_lag`` (historically ~30) smooths the adjustment over time.
  * A rebase is *value neutral at the instant it happens*: your balance scales
    by (1 + rebasePct) while price scales by ~1/(1 + rebasePct) in the very
    short run. The edge a trader can seek is NOT the rebase itself but the
    mean reversion of price back toward target over the following days.

These numbers are configurable because Ampleforth governance has changed them
over the project's history; do not hard-code assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyParams:
    """Parameters of the AMPL supply policy."""

    target_price: float = 1.019  # CPI-adjusted target (approx). Configurable.
    deviation_threshold: float = 0.05  # +/- 5% dead band, no rebase inside it.
    rebase_lag: int = 30  # Smoothing divisor.
    max_rebase_pct: float = 0.10  # Optional clamp on |rebase| per period.


@dataclass(frozen=True)
class RebaseResult:
    """Outcome of applying a rebase at a given market price."""

    rebase_pct: float  # Fractional supply change this period (e.g. 0.021 = +2.1%).
    in_dead_band: bool  # True if inside deviation threshold -> no rebase.
    deviation: float  # (price - target) / target.
    new_supply: float  # Supply after rebase.


def deviation(price: float, params: PolicyParams) -> float:
    """Fractional deviation of price from target. Positive => above target."""
    return (price - params.target_price) / params.target_price


def compute_rebase(price: float, total_supply: float, params: PolicyParams) -> RebaseResult:
    """Compute the supply rebase for a given oracle price.

    Mirrors the protocol: no change inside the dead band, otherwise a lagged,
    optionally-clamped proportional adjustment.
    """
    dev = deviation(price, params)
    if abs(dev) <= params.deviation_threshold:
        return RebaseResult(0.0, True, dev, total_supply)

    rebase_pct = dev / params.rebase_lag
    # Clamp to guard against extreme single-period moves.
    rebase_pct = max(-params.max_rebase_pct, min(params.max_rebase_pct, rebase_pct))
    new_supply = total_supply * (1.0 + rebase_pct)
    return RebaseResult(rebase_pct, False, dev, new_supply)


def apply_rebase_to_balance(balance_ampl: float, rebase: RebaseResult) -> float:
    """A holder's AMPL unit balance scales pro-rata with the rebase."""
    return balance_ampl * (1.0 + rebase.rebase_pct)


def market_zone(price: float, params: PolicyParams) -> str:
    """Human-readable zone used by the strategy and dashboard."""
    dev = deviation(price, params)
    if dev > params.deviation_threshold:
        return "expansion"  # Supply growing; price historically mean-reverts down.
    if dev < -params.deviation_threshold:
        return "contraction"  # Supply shrinking; price historically reverts up.
    return "equilibrium"  # Inside the dead band.
