"""Autopilot: unattended trading on a clear, hard-capped set of rules.

This decides WHETHER and WHAT to trade when the model flips, and enforces the
guardrails that make hands-off trading safe. It does NOT hold a key or sign — that
is the runner's job with a scoped session key (see the security note below). This
separation is deliberate: the risky part (signing) stays in one small, auditable
place, and everything here is pure, testable logic.

Guardrails (all enforced before a trade is ever proposed):
  * DRY-RUN by default (`live=False`) — logs what it WOULD do, moves nothing.
  * per-order cap and a rolling DAILY notional cap (resets at UTC midnight).
  * a COOLDOWN between trades (throttle churn / runaway loops).
  * a minimum move (ignore dust rebalances).
  * token allowlist (via the execution layer).

Security note on the eventual live path: unattended signing uses a SESSION KEY
granted a revocable on-chain SPEND PERMISSION (e.g., "swap up to $X/day of
USDC↔WETH via CoW"). The key lives as a runner secret and can only ever act within
that permission; you revoke it on-chain any time (instant kill switch), and the
caps here are a second, independent limit in code. That is the whole bargain for
hands-off: a tightly-scoped, revocable key — never your main wallet's key.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .execution import ExecutionPolicy, PolicyError, propose


@dataclass
class AutopilotConfig:
    enabled: bool = False              # master switch; when False, decide() always holds
    live: bool = False                 # False = DRY-RUN (decide/log only, no signing)
    max_notional_usd: float = 100.0    # per-order cap
    daily_cap_usd: float = 300.0       # max total notional placed per UTC day
    cooldown_min: int = 60             # minimum minutes between trades
    min_move_frac: float = 0.10        # ignore exposure changes smaller than this fraction of equity
    venue: str = "cow"
    chain: str = "base"
    allowed_tokens: tuple = ("USDC", "WETH", "WBTC")
    stable: str = "USDC"

    def exec_policy(self) -> ExecutionPolicy:
        return ExecutionPolicy(enabled=self.live, venue=self.venue, chain=self.chain,
                               max_notional_usd=self.max_notional_usd,
                               allowed_tokens=tuple(self.allowed_tokens))


@dataclass
class AutoState:
    day: str = ""
    spent_usd: float = 0.0
    last_trade_ts: int = 0
    trades_today: int = 0


@dataclass
class Decision:
    action: str                        # "hold" | "buy" | "sell"
    notional_usd: float
    live: bool
    reason: str
    proposal: Optional[dict] = None    # execution proposal dict when a trade is due
    blocked: Optional[str] = None      # guardrail that stopped/limited it, if any


class Autopilot:
    def __init__(self, cfg: AutopilotConfig, state_path: str = "data/autopilot.json"):
        self.cfg = cfg
        self.state_path = state_path
        self.state = AutoState()
        if os.path.exists(state_path):
            try:
                self.state = AutoState(**json.load(open(state_path)))
            except Exception:  # noqa: BLE001
                self.state = AutoState()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        json.dump(asdict(self.state), open(self.state_path, "w"), indent=1)

    def _roll_day(self, now_ts: int) -> None:
        today = datetime.fromtimestamp(now_ts, tz=timezone.utc).date().isoformat()
        if self.state.day != today:
            self.state.day = today
            self.state.spent_usd = 0.0
            self.state.trades_today = 0

    def decide(self, bag_id: str, wallet: str, target_exposure: float, current_exposure: float,
               equity_usd: float, base_symbol: str, price_usd: dict, now_ts: int) -> Decision:
        """Pure decision: what (if anything) to trade now, within all guardrails."""
        c = self.cfg
        if not c.enabled:
            return Decision("hold", 0.0, c.live, "autopilot disabled")
        self._roll_day(now_ts)

        delta = target_exposure - current_exposure
        notional = abs(delta) * equity_usd
        if notional < max(1.0, c.min_move_frac * equity_usd):
            return Decision("hold", 0.0, c.live, "no material change (below min move)")

        side = "buy" if delta > 0 else "sell"

        # cooldown
        if self.state.last_trade_ts and (now_ts - self.state.last_trade_ts) < c.cooldown_min * 60:
            mins = int((now_ts - self.state.last_trade_ts) / 60)
            return Decision("hold", notional, c.live, f"{side} deferred", blocked=f"cooldown ({mins}/{c.cooldown_min}m)")

        # daily cap (clamp to remaining budget; block if exhausted)
        remaining = c.daily_cap_usd - self.state.spent_usd
        if remaining <= 0:
            return Decision("hold", notional, c.live, f"{side} deferred", blocked="daily cap reached")
        notional = round(min(notional, remaining, c.max_notional_usd), 2)   # clamp to caps

        sell, buy = (c.stable, base_symbol) if delta > 0 else (base_symbol, c.stable)
        try:
            proposal = propose(bag_id, wallet, sell, buy, notional, price_usd, c.exec_policy())
        except PolicyError as e:
            return Decision("hold", notional, c.live, f"{side} refused", blocked=str(e))

        verb = "WOULD " + side if not c.live else side
        reason = f"{verb} ${notional:,.2f} of {base_symbol} ({'DRY-RUN' if not c.live else 'LIVE'})"
        return Decision(side, notional, c.live, reason, proposal=proposal.to_dict())

    def record_fill(self, notional_usd: float, now_ts: int) -> None:
        """Call after a LIVE order is actually placed, to update caps/cooldown."""
        self._roll_day(now_ts)
        self.state.spent_usd += notional_usd
        self.state.trades_today += 1
        self.state.last_trade_ts = now_ts
        self._save()
