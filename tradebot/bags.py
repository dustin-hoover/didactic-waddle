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
    chain: str = "base"               # chain this bag lives on (children can be born elsewhere)
    last_morph_ts: int = 0            # last time this bag changed its own scenario


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
    cross_chain: bool = False         # child is born on the most opportunistic chain (needs a selector)
    consult_memory: bool = False      # let the bag ledger VETO a spawn whose conditions have a weak track record


@dataclass
class RetirePolicy:
    """Natural selection for bags — the honest version of "1000x or it's obsolete".

    A bag must reach ``survival_target`` x its seed by the time it is
    ``deadline_days`` old, or it is RETIRED: removed from the tree, its remaining
    value swept into the strongest surviving bag (value is conserved, never lost).
    ``keep_min`` bags are ALWAYS protected — the strongest survive no matter what —
    so the tree self-prunes toward its best performers instead of vanishing.

    HONESTY: set ``survival_target`` to something reachable (e.g. 1.0 = don't lose
    money, 1.5 = beat a bank). Set it to 1000 and every bag but the single strongest
    is culled the moment it ages past the deadline — a faithful demonstration that a
    "1000x or die" rule terminates almost everything, because ~nothing 1000xes."""
    enabled: bool = False
    survival_target: float = 1.0      # bag must reach >= this multiple of seed to survive
    deadline_days: float = 90.0       # ...by this age (younger bags get a pass)
    grace_days: float = 14.0          # never cull a bag younger than this
    keep_min: int = 1                 # always keep at least this many (the strongest)
    absorb_into_strongest: bool = True  # sweep a retired bag's value into the best survivor


@dataclass
class MorphPolicy:
    """A bag adapts its OWN strategy to the regime — value preserved (only the dials
    change; the bag keeps its holdings and reserve). Defensive in a BTC bear, growth in
    a confirmed bull, aggressive in a strong bull. A cooldown prevents thrash."""
    enabled: bool = False
    cooldown_days: float = 7.0
    bear: str = "guardian"            # BTC regime off -> low-risk
    bull: str = "compounder"          # confirmed bull -> medium growth
    strong_bull: str = "runner"       # strong bull -> high-risk
    strong_threshold: float = 0.15    # BTC this far above its 200d = "strong"


def decide_morph(current: str, regime_on: bool, strength: float,
                 policy: "MorphPolicy") -> tuple:
    """Pure: the scenario a bag should hold given the regime. Returns (target, reason)."""
    if not regime_on:
        return policy.bear, "BTC bear/unconfirmed — morph to defensive"
    if strength >= policy.strong_threshold:
        return policy.strong_bull, f"strong bull (BTC +{strength*100:.0f}% vs 200d) — morph aggressive"
    return policy.bull, "confirmed bull — morph to growth"


