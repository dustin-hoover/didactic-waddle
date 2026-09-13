"""Base tradeable-universe expander — auto-vet which Base tokens are safe to trade.

The execution registry ships with a tiny hand-vetted allowlist (USDC/WETH/cbBTC).
That was never a ceiling — it's just what was verified by hand. This module widens it
SAFELY: it reads live on-chain DEX depth on Base (GeckoTerminal, no key) and keeps
only tokens that clear objective bars, so a scam token squatting a ticker or an
illiquid ghost never lands in the tradeable set.

A token qualifies when it:
  * has real on-chain DEPTH — its deepest Base pool reserve >= `min_reserve_usd`
    (at a $100 trade even a $250k pool slips ~0.04%, so depth is about *fill quality*
    and legitimacy, not capacity),
  * is LISTED/tracked on CoinGecko (has a coin id) — a basic legitimacy signal that
    filters most anonymous rug tokens,
  * is not a stablecoin (those are the quote leg, not a directional trade), and
  * isn't on the explicit blocklist. An allowlist can force-include a known-good name.

The vetting core (`vet_candidates`) is pure and testable; `discover_base` is the thin
network wrapper (injectable) that fetches the pools. Output feeds two places: a
`docs/universe.json` the dashboard shows, and `execution.register_tokens()` so the
engine can actually build proposals for the vetted set.

HONEST LIMITS: "listed + liquid" is a coarse safety screen, not a contract audit. A
deeper on-chain rug-screen for Base (owner powers, mint, proxy — safety.py, but on
chainid 8453) is a worthwhile follow-up; until then treat the long tail with care and
keep the per-order caps small. Depth/volume are live and move — re-run to refresh.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

_GT = "https://api.geckoterminal.com/api/v2/networks/{network}/pools"
_UA = "Mozilla/5.0 tradebot-universe/0.1"

# Stables / pegged units are the quote leg, never a directional position.
STABLES = {"USDC", "USDT", "DAI", "USDE", "USDBC", "GHO", "EURC", "USDS", "USD+",
           "USDA", "USAD", "CRVUSD", "LUSD", "FRAX", "USD0", "DOLA", "MIM"}


@dataclass
class TokenCandidate:
    symbol: str
    address: str
    decimals: Optional[int]
    reserve_usd: float          # deepest single-pool reserve seen
    vol24_usd: float            # summed 24h volume across its pools
    n_pools: int
    coingecko_id: Optional[str]


@dataclass
class VettedToken:
    symbol: str
    address: str
    decimals: int
    reserve_usd: float
    vol24_usd: float
    n_pools: int
    coingecko_id: Optional[str]
    safety_verdict: Optional[str] = None   # OK | CAUTION | AVOID | UNKNOWN (rug-screen)
    safety_risk: Optional[int] = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def vet_candidates(cands: Sequence[TokenCandidate], min_reserve_usd: float = 250_000.0,
                   min_pools: int = 1, require_listed: bool = True,
                   allow: Sequence[str] = (), block: Sequence[str] = ()) -> List[VettedToken]:
    """Pure filter: keep only tokens that clear the safety/liquidity bars. Dedups by
    upper-cased symbol (keeps the deepest), sorts by reserve desc."""
    allow_u = {s.upper() for s in allow}
    block_u = {s.upper() for s in block}
    best: Dict[str, VettedToken] = {}
    for c in cands:
        sym = (c.symbol or "").upper()
        if not sym or c.address is None or c.decimals is None:
            continue
        if sym in block_u:
            continue
        forced = sym in allow_u
        if not forced:
            if sym in STABLES:
                continue
            if c.reserve_usd < min_reserve_usd or c.n_pools < min_pools:
                continue
            if require_listed and not c.coingecko_id:
                continue
        # EVM addresses are case-insensitive (normalize to lower); Solana mints are
        # base58 and CASE-SENSITIVE, so never lowercase a non-0x address.
        addr = c.address.lower() if c.address.lower().startswith("0x") else c.address
        vt = VettedToken(sym, addr, int(c.decimals), round(c.reserve_usd, 2),
                         round(c.vol24_usd, 2), c.n_pools, c.coingecko_id)
        cur = best.get(sym)
        if cur is None or vt.reserve_usd > cur.reserve_usd:
            best[sym] = vt
    return sorted(best.values(), key=lambda v: v.reserve_usd, reverse=True)


def screen_vetted(vetted: Sequence[VettedToken], screen_fn: Callable,
                  drop: Sequence[str] = ("AVOID",)) -> List[VettedToken]:
    """Run a rug-screen over vetted tokens: annotate verdict/risk, drop confirmed-bad.

    HONEST policy: we only DROP a token on a confirmed-bad verdict (default AVOID).
    UNKNOWN (no API key, unverified, or non-contract) is NEVER a rejection — you can't
    gate on missing data — so those pass through annotated as UNKNOWN. `screen_fn` is
    injectable (tests); production passes safety.check(addr, chain="base").
    """
    drop_u = {d.upper() for d in drop}
    out: List[VettedToken] = []
    for v in vetted:
        try:
            rep = screen_fn(v.address)
            v.safety_verdict = getattr(rep, "verdict", None)
            v.safety_risk = getattr(rep, "risk_score", None)
        except Exception:  # noqa: BLE001 — a failed screen must not silently drop a token
            v.safety_verdict = "UNKNOWN"
        if (v.safety_verdict or "").upper() in drop_u:
            continue
        out.append(v)
    return out


def _fetch_page(page: int, network: str = "base", tries: int = 4) -> dict:
    """One page of top pools. Retries with backoff — GeckoTerminal's free tier
    rate-limits (~30/min), and a single 429 shouldn't wipe the whole discovery."""
    base = _GT.format(network=network)
    url = f"{base}?include=base_token&sort=h24_volume_usd_desc&page={page}"
    last: Optional[Exception] = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"geckoterminal {network} p{page}: {last}")


