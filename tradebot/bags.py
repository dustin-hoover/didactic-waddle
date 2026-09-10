"""Bags: reproducible stashes + fractal spawning.

A *bag* is a stash of crypto holdings the model manages. A **BagSpec** is its
reproducible recipe — scenario + seed + wallet + parent — so copying a spec makes
an identical bag (this is the "separate contract" in software form). The
**Supervisor** runs a whole tree of bags and grows it fractally: when a bag's
protected reserve multiplies past a trigger, it carves a slice off into a NEW
smaller child bag running the same model. One stash becomes a tree of stashes,
each accumulating on its own.

Value is conserved on a spawn: the amount that seeds the child is REMOVED from the
parent's protected reserve, never minted — consistent with "never lose money in
total." Everything is paper; a bag's `wallet` is just the address it's associated
with for the UI, never a key.

Persistence: each bag's full engine state lives in `<root>/<id>.json` (the same
format the live paper engine uses), and the tree index (specs + spawn log) in
`<root>/tree.json`, so a scheduled runner advances the whole tree across runs.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional

from . import scenarios
from .engine import TradingEngine
from .ohlcv import Bar


@dataclass
class BagSpec:
    id: str
    scenario: str
    seed: float
    wallet: Optional[str] = None      # 0x address this bag is associated with (UI only)
    parent: Optional[str] = None      # parent bag id; None for a root bag
    created_ts: int = 0


@dataclass
class SpawnPolicy:
    """When and how a bag carves off a child.

    The bag spawns once it has MULTIPLIED — its total value reaches
    ``trigger_multiple`` x its seed (``trigger_on="total"``) — then it carves
    ``fraction`` of its PROTECTED RESERVE into a new smaller child. The child is
    seeded from house money, never from principal or the live position, and the
    amount is removed from the parent (value moves, it is not minted).
    (Set ``trigger_on="reserve"`` to instead trip when the reserve alone reaches
    the multiple — the stricter, original flywheel reading.)"""
    enabled: bool = True
    trigger_multiple: float = 2.0     # spawn when the chosen metric >= trigger_multiple * seed
    trigger_on: str = "total"         # "total" (bag has multiplied) or "reserve"
    fraction: float = 0.5             # move this fraction of the reserve into the child
    max_bags: int = 64                # safety cap on the tree size
    child_scenario: Optional[str] = None   # None -> child inherits the parent's scenario


class Supervisor:
    def __init__(self, root_dir: str, policy: Optional[SpawnPolicy] = None):
        self.root = root_dir
        os.makedirs(root_dir, exist_ok=True)
        self.policy = policy or SpawnPolicy()
        self.specs: Dict[str, BagSpec] = {}
        self.spawns: List[dict] = []
        self._load_index()

    # ---- persistence -----------------------------------------------------
    def _index_path(self) -> str:
        return os.path.join(self.root, "tree.json")

    def _state_path(self, bag_id: str) -> str:
        return os.path.join(self.root, f"{bag_id}.json")

    def _load_index(self) -> None:
        p = self._index_path()
        if not os.path.exists(p):
            return
        try:
            d = json.load(open(p))
            self.specs = {b["id"]: BagSpec(**b) for b in d.get("bags", [])}
            self.spawns = d.get("spawns", [])
        except Exception:  # noqa: BLE001
            self.specs, self.spawns = {}, []

    def _save_index(self) -> None:
        json.dump({"bags": [asdict(s) for s in self.specs.values()], "spawns": self.spawns},
                  open(self._index_path(), "w"), indent=1)

    # ---- bag lifecycle ---------------------------------------------------
    def _engine(self, spec: BagSpec) -> TradingEngine:
        scn = scenarios.by_key(spec.scenario) or scenarios.by_key(scenarios.DEFAULT_KEY)
        cfg = scn.config(starting_cash=spec.seed, state_path=self._state_path(spec.id))
        return TradingEngine(cfg)

    def _new_id(self, parent: Optional[str]) -> str:
        if parent is None:
            n = sum(1 for s in self.specs.values() if s.parent is None)
            return f"b{n + 1}"
        k = sum(1 for s in self.specs.values() if s.parent == parent)
        return f"{parent}.{k + 1}"

    def add_bag(self, scenario: str, seed: float, wallet: Optional[str] = None,
                parent: Optional[str] = None, bag_id: Optional[str] = None) -> BagSpec:
        bid = bag_id or self._new_id(parent)
        spec = BagSpec(id=bid, scenario=scenario, seed=float(seed), wallet=wallet,
                       parent=parent, created_ts=int(time.time()))
        self.specs[bid] = spec
        self._engine(spec)._save()      # persist the bag's initial state (seed as cash)
        self._save_index()
        return spec

    # ---- stepping the whole tree ----------------------------------------
    def advance(self, bars_for: Callable[[str, str], List[Bar]]) -> dict:
        """Advance every bag on its scenario's data, then run the spawn check.

        ``bars_for(symbol, interval)`` supplies candles (injected so tests need no
        network). Returns the full tree snapshot for the UI.
        """
        cache: Dict[str, List[Bar]] = {}
        for bid, spec in list(self.specs.items()):
            scn = scenarios.by_key(spec.scenario) or scenarios.by_key(scenarios.DEFAULT_KEY)
            key = f"{scn.symbol}:{scn.interval}"
            bars = cache.get(key) or cache.setdefault(key, bars_for(scn.symbol, scn.interval))
            if not bars:
                continue
            eng = self._engine(spec)
            eng.advance(bars)
            self._maybe_spawn(spec, eng, bars[-1].close)
        self._save_index()
        return self.snapshot(bars_for)

    def _maybe_spawn(self, spec: BagSpec, eng: TradingEngine, price: float) -> None:
        p = self.policy
        if not p.enabled or len(self.specs) >= p.max_bags:
            return
        reserve = eng.protector.state.reserve
        total = eng.protector.total_equity(eng.pf, price)
        metric = total if p.trigger_on == "total" else reserve
        # Milestone spacing: the Nth child needs the bag to reach trigger**N x seed,
        # so a bag spawns once each time it multiplies AGAIN — not every candle it
        # sits above a fixed line.
        children = sum(1 for s in self.specs.values() if s.parent == spec.id)
        threshold = spec.seed * (p.trigger_multiple ** (children + 1))
        # Need a protected reserve to carve from, and the bag must have multiplied.
        if reserve <= 0 or metric < threshold:
            return
        move = round(p.fraction * reserve, 2)
        if move <= 0:
            return
        eng.protector.state.reserve -= move       # value moves, it is not minted
        eng._save()
        child = self.add_bag(scenario=p.child_scenario or spec.scenario, seed=move,
                             wallet=spec.wallet, parent=spec.id)
        self.spawns.append({"ts": int(time.time()), "parent": spec.id,
                            "child": child.id, "amount": move})

    # ---- reporting -------------------------------------------------------
    def snapshot(self, bars_for: Optional[Callable[[str, str], List[Bar]]] = None) -> dict:
        cache: Dict[str, List[Bar]] = {}
        bags = []
        tot_trading = tot_reserve = tot_seed = 0.0
        for spec in self.specs.values():
            scn = scenarios.by_key(spec.scenario) or scenarios.by_key(scenarios.DEFAULT_KEY)
            price = 0.0
            if bars_for is not None:
                key = f"{scn.symbol}:{scn.interval}"
                bars = cache.get(key) or cache.setdefault(key, bars_for(scn.symbol, scn.interval))
                price = bars[-1].close if bars else 0.0
            eng = self._engine(spec)
            snap = eng.snapshot(price)
            row = {"id": spec.id, "scenario": spec.scenario, "scenario_name": scn.name,
                   "wallet": spec.wallet, "parent": spec.parent, "seed": spec.seed,
                   "symbol": scn.symbol, "created_ts": spec.created_ts,
                   "trading": round(snap["trading_equity"], 2), "reserve": round(snap["reserve"], 2),
                   "total": round(snap["total"], 2), "exposure": snap["exposure"],
                   "total_return": round(snap["total_return"], 4), "trades": snap["trades"],
                   "skims": snap["skims"], "reinvests": snap["reinvests"], "halted": snap["halted"]}
            bags.append(row)
            tot_trading += snap["trading_equity"]
            tot_reserve += snap["reserve"]
            tot_seed += spec.seed if spec.parent is None else 0.0   # only root seeds are external capital
        totals = {"bags": len(bags), "spawns": len(self.spawns),
                  "trading": round(tot_trading, 2), "reserve": round(tot_reserve, 2),
                  "total": round(tot_trading + tot_reserve, 2), "external_seed": round(tot_seed, 2)}
        policy = {"enabled": self.policy.enabled, "trigger_multiple": self.policy.trigger_multiple,
                  "trigger_on": self.policy.trigger_on, "fraction": self.policy.fraction,
                  "child_scenario": self.policy.child_scenario}
        return {"bags": bags, "spawns": self.spawns[-50:], "totals": totals, "policy": policy}
