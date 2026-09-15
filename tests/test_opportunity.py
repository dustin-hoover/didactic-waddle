"""Tests for cross-chain opportunity scoring + cross-chain bag spawning."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.opportunity import best_chain, rank_chains, score_chain
from tradebot.bags import Supervisor, SpawnPolicy


def test_non_executable_scores_zero():
    o = score_chain("x", executable=False, regime_on=True, universe_count=50)
    assert o.tradeable is False and o.score == 0.0


def test_regime_off_scores_zero():
    o = score_chain("base", executable=True, regime_on=False, universe_count=50)
    assert o.tradeable is False and "risk-off" in o.reason


def test_more_breadth_ranks_higher():
    sig = {
        "base":   dict(executable=True, regime_on=True, universe_count=22, vehicle_trend=1.0, avg_liquidity_usd=5e6),
        "solana": dict(executable=True, regime_on=True, universe_count=2,  vehicle_trend=1.0, avg_liquidity_usd=5e6),
    }
    ranked = rank_chains(sig)
    assert ranked[0].chain == "base" and ranked[0].score > ranked[1].score


def test_best_chain_falls_back_when_none_tradeable():
    sig = {"base": dict(executable=False, regime_on=True, universe_count=10),
           "solana": dict(executable=True, regime_on=False, universe_count=10)}
    assert best_chain(sig, default="base") == "base"   # none qualify -> default


def test_best_chain_picks_top():
    sig = {"base": dict(executable=True, regime_on=True, universe_count=5, vehicle_trend=0.2),
           "solana": dict(executable=True, regime_on=True, universe_count=40, vehicle_trend=1.0)}
    assert best_chain(sig) == "solana"


def test_cross_chain_spawn_uses_selector(tmp_path):
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_multiple=2.0, fraction=0.5, cross_chain=True),
                     chain_selector=lambda: "solana")
    spec = sup.add_bag("steady", seed=100, chain="base")
    eng = sup._engine(spec)
    eng.protector.state.reserve = 300.0        # over 2x -> spawns
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)
    child = next(s for s in sup.specs.values() if s.parent == "b1")
    assert child.chain == "solana"             # born on the opportunistic chain
    assert sup.spawns[-1]["chain"] == "solana"


def test_spawn_inherits_chain_without_cross_chain(tmp_path):
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_multiple=2.0, fraction=0.5, cross_chain=False),
                     chain_selector=lambda: "solana")
    spec = sup.add_bag("steady", seed=100, chain="base")
    eng = sup._engine(spec)
    eng.protector.state.reserve = 300.0
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)
    child = next(s for s in sup.specs.values() if s.parent == "b1")
    assert child.chain == "base"               # selector ignored when cross_chain off
