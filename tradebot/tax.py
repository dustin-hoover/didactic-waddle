"""Tax lot tracking + estimated-tax sweep (non-custodial).

Every disposal (a sell) realizes a gain or loss = proceeds − cost basis of the
units sold. Which units count as "sold" depends on the accounting method:
  * FIFO — oldest lots first (the IRS default).
  * HIFO — highest-cost lots first (usually minimizes realized gains).
Holding > 365 days makes a gain long-term (lower rate) vs short-term.

From a bag's trade history this computes realized gains (short/long), an estimated
tax owed at configurable rates, and a one-transaction "sweep" PROPOSAL that sends
the estimated tax to an offramp address — signed in the user's own wallet, same
non-custodial model as every other trade. This is an ESTIMATE and a tool, not tax
advice; rates and rules vary and a professional should confirm the filing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

_YEAR = 365 * 86400   # seconds


@dataclass
class Disposal:
    ts: int
    symbol: str
    amount: float
    proceeds_usd: float
    cost_basis_usd: float
    acquired_ts: int
    @property
    def gain_usd(self) -> float:
        return self.proceeds_usd - self.cost_basis_usd
    @property
    def long_term(self) -> bool:
        return (self.ts - self.acquired_ts) > _YEAR


def trades_from_fills(fills, symbol: str) -> List[dict]:
    """Convert engine/portfolio Fills (objects OR stored dicts) to tax trades."""
    out = []
    for f in fills:
        g = (lambda k: f[k]) if isinstance(f, dict) else (lambda k: getattr(f, k))
        ts = int(g("ts"))
        ts = ts // 1000 if ts > 10_000_000_000 else ts   # ms -> s if needed
        out.append({"ts": ts, "symbol": symbol, "side": g("side"),
                    "amount": abs(g("units")), "price_usd": g("price")})
    return out


def compute_realized(trades: List[dict], method: str = "fifo") -> List[Disposal]:
    """Match sells against prior buys (FIFO or HIFO); return realized disposals."""
    lots: Dict[str, List[list]] = {}      # symbol -> [[ts, amount, cost_per_unit], ...]
    disposals: List[Disposal] = []
    for t in sorted(trades, key=lambda x: x["ts"]):
        sym, amt, px, ts = t["symbol"], float(t["amount"]), float(t["price_usd"]), int(t["ts"])
        if amt <= 0:
            continue
        if t["side"] == "buy":
            lots.setdefault(sym, []).append([ts, amt, px])
            continue
        pool = lots.setdefault(sym, [])
        remaining = amt
        while remaining > 1e-12 and pool:
            idx = 0 if method == "fifo" else max(range(len(pool)), key=lambda i: pool[i][2])
            lot = pool[idx]
            take = min(remaining, lot[1])
            disposals.append(Disposal(ts=ts, symbol=sym, amount=take,
                                      proceeds_usd=take * px, cost_basis_usd=take * lot[2],
                                      acquired_ts=lot[0]))
            lot[1] -= take
            remaining -= take
            if lot[1] <= 1e-12:
                pool.pop(idx)
        # A sell with no matching lot (basis unknown) is booked at zero basis.
        if remaining > 1e-12:
            disposals.append(Disposal(ts=ts, symbol=sym, amount=remaining,
                                      proceeds_usd=remaining * px, cost_basis_usd=0.0,
                                      acquired_ts=ts))
    return disposals


@dataclass
class TaxSummary:
    proceeds_usd: float = 0.0
    cost_basis_usd: float = 0.0
    short_gain_usd: float = 0.0
    long_gain_usd: float = 0.0
    per_symbol: Dict[str, float] = field(default_factory=dict)
    @property
    def realized_gain_usd(self) -> float:
        return self.short_gain_usd + self.long_gain_usd


def summarize(disposals: List[Disposal]) -> TaxSummary:
    s = TaxSummary()
    for d in disposals:
        s.proceeds_usd += d.proceeds_usd
        s.cost_basis_usd += d.cost_basis_usd
        if d.long_term:
            s.long_gain_usd += d.gain_usd
        else:
            s.short_gain_usd += d.gain_usd
        s.per_symbol[d.symbol] = s.per_symbol.get(d.symbol, 0.0) + d.gain_usd
    return s


def estimate_tax(summary: TaxSummary, short_rate: float = 0.35,
                 long_rate: float = 0.15) -> Dict[str, float]:
    """Estimated tax: rate applied to NET gains per bucket (losses offset, no
    credit for a net loss). Rates are placeholders — set your own bracket."""
    short_tax = max(0.0, summary.short_gain_usd) * short_rate
    long_tax = max(0.0, summary.long_gain_usd) * long_rate
    return {"short_tax": round(short_tax, 2), "long_tax": round(long_tax, 2),
            "total_tax": round(short_tax + long_tax, 2),
            "short_rate": short_rate, "long_rate": long_rate}


def sweep_proposal(amount_usd: float, to_address: str, chain: str = "base",
                   token: str = "USDC") -> dict:
    """A one-transaction estimated-tax sweep: send `amount_usd` of a stablecoin to
    an offramp address. Returns an unsigned transfer plan the UI signs in-wallet."""
    from .execution import TOKENS
    reg = TOKENS.get(chain, {})
    if token not in reg:
        raise ValueError(f"{token} not known on chain '{chain}'")
    if not (isinstance(to_address, str) and to_address.startswith("0x") and len(to_address) == 42):
        raise ValueError("offramp address must be a 0x… 40-hex-char address")
    if amount_usd <= 0:
        raise ValueError("sweep amount must be positive")
    addr, dec = reg[token]
    raw = int(round(amount_usd * (10 ** dec)))
    data = "0xa9059cbb" + to_address[2:].lower().rjust(64, "0") + format(raw, "064x")  # transfer(to,amount)
    return {"chain": chain, "token": token, "token_address": addr,
            "to": to_address, "amount_usd": round(amount_usd, 2), "amount_raw": str(raw),
            "calldata": data,
            "summary": f"Send {amount_usd:,.2f} {token} to {to_address[:6]}…{to_address[-4:]} on {chain}"}
