"""Arbitrage scanner — same asset, different venues, honest about net edge.

Detects price spreads for one asset across venues (DEX pools / chains) and reports the
edge NET of what it actually costs to capture: both legs' swap fees, a gas/MEV drag
estimate, and a bridge cost when the venues are on different chains.

HONESTY FIRST: on-chain spreads are contested. Same-chain cross-DEX gaps are closed
within the block by MEV searchers running atomic arbs with priority fees you can't
outbid; cross-chain gaps require a bridge (minutes of price risk + fees). So this will
usually report net <= 0 — that is the correct, useful answer, not a failure. It flags a
spread only when the modelled NET edge clears a threshold, and never claims a gross
spread is free money. Detection is real; capture is the hard (often impossible) part.

Pure `find_arbitrage()` (testable offline) + a thin `scan_token()` that pulls a token's
pool prices from GeckoTerminal (injectable). No keys, no orders.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

_GT = "https://api.geckoterminal.com/api/v2/networks/{network}/tokens/{addr}/pools"
_UA = "Mozilla/5.0 tradebot-arb/0.1"


@dataclass
class ArbConfig:
    min_net_bps: float = 10.0        # flag only if modelled NET edge >= this (0.1%)
    default_fee_bps: float = 30.0    # per-leg DEX fee if a venue doesn't specify (0.3%)
    gas_mev_bps: float = 10.0        # round-trip gas + MEV-competition drag (bps of notional)
    bridge_bps: float = 30.0         # extra cost when the two legs are on different chains


@dataclass
class ArbOpportunity:
    asset: str
    buy_venue: str
    sell_venue: str
    buy_price: float
    sell_price: float
    gross_bps: float
    net_bps: float
    tradeable: bool
    reason: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def find_arbitrage(asset: str, quotes: Sequence[dict], cfg: Optional[ArbConfig] = None,
                   bridge_bps_fn: Optional[Callable[[str, str, str], Optional[float]]] = None
                   ) -> ArbOpportunity:
    """Best buy-low/sell-high across venues, net of costs. `quotes`: list of
    {venue, price, chain?, fee_bps?}. Returns an ArbOpportunity (tradeable only when the
    modelled NET edge clears min_net_bps).

    When the two legs are on different chains the bridge cost is normally the static
    `cfg.bridge_bps` ASSUMPTION. Pass `bridge_bps_fn(asset, buy_chain, sell_chain)` to
    replace that with a LIVE measurement (e.g. a NEAR Intents dry quote) — if it returns
    a number that value is used; if it returns None or raises we fall back to the
    assumption. That turns "cross-chain arb probably doesn't clear a guessed 1% bridge"
    into "…doesn't clear the real 28 bps move cost we just measured."
    """
    c = cfg or ArbConfig()
    valid = [q for q in quotes if float(q.get("price", 0) or 0) > 0]
    if len(valid) < 2:
        return ArbOpportunity(asset, "", "", 0.0, 0.0, 0.0, 0.0, False, "need >=2 venue prices")
    buy = min(valid, key=lambda q: q["price"])
    sell = max(valid, key=lambda q: q["price"])
    if sell["price"] <= buy["price"]:
        return ArbOpportunity(asset, buy.get("venue", "?"), sell.get("venue", "?"),
                              buy["price"], sell["price"], 0.0, 0.0, False, "no spread")
    gross_bps = (sell["price"] - buy["price"]) / buy["price"] * 1e4
    fees = float(buy.get("fee_bps", c.default_fee_bps)) + float(sell.get("fee_bps", c.default_fee_bps))
    cross = bool(buy.get("chain") and sell.get("chain") and buy["chain"] != sell["chain"])
    bridge = 0.0
    bridge_src = ""
    if cross:
        bridge = c.bridge_bps
        bridge_src = "est"
        if bridge_bps_fn is not None:
            try:
                live = bridge_bps_fn(asset, buy["chain"], sell["chain"])
                if live is not None and float(live) >= 0:
                    bridge = float(live)
                    bridge_src = "live"
            except Exception:  # noqa: BLE001 — a live probe must never break scanning
                pass
    net_bps = gross_bps - fees - c.gas_mev_bps - bridge
    tradeable = net_bps >= c.min_net_bps
    reason = (f"buy {buy.get('venue','?')} @ {buy['price']:.6g} → sell {sell.get('venue','?')} "
              f"@ {sell['price']:.6g}: gross {gross_bps:.0f}bps, net {net_bps:.0f}bps"
              f"{f' (cross-chain +{bridge:.0f}bps bridge {bridge_src})' if cross else ''}")
    return ArbOpportunity(asset, buy.get("venue", "?"), sell.get("venue", "?"),
                          buy["price"], sell["price"], round(gross_bps, 1), round(net_bps, 1),
                          tradeable, reason)


def _fetch_token_pools(network: str, addr: str) -> dict:
    url = _GT.format(network=network, addr=addr) + "?include=dex"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def scan_token(asset: str, network: str, token_addr: str,
               cfg: Optional[ArbConfig] = None, fetch: Optional[Callable] = None,
               min_reserve_usd: float = 100_000.0) -> ArbOpportunity:
    """Pull a token's pools on `network` and scan cross-DEX spread. Only pools with
    enough depth are counted (a thin pool's price isn't a real venue). `fetch` injectable."""
    fetch = fetch or _fetch_token_pools
    try:
        pj = fetch(network, token_addr)
    except Exception as e:  # noqa: BLE001
        return ArbOpportunity(asset, "", "", 0.0, 0.0, 0.0, 0.0, False, f"fetch failed: {str(e)[:60]}")
    quotes: List[dict] = []
    for pool in pj.get("data", []) or []:
        a = pool.get("attributes", {}) or {}
        price = float(a.get("base_token_price_usd") or 0.0)
        reserve = float(a.get("reserve_in_usd") or 0.0)
        if price > 0 and reserve >= min_reserve_usd:
            quotes.append({"venue": (a.get("name") or "pool").split()[0], "price": price,
                           "chain": network})
    return find_arbitrage(asset, quotes, cfg)
