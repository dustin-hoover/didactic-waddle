"""Whale-follow detector + forward-return backtest (PHASE 6 validation).

The scalp thesis in one sentence: *when a whale moves big money on-chain, price
keeps going that way long enough to grab a small profit before costs eat it.* That
is a CLAIM, not a fact — this module exists to measure whether it is true on real
data before a dollar is ever risked.

Two pieces, both PURE and testable offline (network is a thin, injectable wrapper):

  1. detect_whales(prints, min_usd) — pick the large single swaps out of the tape.
     Each is a discrete, observable event: "a whale just bought/sold $X of TOKEN in
     one print." This is the event you wanted to follow "as closely as possible."

  2. backtest(prints, cfg) — for every whale event, simulate honestly following it:
        • you CANNOT fill in the whale's own block — enter `entry_lag_blocks` later
          (CoW settles in batches; you are always a little behind).
        • hold `horizon_blocks`, then exit.
        • charge a round-trip `cost_bps` (slippage + fee + MEV) — deliberately
          conservative on the thin long tail.
     Then it reports the numbers that decide everything:
        HIT RATE, average NET return after costs, and EVENTS PER DAY (how often it
        even fires — i.e. how many days are genuinely quiet).

Honesty rules baked in:
  * The entry price is a LATER print, never the whale's own — no look-ahead fill.
  * Returns are always NET of a cost assumption; gross is shown only alongside net.
  * One in-sample run NEVER earns a "confirmed edge" verdict. The best you can get
    here is "POSSIBLE EDGE — confirm out-of-sample." No edge, or too few events,
    says so plainly.
  * Coverage caveat still stands: this sees on-chain DEX prints only, not CEX/OTC
    flow. A "quiet" result may mean the whales are trading where we can't see.

This module reads and measures. It holds no key and places no orders.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

_BLOCKS_PER_DAY = 7200.0          # ~12s blocks on Ethereum mainnet


@dataclass
class WhaleEvent:
    symbol: str
    block: int
    tx: str
    side: str                     # "BUY" | "SELL" of the base asset
    usd_size: float
    price: float                  # base price in USD at the whale's print

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _attr(o, name, default=None):
    """Read either an object attribute or a dict key — so tape.Block OR a plain dict works."""
    if isinstance(o, dict):
        return o.get(name, default)
    return getattr(o, name, default)


def detect_whales(prints: Sequence, min_usd: float, symbol: str = "?") -> List[WhaleEvent]:
    """The discrete 'a whale just moved big money' events: prints at/above min_usd."""
    out: List[WhaleEvent] = []
    for p in prints:
        size = float(_attr(p, "usd_size", 0.0) or 0.0)
        if size >= min_usd:
            out.append(WhaleEvent(
                symbol=_attr(p, "symbol", symbol) or symbol,
                block=int(_attr(p, "block", 0) or 0),
                tx=_attr(p, "tx", "") or "",
                side=_attr(p, "side", "") or "",
                usd_size=size,
                price=float(_attr(p, "price", 0.0) or 0.0)))
    return out


def _price_at_or_after(prints: Sequence, block: int) -> Optional[float]:
    """First print price at or after `block` (prints assumed sorted ascending)."""
    for p in prints:
        if int(_attr(p, "block", 0) or 0) >= block:
            price = float(_attr(p, "price", 0.0) or 0.0)
            return price if price > 0 else None
    return None


def forward_return(prints: Sequence, event: WhaleEvent, horizon_blocks: int,
                   entry_lag_blocks: int = 2) -> Optional[float]:
    """Signed forward return IN THE WHALE'S DIRECTION, gross of costs.

    Enter at the first print >= event.block + entry_lag_blocks (you can't fill in
    the whale's own block), exit at the first print >= entry_block + horizon_blocks.
    Returns None if the window runs off the end of the data (event too recent).
    """
    entry_block = event.block + max(1, entry_lag_blocks)
    entry = None
    exit_block = None
    for p in prints:                                     # find entry print
        b = int(_attr(p, "block", 0) or 0)
        if b >= entry_block:
            pr = float(_attr(p, "price", 0.0) or 0.0)
            if pr <= 0:
                return None
            entry, exit_block = pr, b + horizon_blocks
            break
    if entry is None:
        return None
    exit_price = _price_at_or_after(prints, exit_block)
    if exit_price is None:
        return None
    move = (exit_price - entry) / entry
    return move if event.side == "BUY" else -move       # SELL whale => we profit if price drops


@dataclass
class WhaleBacktestConfig:
    min_whale_usd: float = 25_000.0   # what counts as a whale print on the long tail
    horizon_blocks: int = 150         # hold ~30 min after entry
    entry_lag_blocks: int = 2         # you fill a couple blocks behind the whale
    cost_bps: float = 100.0           # round-trip slippage+fee+MEV assumption (1%)
    min_events: int = 20              # below this, refuse to conclude anything


@dataclass
class BacktestResult:
    symbol: str
    n_events: int
    n_evaluated: int
    hits: int
    hit_rate: float
    avg_gross: float
    avg_net: float
    median_net: float
    best: float
    worst: float
    events_per_day: float
    span_blocks: int
    min_whale_usd: float
    horizon_blocks: int
    entry_lag_blocks: int
    cost_bps: float
    verdict: str
    note: str = ""

    def summary(self) -> str:
        pct = lambda x: f"{x*100:+.2f}%"
        return (
            f"{self.symbol}: {self.verdict}\n"
            f"  whale events: {self.n_events} ({self.events_per_day:.2f}/day)"
            f"  · evaluated: {self.n_evaluated}  · min size ${self.min_whale_usd:,.0f}\n"
            f"  follow @ {self.entry_lag_blocks}-blk lag, hold {self.horizon_blocks} blk, "
            f"cost {self.cost_bps:.0f}bps round-trip\n"
            f"  hit rate: {self.hit_rate*100:.0f}%   avg net: {pct(self.avg_net)}   "
            f"median net: {pct(self.median_net)}\n"
            f"  gross avg: {pct(self.avg_gross)}   best {pct(self.best)} / worst {pct(self.worst)}"
            + (f"\n  note: {self.note}" if self.note else ""))

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _verdict(n_eval: int, avg_net: float, hit_rate: float, cfg: WhaleBacktestConfig) -> tuple:
    if n_eval < cfg.min_events:
        return "INSUFFICIENT DATA", f"only {n_eval} evaluable events (< {cfg.min_events}); can't conclude"
    if avg_net <= 0:
        return "NO EDGE", "average net return is <= 0 after costs — following this signal loses money"
    if hit_rate < 0.5:
        return "NO EDGE", f"wins only {hit_rate*100:.0f}% of the time — a coin flip or worse"
    return ("POSSIBLE EDGE — confirm out-of-sample",
            "positive in-sample; must hold on a separate period/universe before trusting a dollar")


def backtest(prints: Sequence, cfg: Optional[WhaleBacktestConfig] = None,
             symbol: str = "?") -> BacktestResult:
    """Measure whether following on-chain whale prints paid, net of costs.

    `prints` : the tape (tape.Block objects or dicts), any order — sorted here.
    """
    c = cfg or WhaleBacktestConfig()
    ordered = sorted(prints, key=lambda p: int(_attr(p, "block", 0) or 0))
    span = 0
    if ordered:
        span = int(_attr(ordered[-1], "block", 0) or 0) - int(_attr(ordered[0], "block", 0) or 0)

    events = detect_whales(ordered, c.min_whale_usd, symbol=symbol)
    cost = c.cost_bps / 10_000.0
    nets: List[float] = []
    grosses: List[float] = []
    for ev in events:
        g = forward_return(ordered, ev, c.horizon_blocks, c.entry_lag_blocks)
        if g is None:
            continue
        grosses.append(g)
        nets.append(g - cost)

    n_eval = len(nets)
    hits = sum(1 for x in nets if x > 0)
    hit_rate = hits / n_eval if n_eval else 0.0
    avg_net = statistics.fmean(nets) if nets else 0.0
    avg_gross = statistics.fmean(grosses) if grosses else 0.0
    median_net = statistics.median(nets) if nets else 0.0
    events_per_day = (len(events) / (span / _BLOCKS_PER_DAY)) if span > 0 else 0.0

    verdict, note = _verdict(n_eval, avg_net, hit_rate, c)
    return BacktestResult(
        symbol=symbol, n_events=len(events), n_evaluated=n_eval, hits=hits,
        hit_rate=round(hit_rate, 4), avg_gross=round(avg_gross, 6), avg_net=round(avg_net, 6),
        median_net=round(median_net, 6), best=round(max(nets), 6) if nets else 0.0,
        worst=round(min(nets), 6) if nets else 0.0, events_per_day=round(events_per_day, 3),
        span_blocks=span, min_whale_usd=c.min_whale_usd, horizon_blocks=c.horizon_blocks,
        entry_lag_blocks=c.entry_lag_blocks, cost_bps=c.cost_bps, verdict=verdict, note=note)


def run_backtest(symbol: str, blocks: int = 43_200, cfg: Optional[WhaleBacktestConfig] = None,
                 get_swaps_fn: Optional[Callable] = None) -> BacktestResult:
    """Network wrapper: pull ~`blocks` of history for `symbol` and backtest the follow.

    43_200 blocks ≈ 6 days. `get_swaps_fn(pool, blocks)` is injectable so tests never
    touch the RPC; the default wires tape's pool map + get_swaps.
    """
    c = cfg or WhaleBacktestConfig()
    if get_swaps_fn is None:
        from .tape import _TAPE_POOLS, get_swaps
        pool = _TAPE_POOLS.get(symbol.upper())
        if not pool:
            return BacktestResult(symbol.upper(), 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0,
                                  c.min_whale_usd, c.horizon_blocks, c.entry_lag_blocks, c.cost_bps,
                                  "INSUFFICIENT DATA", "no configured on-chain pool for this symbol")
        prints = get_swaps(pool, blocks=blocks)
    else:
        prints = get_swaps_fn(symbol, blocks)
    return backtest(prints, c, symbol=symbol.upper())
