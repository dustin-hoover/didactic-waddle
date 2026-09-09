"""On-chain / decentralized price data — no centralized exchange in the path.

For operators who want to stay off CEXs and keep everything on-chain. Live price
follows a trustlessness gradient, purest first:
  * LIVE price  -> DIRECT Uniswap V3 pool read (slot0) via your own RPC — no
                   aggregator at all — CROSS-CHECKED against the Chainlink oracle
                   (if the pool spot and the oracle disagree beyond a tolerance,
                   a sign of a thin/manipulated pool, we fall back to the oracle).
                   Then Chainlink alone, then DefiLlama's current price.
  * HISTORY     -> DefiLlama's coin price chart, which is sourced from on-chain
                   DEX liquidity (not CEX order books). Daily close granularity.
                   (Fully trustless history would need your own archive node or a
                   subgraph; DefiLlama is the practical on-chain-sourced option.)

Honest tradeoffs vs. the CEX feeds:
  * Free on-chain history is DAILY CLOSE only — no intraday OHLC or volume. The
    validated daily trend strategy works fine on this; intraday backtesting does
    not. So on-chain mode is a 1d-interval mode.
  * A single DEX pool's spot can be thin/manipulable; Chainlink oracles (a
    decentralized network aggregating many sources) avoid that for majors.
  * Reads need a JSON-RPC endpoint. Public ones work but are rate-limited — set
    ETH_RPC_URL to your own (e.g. a QuickNode endpoint) for reliability.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .ohlcv import Bar, cg_resolve_id

_UA = "Mozilla/5.0 tradebot-onchain/0.1"

# Verified Ethereum-mainnet Chainlink USD feeds (8 decimals, latestAnswer).
CHAINLINK_USD = {
    "BTC": "0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",
    "ETH": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "SOL": "0x4ffC43a60e009B551865A93d232E33Fce9f01507",
    "BNB": "0x14e613AC84a31f709eadbdF89C6CC390fDc9540A",
    "AVAX": "0xFF3EEb22B5E3dE6e705b44749C2559d704923FD7",
    "LINK": "0x2c1d072e956AFFC0D435Cb7AC38EF18d24d9127c",
    "UNI": "0x553303d460EE0afB37EdFf9bE42922D8FF63220e",
    "AAVE": "0x547a514d5e3769680Ce22B2361c10Ea13619e8a9",
    "MATIC": "0x7bAC85A8a13A4BcD8abb3eB7d6b4d632c5a57676",
}


def _rpc_urls() -> List[str]:
    urls = []
    env = os.environ.get("ETH_RPC_URL", "").strip()
    if env:
        urls.append(env)  # e.g. your QuickNode/Alchemy endpoint
    urls += ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"]
    return urls


def _http_json(url: str, data: Optional[bytes] = None, tries: int = 3, timeout: int = 25):
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def _eth_call(to: str, data: str) -> Optional[str]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": data}, "latest"]}).encode()
    for url in _rpc_urls():
        try:
            resp = _http_json(url, data=body, tries=1)
            if "result" in resp:
                return resp["result"]
        except Exception:  # noqa: BLE001
            continue
    return None


# ---- Direct Uniswap V3 pool reads (purest: your RPC, no aggregator) ----------
# Token decimals for the USD/quote legs we price against.
_TOKEN_DEC = {
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 6,   # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7": 6,   # USDT
    "0x6b175474e89094c44da98b954eedeac495271d0f": 18,  # DAI
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": 18,  # WETH
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": 8,   # WBTC
}
_USD_TOKENS = {"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
               "0xdac17f958d2ee523a2206206994597c13d831ec7",
               "0x6b175474e89094c44da98b954eedeac495271d0f"}
_WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
# Deep, canonical Uniswap V3 pools (verified against Chainlink).
_V3_POOLS = {
    "ETH": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",  # WETH/USDC 0.05%
    "BTC": "0x99ac8ca7087fa4a2a1fb6357269965a2014abc35",  # WBTC/USDC 0.3%
}


def _erc20_decimals(addr: str) -> Optional[int]:
    if addr in _TOKEN_DEC:
        return _TOKEN_DEC[addr]
    res = _eth_call(addr, "0x313ce567")  # decimals()
    return int(res, 16) if res and res != "0x" else None


def _v3_pool_price_usd(pool: str) -> Optional[float]:
    """USD price of the non-quote token in a Uniswap V3 pool, read directly."""
    t0 = ("0x" + (_eth_call(pool, "0x0dfe1681") or "")[-40:]).lower()  # token0()
    t1 = ("0x" + (_eth_call(pool, "0xd21220a7") or "")[-40:]).lower()  # token1()
    res = _eth_call(pool, "0x3850c7bd")  # slot0()
    if not res or res == "0x" or len(t0) != 42 or len(t1) != 42:
        return None
    sqrt_p = int(res[2:66], 16)  # sqrtPriceX96 (first word)
    d0, d1 = _erc20_decimals(t0), _erc20_decimals(t1)
    if d0 is None or d1 is None or sqrt_p == 0:
        return None
    p = (sqrt_p / 2 ** 96) ** 2                 # token1_raw / token0_raw
    t0_in_t1 = p * 10 ** (d0 - d1)              # human: 1 token0 in token1
    if t0_in_t1 == 0:
        return None
    t1_in_t0 = 1 / t0_in_t1
    if t1 in _USD_TOKENS:
        return t0_in_t1                          # token0 priced in USD stable
    if t0 in _USD_TOKENS:
        return t1_in_t0                          # token1 priced in USD stable
    if t1 == _WETH:
        eth = v3_price_usd("ETH")
        return t0_in_t1 * eth if eth else None
    if t0 == _WETH:
        eth = v3_price_usd("ETH")
        return t1_in_t0 * eth if eth else None
    return None


def v3_price_usd(symbol: str) -> Optional[float]:
    """Live USD price read DIRECTLY from a Uniswap V3 pool (no aggregator)."""
    pool = _V3_POOLS.get(symbol.upper())
    if not pool:
        return None
    try:
        return _v3_pool_price_usd(pool)
    except Exception:  # noqa: BLE001
        return None


def trustless_price(symbol: str, tolerance: float = 0.03) -> Optional[float]:
    """Direct Uniswap V3 pool price, CROSS-CHECKED against the Chainlink oracle.

    If the pool and the oracle agree within ``tolerance`` we trust the direct pool
    read (most trustless). If they diverge — a sign of a thin/manipulated pool —
    we fall back to the decentralized oracle. If only one is available, use it.
    """
    v3 = v3_price_usd(symbol)
    cl = chainlink_price(symbol)
    if v3 and cl:
        return v3 if abs(v3 - cl) / cl <= tolerance else cl
    return v3 or cl


def chainlink_price(symbol: str) -> Optional[float]:
    """Live USD price from a Chainlink decentralized oracle, or None."""
    addr = CHAINLINK_USD.get(symbol.upper())
    if not addr:
        return None
    res = _eth_call(addr, "0x50d25bcd")  # latestAnswer()
    if not res or res == "0x":
        return None
    return int(res, 16) / 1e8


def defillama_current(base: str) -> Optional[float]:
    cid = cg_resolve_id(base)
    if not cid:
        return None
    try:
        d = _http_json(f"https://coins.llama.fi/prices/current/coingecko:{cid}")
        return float(d["coins"][f"coingecko:{cid}"]["price"])
    except Exception:  # noqa: BLE001
        return None


def defillama_history(base: str, limit: int = 400) -> List[Bar]:
    """Daily close history from DefiLlama (on-chain DEX-sourced). Volume 0."""
    cid = cg_resolve_id(base)
    if not cid:
        return []
    coin = f"coingecko:{cid}"
    day = 86_400
    now = int(time.time())
    start = now - (limit + 3) * day
    by_date: Dict[str, float] = {}
    cursor = start
    for _ in range(12):
        if cursor >= now:
            break
        url = f"https://coins.llama.fi/chart/{coin}?start={cursor}&span=365&period=1d"
        try:
            pts = _http_json(url).get("coins", {}).get(coin, {}).get("prices", [])
        except Exception:  # noqa: BLE001
            break
        if not pts:
            break
        for p in pts:
            d = datetime.fromtimestamp(p["timestamp"], tz=timezone.utc).date().isoformat()
            by_date[d] = float(p["price"])
        last = pts[-1]["timestamp"]
        if last <= cursor:
            break
        cursor = last + day
        time.sleep(0.15)
    bars = [Bar(int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()) * 1000,
                p, p, p, p, 0.0) for d, p in sorted(by_date.items())]
    return bars[-limit:]


class OnChainFeed:
    """Same interface as ExchangeFeed, but sourced on-chain (no CEX). Daily only."""

    def history(self, base: str, interval: str = "1d", limit: int = 400) -> List[Bar]:
        if interval != "1d":
            raise ValueError("on-chain data is daily-only (free on-chain OHLC/volume "
                             "isn't available); use interval='1d' in on-chain mode.")
        bars = defillama_history(base, limit)
        if not bars:
            raise RuntimeError(f"no on-chain history for {base}")
        return bars

    def latest(self, base: str, interval: str = "1d") -> Bar:
        # Purest first: a direct Uniswap V3 pool read cross-checked against the
        # Chainlink oracle; then oracle alone; then the DefiLlama aggregator.
        px = trustless_price(base) or defillama_current(base)
        if px is None:
            raise RuntimeError(f"no on-chain price for {base}")
        ts = int(time.time() * 1000)
        return Bar(ts, px, px, px, px, 0.0)
