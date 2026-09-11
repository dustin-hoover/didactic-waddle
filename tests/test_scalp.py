"""Tests for the scalp-suite scaffold (PHASE 6). Pure ranking + hard gates.

Everything here runs offline: we feed fake tape scores and fake safety verdicts
into rank_candidates()/scan(), so no RPC or Etherscan call is ever made.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.scalp import ScalpConfig, rank_candidates, scan


@dataclass
class FakeScore:
    """Duck-types tape.TapeScore for the attrs rank_candidates reads."""
    symbol: str
    score: float = 0.0
    whale_share: float = 0.0
    net_usd: float = 0.0
    total_usd: float = 0.0
    price: float = 0.0
    error: Optional[str] = None


@dataclass
class FakeSafety:
    verdict: str = "OK"
    risk_score: int = 5


def _strong(sym="PEPE", score=0.6):
    # A clean, liquid, whale-backed accumulation setup.
    return FakeScore(sym, score=score, whale_share=0.5, net_usd=120_000,
                     total_usd=400_000, price=0.0000012)


def _cfg(**kw):
    return ScalpConfig(**kw)


def test_disabled_layer_never_enters():
    cands = rank_candidates([_strong()], {"PEPE": FakeSafety()}, _cfg(enabled=False))
    assert cands[0].action != "enter"
    assert cands[0].blocked == "disabled"


def test_clean_setup_enters_but_dry_run_not_signable():
    cfg = _cfg(enabled=True, live=False)
    c = rank_candidates([_strong()], {"PEPE": FakeSafety()}, cfg)[0]
    assert c.action == "enter" and c.signable is False
    assert c.notional_usd == cfg.per_trade_usd
    assert c.take_profit > c.price > c.stop_loss
    assert "DRY-RUN" in c.reason


def test_live_but_unvalidated_still_not_signable():
    # The whole point of the validated gate: live alone must not sign.
    c = rank_candidates([_strong()], {"PEPE": FakeSafety()},
                        _cfg(enabled=True, live=True, validated=False))[0]
    assert c.action == "enter" and c.signable is False
    assert "UNVALIDATED" in c.reason


def test_validated_and_live_is_signable():
    c = rank_candidates([_strong()], {"PEPE": FakeSafety()},
                        _cfg(enabled=True, live=True, validated=True))[0]
    assert c.action == "enter" and c.signable is True
    assert "SIGNABLE" in c.reason


def test_weak_conviction_skips():
    weak = FakeScore("UNI", score=0.10, whale_share=0.5, total_usd=400_000, price=7.0)
    c = rank_candidates([weak], {"UNI": FakeSafety()}, _cfg(enabled=True))[0]
    assert c.action == "skip" and "conviction" in c.reason


def test_low_whale_share_skips():
    s = FakeScore("LINK", score=0.6, whale_share=0.05, total_usd=400_000, price=15.0)
    c = rank_candidates([s], {"LINK": FakeSafety()}, _cfg(enabled=True))[0]
    assert c.action == "skip" and "whale share" in c.reason


def test_thin_window_is_watch_not_enter():
    s = FakeScore("LDO", score=0.6, whale_share=0.5, total_usd=1_000, price=2.0)
    c = rank_candidates([s], {"LDO": FakeSafety()}, _cfg(enabled=True))[0]
    assert c.action == "watch" and c.blocked == "illiquid-window"


def test_failed_rug_screen_blocks_entry():
    c = rank_candidates([_strong("SHIB")], {"SHIB": FakeSafety(verdict="AVOID", risk_score=80)},
                        _cfg(enabled=True))[0]
    assert c.action == "watch" and c.blocked == "failed-safety-screen"
    assert "AVOID" in c.reason


def test_unscreened_token_is_unknown_and_blocked():
    # No entry in screens → UNKNOWN → never treated as OK.
    c = rank_candidates([_strong("AAVE")], {}, _cfg(enabled=True))[0]
    assert c.action == "watch" and c.safety_verdict == "UNKNOWN"
    assert c.blocked == "failed-safety-screen"


def test_distribution_is_long_only_watch():
    dist = FakeScore("PEPE", score=-0.6, whale_share=0.5, total_usd=400_000, price=0.000001)
    c = rank_candidates([dist], {"PEPE": FakeSafety()}, _cfg(enabled=True))[0]
    assert c.side == "exit" and c.action == "watch" and c.blocked == "short-only-signal"


def test_tape_error_reports_no_read():
    c = rank_candidates([FakeScore("MATIC", error="rpc timeout")], {}, _cfg(enabled=True))[0]
    assert c.action == "skip" and "no read" in c.reason


def test_enters_ranked_ahead_of_skips():
    scores = [
        FakeScore("UNI", score=0.10, whale_share=0.5, total_usd=400_000, price=7.0),  # weak → skip
        _strong("PEPE", score=0.7),                                                   # strong → enter
    ]
    screens = {"UNI": FakeSafety(), "PEPE": FakeSafety()}
    ranked = rank_candidates(scores, screens, _cfg(enabled=True))
    assert ranked[0].symbol == "PEPE" and ranked[0].action == "enter"


def test_scan_injects_fetchers_and_only_screens_directional():
    """scan() must use injected fetchers (no network) and skip screening weak names."""
    universe = ("PEPE", "UNI")
    tape = {
        "PEPE": _strong("PEPE", score=0.7),
        "UNI": FakeScore("UNI", score=0.05, whale_share=0.5, total_usd=400_000, price=7.0),
    }
    screened = []

    def fake_read(sym, blocks):
        assert blocks == 300
        return tape[sym]

    def fake_screen(sym):
        screened.append(sym)
        return FakeSafety()

    cfg = ScalpConfig(enabled=True, universe=universe)
    cands = scan(cfg, read_tape_fn=fake_read, screen_fn=fake_screen)
    # Only PEPE cleared the min_score bar, so only PEPE should have been screened.
    assert screened == ["PEPE"]
    top = {c.symbol: c for c in cands}
    assert top["PEPE"].action == "enter"
    assert top["UNI"].action == "skip"
