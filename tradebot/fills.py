"""Fill logging + realized-cost reconciliation (Phase 0.5).

Every LIVE canary fill is appended as one JSON line to docs/fills.jsonl, recording
what we QUOTED vs what actually EXECUTED, plus fees, gas, slippage, latency and any
failure. That record is the ground truth that `scripts/cost_report.py` reconciles
against the backtester's modelled costs — so a backtest can never quietly assume
cheaper execution than reality delivers.

Nothing here signs or moves funds; it only records outcomes. The module is pure and
stdlib-only, and every read/write is defensive (a missing or half-written log never
crashes the caller).
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional

DEFAULT_FILLS_PATH = "docs/fills.jsonl"


@dataclass
class Fill:
    """One attempted canary fill. Prices are USD per unit of the token traded.

    slippage_bps is the ADVERSE slippage (quoted vs executed, signed so that a
    positive number is a cost to us); latency_s is signal-to-fill wall-clock seconds.
    Set ok=False and an `error` string for a failed/reverted attempt.
    """
    ts_signal: float                     # unix seconds when the signal fired
    ts_fill: float                       # unix seconds when the fill confirmed (or failed)
    chain: str
    venue: str
    sell_symbol: str
    buy_symbol: str
    notional_usd: float
    quoted_price: float                  # expected execution price at signal time
    executed_price: float                # actual fill price (0.0 if failed)
    fee_usd: float = 0.0                 # venue/protocol fee
    gas_usd: float = 0.0                 # network gas paid
    slippage_bps: float = 0.0            # adverse price slippage, bps (>0 = cost)
    latency_s: float = 0.0               # signal -> fill latency
    ok: bool = True                      # did the fill succeed?
    error: Optional[str] = None          # failure reason when ok is False
    tx: Optional[str] = None             # tx hash / order uid for audit
    config_hash: Optional[str] = None    # strategy identity that produced the signal

    def to_dict(self) -> dict:
        return asdict(self)


def adverse_slippage_bps(quoted_price: float, executed_price: float, side: str) -> float:
    """Signed adverse slippage in bps (>0 means we got a worse price than quoted).

    For a buy, paying ABOVE the quote is adverse; for a sell, receiving BELOW is."""
    if quoted_price <= 0 or executed_price <= 0:
        return 0.0
    diff = (executed_price - quoted_price) / quoted_price
    adverse = diff if side.lower() == "buy" else -diff
    return round(adverse * 10_000, 3)


def record_fill(fill: Fill, path: str = DEFAULT_FILLS_PATH) -> None:
    """Append one fill as a JSON line (append-only; creates the file/dir if needed)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(fill.to_dict(), separators=(",", ":")) + "\n")


def load_fills(path: str = DEFAULT_FILLS_PATH) -> List[dict]:
    """Read all fills. Tolerant of a missing file and of a trailing half-written line."""
    out: List[dict] = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue            # skip a corrupt/partial line, keep the rest
    except FileNotFoundError:
        return []
    return out


@dataclass
class RealizedCosts:
    n_fills: int = 0
    n_ok: int = 0
    n_failed: int = 0
    failure_rate: float = 0.0
    fee_frac: float = 0.0                # (fee+gas)/notional, median over OK fills
    slippage_frac: float = 0.0           # median adverse slippage, as a fraction
    p90_slippage_frac: float = 0.0       # tail slippage (p90), as a fraction
    median_latency_s: float = 0.0
    fee_bps: float = 0.0                 # convenience: fee_frac in bps
    slippage_bps: float = 0.0            # convenience: slippage_frac in bps
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _pctile(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def realized_costs(fills: List[dict]) -> RealizedCosts:
    """Aggregate logged fills into realized cost parameters.

    Costs are measured over SUCCESSFUL fills only (a failed attempt has no fill price),
    but the failure rate is reported separately — repeated failures are themselves a
    cost signal the operator must see. Fee combines venue fee + gas, as a fraction of
    notional; slippage uses the logged adverse bps (floored at 0, since a favorable
    fill is not a cost to budget for)."""
    n = len(fills)
    ok = [f for f in fills if f.get("ok", True)]
    failed = n - len(ok)
    fee_fracs, slips, lats = [], [], []
    for f in ok:
        notional = float(f.get("notional_usd") or 0.0)
        if notional > 0:
            fee_fracs.append((float(f.get("fee_usd") or 0.0) + float(f.get("gas_usd") or 0.0)) / notional)
        slips.append(max(0.0, float(f.get("slippage_bps") or 0.0)) / 10_000.0)
        lats.append(float(f.get("latency_s") or 0.0))
    fee_frac = statistics.median(fee_fracs) if fee_fracs else 0.0
    slip_frac = statistics.median(slips) if slips else 0.0
    return RealizedCosts(
        n_fills=n, n_ok=len(ok), n_failed=failed,
        failure_rate=round(failed / n, 4) if n else 0.0,
        fee_frac=round(fee_frac, 6), slippage_frac=round(slip_frac, 6),
        p90_slippage_frac=round(_pctile(slips, 0.90), 6),
        median_latency_s=round(statistics.median(lats), 3) if lats else 0.0,
        fee_bps=round(fee_frac * 10_000, 2), slippage_bps=round(slip_frac * 10_000, 2))


def demo_fill(**kw) -> Fill:
    """Construct a Fill with sensible defaults, for tests/examples (not a real fill)."""
    base = dict(ts_signal=time.time(), ts_fill=time.time(), chain="base", venue="cow",
                sell_symbol="USDC", buy_symbol="CBBTC", notional_usd=100.0,
                quoted_price=77000.0, executed_price=77050.0)
    base.update(kw)
    return Fill(**base)
