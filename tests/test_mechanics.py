import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ampl_bot.mechanics import (
    PolicyParams,
    apply_rebase_to_balance,
    compute_rebase,
    deviation,
    market_zone,
)


def test_dead_band_no_rebase():
    p = PolicyParams(target_price=1.0, deviation_threshold=0.05, rebase_lag=30)
    r = compute_rebase(1.02, 1_000_000, p)  # within +/-5%
    assert r.in_dead_band
    assert r.rebase_pct == 0.0
    assert r.new_supply == 1_000_000


def test_positive_rebase_above_band():
    p = PolicyParams(target_price=1.0, deviation_threshold=0.05, rebase_lag=30)
    r = compute_rebase(1.30, 1_000_000, p)  # +30% deviation
    assert not r.in_dead_band
    assert r.rebase_pct > 0
    # 0.30 / 30 = 0.01
    assert abs(r.rebase_pct - 0.01) < 1e-9
    assert r.new_supply > 1_000_000


def test_negative_rebase_below_band():
    p = PolicyParams(target_price=1.0, deviation_threshold=0.05, rebase_lag=30)
    r = compute_rebase(0.70, 1_000_000, p)
    assert r.rebase_pct < 0
    assert r.new_supply < 1_000_000


def test_rebase_clamp():
    p = PolicyParams(target_price=1.0, deviation_threshold=0.05, rebase_lag=1, max_rebase_pct=0.10)
    r = compute_rebase(2.0, 1_000_000, p)  # +100% dev / lag 1 = 1.0, clamped to 0.10
    assert abs(r.rebase_pct - 0.10) < 1e-9


def test_balance_scales_with_rebase():
    p = PolicyParams(target_price=1.0, rebase_lag=30)
    r = compute_rebase(1.30, 1.0, p)
    assert apply_rebase_to_balance(100.0, r) == 100.0 * (1.0 + r.rebase_pct)


def test_zones():
    p = PolicyParams(target_price=1.0, deviation_threshold=0.05)
    assert market_zone(1.20, p) == "expansion"
    assert market_zone(0.80, p) == "contraction"
    assert market_zone(1.00, p) == "equilibrium"


def test_deviation_sign():
    p = PolicyParams(target_price=1.0)
    assert deviation(1.1, p) > 0
    assert deviation(0.9, p) < 0
