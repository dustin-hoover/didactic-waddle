"""Real market-data feeds: CoinGecko history + live on-chain spot.

Stdlib-only (urllib). Kept separate from data.py so the core stays offline and
unit-testable. Two providers:

  * CoinGeckoFeed   -> real AMPL/USD daily history (for backtesting).
  * OnChainFeed     -> live AMPL/USD spot read directly from Ethereum:
                       Uniswap V2 AMPL/WETH reserves priced in ETH, times a
                       Chainlink ETH/USD feed. No third-party API key needed,
                       just a JSON-RPC endpoint.

On-chain history is intentionally not implemented: a single public RPC node
can't cheaply serve historical spot without an archive node + per-block calls.
Use CoinGecko (or a CSV) for history; use OnChainFeed for the live tick.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .data import PriceBar

# ---- Ethereum mainnet addresses (well-known, verifiable on Etherscan) --------
AMPL_TOKEN = "0xd46ba6d942050d489dbd938a2c909a5d5039a161"  # 9 decimals
UNIV2_AMPL_WETH = "0xc5be99A02C6857f9Eac67BbCE58DF5572498F40c"
CHAINLINK_ETH_USD = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"  # 8 decimals

# Function selectors (first 4 bytes of keccak256 of the signature).
SEL_TOKEN0 = "0x0dfe1681"       # token0()
SEL_GET_RESERVES = "0x0902f1ac"  # getReserves()
SEL_LATEST_ANSWER = "0x50d25bcd"  # latestAnswer()

DEFAULT_RPCS = [
    "https://ethereum-rpc.publicnode.com",
    "https://eth.drpc.org",
    "https://rpc.mevblocker.io",
]
_UA = "Mozilla/5.0 ampl-bot/0.1"


def _http_json(url: str, data: Optional[bytes] = None, tries: int = 4, timeout: int = 30) -> dict:
    """GET (data=None) or POST a JSON request with exponential-backoff retry."""
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last: Optional[Exception] = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001 - retry on any transient failure
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"request to {url} failed after {tries} tries: {last}")


# ------------------------------ CoinGecko -------------------------------------
class CoinGeckoFeed:
    """Real AMPL/USD daily history from CoinGecko's public API."""

    BASE = "https://api.coingecko.com/api/v3"

    def __init__(self, coin_id: str = "ampleforth", vs: str = "usd", api_key: Optional[str] = None):
        self.coin_id = coin_id
        self.vs = vs
        self.api_key = api_key  # optional CoinGecko demo/pro key

    def history(self, days: int | str = 365) -> List[PriceBar]:
        # Note: without an API key the public API caps history at ~365 days and
        # auto-returns daily granularity for ranges > 90 days, so we do NOT send
        # `interval` (enterprise-only) and instead reduce to one bar per day.
        url = (
            f"{self.BASE}/coins/{self.coin_id}/market_chart"
            f"?vs_currency={self.vs}&days={days}"
        )
        if self.api_key:
            url += f"&x_cg_demo_api_key={self.api_key}"
        payload = _http_json(url)
        prices = payload.get("prices", [])
        # Reduce to one bar per UTC date (last observation of the day).
        by_date: Dict[str, float] = {}
        for ts_ms, price in prices:
            date = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
            by_date[date] = float(price)
        return [PriceBar(d, p) for d, p in sorted(by_date.items())]

    def latest(self) -> PriceBar:
        bars = self.history(days=1)
        if not bars:
            raise RuntimeError("CoinGecko returned no data")
        return bars[-1]


# ------------------------------ On-chain --------------------------------------
class OnChainFeed:
    """Live AMPL/USD spot read directly from Ethereum mainnet.

    price = (WETH_reserve / AMPL_reserve) * ETH_USD  from the Uniswap V2
    AMPL/WETH pool and the Chainlink ETH/USD aggregator.
    """

    def __init__(
        self,
        rpc_urls: Optional[List[str]] = None,
        pair: str = UNIV2_AMPL_WETH,
        ampl_token: str = AMPL_TOKEN,
        eth_usd_feed: str = CHAINLINK_ETH_USD,
    ):
        self.rpc_urls = rpc_urls or list(DEFAULT_RPCS)
        self.pair = pair
        self.ampl_token = ampl_token.lower()
        self.eth_usd_feed = eth_usd_feed

    def _eth_call(self, to: str, data: str) -> str:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
             "params": [{"to": to, "data": data}, "latest"]}
        ).encode()
        last: Optional[Exception] = None
        for url in self.rpc_urls:
            try:
                resp = _http_json(url, data=body, tries=2)
                if "result" in resp:
                    return resp["result"]
                last = RuntimeError(str(resp.get("error", resp)))
            except Exception as e:  # noqa: BLE001 - try the next endpoint
                last = e
        raise RuntimeError(f"all RPC endpoints failed: {last}")

    def spot_price(self) -> float:
        token0 = "0x" + self._eth_call(self.pair, SEL_TOKEN0)[-40:]
        raw = self._eth_call(self.pair, SEL_GET_RESERVES)[2:]
        reserve0 = int(raw[0:64], 16)
        reserve1 = int(raw[64:128], 16)
        ampl_is_token0 = token0.lower() == self.ampl_token
        ampl_reserve = reserve0 if ampl_is_token0 else reserve1  # 9 decimals
        weth_reserve = reserve1 if ampl_is_token0 else reserve0  # 18 decimals
        if ampl_reserve == 0:
            raise RuntimeError("empty AMPL reserve")
        eth_per_ampl = (weth_reserve / 1e18) / (ampl_reserve / 1e9)

        eth_usd = int(self._eth_call(self.eth_usd_feed, SEL_LATEST_ANSWER), 16) / 1e8
        return eth_per_ampl * eth_usd

    def latest(self) -> PriceBar:
        ts = datetime.now(tz=timezone.utc).isoformat()
        return PriceBar(ts, round(self.spot_price(), 6))

    def history(self) -> List[PriceBar]:  # pragma: no cover - intentional
        raise NotImplementedError(
            "On-chain historical spot needs an archive node + per-block calls. "
            "Use CoinGeckoFeed or a CSV for history; OnChainFeed serves the live tick."
        )
