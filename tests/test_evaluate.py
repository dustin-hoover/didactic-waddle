"""Tests for the evaluation harness (Phase 1.2).

Known-answer acceptance (from the action plan):
  * a PURE-NOISE strategy gives PBO at/above 0.5 and DSR below 0.5;
  * a SYNTHETIC PLANTED-EDGE strategy is detected (PBO low, DSR high)."""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tradebot import evaluate as ev


# ---- normal helpers --------------------------------------------------------
def test_norm_cdf_ppf_roundtrip():
    assert abs(ev.norm_cdf(0.0) - 0.5) < 1e-9
    for p in (0.01, 0.25, 0.5, 0.84, 0.99):
        assert abs(ev.norm_cdf(ev.norm_ppf(p)) - p) < 1e-6


# ---- sharpe / moments ------------------------------------------------------
def test_sharpe_zero_when_flat():
    assert ev.sharpe([0.0] * 10) == 0.0


def test_sharpe_positive_for_steady_gains():
    assert ev.sharpe([0.01] * 50 + [0.009, 0.011] * 25) > 0


# ---- splitters -------------------------------------------------------------
def test_walk_forward_expanding_train_fixed_test():
    splits = ev.walk_forward_splits(10, train_min=4, test_size=2)
    assert splits[0] == (list(range(4)), [4, 5])
    assert splits[1] == (list(range(6)), [6, 7])           # train expanded
    for train, test in splits:
        assert max(train) < min(test)                       # train strictly precedes test


def test_cpcv_purge_embargo_removes_boundary_bars():
    splits = ev.cpcv_splits(100, n_groups=5, k_test=2, purge=2, embargo=2)
    assert len(splits) == math.comb(5, 2)
    for train, test in splits:
        assert not (set(train) & set(test))                 # disjoint
        # no train bar sits inside the purge/embargo band immediately around a test bar
        tset = set(test)
        for i in train:
            assert not (i + 1 in tset or i + 2 in tset)      # purge before test
            assert not (i - 1 in tset or i - 2 in tset)      # embargo after test


# ---- DSR -------------------------------------------------------------------
def test_dsr_low_for_noise_high_for_edge():
    rng = random.Random(7)
    noise = [rng.gauss(0.0, 0.01) for _ in range(500)]
    edge = [rng.gauss(0.004, 0.01) for _ in range(500)]     # per-period Sharpe ~0.4
    dsr_noise = ev.deflated_sharpe_ratio(noise, n_trials=200)
    dsr_edge = ev.deflated_sharpe_ratio(edge, n_trials=200)
    assert dsr_noise < 0.5                                   # luck, not skill
    assert dsr_edge > 0.9                                    # real edge survives deflation


def test_expected_max_sharpe_grows_with_trials():
    s = 0.03
    assert ev.expected_max_sharpe(1000, s) > ev.expected_max_sharpe(10, s) > 0


# ---- PBO via CSCV ----------------------------------------------------------
def test_pbo_high_for_noise():
    rng = random.Random(0)
    # 24 pure-noise strategies — selecting the IS-best overfits, so it lands in the
    # OOS bottom half at least half the time (PBO at/above 0.5).
    mat = [[rng.gauss(0.0, 0.01) for _ in range(120)] for _ in range(24)]
    res = ev.pbo_cscv(mat, n_blocks=10)
    assert res.pbo >= 0.5                                    # overfit: no better than a coin flip


def test_pbo_low_for_planted_edge():
    rng = random.Random(13)
    mat = [[rng.gauss(0.0, 0.01) for _ in range(120)] for _ in range(23)]
    # one strategy with a persistent real edge across the whole timeline
    mat.append([rng.gauss(0.006, 0.01) for _ in range(120)])
    res = ev.pbo_cscv(mat, n_blocks=10)
    assert res.pbo < 0.2                                     # the real edge is picked and holds OOS


# ---- equity stats + bootstrap ---------------------------------------------
def test_max_drawdown_and_cagr():
    assert abs(ev.max_drawdown([0.1, -0.5, 0.1]) - 0.5) < 1e-9
    assert ev.cagr([0.0] * 365, periods_per_year=365) == 0.0
    assert ev.cagr([0.01] * 365, 365) > 0


def test_bootstrap_distribution_shape_and_ruin():
    rng = [(-0.6 if i == 0 else 0.0) for i in range(50)]     # a 60% crash then flat
    dist = ev.bootstrap_distribution(rng, n_paths=300, mean_block=5, ruin_dd=0.5, seed=1)
    assert dist.n_paths == 300
    assert 0.0 <= dist.ruin_prob <= 1.0 and dist.ruin_prob > 0  # the crash can breach 50% DD
    assert set(dist.cagr) >= {"p05", "median", "p95"}


def test_bootstrap_preserves_length():
    out = ev.stationary_block_bootstrap([0.01, -0.02, 0.03], mean_block=2,
                                        rng=random.Random(0))
    assert len(out) == 3


# ---- benchmarks ------------------------------------------------------------
def test_sma_rule_flat_before_window_and_reacts():
    closes = [100.0] * 50 + [100.0 + i for i in range(1, 60)]  # flat then uptrend
    r = ev.sma_rule_returns(closes, window=20, fee_frac=0.001)
    assert len(r) == len(closes) - 1
    # during the clean uptrend after the window, the rule is long and makes money
    assert sum(r[-30:]) > 0


def test_buy_hold_returns_match_price_path():
    assert ev.buy_hold_returns([100, 110, 99]) == pytest.approx([0.1, -0.1], rel=1e-9)


# ---- trial registry --------------------------------------------------------
def test_trial_registry_counts_and_dedups(tmp_path):
    reg = ev.TrialRegistry(str(tmp_path / "trials.jsonl"))
    assert reg.count() == 0
    reg.record("hashA", "commit1", {"sharpe": 1.2})
    reg.record("hashA", "commit2", {"sharpe": 1.1})          # same config, re-run
    reg.record("hashB", "commit2", {"sharpe": 0.3})
    assert reg.count() == 3 and reg.distinct_configs() == 2
