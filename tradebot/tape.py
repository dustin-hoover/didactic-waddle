"""Read the on-chain tape: every DEX block order, scored and ranked.

"Follow the tape, don't just predict." On centralized venues the real order flow
(block trades, OTC, dark pools) is private. On-chain it is PUBLIC: every swap on a
Uniswap V3 pool emits a ``Swap`` event, and large swaps are the whale / desk block
prints. This module reads them directly from a pool via your own RPC — no
aggregator, no CEX — decodes each one, and scores the flow.

For each swap ("block order") we recover, from the event alone:
  * USD size          — the notional that actually traded.
  * direction         — BUY or SELL of the base asset (from the signed amounts).
  * price             — the pool price at that swap (from sqrtPriceX96).
  * price impact      — realized move vs. the previous print (the tape moving).

From a window of prints we compute the numbers desks actually watch:
  * CVD (cumulative volume delta) = net USD bought minus sold — are strong hands
    stepping in or stepping out?
  * whale participation — how much of the flow is large (institutional-size) prints.
  * a tape score in [-1, 1]: signed flow imbalance, weighted by whale share.

``rank_universe`` scans several pools and returns the strongest opportunities of
the window, ranked by conviction. This RANKS and READS the tape; it does not place
orders. Whether the tape actually predicts forward returns is a question for
``scripts/tape_backtest.py`` — we validate before we let flow size a position, per
the capital-preservation rule that the book should never lose money in total.

Honest boundary: this is on-chain DEX flow — real, public, decentralized — but it
is NOT hidden CEX/OTC institutional flow, which no free or on-chain source exposes.
It is one true slice of the order flow, not all of it. Reads need a JSON-RPC
endpoint; set ETH_RPC_URL to your own for reliable, deep log queries (public nodes
cap block ranges and result counts).
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .onchain_feed import (_USD_TOKENS, _V3_POOLS, _WETH, _erc20_decimals,
                           _eth_call, _rpc_urls, v3_price_usd)

_UA = "Mozilla/5.0 tradebot-tape/0.1"

# Pools whose tape we read. Majors are USD-quoted; the long tail trades against
# WETH, so those prints are priced through the live ETH price. All verified on
# mainnet (token0 = base, token1 = quote).
_TAPE_POOLS = {
    "ETH": _V3_POOLS["ETH"],   # USDC/WETH 0.05%
    "BTC": _V3_POOLS["BTC"],   # WBTC/USDC 0.3%
    "UNI": "0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801",   # UNI/WETH 0.3%
    "LINK": "0xa6cc3c2531fdaa6ae1a3ca84c2855806728693e8",  # LINK/WETH 0.3%
    "PEPE": "0x11950d141ecb863f01007add7d1a342041227b58",  # PEPE/WETH 0.3%
    "MATIC": "0x290a6a7460b308ee3f19023d2d00de604bcf5b42", # MATIC/WETH 0.3%
    "SHIB": "0x2f62f2b4c5fcd7570a709dec05d68ea19c82a9ec",  # SHIB/WETH 0.3%
    "LDO": "0xa3f558aebaecaf0e11ca4b2199cc5ed341edfd74",   # LDO/WETH 0.3%
    "AAVE": "0x5ab53ee1d50eef2c1dd3d5402789cd27bb52c1bb",  # AAVE/WETH 0.3%
}

# keccak256("Swap(address,address,int256,int256,uint160,uint128,int24)")
SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"

_SECS_PER_BLOCK = 12.0            # Ethereum mainnet, post-merge (for approx timestamps)
# A "whale"/institutional-size print, in USD. Overridable per call.
DEFAULT_WHALE_USD = 250_000.0


def _rpc(method: str, params: list, timeout: int = 25):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for url in _rpc_urls():
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
                if "result" in d:
                    return d["result"]
                last = d.get("error")
        except Exception as e:  # noqa: BLE001
            last = e
            continue
    raise RuntimeError(f"rpc {method}: {last}")


def latest_block() -> int:
    return int(_rpc("eth_blockNumber", []), 16)


def _to_signed(word: int, bits: int = 256) -> int:
    return word - (1 << bits) if word >= (1 << (bits - 1)) else word


@dataclass
class PoolMeta:
    pool: str
    base_is_token0: bool
    base_dec: int
    quote_dec: int
    quote: str           # "USD" (stable leg) or "WETH" (priced through live ETH)


def pool_meta(pool: str) -> Optional[PoolMeta]:
    """Resolve token ordering + decimals so we can decode swaps for this pool."""
    t0 = ("0x" + (_eth_call(pool, "0x0dfe1681") or "")[-40:]).lower()  # token0()
    t1 = ("0x" + (_eth_call(pool, "0xd21220a7") or "")[-40:]).lower()  # token1()
    if len(t0) != 42 or len(t1) != 42:
        return None
    d0, d1 = _erc20_decimals(t0), _erc20_decimals(t1)
    if d0 is None or d1 is None:
        return None
    if t1 in _USD_TOKENS:
        return PoolMeta(pool, base_is_token0=True, base_dec=d0, quote_dec=d1, quote="USD")
    if t0 in _USD_TOKENS:
        return PoolMeta(pool, base_is_token0=False, base_dec=d1, quote_dec=d0, quote="USD")
    if t1 == _WETH:
        return PoolMeta(pool, base_is_token0=True, base_dec=d0, quote_dec=d1, quote="WETH")
    if t0 == _WETH:
        return PoolMeta(pool, base_is_token0=False, base_dec=d1, quote_dec=d0, quote="WETH")
    return None  # neither leg is a USD stable or WETH — not priced here


@dataclass
class Block:
    """One decoded on-chain swap — a print on the tape."""
    block: int
    tx: str
    usd_size: float
    side: str            # "BUY" or "SELL" of the base asset (taker perspective)
    price: float         # base price in USD at this swap
    price_impact: float = 0.0   # signed % move vs. the previous print (filled by scorer)
    ts: Optional[int] = None    # approx unix seconds

    @property
    def signed_usd(self) -> float:
        return self.usd_size if self.side == "BUY" else -self.usd_size


def decode_swap(meta: PoolMeta, log: dict, eth_price: float = 0.0) -> Optional[Block]:
    """Decode one Uniswap V3 Swap log into a Block (price, size, direction).

    ``eth_price`` (live ETH/USD) is required to price WETH-quoted pools; ignored
    for USD-quoted pools.
    """
    data = log.get("data", "0x")
    raw = data[2:] if data.startswith("0x") else data
    if len(raw) < 5 * 64:
        return None
    words = [int(raw[i * 64:(i + 1) * 64], 16) for i in range(5)]
    amount0 = _to_signed(words[0])
    amount1 = _to_signed(words[1])
    sqrt_p = words[2]                       # uint160, unsigned
    if sqrt_p == 0:
        return None
    p = (sqrt_p / 2 ** 96) ** 2             # token1_raw / token0_raw
    d0 = meta.base_dec if meta.base_is_token0 else meta.quote_dec
    d1 = meta.quote_dec if meta.base_is_token0 else meta.base_dec
    t0_in_t1 = p * 10 ** (d0 - d1)
    if t0_in_t1 == 0:
        return None
    price_in_quote = t0_in_t1 if meta.base_is_token0 else 1 / t0_in_t1  # base per 1 quote token

    base_amt = amount0 if meta.base_is_token0 else amount1     # pool perspective
    quote_amt = amount1 if meta.base_is_token0 else amount0
    quote_size = abs(quote_amt) / 10 ** meta.quote_dec        # in quote-token units
    if meta.quote == "USD":
        price = price_in_quote
        usd_size = quote_size
    else:                                                     # WETH-quoted
        if eth_price <= 0:
            return None
        price = price_in_quote * eth_price                    # base in USD
        usd_size = quote_size * eth_price                     # WETH notional -> USD
    # Pool receiving base (amount>0) == taker SOLD base; pool sending base == taker BOUGHT.
    side = "SELL" if base_amt > 0 else "BUY"

    blk = int(log["blockNumber"], 16) if isinstance(log["blockNumber"], str) else int(log["blockNumber"])
    return Block(block=blk, tx=log.get("transactionHash", ""), usd_size=usd_size,
                 side=side, price=price)


def get_swaps(pool: str, blocks: int = 7200, span: int = 800,
              max_swaps: int = 4000) -> List[Block]:
    """Fetch and decode recent Swap prints for a pool over the last ``blocks``.

    Chunks the range into ``span``-sized windows (public RPCs cap ranges/result
    counts) and stops at ``max_swaps``. ~7200 blocks ≈ one day on mainnet.
    """
    meta = pool_meta(pool)
    if meta is None:
        return []
    eth_price = v3_price_usd("ETH") or 0.0 if meta.quote == "WETH" else 0.0
    tip = latest_block()
    now = time.time()
    start = max(0, tip - blocks)
    out: List[Block] = []
    lo = start
    while lo <= tip and len(out) < max_swaps:
        hi = min(lo + span - 1, tip)
        try:
            logs = _rpc("eth_getLogs", [{
                "address": pool,
                "topics": [SWAP_TOPIC],
                "fromBlock": hex(lo),
                "toBlock": hex(hi),
            }])
        except Exception:  # noqa: BLE001 — shrink and retry once on a range error
            if span > 200:
                span //= 2
                continue
            lo = hi + 1
            continue
        for log in logs or []:
            b = decode_swap(meta, log, eth_price=eth_price)
            if b:
                b.ts = int(now - (tip - b.block) * _SECS_PER_BLOCK)
                out.append(b)
        lo = hi + 1
    out.sort(key=lambda b: b.block)
    return out[:max_swaps]


@dataclass
class TapeScore:
    symbol: str
    pool: str
    n_prints: int
    buy_usd: float
    sell_usd: float
    whale_usd: float             # gross USD from whale-size prints
    largest: Optional[Block]
    score: float                 # [-1, 1]: signed flow imbalance, whale-weighted
    price: float                 # last print price
    error: Optional[str] = None

    @property
    def net_usd(self) -> float:  # CVD: net taker USD (buys - sells)
        return self.buy_usd - self.sell_usd

    @property
    def total_usd(self) -> float:
        return self.buy_usd + self.sell_usd

    @property
    def whale_share(self) -> float:
        return self.whale_usd / self.total_usd if self.total_usd else 0.0

    @property
    def bias(self) -> str:
        return "ACCUMULATION" if self.score > 0.15 else ("DISTRIBUTION" if self.score < -0.15 else "balanced")


def score_blocks(symbol: str, pool: str, blocks: List[Block],
                 whale_usd: float = DEFAULT_WHALE_USD) -> TapeScore:
    """Turn a window of prints into the numbers desks watch: CVD, whale share, score."""
    if not blocks:
        return TapeScore(symbol, pool, 0, 0, 0, 0, None, 0.0, 0.0)
    # Fill realized price impact vs. the previous print.
    prev = blocks[0].price
    for b in blocks:
        b.price_impact = (b.price - prev) / prev * 100 if prev else 0.0
        prev = b.price
    buy = sum(b.usd_size for b in blocks if b.side == "BUY")
    sell = sum(b.usd_size for b in blocks if b.side == "SELL")
    whales = [b for b in blocks if b.usd_size >= whale_usd]
    whale_gross = sum(b.usd_size for b in whales)
    total = buy + sell
    imbalance = (buy - sell) / total if total else 0.0        # [-1, 1]
    # Weight the imbalance up when whales dominate the flow; whale-only net can
    # sharpen the read of where the STRONG hands are.
    whale_net = sum(b.signed_usd for b in whales)
    whale_imb = whale_net / whale_gross if whale_gross else 0.0
    share = (whale_gross / total) if total else 0.0
    score = max(-1.0, min(1.0, imbalance * (1 - share) + whale_imb * share))
    largest = max(blocks, key=lambda b: b.usd_size)
    return TapeScore(symbol, pool, len(blocks), buy, sell, whale_gross, largest,
                     score, blocks[-1].price)


def read_tape(symbol: str, blocks: int = 7200, whale_usd: float = DEFAULT_WHALE_USD) -> TapeScore:
    pool = _TAPE_POOLS.get(symbol.upper())
    if not pool:
        return TapeScore(symbol.upper(), "", 0, 0, 0, 0, None, 0.0, 0.0,
                         error="no configured V3 pool for this symbol")
    try:
        prints = get_swaps(pool, blocks=blocks)
        return score_blocks(symbol.upper(), pool, prints, whale_usd=whale_usd)
    except Exception as e:  # noqa: BLE001
        return TapeScore(symbol.upper(), pool, 0, 0, 0, 0, None, 0.0, 0.0, error=str(e)[:80])


def rank_universe(symbols: Optional[List[str]] = None, blocks: int = 7200,
                  whale_usd: float = DEFAULT_WHALE_USD, top: int = 10) -> List[TapeScore]:
    """Read the tape across a universe and rank the strongest opportunities.

    Conviction = strength of directional flow, so we rank by |score|; the sign
    tells you the side (accumulation = long setup, distribution = exit/avoid).
    """
    syms = symbols or list(_TAPE_POOLS.keys())
    scored = [read_tape(s, blocks=blocks, whale_usd=whale_usd) for s in syms]
    scored.sort(key=lambda t: (t.error is None, abs(t.score), t.total_usd), reverse=True)
    return scored[:top]
