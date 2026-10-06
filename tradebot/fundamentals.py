"""Opportunity screener — rank the top-100–150 by REAL quality, not price hype.

The doctrine: BTC is the market-bullishness gate (see tradebot.regime); within a
confirmed bull, we want to own the best *quality* names across the board, chosen
systematically and without impulse. "Quality" here is deliberately the opposite of
the momentum-rotation idea we tested and killed — it's grounded in tangible,
hard-to-fake signals:

  * USAGE      — do people actually pay to use it? DeFi TVL + protocol fees
                 (DefiLlama). Real economic weight, far harder to fake than tx counts.
  * LIQUIDITY  — can we actually trade it without moving the price? 24h volume.
  * TREND      — don't fight the tape; the validated trend filter's current read.
  * SAFETY     — a hard filter: drop anything the rug-screen flags AVOID.

Each factor is RANK-NORMALIZED across the universe (percentile in [0,1]) — robust to
crypto's fat tails, where a z-score would let one outlier dominate. The composite is
a weighted sum; the board is sorted by it. The BTC regime gate governs whether we'd
ACT on the ranking (open new longs), never the ranking itself.

HONEST LIMITS (v1): usage leans on TVL/fees, which favors coins with real DeFi/L1
ecosystems — a defensible bias ("real-world usage"), not a bug, but it under-credits
non-DeFi use. Social following is deliberately omitted (free feeds are deprecated;
it's also often a lagging/contrarian signal). And this ranks on CURRENT fundamentals
— it is a disciplined CANDIDATE GENERATOR, not yet a proven-edge strategy, until a
point-in-time backtest (Phase 2) validates that trading the top-N actually beats
BTC-only on risk-adjusted terms. Pure scoring here is offline-testable; the network
fetchers are injectable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# Symbols we never treat as opportunities: stablecoins and wrapped/pegged proxies
# (they top the mcap list but aren't "trades"). Extend as needed.
_EXCLUDE = {
    "USDT", "USDC", "USDS", "DAI", "TUSD", "FDUSD", "USDE", "PYUSD", "USD1", "BUSD",
    "USDG", "USR", "USDF", "USDD", "GUSD", "LUSD", "FRAX", "USDX", "RLUSD", "USDY", "USDO",
    "WBTC", "WETH", "WBT", "CBBTC", "BTCB", "WEETH", "WSTETH", "STETH", "RETH",
    "LEO", "WBETH", "WBETH", "SUSDE", "BSC-USD",
}


@dataclass
class CoinMetrics:
    symbol: str
    coingecko_id: str = ""
    mcap_rank: Optional[int] = None
    mcap_usd: float = 0.0
    vol24_usd: float = 0.0
    tvl_usd: Optional[float] = None       # DefiLlama protocol/chain TVL (usage)
    fees24_usd: Optional[float] = None    # DefiLlama 24h fees (usage; harder to fake)
    trend_strength: Optional[float] = None  # momentum factor in ~[-1,1] (injected)
    safety_verdict: Optional[str] = None  # "OK"|"CAUTION"|"AVOID"|"UNKNOWN"|None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ScoreWeights:
    usage: float = 0.40        # TVL + fees (real economic usage)
    liquidity: float = 0.25    # 24h volume (tradeability)
    trend: float = 0.35        # current trend read (don't fight the tape)


def _pct_ranks(vals: List[Optional[float]]) -> List[float]:
    """Percentile rank in [0,1] for each value; None -> 0 (missing = no credit).

    Robust to fat tails: we rank, not z-score. Ties share the average rank.
    """
    present = [(i, v) for i, v in enumerate(vals) if v is not None]
    out = [0.0] * len(vals)
    n = len(present)
    if n == 0:
        return out
    if n == 1:
        out[present[0][0]] = 1.0
        return out
    order = sorted(present, key=lambda kv: kv[1])
    # average-rank for ties
    i = 0
    while i < n:
        j = i
        while j + 1 < n and order[j + 1][1] == order[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0
        for k in range(i, j + 1):
            out[order[k][0]] = avg_rank / (n - 1)
        i = j + 1
    return out


def _log_or_none(x: Optional[float]) -> Optional[float]:
    if x is None or x <= 0:
        return None
    return math.log10(x)


def rank(coins: List[CoinMetrics], weights: Optional[ScoreWeights] = None,
         max_rank: int = 150, min_vol_usd: float = 5_000_000.0,
         drop_avoid: bool = True, top_n: int = 25) -> List[dict]:
    """Score and rank a universe by composite quality. Returns ranked rows (best first).

    Hard filters applied first (these are gates, not score penalties): excluded
    symbols (stables/wrapped), market-cap rank beyond ``max_rank``, 24h volume below
    ``min_vol_usd``, and — when ``drop_avoid`` — anything the rug-screen flagged AVOID.
    Then each factor is rank-normalized across the survivors and combined.
    """
    w = weights or ScoreWeights()
    elig = []
    for c in coins:
        if c.symbol.upper() in _EXCLUDE:
            continue
        if c.mcap_rank is not None and c.mcap_rank > max_rank:
            continue
        if c.vol24_usd < min_vol_usd:
            continue
        if drop_avoid and (c.safety_verdict or "").upper() == "AVOID":
            continue
        elig.append(c)
    if not elig:
        return []

    # Usage = blend of TVL and fees (whichever present), each rank-normalized.
    tvl_r = _pct_ranks([_log_or_none(c.tvl_usd) for c in elig])
    fee_r = _pct_ranks([_log_or_none(c.fees24_usd) for c in elig])
    liq_r = _pct_ranks([_log_or_none(c.vol24_usd) for c in elig])
    # Trend: map strength ~[-1,1] -> [0,1]; missing -> neutral 0.5 (don't punish a
    # coin for an un-measured trend the way we punish un-measured usage).
    trend_vals = [None if c.trend_strength is None else max(-1.0, min(1.0, c.trend_strength))
                  for c in elig]
    trend_r = [0.5 if v is None else (v + 1.0) / 2.0 for v in trend_vals]

    rows = []
    for i, c in enumerate(elig):
        has_tvl, has_fee = c.tvl_usd not in (None, 0), c.fees24_usd not in (None, 0)
        if has_tvl and has_fee:
            usage = 0.6 * tvl_r[i] + 0.4 * fee_r[i]
        elif has_tvl:
            usage = tvl_r[i]
        elif has_fee:
            usage = fee_r[i]
        else:
            usage = 0.0                      # no measurable usage -> no usage credit
        composite = w.usage * usage + w.liquidity * liq_r[i] + w.trend * trend_r[i]
        rows.append({
            "symbol": c.symbol.upper(), "coingecko_id": c.coingecko_id,
            "mcap_rank": c.mcap_rank, "mcap_usd": round(c.mcap_usd),
            "vol24_usd": round(c.vol24_usd), "tvl_usd": (round(c.tvl_usd) if c.tvl_usd else None),
            "fees24_usd": (round(c.fees24_usd) if c.fees24_usd else None),
            "safety_verdict": c.safety_verdict,
            "usage_score": round(usage, 3), "liquidity_score": round(liq_r[i], 3),
            "trend_score": round(trend_r[i], 3), "score": round(composite, 4),
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:top_n]


# ---- networked assembly (injectable; not exercised by offline tests) ---------
def fetch_universe(markets_fn: Optional[Callable[[], List[dict]]] = None,
                   tvl_fn: Optional[Callable[[], Dict[str, float]]] = None,
                   fees_fn: Optional[Callable[[], Dict[str, float]]] = None
                   ) -> List[CoinMetrics]:
    """Assemble CoinMetrics from CoinGecko markets + DefiLlama TVL/fees (by gecko id).

    Each *_fn is injectable so this stays testable and the data sources are swappable.
    Defaults use the module's thin HTTP fetchers (CoinGecko markets, DefiLlama).
    Trend + safety are layered on later by the runner (they need price history /
    an on-chain screen and only matter for the shortlist).
    """
    markets = (markets_fn or _cg_markets)()
    tvl_by_id = (tvl_fn or _llama_tvl_by_gecko)() if tvl_fn is not False else {}
    fees_by_id = (fees_fn or _llama_fees_by_gecko)() if fees_fn is not False else {}
    out: List[CoinMetrics] = []
    for m in markets:
        gid = m.get("id", "")
        out.append(CoinMetrics(
            symbol=(m.get("symbol") or "").upper(), coingecko_id=gid,
            mcap_rank=m.get("market_cap_rank"), mcap_usd=float(m.get("market_cap") or 0),
            vol24_usd=float(m.get("total_volume") or 0),
            tvl_usd=tvl_by_id.get(gid), fees24_usd=fees_by_id.get(gid)))
    return out


_UA = "Mozilla/5.0 (compatible; saatgut-screen/1.0)"


def _http_json(url: str):
    import json
    import os
    import ssl
    import urllib.request
    ca = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
    ctx = ssl.create_default_context(cafile=ca) if os.path.exists(ca) else None
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read())


def _cg_markets(pages: int = 1, per_page: int = 150) -> List[dict]:
    import os
    key = os.environ.get("COINGECKO_API_KEY", "").strip()
    base = "https://api.coingecko.com/api/v3/coins/markets"
    suffix = f"?vs_currency=usd&order=market_cap_desc&per_page={per_page}&page=1"
    url = base + suffix + (f"&x_cg_demo_api_key={key}" if key else "")
    return _http_json(url)


_PROTOCOLS_CACHE: Optional[List[dict]] = None


def _llama_protocols() -> List[dict]:
    """DefiLlama /protocols (big; memoized for the process)."""
    global _PROTOCOLS_CACHE
    if _PROTOCOLS_CACHE is None:
        _PROTOCOLS_CACHE = _http_json("https://api.llama.fi/protocols")
    return _PROTOCOLS_CACHE


def _llama_tvl_by_gecko() -> Dict[str, float]:
    """{gecko_id: TVL}. Credits BOTH a project's protocol TVL AND, for L1/L2 tokens,
    their whole chain's ecosystem TVL — so ETH gets Ethereum, SOL gets Solana, not
    just DeFi-protocol tokens. This is the 'real-world usage' signal done fairly."""
    out: Dict[str, float] = {}
    for p in _llama_protocols():                      # per-protocol TVL (AAVE, LDO, …)
        gid = p.get("gecko_id")
        if gid and p.get("tvl"):
            out[gid] = out.get(gid, 0.0) + float(p["tvl"])
    try:                                              # per-chain TVL (ETH, SOL, BNB, …)
        for ch in _http_json("https://api.llama.fi/v2/chains"):
            gid = ch.get("gecko_id")
            if gid and ch.get("tvl"):
                out[gid] = out.get(gid, 0.0) + float(ch["tvl"])
    except Exception:  # noqa: BLE001
        pass
    return out


def _llama_fees_by_gecko() -> Dict[str, float]:
    """{gecko_id: 24h fees}. The fees feed has no gecko_id, so join it to /protocols
    by slug to recover one (covers protocol tokens like UNI/AAVE)."""
    slug_to_gecko = {p.get("slug"): p.get("gecko_id")
                     for p in _llama_protocols() if p.get("slug") and p.get("gecko_id")}
    out: Dict[str, float] = {}
    d = _http_json("https://api.llama.fi/overview/fees"
                   "?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true")
    for p in d.get("protocols", []) or []:
        gid = p.get("gecko_id") or slug_to_gecko.get(p.get("slug"))
        if gid and p.get("total24h"):
            out[gid] = out.get(gid, 0.0) + float(p["total24h"])
    return out
