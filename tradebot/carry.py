"""Carry monitor — is delta-neutral funding income worth harvesting right now?

The honest, market-neutral income idea: hold spot long + short the perpetual of the
same coin. You're delta-neutral (price direction doesn't matter) and you EARN the
funding rate — a published, measurable number. This module turns live funding into a
decision: for each coin, the realized annualized carry, how PERSISTENT it's been
(% of funding periods positive), net of a fee-drag estimate, and whether it clears a
threshold worth acting on.

It only MONITORS — no position, no venue integration yet. The pure math is
offline-testable; the OKX/Hyperliquid fetchers are injectable. Honest by construction:
carry is real but modest and regime-dependent (funding goes flat/negative in bears),
and capturing it needs a perp venue with liquidation + counterparty risk — so a high
reading is an *invitation to look*, never free money.
"""

from __future__ import annotations

import json
import os
import ssl
import statistics
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class CarryConfig:
    periods_per_day: int = 3          # 8h funding venues (OKX, Binance, Bybit)
    fee_drag_apr: float = 1.9         # ~monthly hedge rebalance fees, annualized %
    min_net_apr: float = 3.0          # net APR at/above this is "attractive"
    min_pct_positive: float = 0.70    # …and funding positive at least this often


@dataclass
class CarryRow:
    coin: str
    venue: str
    gross_apr: float
    net_apr: float
    pct_positive: float
    n: int
    attractive: bool
    note: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def annualize(mean_period_rate: float, periods_per_day: int) -> float:
    """A single-period funding rate -> annualized percent."""
    return mean_period_rate * periods_per_day * 365 * 100


def net_apr(gross_apr: float, cfg: Optional[CarryConfig] = None) -> float:
    return gross_apr - (cfg or CarryConfig()).fee_drag_apr


def realized(rates: List[float], cfg: Optional[CarryConfig] = None) -> dict:
    """Summarize a list of per-period funding rates into the honest decision numbers."""
    c = cfg or CarryConfig()
    if not rates:
        return {"gross_apr": 0.0, "net_apr": 0.0, "pct_positive": 0.0, "n": 0}
    gross = annualize(statistics.mean(rates), c.periods_per_day)
    return {"gross_apr": round(gross, 2), "net_apr": round(net_apr(gross, c), 2),
            "pct_positive": round(sum(1 for r in rates if r > 0) / len(rates), 3),
            "n": len(rates)}


def is_attractive(net_apr_val: float, pct_positive: float, cfg: Optional[CarryConfig] = None) -> bool:
    """Attractive = enough net yield AND persistent (not a one-off spike)."""
    c = cfg or CarryConfig()
    return net_apr_val >= c.min_net_apr and pct_positive >= c.min_pct_positive


def build_row(coin: str, rates: List[float], venue: str = "okx",
              cfg: Optional[CarryConfig] = None) -> CarryRow:
    c = cfg or CarryConfig()
    s = realized(rates, c)
    attr = is_attractive(s["net_apr"], s["pct_positive"], c)
    note = ("" if s["n"] else "no data")
    if s["n"] and not attr:
        note = ("yield below threshold" if s["net_apr"] < c.min_net_apr else "not persistent")
    return CarryRow(coin=coin.upper(), venue=venue, gross_apr=s["gross_apr"],
                    net_apr=s["net_apr"], pct_positive=s["pct_positive"], n=s["n"],
                    attractive=attr, note=note)


def rank(rows: List[CarryRow]) -> List[CarryRow]:
    """Best net carry first; data-less rows sink to the bottom."""
    return sorted(rows, key=lambda r: (r.n > 0, r.net_apr), reverse=True)


# ---- networked fetchers (injectable; not exercised by offline tests) ---------
_CA = "/root/.ccr/ca-bundle.crt"


def _get(url: str):
    ctx = ssl.create_default_context(cafile=_CA) if os.path.exists(_CA) else None
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
        return json.loads(r.read())


def _post(url: str, body: dict):
    ctx = ssl.create_default_context(cafile=_CA) if os.path.exists(_CA) else None
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
        return json.loads(r.read())


def okx_funding_history(inst: str, pages: int = 3) -> List[float]:
    """OKX realized funding (8h) for ~90 days; paged (100/call)."""
    rates: List[float] = []
    before = None
    for _ in range(pages):
        url = f"https://www.okx.com/api/v5/public/funding-rate-history?instId={inst}&limit=100"
        if before:
            url += f"&before={before}"
        data = _get(url).get("data", [])
        if not data:
            break
        rates += [float(x["realizedRate"]) for x in data]
        before = data[-1]["fundingTime"]
    return rates


def hl_cross_section() -> Dict[str, float]:
    """Hyperliquid current funding, annualized % per coin (hourly funding)."""
    meta, ctxs = _post("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
    out: Dict[str, float] = {}
    for a, cx in zip(meta["universe"], ctxs):
        out[a["name"]] = round(float(cx.get("funding") or 0) * 24 * 365 * 100, 1)
    return out


DEFAULT_MAJORS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]


def fetch_carry(coins: Optional[List[str]] = None, cfg: Optional[CarryConfig] = None,
                history_fn: Optional[Callable[[str], List[float]]] = None) -> List[CarryRow]:
    """Assemble ranked CarryRows for `coins` from OKX realized funding (injectable)."""
    c = cfg or CarryConfig()
    coins = coins or DEFAULT_MAJORS
    fetch = history_fn or (lambda sym: okx_funding_history(f"{sym}-USDT-SWAP"))
    rows = []
    for sym in coins:
        try:
            rates = fetch(sym)
        except Exception:  # noqa: BLE001 — one bad coin never breaks the monitor
            rates = []
        rows.append(build_row(sym, rates, venue="okx", cfg=c))
    return rank(rows)
