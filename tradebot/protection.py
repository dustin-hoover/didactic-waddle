"""Capital preservation — "protect the accumulated bags at all costs".

Seasoned traders don't just chase entries; they take money off the table and
ring-fence it. This module implements that discipline as a layer on top of the
trading account:

  * PROFIT SKIM: each time total equity makes a new high by a tier, a fixed
    fraction of the new gain is *realized* and swept into a stable RESERVE
    (think USDC). Selling into strength, banking wins.
  * RATCHET: the reserve only ever grows (plus yield). Drawdowns in the trading
    book can never claw back money already banked. This is the "at all costs"
    part — banked profit is off the table for good.
  * YIELD: the reserve is assumed to earn a stable APY (lending/staking a
    stablecoin, or SPOT). Accounting only here — an actual deposit is a signed,
    on-chain action the operator authorizes; the bot never moves real funds.
  * RESERVE FLOOR: an optional minimum fraction of total equity always kept in
    the reserve (cash/stable is always a position).

The strategy only ever trades the *unreserved* book, so as the reserve grows the
amount at risk shrinks — you compound safety, not just exposure.

FLYWHEEL (reinvestment): the reserve isn't a dead end. Once it grows to a
multiple of the original seed (default: triples it), a fraction of it (default:
two-thirds) is injected back into the trading pool, enlarging the base that
generates future profit — which refills the reserve faster, which triggers the
next injection. Each cycle ratchets the machine up. The remaining third stays
banked and compounding, so safety keeps growing too. Runs until you stop it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid a circular import (portfolio -> config -> protection)
    from .portfolio import PaperExecutor, Portfolio


@dataclass
class ProtectionConfig:
    enabled: bool = True
    skim_rate: float = 0.30       # fraction of each new gain swept to reserve
    skim_tier: float = 0.08       # skim fires on each new equity high of +this
    reserve_floor: float = 0.05   # min fraction of total equity kept in reserve
    reserve_apy: float = 0.06     # assumed stable yield on the reserve (accounting)
    # Flywheel / reinvestment
    reinvest_enabled: bool = True
    reinvest_fraction: float = 2 / 3   # portion of ELIGIBLE reserve injected into trading
    # Trigger mode:
    #   "ratio" (default, actually fires) — recycle when the eligible reserve grows
    #     to >= reinvest_ratio x the current trading pool. Scales with the account,
    #     so it stays a living mechanism instead of a once-a-decade event.
    #   "seed" — the literal "reserve reaches reinvest_multiple x the original seed"
    #     rule. Faithful to the first spec, but on realistic returns it almost
    #     never fires (the reserve rarely reaches multiples of the seed).
    reinvest_trigger_mode: str = "ratio"
    reinvest_ratio: float = 0.5        # ratio-mode threshold (reserve vs trading pool)
    reinvest_multiple: float = 3.0     # seed-mode threshold (reserve vs original seed)
    # Principal protection ("house money"): once the seed is banked, never push it
    # back into risk — the flywheel then recycles only profit ABOVE the seed, and
    # the reserve is never drawn below the seed. Bounds the realistic worst case to
    # losing profit, not capital (after the seed has been secured once).
    protect_principal: bool = True


@dataclass
class ReserveState:
    reserve: float = 0.0          # banked stable value (earns apy)
    hwm: float | None = None      # total-equity high-water at last skim
    skims: int = 0
    yield_earned: float = 0.0
    reinvests: int = 0            # times the flywheel fired
    total_reinvested: float = 0.0  # cumulative reserve -> trading injections
    trading_base: float = 0.0     # seed + everything injected back into trading


class ProfitProtector:
    def __init__(self, cfg: ProtectionConfig, executor: PaperExecutor, bars_per_year: float,
                 seed: float = 0.0):
        self.cfg = cfg
        self.execu = executor
        self.bpy = max(bars_per_year, 1.0)
        self.seed = seed          # original trading investment; flywheel trigger reference
        self.state = ReserveState(trading_base=seed)

    def total_equity(self, pf: Portfolio, price: float) -> float:
        return self.state.reserve + pf.equity(price)

    def _bank(self, pf: Portfolio, price: float, amount: float, ts: int) -> float:
        """Realize `amount` of value from the trading book into the reserve.

        Pull from idle cash first, then sell just enough of the asset (paying
        costs) to cover the rest. Returns the amount actually banked.
        """
        amount = max(0.0, amount)
        take_cash = min(amount, pf.cash)
        pf.cash -= take_cash
        banked = take_cash
        remaining = amount - take_cash
        if remaining > 1e-9 and pf.units > 0:
            before = pf.cash
            # target exposure that frees ~`remaining` of value by selling asset
            eq = pf.equity(price)
            if eq > 0:
                cur_val = pf.units * price
                sell_val = min(remaining, cur_val)
                target_exposure = max(0.0, (cur_val - sell_val) / eq)
                self.execu.rebalance_to(pf, target_exposure, price, ts)
                banked += pf.cash - before  # net proceeds after fees
        self.state.reserve += banked
        return banked

    def step(self, pf: Portfolio, price: float, ts: int) -> None:
        if not self.cfg.enabled:
            return
        # 1) accrue yield on the reserve.
        y = self.state.reserve * (self.cfg.reserve_apy / self.bpy)
        self.state.reserve += y
        self.state.yield_earned += y

        total = self.total_equity(pf, price)
        if self.state.hwm is None:
            self.state.hwm = total

        # 2) profit skim on a new equity high.
        if total >= self.state.hwm * (1.0 + self.cfg.skim_tier):
            gain = total - self.state.hwm
            self._bank(pf, price, self.cfg.skim_rate * gain, ts)
            self.state.hwm = self.total_equity(pf, price)
            self.state.skims += 1

        # 3) enforce the reserve floor (always keep some stable/cash banked).
        total = self.total_equity(pf, price)
        floor_target = self.cfg.reserve_floor * total
        if self.state.reserve < floor_target - 1e-9:
            self._bank(pf, price, floor_target - self.state.reserve, ts)

        # 4) FLYWHEEL: recycle reserve back into the trading pool once it has
        #    grown enough. With principal protection ON, the seed is a floor the
        #    reserve is never drawn below, and only profit ABOVE the seed is
        #    eligible to be reinvested — so your capital, once banked, stays safe.
        if self.cfg.reinvest_enabled and self.seed > 0:
            floor = self.seed if self.cfg.protect_principal else 0.0
            eligible = self.state.reserve - floor
            if self.cfg.reinvest_trigger_mode == "ratio":
                threshold = self.cfg.reinvest_ratio * max(pf.equity(price), 1e-9)
            else:
                threshold = self.cfg.reinvest_multiple * self.seed
            if eligible > 0 and eligible >= threshold:
                move = self.cfg.reinvest_fraction * eligible
                self.state.reserve -= move
                pf.cash += move                         # internal transfer into trading
                self.state.reinvests += 1
                self.state.total_reinvested += move
                self.state.trading_base += move
                # reset the skim high-water to the new, larger total
                self.state.hwm = self.total_equity(pf, price)
