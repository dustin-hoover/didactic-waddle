"""Bull-market regime gate — the master switch, with BTC as the primary indicator.

Everything we measured says the trend/momentum engine is a BULL-MARKET tool: it
beats buy-and-hold by sitting in cash during downtrends, but in a real bull it is
meant to be ON and carrying beta. So the honest design is a REGIME GATE in front of
it: stay flat until a bull market is *confirmed* off BTC, then switch the engine on;
switch it back off when the bull structure breaks.

BTC leads crypto — alts rarely sustain a bull while BTC is in a downtrend — so BTC
is the primary (and default sole) indicator. The gate is deliberately slow and
hysteretic: it would rather turn on a bit late and off a bit late than whipsaw in
and out around the line. The classic, robust bull/bear divide is price vs the
200-day average; we confirm with structure (50d > 200d), a rising long-term trend,
and a persistence requirement so a single green day can't flip the switch.

Bull is CONFIRMED (gate ON) when, for `confirm_days` running days, ALL hold:
  * BTC close is above its `sma_long` (200d) by the `buffer`,
  * the short average is above the long (20d > 200d — cross structure),
  * the long average is rising (non-negative slope over `slope_lookback`).
Bull is BROKEN (gate OFF) when, for `confirm_days` running days, BTC closes below
the 200d by the buffer OR the short average falls back below the long. Between those
two triggers the gate HOLDS its last state — that band is the anti-whipsaw buffer.

Defaults (sma_short=20, confirm_days=3) were chosen by a sensitivity sweep over
~3.5y of BTC daily: they beat the slower 50d/5d gate on risk-adjusted return AND
drawdown while staying positive in BOTH halves of the window (i.e. not overfit).
Faster-reacting short/long spans scored higher in-sample but went negative
out-of-sample, so they were rejected.

`mode` allows a manual override: "auto" (detect), "on" (force-enable), "off"
(force-disable / hard kill). This is pure logic over a BTC close series — no keys,
no orders. A runner/engine calls `detect()` and, when `state.on` is False, holds
everything flat regardless of what the per-asset signal says.

Design doctrine (see STRATEGY.md, backed by scripts/regime_validation.py):
  * BTC is the market's macro trend anchor; the regime is confirmed on BTC and that
    one switch governs everything. Read it from BTC's TREND STRUCTURE, not
    stock-to-flow (S2F is a scarcity rhythm, not a reliable price predictor).
  * BTC regime is the risk-on UMBRELLA. Never open new alt longs while BTC is in a
    confirmed bear; when BTC is bull, trade each alt on its OWN trend. De-risking is
    always allowed — the umbrella never traps a position. This is `apply_umbrella()`.
  * Trading BTC itself (the live vehicle: cbBTC on Base) sidesteps the alt lead/lag
    mismatch entirely — gate and asset are then the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import indicators as ind


@dataclass
class RegimeConfig:
    mode: str = "auto"                 # "auto" | "on" (force ON) | "off" (force OFF / kill)
    sma_long: int = 200               # the bull/bear line
    sma_short: int = 20               # structure confirm (responsive cross vs the 200d)
    buffer: float = 0.02              # +/- band around the long MA (hysteresis)
    confirm_days: int = 3             # a trigger must persist this many days to flip
    slope_lookback: int = 20          # window for the long-MA slope check
    require_golden_cross: bool = True # also require 50d > 200d to confirm a bull


@dataclass
class RegimeState:
    on: bool                          # master switch: is the trading engine enabled?
    regime: str                       # "bull" | "bear"
    mode: str                         # echo of the config mode actually applied
    price: float = 0.0
    sma_long: Optional[float] = None
    sma_short: Optional[float] = None
    pct_above_long: Optional[float] = None   # (price/sma_long - 1)
    long_rising: Optional[bool] = None
    golden_cross: Optional[bool] = None
    days_in_regime: int = 0           # how long the current on/off state has held
    confirmed: bool = False           # detection had enough history to decide
    reason: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _raw_flags(closes: List[float], i: int, cfg: RegimeConfig):
    """Instantaneous bull/bear structure flags at index i (no persistence yet)."""
    sl = ind.sma(closes[: i + 1], cfg.sma_long)
    ss = ind.sma(closes[: i + 1], cfg.sma_short)
    long_ma = sl[-1] if sl else None
    short_ma = ss[-1] if ss else None
    if long_ma is None:
        return None
    price = closes[i]
    golden = (short_ma is not None and short_ma > long_ma)
    # long-MA slope over slope_lookback (needs the MA that far back)
    rising = None
    if len(sl) > cfg.slope_lookback and sl[-1] is not None and sl[-1 - cfg.slope_lookback] is not None:
        rising = sl[-1] >= sl[-1 - cfg.slope_lookback]
    bull_raw = (price > long_ma * (1 + cfg.buffer)
                and (golden or not cfg.require_golden_cross)
                and (rising is not False))
    bear_raw = (price < long_ma * (1 - cfg.buffer)
                or (cfg.require_golden_cross and short_ma is not None and short_ma < long_ma))
    return dict(price=price, long_ma=long_ma, short_ma=short_ma, golden=golden,
                rising=rising, bull_raw=bull_raw, bear_raw=bear_raw)


def sweep(closes: List[float], cfg: Optional[RegimeConfig] = None) -> List[bool]:
    """Per-day gate state (True=ON) across the whole series, with hysteresis.

    Starts OFF (capital preservation is the safe default). Flips ON only after a bull
    trigger persists `confirm_days`, OFF only after a bear trigger persists the same.
    """
    c = cfg or RegimeConfig()
    on = False
    out: List[bool] = []
    bull_run = bear_run = 0
    for i in range(len(closes)):
        f = _raw_flags(closes, i, c)
        if f is None:
            out.append(on)                     # not enough history: hold default (OFF)
            continue
        bull_run = bull_run + 1 if f["bull_raw"] else 0
        bear_run = bear_run + 1 if f["bear_raw"] else 0
        if not on and bull_run >= c.confirm_days:
            on = True
        elif on and bear_run >= c.confirm_days:
            on = False
        out.append(on)
    return out


def detect(closes: List[float], cfg: Optional[RegimeConfig] = None) -> RegimeState:
    """Current regime + master switch for the latest bar of a BTC close series."""
    c = cfg or RegimeConfig()
    if c.mode == "on":
        return RegimeState(True, "bull", "on", price=(closes[-1] if closes else 0.0),
                           confirmed=True, reason="manual override: forced ON")
    if c.mode == "off":
        return RegimeState(False, "bear", "off", price=(closes[-1] if closes else 0.0),
                           confirmed=True, reason="manual override: forced OFF (kill switch)")

    need = c.sma_long + c.slope_lookback + c.confirm_days
    if len(closes) < c.sma_long:
        return RegimeState(False, "bear", "auto", price=(closes[-1] if closes else 0.0),
                           confirmed=False,
                           reason=f"insufficient history ({len(closes)}/{c.sma_long}d) — gate OFF")

    states = sweep(closes, c)
    on = states[-1]
    # how many trailing days the current state has held
    days = 1
    for j in range(len(states) - 2, -1, -1):
        if states[j] == on:
            days += 1
        else:
            break
    f = _raw_flags(closes, len(closes) - 1, c)
    price, long_ma, short_ma = f["price"], f["long_ma"], f["short_ma"]
    pct = (price / long_ma - 1) if long_ma else None
    warming = len(closes) < need
    regime = "bull" if on else "bear"
    if on:
        reason = (f"BULL confirmed: BTC {pct*100:+.1f}% vs {c.sma_long}d, "
                  f"{c.sma_short}d{'>' if f['golden'] else '<'}{c.sma_long}d")
    else:
        reason = f"BEAR / unconfirmed: BTC {pct*100:+.1f}% vs {c.sma_long}d — engine gated OFF"
    if warming:
        reason += " (limited history)"
    return RegimeState(on=on, regime=regime, mode="auto", price=price, sma_long=long_ma,
                       sma_short=short_ma, pct_above_long=pct, long_rising=f["rising"],
                       golden_cross=f["golden"], days_in_regime=days, confirmed=not warming,
                       reason=reason)


def gate(target_exposure: float, state: RegimeState) -> Tuple[float, str]:
    """Apply the master switch to a per-asset target: flat unless the gate is ON."""
    if not state.on:
        return 0.0, f"regime gate OFF ({state.regime}) — holding flat"
    return target_exposure, f"regime gate ON ({state.regime})"
