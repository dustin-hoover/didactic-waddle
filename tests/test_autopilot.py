"""Tests for the autopilot decision engine + guardrails (no signing)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.autopilot import Autopilot, AutopilotConfig

PRICES = {"USDC": 1.0, "WETH": 2000.0}
NOW = 1_800_000_000


def _ap(tmp_path, **kw):
    cfg = AutopilotConfig(**kw)
    return Autopilot(cfg, str(tmp_path / "auto.json"))


def test_disabled_holds(tmp_path):
    d = _ap(tmp_path).decide("b1", "0xabc", 1.0, 0.0, 100, "WETH", PRICES, NOW)
    assert d.action == "hold" and "disabled" in d.reason


def test_dryrun_buy_proposes_but_not_live(tmp_path):
    ap = _ap(tmp_path, enabled=True, live=False)
    d = ap.decide("b1", "0xabc", 1.0, 0.0, 100, "WETH", PRICES, NOW)
    assert d.action == "buy" and d.live is False and d.proposal is not None
    assert d.proposal["ok"] is False and "DRY-RUN" in d.reason
    assert abs(d.notional_usd - 100) < 1e-6


def test_live_flag_marks_proposal_signable(tmp_path):
    ap = _ap(tmp_path, enabled=True, live=True, max_notional_usd=100)
    d = ap.decide("b1", "0xabc", 1.0, 0.0, 100, "WETH", PRICES, NOW)
    assert d.live is True and d.proposal["ok"] is True and "LIVE" in d.reason


def test_min_move_holds(tmp_path):
    ap = _ap(tmp_path, enabled=True, min_move_frac=0.10)
    d = ap.decide("b1", "0xabc", 0.55, 0.50, 100, "WETH", PRICES, NOW)   # 5% of equity < 10%
    assert d.action == "hold" and "min move" in d.reason


def test_cooldown_blocks(tmp_path):
    ap = _ap(tmp_path, enabled=True, cooldown_min=60)
    ap.state.last_trade_ts = NOW - 600           # 10 min ago
    d = ap.decide("b1", "0xabc", 1.0, 0.0, 100, "WETH", PRICES, NOW)
    assert d.action == "hold" and d.blocked and "cooldown" in d.blocked


def test_daily_cap_clamps_order(tmp_path):
    ap = _ap(tmp_path, enabled=True, daily_cap_usd=300, max_notional_usd=100)
    import datetime
    ap.state.day = datetime.datetime.fromtimestamp(NOW, tz=datetime.timezone.utc).date().isoformat()
    ap.state.spent_usd = 295                      # only $5 of daily budget left
    d = ap.decide("b1", "0xabc", 1.0, 0.0, 1000, "WETH", PRICES, NOW)
    assert d.action == "buy" and abs(d.notional_usd - 5) < 1e-6         # clamped to remaining
    assert abs(d.proposal["notional_usd"] - 5) < 1e-6


def test_daily_cap_exhausted_blocks(tmp_path):
    ap = _ap(tmp_path, enabled=True, daily_cap_usd=300)
    import datetime
    ap.state.day = datetime.datetime.fromtimestamp(NOW, tz=datetime.timezone.utc).date().isoformat()
    ap.state.spent_usd = 300
    d = ap.decide("b1", "0xabc", 1.0, 0.0, 100, "WETH", PRICES, NOW)
    assert d.action == "hold" and d.blocked == "daily cap reached"


def test_record_fill_updates_ledger_and_persists(tmp_path):
    ap = _ap(tmp_path, enabled=True, live=True)
    ap.record_fill(50.0, NOW)
    assert ap.state.spent_usd == 50.0 and ap.state.trades_today == 1 and ap.state.last_trade_ts == NOW
    # reload from disk
    ap2 = Autopilot(ap.cfg, ap.state_path)
    assert ap2.state.spent_usd == 50.0 and ap2.state.trades_today == 1


def test_day_rolls_over_resets_budget(tmp_path):
    ap = _ap(tmp_path, enabled=True)
    ap.record_fill(200.0, NOW)
    d_next = ap.decide("b1", "0xabc", 1.0, 0.0, 100, "WETH", PRICES, NOW + 2 * 86400)  # 2 days later
    assert ap.state.spent_usd == 0.0            # budget reset on the new day
    assert d_next.action == "buy"
