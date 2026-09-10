"""Tests for the experimental on-chain flow-confirmation gate in the engine."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.config import BotConfig, StrategyConfig
from tradebot.engine import TradingEngine


def _engine(tmp_path, **strat):
    cfg = BotConfig(mode="paper", symbol="ETH", interval="1d",
                    strategy=StrategyConfig(**strat),
                    state_path=str(tmp_path / "state.json"))
    return TradingEngine(cfg)


class _Score:
    def __init__(self, score):
        self.score = score


def test_gate_off_is_passthrough(tmp_path):
    eng = _engine(tmp_path)                     # flow_confirm defaults False
    assert eng._flow_gate(1.0, 100.0) == (1.0, "")


def test_accum_blocks_when_no_buying(tmp_path, monkeypatch):
    eng = _engine(tmp_path, flow_confirm=True, flow_mode="accum")
    monkeypatch.setattr("tradebot.tape.read_tape", lambda *a, **k: _Score(-0.2))
    target, note = eng._flow_gate(1.0, 100.0)
    assert target == 0.0 and "no accumulation" in note


def test_accum_permits_when_buying(tmp_path, monkeypatch):
    eng = _engine(tmp_path, flow_confirm=True, flow_mode="accum")
    monkeypatch.setattr("tradebot.tape.read_tape", lambda *a, **k: _Score(0.4))
    assert eng._flow_gate(1.0, 100.0) == (1.0, "")


def test_distexit_only_blocks_on_strong_distribution(tmp_path, monkeypatch):
    eng = _engine(tmp_path, flow_confirm=True, flow_mode="distexit", flow_dist_thr=0.15)
    # mild negative -> still permitted
    monkeypatch.setattr("tradebot.tape.read_tape", lambda *a, **k: _Score(-0.1))
    assert eng._flow_gate(1.0, 100.0)[0] == 1.0
    # strong distribution -> stand aside
    monkeypatch.setattr("tradebot.tape.read_tape", lambda *a, **k: _Score(-0.5))
    target, note = eng._flow_gate(1.0, 100.0)
    assert target == 0.0 and "distribution" in note


def test_gate_never_blocks_on_fetch_error(tmp_path, monkeypatch):
    eng = _engine(tmp_path, flow_confirm=True, flow_mode="accum")
    def boom(*a, **k):
        raise RuntimeError("rpc down")
    monkeypatch.setattr("tradebot.tape.read_tape", boom)
    assert eng._flow_gate(1.0, 100.0) == (1.0, "")   # trading is never blocked by a flaky read


def test_gate_ignores_flat_target(tmp_path, monkeypatch):
    eng = _engine(tmp_path, flow_confirm=True, flow_mode="accum")
    # target 0 -> gate is irrelevant, must not even call the tape
    def boom(*a, **k):
        raise AssertionError("should not read tape when already flat")
    monkeypatch.setattr("tradebot.tape.read_tape", boom)
    assert eng._flow_gate(0.0, 100.0) == (0.0, "")
