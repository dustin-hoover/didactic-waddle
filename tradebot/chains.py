"""Chain registry — the high-level toggle that makes every service multi-chain.

One place that describes each chain we can operate on and, honestly, WHICH of our
services work there. Chains differ in ways that matter: EVM chains (Base, Ethereum,
Arbitrum…) use 0x addresses, CoW/1inch execution, and an Etherscan rug-screen; Solana
is non-EVM (base58 mints, Jupiter for swaps, no Etherscan) so some capabilities simply
don't exist there yet. Rather than fake uniformity, each ChainSpec declares its
capabilities and the runner does only what a chain actually supports.

Adding a chain = add one ChainSpec entry here (and, for execution, a token registry +
venue adapter). Everything else — universe discovery, the dashboard toggle, capability
gating — reads from this registry, so nothing else needs to change to LIST a new chain.

The active chain is chosen by the CHAIN env var (default "base"); `active()` resolves
it. The BTC regime gate is deliberately chain-agnostic — BTC leads the whole market,
so the same macro switch governs trading on any chain.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ChainSpec:
    id: str                     # our key, e.g. "base", "solana"
    name: str                   # display name
    kind: str                   # "evm" | "svm" (Solana VM)
    gt_network: str             # GeckoTerminal network id for discovery ("" = none)
    native: str                 # native gas asset symbol
    stable: str                 # canonical USD stable on this chain
    rpc_env: str                # env var holding the RPC url (e.g. an Alchemy endpoint)
    explorer: str
    exec_venue: str             # "cow" | "1inch" | "jupiter" | ""
    exec_supported: bool        # is trade execution actually wired for this chain?
    screen_supported: bool      # on-chain rug-screen available?
    screen_chainid: Optional[str]   # Etherscan V2 chainid (EVM only)
    primary_vehicle: str        # the BTC-proxy asset traded here ("" if none)
    enabled: bool = True        # is this chain toggled on / selectable?

    # --- capabilities (what the services may do here) ---
    @property
    def can_discover(self) -> bool:      # auto-vet a tradeable universe
        return bool(self.gt_network)

    @property
    def can_screen(self) -> bool:        # rug-screen tokens
        return self.screen_supported

    @property
    def can_execute(self) -> bool:       # place (or dry-run) real orders
        return self.exec_supported and bool(self.primary_vehicle)

    @property
    def rpc_url(self) -> str:
        return os.environ.get(self.rpc_env, "").strip()

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind,
                "native": self.native, "stable": self.stable, "venue": self.exec_venue,
                "enabled": self.enabled, "can_discover": self.can_discover,
                "can_screen": self.can_screen, "can_execute": self.can_execute,
                "primary_vehicle": self.primary_vehicle, "explorer": self.explorer}


# The registry. Base is fully wired today; Solana is enabled for DATA + UNIVERSE now,
# with execution (Jupiter) and a Solana token-safety screen still to come — declared
# honestly so the toggle never pretends to trade a chain it can't yet.
CHAINS: Dict[str, ChainSpec] = {
    "base": ChainSpec(
        id="base", name="Base", kind="evm", gt_network="base", native="ETH", stable="USDC",
        rpc_env="BASE_RPC_URL", explorer="https://basescan.org", exec_venue="cow",
        exec_supported=True, screen_supported=True, screen_chainid="8453",
        primary_vehicle="CBBTC", enabled=True),
    "solana": ChainSpec(
        id="solana", name="Solana", kind="svm", gt_network="solana", native="SOL", stable="USDC",
        rpc_env="SOLANA_RPC_URL", explorer="https://solscan.io", exec_venue="jupiter",
        exec_supported=False, screen_supported=False, screen_chainid=None,
        primary_vehicle="", enabled=True),
    # --- ready to flip on as you choose them (enabled=False for now) ---
    "ethereum": ChainSpec(
        id="ethereum", name="Ethereum", kind="evm", gt_network="eth", native="ETH", stable="USDC",
        rpc_env="ETH_RPC_URL", explorer="https://etherscan.io", exec_venue="cow",
        exec_supported=False, screen_supported=True, screen_chainid="1",
        primary_vehicle="WBTC", enabled=False),
    "arbitrum": ChainSpec(
        id="arbitrum", name="Arbitrum", kind="evm", gt_network="arbitrum", native="ETH", stable="USDC",
        rpc_env="ARBITRUM_RPC_URL", explorer="https://arbiscan.io", exec_venue="cow",
        exec_supported=False, screen_supported=True, screen_chainid="42161",
        primary_vehicle="WBTC", enabled=False),
}

DEFAULT_CHAIN = "base"


def get(chain_id: str) -> Optional[ChainSpec]:
    return CHAINS.get((chain_id or "").strip().lower())


def active() -> ChainSpec:
    """The toggled-on chain from the CHAIN env var (falls back to Base)."""
    spec = get(os.environ.get("CHAIN", DEFAULT_CHAIN))
    if spec is None or not spec.enabled:
        return CHAINS[DEFAULT_CHAIN]
    return spec


def enabled() -> List[ChainSpec]:
    return [c for c in CHAINS.values() if c.enabled]
