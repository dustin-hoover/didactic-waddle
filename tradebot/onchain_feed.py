"""On-chain / decentralized price data — no centralized exchange in the path.

For operators who want to stay off CEXs and keep everything on-chain:
  * LIVE price  -> Chainlink decentralized oracle feeds, read via JSON-RPC
                   (eth_call). Falls back to DefiLlama's current price for coins
                   without a verified feed.
  * HISTORY     -> DefiLlama's coin price chart, which is sourced from on-chain
                   DEX liquidity (not CEX order books). Daily close granularity.

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
        px = chainlink_price(base) or defillama_current(base)
        if px is None:
            raise RuntimeError(f"no on-chain price for {base}")
        ts = int(time.time() * 1000)
        return Bar(ts, px, px, px, px, 0.0)
