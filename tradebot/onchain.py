"""On-chain & market-structure metrics — real data, free public APIs, no key.

These are the "macro/context" signals seasoned traders check before sizing up:
sentiment, liquidity, and where money is hiding. Sources:

  * Fear & Greed index      (alternative.me)         — crowd sentiment
  * Total DeFi TVL          (DefiLlama)              — on-chain liquidity/risk appetite
  * Stablecoin market cap   (DefiLlama)              — dry powder on the sidelines
  * Ethereum gas price      (JSON-RPC eth_gasPrice)  — network demand / congestion

From these we derive a coarse RISK REGIME (risk_on / neutral / risk_off) that can
optionally scale the bot's exposure — e.g. trade smaller when the crowd is greedy
and gas is spiking, lean in when fear is extreme. It is CONTEXT, surfaced for you
and available as an optional gate; it is not a standalone trading signal.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Optional

_UA = "Mozilla/5.0 tradebot/0.2"
_RPCS = ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"]


def _get(url: str, tries: int = 3, timeout: int = 20):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


@dataclass
class OnChainMetrics:
    fear_greed: Optional[int] = None          # 0 (extreme fear) .. 100 (extreme greed)
    fear_greed_label: Optional[str] = None
    defi_tvl_usd: Optional[float] = None
    stablecoin_mcap_usd: Optional[float] = None
    eth_gas_gwei: Optional[float] = None
    risk_regime: str = "neutral"              # risk_on / neutral / risk_off
    notes: Dict[str, str] = field(default_factory=dict)

    def exposure_scale(self) -> float:
        """Multiplier a strategy may apply to its exposure given the regime."""
        return {"risk_on": 1.0, "neutral": 0.85, "risk_off": 0.5}.get(self.risk_regime, 0.85)


def _fear_greed():
    d = _get("https://api.alternative.me/fng/?limit=1")
    row = d["data"][0]
    return int(row["value"]), row.get("value_classification")


def _defi_tvl():
    # Sum current TVL across chains.
    chains = _get("https://api.llama.fi/v2/chains")
    return float(sum(c.get("tvl", 0.0) for c in chains))


def _stablecoin_mcap():
    d = _get("https://stablecoins.llama.fi/stablecoins?includePrices=false")
    total = 0.0
    for s in d.get("peggedAssets", []):
        circ = s.get("circulating", {})
        total += float(circ.get("peggedUSD", 0.0) or 0.0)
    return total


def _eth_gas_gwei():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_gasPrice", "params": []}).encode()
    for url in _RPCS:
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                wei = int(json.loads(r.read())["result"], 16)
                return wei / 1e9
        except Exception:  # noqa: BLE001
            continue
    return None


def fetch() -> OnChainMetrics:
    m = OnChainMetrics()
    for name, fn, attr in [
        ("fear_greed", _fear_greed, None),
        ("defi_tvl", _defi_tvl, "defi_tvl_usd"),
        ("stablecoins", _stablecoin_mcap, "stablecoin_mcap_usd"),
        ("gas", _eth_gas_gwei, "eth_gas_gwei"),
    ]:
        try:
            if name == "fear_greed":
                m.fear_greed, m.fear_greed_label = fn()
            else:
                setattr(m, attr, fn())
        except Exception as e:  # noqa: BLE001 — partial data is fine
            m.notes[name] = f"unavailable: {str(e)[:60]}"

    m.risk_regime = _derive_regime(m)
    return m


# Read-only wallet balances (self-custody view: no keys, no signing).
_ERC20 = {  # symbol: (address, decimals)
    "USDC": ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    "USDT": ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    "WETH": ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
    "AMPL": ("0xd46ba6d942050d489dbd938a2c909a5d5039a161", 9),
    "SPOT": ("0xc1f33e0cf7e40a67375007104b929e49a581bafe", 9),
}


def _rpc(method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for url in _RPCS:
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
                if "result" in d:
                    return d["result"]
        except Exception:  # noqa: BLE001
            continue
    return None


def wallet_balances(address: str) -> Dict[str, float]:
    """ERC-20 + ETH balances for an address. READ ONLY — reads public chain state,
    never touches keys. This is the safe way to 'connect a wallet': view, don't sign.
    """
    address = address.strip().lower()
    if not (address.startswith("0x") and len(address) == 42):
        raise ValueError("expected a 0x… 40-hex-char Ethereum address")
    out: Dict[str, float] = {}
    eth = _rpc("eth_getBalance", [address, "latest"])
    if eth is not None:
        out["ETH"] = int(eth, 16) / 1e18
    for sym, (token, decimals) in _ERC20.items():
        data = "0x70a08231" + "0" * 24 + address[2:]  # balanceOf(address)
        res = _rpc("eth_call", [{"to": token, "data": data}, "latest"])
        if res and res != "0x":
            out[sym] = int(res, 16) / (10 ** decimals)
    return out


def _derive_regime(m: OnChainMetrics) -> str:
    """Coarse, transparent rules. Extreme greed = risk_off (crowd euphoria is
    where tops form); extreme fear = risk_on (contrarian). Gas spikes add caution.
    """
    fg = m.fear_greed
    if fg is None:
        return "neutral"
    if fg >= 78:
        regime = "risk_off"     # extreme greed
    elif fg <= 25:
        regime = "risk_on"      # extreme fear (contrarian)
    elif fg >= 60:
        regime = "neutral"
    else:
        regime = "risk_on" if fg < 45 else "neutral"
    # Congestion caution: very high gas often coincides with frothy conditions.
    if m.eth_gas_gwei and m.eth_gas_gwei > 80 and regime == "risk_on":
        regime = "neutral"
    return regime
