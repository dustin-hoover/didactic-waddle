"""Tests for the BTC-primary bull-market regime gate (pure logic, offline)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.regime import RegimeConfig, RegimeState, detect, gate, sweep


def _uptrend(n=400, start=100.0, daily=0.004):
    p = start
    out = []
    for _ in range(n):
        out.append(p)
        p *= (1 + daily)
    return out


def _downtrend(n=400, start=1000.0, daily=0.004):
    p = start
    out = []
    for _ in range(n):
        out.append(p)
        p *= (1 - daily)
    return out


def test_insufficient_history_gates_off():
    st = detect([100.0] * 50)  # < 200d
    assert st.on is False and st.confirmed is False and "insufficient" in st.reason


def test_sustained_uptrend_confirms_bull_on():
    st = detect(_uptrend())
    assert st.on is True and st.regime == "bull"
    assert st.pct_above_long > 0 and st.golden_cross is True


def test_sustained_downtrend_gates_off():
    st = detect(_downtrend())
    assert st.on is False and st.regime == "bear"
    assert st.pct_above_long < 0


def test_bull_then_crash_flips_off():
    # 300 up days (bull), then a hard crash — gate should end OFF.
    series = _uptrend(300) + _downtrend(150, start=_uptrend(300)[-1], daily=0.01)
    states = sweep(series)
    assert states[299] is True                       # bull confirmed during the run-up
    assert states[-1] is False                       # broke down after the crash


def test_persistence_blocks_single_day_flip():
    # A long bear with ONE spike above the 200d must NOT turn the gate on.
    series = _downtrend(400)
    series[-1] = series[-1] * 3.0                     # single green spike on the last day
    st = detect(series)
    assert st.on is False                             # one day can't satisfy confirm_days


def test_hysteresis_holds_state_in_the_buffer():
    # Confirm ON in an uptrend, then drift flat right around the 200d line: the gate
    # should HOLD ON (not immediately flip) while inside the buffer band.
    up = _uptrend(360)
    flat = [up[-1]] * 10                              # sit flat near the MA
    states = sweep(up + flat)
    assert states[359] is True and states[-1] is True


def test_manual_override_on_and_off():
    bear = _downtrend(400)
    on = detect(bear, RegimeConfig(mode="on"))
    off = detect(_uptrend(), RegimeConfig(mode="off"))
    assert on.on is True and "forced ON" in on.reason
    assert off.on is False and "forced OFF" in off.reason


def test_gate_applies_master_switch():
    off_state = RegimeState(on=False, regime="bear", mode="auto")
    on_state = RegimeState(on=True, regime="bull", mode="auto")
    exp_off, why_off = gate(1.0, off_state)
    exp_on, why_on = gate(0.8, on_state)
    assert exp_off == 0.0 and "OFF" in why_off
    assert exp_on == 0.8 and "ON" in why_on
