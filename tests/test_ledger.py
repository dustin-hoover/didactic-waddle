"""Tests for the bag ledger — the tree's memory of what survived, what died, and why."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.ledger import BagLedger, regime_bucket
from tradebot.bags import Supervisor, SpawnPolicy, RetirePolicy
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


# ---- pure ledger unit tests -------------------------------------------------

def test_regime_bucket_labels():
    assert regime_bucket(None, None) == "unknown"
    assert regime_bucket(False, 0.3) == "bear"
    assert regime_bucket(True, 0.05) == "bull"
    assert regime_bucket(True, 0.20) == "bull_strong"


def test_birth_is_idempotent(tmp_path):
    L = BagLedger(str(tmp_path / "ledger.json"))
    L.record_birth("b1", "steady", "base", 100, regime_on=True, strength=0.2)
    L.record_birth("b1", "steady", "base", 100, regime_on=True, strength=0.2)
    born = [r for r in L.records if r["event"] == "born"]
    assert len(born) == 1 and born[0]["regime_bucket"] == "bull_strong"


def test_outcome_denormalizes_birth_conditions(tmp_path):
    L = BagLedger(str(tmp_path / "ledger.json"))
    L.record_birth("b1", "runner", "solana", 100, regime_on=False, strength=0.0, ts=0)
    L.record_failure("b1", multiple=0.6, final_value=60, ts=90 * 86400)
    rows = L.resolved()
    assert len(rows) == 1
    r = rows[0]
    assert r["success"] is False and r["chain"] == "solana"
    assert r["scenario"] == "runner" and r["regime_bucket"] == "bear"


def test_success_and_failure_markers_are_once(tmp_path):
    L = BagLedger(str(tmp_path / "ledger.json"))
    L.record_birth("b1", "steady", "base", 100, regime_on=True, strength=0.2)
    L.record_success("b1", 2.0, 200)
    L.record_success("b1", 3.0, 300)     # second reproduction — not double-counted
    assert sum(1 for r in L.records if r["event"] == "spawned") == 1


def test_analyze_base_rate_and_open(tmp_path):
    L = BagLedger(str(tmp_path / "ledger.json"))
    # 3 resolved: 2 success, 1 fail; 1 still open (born, no outcome)
    for i in range(3):
        L.record_birth(f"b{i}", "steady", "base", 100, regime_on=True, strength=0.2)
    L.record_success("b0", 2.0, 200)
    L.record_success("b1", 2.0, 200)
    L.record_failure("b2", 0.5, 50)
    L.record_birth("b3", "steady", "base", 100, regime_on=True, strength=0.2)  # open
    a = L.analyze()
    assert a["born"] == 4 and a["resolved"] == 3 and a["open"] == 1
    assert a["base_success_rate"] == round(2 / 3, 3)


def test_lessons_need_min_sample(tmp_path):
    L = BagLedger(str(tmp_path / "ledger.json"))
    L.record_birth("b1", "steady", "base", 100, regime_on=True, strength=0.2)
    L.record_success("b1", 2.0, 200)
    a = L.analyze()                       # only 1 resolved
    assert any("not enough memory" in s for s in a["lessons"])


def test_analyze_flags_weak_regime(tmp_path):
    L = BagLedger(str(tmp_path / "ledger.json"))
    # 6 bull bags all succeed; 6 bear bags all fail -> bear is a clear caution
    for i in range(6):
        L.record_birth(f"u{i}", "steady", "base", 100, regime_on=True, strength=0.2)
        L.record_success(f"u{i}", 2.0, 200)
    for i in range(6):
        L.record_birth(f"d{i}", "steady", "base", 100, regime_on=False, strength=0.0)
        L.record_failure(f"d{i}", 0.5, 50)
    a = L.analyze()
    assert a["by_regime"]["bear"]["rate"] == 0.0
    assert a["by_regime"]["bull_strong"]["rate"] == 1.0
    assert any("bear" in s and "caution" in s for s in a["lessons"])


def test_recommend_insufficient_then_caution(tmp_path):
    L = BagLedger(str(tmp_path / "ledger.json"))
    # too little memory -> insufficient, never gates
    r = L.recommend(chain="solana", regime_on=False, strength=0.0)
    assert r.verdict == "insufficient"
    # build a weak bear track record + a strong bull one
    for i in range(6):
        L.record_birth(f"u{i}", "steady", "base", 100, regime_on=True, strength=0.2)
        L.record_success(f"u{i}", 2.0, 200)
    for i in range(6):
        L.record_birth(f"d{i}", "steady", "solana", 100, regime_on=False, strength=0.0)
        L.record_failure(f"d{i}", 0.5, 50)
    bear = L.recommend(chain="solana", regime_on=False, strength=0.0)
    bull = L.recommend(chain="base", regime_on=True, strength=0.2)
    assert bear.verdict == "caution" and bear.n >= 5
    assert bull.verdict in ("favorable", "neutral")


def test_persistence_roundtrip(tmp_path):
    p = str(tmp_path / "ledger.json")
    L = BagLedger(p)
    L.record_birth("b1", "steady", "base", 100, regime_on=True, strength=0.2)
    L.record_success("b1", 2.0, 200)
    L.save()
    L2 = BagLedger(p)
    assert len(L2.resolved()) == 1 and L2.resolved()[0]["success"] is True


# ---- Supervisor integration -------------------------------------------------

def test_supervisor_records_birth_and_success(tmp_path):
    led = BagLedger(str(tmp_path / "ledger.json"))
    sup = Supervisor(str(tmp_path), SpawnPolicy(trigger_multiple=3.0, fraction=0.5), ledger=led)
    sup._signals = {"regime_on": True, "strength": 0.2}
    spec = sup.add_bag("steady", seed=100)         # birth recorded with regime context
    eng = sup._engine(spec)
    eng.protector.state.reserve = 400.0            # push over the 3x trigger
    eng._save()
    sup._maybe_spawn(spec, eng, price=100.0)       # parent reproduces -> success + child birth
    births = [r for r in led.records if r["event"] == "born"]
    assert len(births) == 2                         # parent + child
    assert births[0]["regime_bucket"] == "bull_strong"
    assert led._has("b1", "spawned")                # parent marked successful


def test_supervisor_records_failure_on_retire(tmp_path):
    led = BagLedger(str(tmp_path / "ledger.json"))
    retire = RetirePolicy(enabled=True, survival_target=1000.0, deadline_days=0.0,
                          grace_days=0.0, keep_min=1)
    sup = Supervisor(str(tmp_path), SpawnPolicy(enabled=False), retire=retire, ledger=led)
    sup._signals = {"regime_on": False, "strength": 0.0}
    sup.add_bag("steady", seed=100)                # strongest, protected
    weak = sup.add_bag("steady", seed=100)         # will be culled (can't 1000x)
    # backdate births so they're past the (zero) deadline
    for r in led.records:
        r["ts"] = 0
    sup._maybe_retire({"b1": 200.0, "b2": 50.0})
    assert "b2" not in sup.specs                    # culled
    fails = [r for r in led.records if r["event"] == "retired"]
    assert len(fails) == 1 and fails[0]["bag"] == "b2"
    assert fails[0]["born_regime_bucket"] == "bear" and "retired" in fails[0]["reason"]


def test_memory_gate_vetoes_weak_spawn(tmp_path):
    led = BagLedger(str(tmp_path / "ledger.json"))
    # seed a weak bear track record on solana so memory will veto a bear/solana spawn
    for i in range(6):
        led.record_birth(f"h{i}", "steady", "base", 100, regime_on=True, strength=0.2)
        led.record_success(f"h{i}", 2.0, 200)
    for i in range(6):
        led.record_birth(f"x{i}", "steady", "solana", 100, regime_on=False, strength=0.0)
        led.record_failure(f"x{i}", 0.5, 50)
    sup = Supervisor(str(tmp_path),
                     SpawnPolicy(trigger_multiple=3.0, fraction=0.5, consult_memory=True),
                     chain_selector=lambda: "solana", ledger=led)
    sup._signals = {"regime_on": False, "strength": 0.0}
    spec = sup.add_bag("steady", seed=100, chain="solana")
    eng = sup._engine(spec)
    eng.protector.state.reserve = 400.0
    eng._save()
    before = len(sup.specs)
    sup._maybe_spawn(spec, eng, price=100.0)
    assert len(sup.specs) == before                 # spawn vetoed
    assert any(r["event"] == "skipped" for r in led.records)
    # reserve was NOT carved (value preserved) because the spawn was blocked
    assert sup._engine(spec).protector.state.reserve == 400.0