class Supervisor:
    def __init__(self, root_dir: str, policy: Optional[SpawnPolicy] = None,
                 retire: Optional["RetirePolicy"] = None,
                 chain_selector: Optional[Callable[[], str]] = None,
                 morph: Optional["MorphPolicy"] = None,
                 ledger: Optional[object] = None):
        self.root = root_dir
        os.makedirs(root_dir, exist_ok=True)
        self.policy = policy or SpawnPolicy()
        self.retire = retire or RetirePolicy()
        self.morph = morph or MorphPolicy()
        # Returns the most opportunistic chain id for a new child (opportunity.best_chain,
        # wired by the runner). Injected so the bag engine stays pure/testable.
        self.chain_selector = chain_selector
        # The tree's MEMORY (tradebot.ledger.BagLedger or None): records births/outcomes
        # so future spawns can consult the track record. Injected; None => no memory kept.
        self.ledger = ledger
        self._signals: dict = {}          # regime context for the current advance() run
        self.specs: Dict[str, BagSpec] = {}
        self.spawns: List[dict] = []
        self.retired: List[dict] = []
        self.morphs: List[dict] = []
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
            self.retired = d.get("retired", [])
            self.morphs = d.get("morphs", [])
        except Exception:  # noqa: BLE001
            self.specs, self.spawns, self.retired, self.morphs = {}, [], [], []

    def _save_index(self) -> None:
        json.dump({"bags": [asdict(s) for s in self.specs.values()], "spawns": self.spawns,
                   "retired": self.retired, "morphs": self.morphs},
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
                parent: Optional[str] = None, bag_id: Optional[str] = None,
                chain: str = "base") -> BagSpec:
        bid = bag_id or self._new_id(parent)
        spec = BagSpec(id=bid, scenario=scenario, seed=float(seed), wallet=wallet,
                       parent=parent, created_ts=int(time.time()), chain=chain)
        self.specs[bid] = spec
        self._engine(spec)._save()      # persist the bag's initial state (seed as cash)
        if self.ledger is not None:     # remember the conditions this bag was born into
            self.ledger.record_birth(
                bid, scenario=scenario, chain=chain, seed=float(seed), parent=parent,
                regime_on=self._signals.get("regime_on"),
                strength=self._signals.get("strength"),
                risk_regime=self._signals.get("risk_regime"))
        self._save_index()
        return spec

    # ---- stepping the whole tree ----------------------------------------
    def advance(self, bars_for: Callable[[str, str], List[Bar]],
                signals: Optional[dict] = None) -> dict:
        """Advance every bag on its scenario's data, then run spawn/retire checks.

        ``bars_for(symbol, interval)`` supplies candles (injected so tests need no
        network). ``signals`` (e.g. {"regime_on": bool, "strength": float}) drives
        morphing when a MorphPolicy is enabled. Returns the full tree snapshot.
        """
        self._signals = signals or {}            # regime context used for births/memory this run
        cache: Dict[str, List[Bar]] = {}
        totals: Dict[str, float] = {}
        for bid, spec in list(self.specs.items()):
            self._maybe_morph(spec, signals)     # adapt strategy BEFORE trading this candle
            scn = scenarios.by_key(spec.scenario) or scenarios.by_key(scenarios.DEFAULT_KEY)
            key = f"{scn.symbol}:{scn.interval}"
            bars = cache.get(key) or cache.setdefault(key, bars_for(scn.symbol, scn.interval))
            if not bars:
                continue
            eng = self._engine(spec)
            eng.advance(bars)
            totals[bid] = eng.protector.total_equity(eng.pf, bars[-1].close)
            self._maybe_spawn(spec, eng, bars[-1].close)
        self._maybe_retire(totals)
        self._save_index()
        if self.ledger is not None:
            self.ledger.save()
        return self.snapshot(bars_for)

    def _maybe_morph(self, spec: BagSpec, signals: Optional[dict]) -> None:
        """Adapt a bag's scenario to the regime (value preserved — the engine state at
        this bag's path carries over; only the strategy dials change). Cooldown-gated."""
        m = self.morph
        if not m.enabled or not signals:
            return
        now = time.time()
        if spec.last_morph_ts and (now - spec.last_morph_ts) < m.cooldown_days * 86400:
            return
        target, reason = decide_morph(spec.scenario, bool(signals.get("regime_on", True)),
                                      float(signals.get("strength", 0.0) or 0.0), m)
        if target and target != spec.scenario and scenarios.by_key(target):
            old = spec.scenario
            spec.scenario = target
            spec.last_morph_ts = int(now)
            self.morphs.append({"ts": int(now), "bag": spec.id, "from": old,
                                "to": target, "reason": reason})

    def _maybe_retire(self, totals: Dict[str, float]) -> None:
        """Cull bags that failed to reach the survival bar by their deadline; the
        strongest always survive (keep_min). A retired bag's value is swept into the
        strongest survivor, so total value is conserved — the strong absorb the weak."""
        r = self.retire
        if not r.enabled or len(self.specs) <= r.keep_min:
            return
        now = time.time()
        ranked = sorted(self.specs.values(), key=lambda s: totals.get(s.id, 0.0), reverse=True)
        protected = {s.id for s in ranked[:max(1, r.keep_min)]}
        strongest = ranked[0]
        for spec in ranked:
            if spec.id in protected or len(self.specs) <= r.keep_min:
                continue
            age_days = (now - spec.created_ts) / 86400.0 if spec.created_ts else 1e9
            if age_days < r.grace_days:
                continue
            total = totals.get(spec.id, 0.0)
            mult = (total / spec.seed) if spec.seed > 0 else 0.0
            if age_days >= r.deadline_days and mult < r.survival_target:
                if r.absorb_into_strongest and strongest.id != spec.id and strongest.id in self.specs:
                    seng = self._engine(strongest)
                    seng.protector.state.reserve += total     # value moves, never minted
                    seng._save()
                reason = (f"retired: reached {mult:.2f}x (< {r.survival_target:.2f}x bar) "
                          f"by {age_days:.0f}d")
                if self.ledger is not None:      # remember the failure + its birth conditions
                    self.ledger.record_failure(spec.id, multiple=mult, final_value=total, reason=reason)
                del self.specs[spec.id]
                try:
                    os.remove(self._state_path(spec.id))
                except OSError:
                    pass
                self.retired.append({"ts": int(now), "bag": spec.id, "seed": spec.seed,
                                     "final_value": round(total, 2), "multiple": round(mult, 3),
                                     "reason": reason,
                                     "absorbed_by": strongest.id if r.absorb_into_strongest else None})

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
        # Cross-chain: a child can be born on the most opportunistic chain (else inherit).
        child_chain = spec.chain
        if p.cross_chain and self.chain_selector is not None:
            try:
                child_chain = self.chain_selector() or spec.chain
            except Exception:  # noqa: BLE001 — a bad selector never blocks reproduction
                child_chain = spec.chain
        child_scenario = p.child_scenario or spec.scenario
        # MEMORY GATE: consult the track record before carving capital into these
        # conditions. A weak history (enough sample, low success) vetoes the spawn so
        # we don't repeat a wasted investment. Advisory-by-default (consult_memory off).
        if p.consult_memory and self.ledger is not None:
            rec = self.ledger.recommend(chain=child_chain, scenario=child_scenario,
                                        regime_on=self._signals.get("regime_on"),
                                        strength=self._signals.get("strength"))
            if getattr(rec, "verdict", "") == "caution":
                self.ledger.record_skip(child_chain, child_scenario,
                                        self._signals.get("regime_on"),
                                        self._signals.get("strength"),
                                        reason="memory veto: " + rec.reason)
                return
        eng.protector.state.reserve -= move       # value moves, it is not minted
        eng._save()
        child = self.add_bag(scenario=child_scenario, seed=move,
                             wallet=spec.wallet, parent=spec.id, chain=child_chain)
        self.spawns.append({"ts": int(time.time()), "parent": spec.id,
                            "child": child.id, "amount": move, "chain": child_chain})
        if self.ledger is not None:               # the parent demonstrably worked — it reproduced
            self.ledger.record_success(spec.id, multiple=(total / spec.seed if spec.seed > 0 else 0.0),
                                       final_value=total)

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
            from . import tax as _tax
            _summ = _tax.summarize(_tax.compute_realized(_tax.trades_from_fills(eng.pf.fills, scn.symbol)))
            _est = _tax.estimate_tax(_summ)
            row = {"id": spec.id, "scenario": spec.scenario, "scenario_name": scn.name,
                   "realized_gain": round(_summ.realized_gain_usd, 2), "est_tax": _est["total_tax"],
                   "wallet": spec.wallet, "parent": spec.parent, "seed": spec.seed,
                   "chain": getattr(spec, "chain", "base"),
                   "symbol": scn.symbol, "created_ts": spec.created_ts,
                   "trading": round(snap["trading_equity"], 2), "reserve": round(snap["reserve"], 2),
                   "total": round(snap["total"], 2), "exposure": snap["exposure"],
                   "total_return": round(snap["total_return"], 4), "trades": snap["trades"],
                   "fitness": round(snap["total"] / spec.seed, 3) if spec.seed > 0 else 0.0,
                   "skims": snap["skims"], "reinvests": snap["reinvests"], "halted": snap["halted"]}
            bags.append(row)
            tot_trading += snap["trading_equity"]
            tot_reserve += snap["reserve"]
            tot_seed += spec.seed if spec.parent is None else 0.0   # only root seeds are external capital
        totals = {"bags": len(bags), "spawns": len(self.spawns), "retired": len(self.retired),
                  "trading": round(tot_trading, 2), "reserve": round(tot_reserve, 2),
                  "total": round(tot_trading + tot_reserve, 2), "external_seed": round(tot_seed, 2),
                  "realized_gain": round(sum(b.get("realized_gain", 0.0) for b in bags), 2),
                  "est_tax": round(sum(b.get("est_tax", 0.0) for b in bags), 2)}
        policy = {"enabled": self.policy.enabled, "trigger_multiple": self.policy.trigger_multiple,
                  "trigger_on": self.policy.trigger_on, "fraction": self.policy.fraction,
                  "child_scenario": self.policy.child_scenario,
                  "retire_enabled": self.retire.enabled, "survival_target": self.retire.survival_target,
                  "deadline_days": self.retire.deadline_days}
        snap = {"bags": bags, "spawns": self.spawns[-50:], "retired": self.retired[-50:],
                "morphs": self.morphs[-50:], "totals": totals, "policy": policy}
        if self.ledger is not None:               # the tree's memory: lessons from what lived/died
            try:
                snap["memory"] = self.ledger.analyze()
            except Exception:  # noqa: BLE001 — memory analysis never blocks the snapshot
                pass
        return snap
