"""Tests for scripts/kill.py — the one-command kill switch (local layer).

The on-chain pause is Phase 0.2; until it is wired, `on` must exit non-zero so an
operator is never told the on-chain stop is armed when it is not. These tests cover
the local sentinel layer and that contract."""

import importlib.util
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_KILL = os.path.join(os.path.dirname(_HERE), "scripts", "kill.py")
_spec = importlib.util.spec_from_file_location("kill_cli", _KILL)
kill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kill)


def test_engage_then_clear(tmp_path):
    kf = str(tmp_path / "KILL")
    assert kill.is_killed(kf) is False
    kill.engage(kf)
    assert os.path.exists(kf) and kill.is_killed(kf) is True
    assert kill.clear(kf) is True
    assert not os.path.exists(kf) and kill.is_killed(kf) is False
    # Clearing a missing sentinel is a safe no-op.
    assert kill.clear(kf) is False


def test_env_var_forces_killed(tmp_path, monkeypatch):
    kf = str(tmp_path / "KILL")
    monkeypatch.setenv("TB_KILL", "yes")
    assert kill.is_killed(kf) is True              # engaged by env even with no file


def test_main_on_exits_nonzero_until_onchain_wired(tmp_path, monkeypatch):
    kf = str(tmp_path / "KILL")
    monkeypatch.setattr(kill, "DEFAULT_KILL_FILE", kf)
    monkeypatch.delenv("TB_KILL", raising=False)
    # `on` writes the sentinel but returns 3 (on-chain not armed) — never a false green.
    assert kill.main(["kill.py", "on"]) == 3
    assert os.path.exists(kf)
    # `status` is informational and returns 0.
    assert kill.main(["kill.py", "status"]) == 0
    # `off` clears cleanly.
    assert kill.main(["kill.py", "off"]) == 0
    assert not os.path.exists(kf)


def test_main_unknown_action_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(kill, "DEFAULT_KILL_FILE", str(tmp_path / "KILL"))
    assert kill.main(["kill.py", "frobnicate"]) == 2
