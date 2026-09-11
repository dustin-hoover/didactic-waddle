"""Scalp suite (PHASE 6 — SCAFFOLD, NOT YET VALIDATED).

A second, faster layer that lives on the same site as the daily flywheel but plays
a completely different game: many small trades per day on the LOWER-market-cap long
tail, entered off short-window whale flow, exited fast on a tight take-profit / stop.
More potential gain per move, and far more ways to lose.

    ┌─────────────────────────────────────────────────────────────────────┐
    │  READ THIS BEFORE YOU TRUST A DOLLAR TO IT                            │
    │                                                                       │
    │  This is a SCAFFOLD to be TESTED, not a validated strategy.           │
    │  `validated=False` by default and live signing is REFUSED until it    │
    │  is flipped — and it should only be flipped after the intraday edge   │
    │  is demonstrated out-of-sample on this exact universe. The daily      │
    │  flywheel's edge DOES NOT transfer to intraday scalping; it must be   │
    │  proven on its own.                                                   │
    │                                                                       │
    │  Why the long tail is dangerous, specifically:                        │
    │    • THIN LIQUIDITY — the size you want to trade moves the price       │
    │      against you; realized slippage can dwarf the "edge".             │
    │    • MEV / sandwiching — small illiquid swaps are prime sandwich bait  │
    │      (CoW helps, but does not make it free).                          │
    │    • RUG / honeypot risk — the long tail is where contracts can freeze │
    │      selling, tax you to zero, or mint supply. Every candidate is run  │
    │      through safety.check(); anything not OK is refused.               │
    │    • FEES & CHURN — many small trades multiply cost and taxable        │
    │      events; the per-trade edge must clear all of it to net positive.  │
    │                                                                       │
    │  So this module RANKS candidates and gates them behind hard caps. It   │
    │  does not hold a key, does not sign, and will not mark anything        │
    │  signable until BOTH live AND validated are true.                     │
    └─────────────────────────────────────────────────────────────────────┘

Signal thesis (to be validated, not assumed): on a SHORT window (≈1h of blocks,
not a full day), a strong whale-weighted flow imbalance in a liquid-enough long-tail
pool tends to continue for long enough to capture a small take-profit before a tight
stop. `rank_candidates` encodes exactly that filter so it can be backtested:

    strong |tape score|  AND  whales actually in the flow  AND  enough $ traded in
    the window to get filled  AND  the token passes the rug screen  →  candidate.

The pure ranking (`rank_candidates`) takes already-fetched tape scores + safety
verdicts so it is fully testable offline; `scan` is the thin network wrapper that
fetches them (injectable, so tests never touch the RPC).

Phase plan:
  1. (this file) candidate ranking + hard gates + honest framing.            ← now
  2. backtest: does the short-window flow actually predict the next move on
     THIS universe, net of slippage/fees?  (scripts/, reuse backtest.py)
  3. execution wiring for the long tail (their token addresses are NOT yet in
     execution.TOKENS; majors-only today) + intraday day-ledger like autopilot.
  4. flip `validated` only if step 2 clears out-of-sample; live stays gated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence


# Lower-market-cap long tail we're willing to look at. These trade against WETH in
# tape.py's pool set; majors (ETH/BTC) are deliberately excluded — this layer is
# about the long tail. Every one still gets screened before it's ever tradeable.
DEFAULT_UNIVERSE = ("UNI", "LINK", "LDO", "AAVE", "MATIC", "PEPE", "SHIB")


@dataclass
class ScalpConfig:
    enabled: bool = False              # master switch for the scalp layer
    live: bool = False                 # False = DRY-RUN (rank/log only, never signs)
    validated: bool = False            # HARD gate: no live signing until backtested
    universe: Sequence[str] = DEFAULT_UNIVERSE

    # --- signal thresholds (a HIGHER bar than the daily flywheel) ---
    blocks_window: int = 300           # ~1h of intraday flow (vs. 7200 ≈ a day)
    min_score: float = 0.35            # require real directional conviction
    min_whale_share: float = 0.30      # whales must actually be in the flow
    min_flow_usd: float = 50_000.0     # skip windows too thin to get filled cleanly

    # --- safety (rug screen) ---
    max_safety_risk: int = 25          # only OK-verdict tokens (safety.risk_score)

    # --- position / risk sizing (small and tight; scalps, not swings) ---
    per_trade_usd: float = 25.0
    daily_cap_usd: float = 150.0
    max_trades_per_day: int = 6
    cooldown_sec: int = 600            # throttle re-entries on the same churn
    take_profit_frac: float = 0.04     # +4% target ...
    stop_loss_frac: float = 0.02       # ... against a -2% stop (2:1)
    max_hold_sec: int = 3600           # time-stop: don't marry a scalp

    venue: str = "cow"
    chain: str = "ethereum"


@dataclass
class ScalpCandidate:
    symbol: str
    action: str                        # "enter" | "watch" | "skip"
    side: str                          # "long" | "exit" (spot is long-only)
    live: bool
    score: float
    whale_share: float
    net_usd: float                     # CVD over the window
    flow_usd: float                    # total $ traded in the window
    price: float
    safety_verdict: str                # OK | CAUTION | AVOID | UNKNOWN
    safety_risk: Optional[int]
    notional_usd: float
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    signable: bool = False             # only true when enabled AND live AND validated
    reason: str = ""
    blocked: Optional[str] = None      # first hard gate that stopped it, if any

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _verdict(screen) -> tuple:
    """Duck-type a safety result to (verdict, risk). Accepts a SafetyReport, a dict,
    or None. None means 'not screened' → treated as UNKNOWN (never reassure)."""
    if screen is None:
        return "UNKNOWN", None
    verdict = getattr(screen, "verdict", None)
    if verdict is None and isinstance(screen, dict):
        verdict = screen.get("verdict")
    risk = getattr(screen, "risk_score", None)
    if risk is None and isinstance(screen, dict):
        risk = screen.get("risk_score", screen.get("risk"))
    return (verdict or "UNKNOWN"), risk


def rank_candidates(scores: Sequence, screens: dict, cfg: Optional[ScalpConfig] = None) -> List[ScalpCandidate]:
    """Pure, testable ranking: turn tape scores + safety verdicts into scalp candidates.

    `scores`  : iterable of tape-score-like objects (attrs: symbol, score,
                whale_share, net_usd, total_usd, price, error).
    `screens` : {symbol -> SafetyReport|dict|None} rug-screen results.

    A candidate is only ``action == "enter"`` when EVERY hard gate passes; otherwise
    it is "watch" (interesting but blocked) or "skip" (not a setup). ``signable`` is
    the last, strictest gate: enabled AND live AND validated — so a backtest-unproven
    config can rank all day and still never produce anything a runner would sign.
    """
    c = cfg or ScalpConfig()
    out: List[ScalpCandidate] = []

    for s in scores:
        sym = getattr(s, "symbol", "?")
        err = getattr(s, "error", None)
        score = float(getattr(s, "score", 0.0) or 0.0)
        wshare = float(getattr(s, "whale_share", 0.0) or 0.0)
        net = float(getattr(s, "net_usd", 0.0) or 0.0)
        flow = float(getattr(s, "total_usd", 0.0) or 0.0)
        price = float(getattr(s, "price", 0.0) or 0.0)
        verdict, risk = _verdict(screens.get(sym))
        side = "long" if score > 0 else "exit"

        cand = ScalpCandidate(
            symbol=sym, action="skip", side=side, live=c.live, score=round(score, 4),
            whale_share=round(wshare, 4), net_usd=round(net, 2), flow_usd=round(flow, 2),
            price=price, safety_verdict=verdict, safety_risk=risk,
            notional_usd=0.0)

        # ---- hard gates, most fundamental first ----
        if err:
            cand.reason = f"no read ({err})"
            out.append(cand); continue
        if not c.enabled:
            cand.reason = "scalp layer disabled"; cand.blocked = "disabled"
            out.append(cand); continue
        if side != "long":
            cand.reason = "distribution — spot is long-only, no entry"
            cand.action = "watch"; cand.blocked = "short-only-signal"
            out.append(cand); continue
        if abs(score) < c.min_score:
            cand.reason = f"conviction {abs(score):.2f} < {c.min_score:.2f}"
            out.append(cand); continue
        if wshare < c.min_whale_share:
            cand.reason = f"whale share {wshare:.0%} < {c.min_whale_share:.0%}"
            out.append(cand); continue
        if flow < c.min_flow_usd:
            cand.reason = f"window flow ${flow:,.0f} < ${c.min_flow_usd:,.0f} (too thin to fill)"
            cand.action = "watch"; cand.blocked = "illiquid-window"
            out.append(cand); continue
        if price <= 0:
            cand.reason = "no usable price"; out.append(cand); continue
        if verdict != "OK" or (risk is not None and risk > c.max_safety_risk):
            cand.reason = f"rug screen: {verdict}" + (f" (risk {risk})" if risk is not None else "")
            cand.action = "watch"; cand.blocked = "failed-safety-screen"
            out.append(cand); continue

        # ---- setup qualifies; size it and set the bracket ----
        cand.action = "enter"
        cand.notional_usd = round(c.per_trade_usd, 2)
        cand.take_profit = round(price * (1 + c.take_profit_frac), 10)
        cand.stop_loss = round(price * (1 - c.stop_loss_frac), 10)
        cand.signable = bool(c.enabled and c.live and c.validated)
        gate = ("SIGNABLE" if cand.signable
                else "LIVE-but-UNVALIDATED" if (c.live and not c.validated)
                else "DRY-RUN")
        cand.reason = (f"WOULD enter ${cand.notional_usd:,.2f} {sym} @ {price:.6g} "
                       f"(+{c.take_profit_frac:.0%}/-{c.stop_loss_frac:.0%}, {gate})")
        out.append(cand)

    # Rank the actionable ones first, by conviction then by how much traded.
    out.sort(key=lambda x: (x.action == "enter", abs(x.score), x.flow_usd), reverse=True)
    return out


def scan(cfg: Optional[ScalpConfig] = None,
         read_tape_fn: Optional[Callable] = None,
         screen_fn: Optional[Callable] = None) -> List[ScalpCandidate]:
    """Network wrapper: read the short-window tape across the universe, screen each
    token, then rank. Both fetchers are injectable so tests never touch the RPC.

    read_tape_fn(symbol, blocks) -> tape-score-like ; screen_fn(symbol) -> SafetyReport.
    Defaults wire the real tape.read_tape and safety.check.
    """
    c = cfg or ScalpConfig()
    if read_tape_fn is None:
        from .tape import read_tape as read_tape_fn  # lazy: keep import light for tests
    if screen_fn is None:
        from .safety import check as _check
        from .safety import resolve as _resolve
        screen_fn = lambda sym: _check(_resolve(sym))  # noqa: E731

    scores = [read_tape_fn(sym, c.blocks_window) for sym in c.universe]
    screens = {}
    for s in scores:
        sym = getattr(s, "symbol", None)
        # Only pay for a rug screen on names that at least look directional.
        if sym and getattr(s, "error", None) is None and abs(getattr(s, "score", 0.0) or 0.0) >= c.min_score:
            try:
                screens[sym] = screen_fn(sym)
            except Exception:  # noqa: BLE001 — a failed screen must read as UNKNOWN, not OK
                screens[sym] = None
    return rank_candidates(scores, screens, c)
