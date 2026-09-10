"""Tests for reproducible bags + fractal spawning."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.bags import BagSpec, Supervisor, SpawnPolicy
from tradebot.ohlcv import Bar


def _bars(n=300, start=100.0, step=1.005):
    p = start
    out = []
    for i in range(n):
        p *= step
        out.append(Bar(i * 86_400_000, p, p * 1.01, p * 0.99, p, 1000.0))
    return out


def _feed(bars):
    return lambda sym, interval: bars


def test_add_bag_persists_spec_and_state(tmp_path):
    sup = Supervisor(str(tmp_path))
    spec = sup.add_bag("steady", seed=1000, wallet="0xabc")
    assert spec.id == "b1" and spec.parent is None
    assert os.path.exists(os.path.join(str(tmp_path), "tree.json"))
    assert os.path.exists(os.path.join(str(tmp_path), "b1.json"))
    # reload from disk -> spec survives
    sup2 = Supervisor(str(tmp_path))
    assert "b1" in sup2.specs and sup2.specs["b1"].wallet == "0xabc"


def test_ids_are_hierarchical(tmp_path):
    sup = Supervisor(str(tmp_path))
    sup.add_bag("steady", 1000)
    sup.add_bag("steady", 1000)
    child = sup.add_bag("steady", 100, parent="b1")
    assert child.id == "b1.1"
    assert sup._new_id(None) == "b3"


def test_advance_runs_and_snapshots(tmp_path):
    sup = Supervisor(str(tmp_path), SpawnPolicy(enabled=False))
    sup.add_bag("steady", 1000)
    snap = sup.advance(_feed(_bars()))
    assert snap["totals"]["bags"] == 1
    assert snap["bags"][0]["total"] > 0


def test_spawn_conserves_value_and_creates_child(tmp_path):
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_multiple=3.0, fraction=0.5))
    spec = sup.add_bag("steady", seed=100)
    eng = sup._engine(spec)
    eng.protector.state.reserve = 400.0        # 4x seed -> over the 3x trigger
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)
    # a child exists, seeded from HALF the reserve
    assert "b1.1" in sup.specs
    child = sup.specs["b1.1"]
    assert child.parent == "b1" and abs(child.seed - 200.0) < 1e-6
    # parent reserve reduced by exactly the moved amount (value conserved, not minted)
    assert abs(eng.protector.state.reserve - 200.0) < 1e-6
    assert len(sup.spawns) == 1 and sup.spawns[0]["amount"] == 200.0


def test_no_spawn_below_trigger(tmp_path):
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_multiple=5.0))
    spec = sup.add_bag("steady", seed=100)
    eng = sup._engine(spec)
    eng.protector.state.reserve = 200.0        # total ~300 < 5x seed (500) -> below trigger
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)
    assert len(sup.specs) == 1 and not sup.spawns


def test_reserve_mode_trigger(tmp_path):
    # explicit reserve-mode: trips only when the reserve itself reaches the multiple
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_on="reserve", trigger_multiple=3.0))
    spec = sup.add_bag("steady", seed=100)
    eng = sup._engine(spec)
    eng.protector.state.reserve = 250.0        # total high, but reserve < 3x seed
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)
    assert not sup.spawns                       # reserve 250 < 300 -> no spawn


def test_spawn_respects_max_bags(tmp_path):
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_multiple=1.0, fraction=0.5, max_bags=1))
    spec = sup.add_bag("steady", seed=100)
    eng = sup._engine(spec)
    eng.protector.state.reserve = 1000.0
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)
    assert len(sup.specs) == 1                 # capped, no child

def test_spawn_milestones_space_out(tmp_path):
    # After one spawn, the next needs the bag to reach trigger**2 x seed.
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_multiple=2.0, fraction=0.5))
    spec = sup.add_bag("steady", seed=100)
    eng = sup._engine(spec)
    eng.protector.state.reserve = 250.0        # total ~350 >= 2x100 -> first spawn
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)
    assert len(sup.spawns) == 1
    # reserve now ~125, total ~225; second milestone is 4x seed (400) -> no spawn
    sup._maybe_spawn(spec, eng, price=100.0)
    assert len(sup.spawns) == 1


def test_child_can_use_different_scenario(tmp_path):
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_multiple=2.0, fraction=0.5,
                                                child_scenario="guardian"))
    spec = sup.add_bag("runner", seed=100)
    eng = sup._engine(spec)
    eng.protector.state.reserve = 300.0
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)
    assert sup.specs["b1.1"].scenario == "guardian"


def test_reproducible_same_spec_same_result(tmp_path):
    b = _bars()
    s1 = Supervisor(str(tmp_path / "a"), SpawnPolicy(enabled=False)); s1.add_bag("steady", 1000)
    s2 = Supervisor(str(tmp_path / "b"), SpawnPolicy(enabled=False)); s2.add_bag("steady", 1000)
    r1 = s1.advance(_feed(b))["bags"][0]
    r2 = s2.advance(_feed(b))["bags"][0]
    assert r1["total"] == r2["total"] and r1["exposure"] == r2["exposure"]