def _candidates_from_pages(pages_json: Sequence[dict]) -> List[TokenCandidate]:
    """Aggregate GeckoTerminal pool pages into per-token candidates."""
    info: Dict[str, dict] = {}          # token id -> attributes (address, symbol, decimals, cg id)
    agg: Dict[str, Dict] = {}           # token id -> aggregated stats
    for pj in pages_json:
        for inc in pj.get("included", []) or []:
            if inc.get("type") == "token":
                info[inc["id"]] = inc.get("attributes", {}) or {}
        for pool in pj.get("data", []) or []:
            attrs = pool.get("attributes", {}) or {}
            rel = ((pool.get("relationships", {}) or {}).get("base_token", {}) or {}).get("data", {}) or {}
            tid = rel.get("id")
            if not tid:
                continue
            reserve = float(attrs.get("reserve_in_usd") or 0.0)
            vol = float((attrs.get("volume_usd", {}) or {}).get("h24") or 0.0)
            a = agg.setdefault(tid, {"reserve": 0.0, "vol": 0.0, "n": 0})
            a["reserve"] = max(a["reserve"], reserve)
            a["vol"] += vol
            a["n"] += 1
    out: List[TokenCandidate] = []
    for tid, a in agg.items():
        meta = info.get(tid, {})
        addr = meta.get("address") or (tid.split("_", 1)[1] if "_" in tid else None)
        dec = meta.get("decimals")
        out.append(TokenCandidate(
            symbol=(meta.get("symbol") or "").upper(), address=addr,
            decimals=dec, reserve_usd=a["reserve"], vol24_usd=a["vol"],
            n_pools=a["n"], coingecko_id=meta.get("coingecko_coin_id") or None))
    return out


def discover(network: str = "base", pages: int = 3, min_reserve_usd: float = 250_000.0,
             fetch: Optional[Callable[..., dict]] = None,
             allow: Sequence[str] = (), block: Sequence[str] = (),
             screen: bool = False, screen_fn: Optional[Callable] = None,
             screen_chain: Optional[str] = None) -> List[VettedToken]:
    """Fetch a chain's top pools (by 24h volume), aggregate per token, and vet. When
    ``screen`` is on, also run the on-chain rug-screen and drop confirmed-bad tokens.

    Chain-agnostic: `network` is the GeckoTerminal network id (base, solana, eth, …).
    `fetch(page, network)` and `screen_fn(address)` are injectable so tests skip the
    network. Base58 (Solana) addresses are preserved case-sensitively by the vetter.
    """
    fetch = fetch or _fetch_page
    pages_json = []
    for p in range(1, pages + 1):
        try:
            try:
                pj = fetch(p, network)
            except TypeError:                   # injected fetch(page) with no network arg
                pj = fetch(p)
            pages_json.append(pj)
        except Exception:  # noqa: BLE001 — partial pages are fine
            break
        if p < pages and fetch is _fetch_page:
            time.sleep(0.5)                     # pace real requests under the rate limit
    cands = _candidates_from_pages(pages_json)
    vetted = vet_candidates(cands, min_reserve_usd=min_reserve_usd, allow=allow, block=block)
    if screen:
        if screen_fn is None:
            from .safety import check as _check
            sc = screen_chain or network
            screen_fn = lambda a: _check(a, chain=sc)  # noqa: E731
        vetted = screen_vetted(vetted, screen_fn)
    return vetted


def discover_base(pages: int = 3, min_reserve_usd: float = 250_000.0,
                  fetch: Optional[Callable[..., dict]] = None,
                  allow: Sequence[str] = (), block: Sequence[str] = (),
                  screen: bool = False, screen_fn: Optional[Callable] = None) -> List[VettedToken]:
    """Back-compat convenience wrapper: discover on Base."""
    return discover("base", pages=pages, min_reserve_usd=min_reserve_usd, fetch=fetch,
                    allow=allow, block=block, screen=screen, screen_fn=screen_fn,
                    screen_chain="base")


def to_registry(vetted: Sequence[VettedToken]) -> Dict[str, tuple]:
    """Shape the vetted set for execution.register_tokens: {SYMBOL: (address, decimals)}."""
    return {v.symbol: (v.address, v.decimals) for v in vetted}
