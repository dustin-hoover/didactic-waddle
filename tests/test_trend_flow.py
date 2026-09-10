"""Tests for the trend + flow-overlay experiment (no-lookahead, filter logic)."""

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "trend_flow_test", os.path.join(_HERE, "..", "scripts", "trend_flow_test.py"))
tf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tf)


def _journal(prices, imbs, sym="ETH"):
    days = {}
    for k, (p, i) in enumerate(zip(prices, imbs)):
        days[f"2026-03-{k+1:02d}"] = {sym: {"price": float(p), "imb": float(i)}}
    return {"days": days}


def test_ema_and_stats_basic():
    assert tf._ema([1, 1, 1], 2) == [1, 1, 1]
    s = tf._stats([0.1, -0.05, 0.1])
    assert s["n"] == 3 and s["maxdd"] <= 0 and s["ret"] > 0


def test_accum_filter_reduces_exposure():
    # rising series so trend is up throughout; flip flow sign every other day
    prices = [100 + i for i in range(20)]
    imbs = [0.3 if i % 2 == 0 else -0.3 for i in range(20)]
    books, exposure, total_days, _ = tf.run(_journal(prices, imbs), ema_span=5)
    # accumulation gate must be in-market no more often than plain trend
    assert exposure["trend+accum"] <= exposure["trend"]
    assert total_days > 0


def test_no_lookahead_buyhold_matches_product():
    prices = [100, 110, 99, 120, 118, 130]
    imbs = [0.1] * 6
    books, _, _, _ = tf.run(_journal(prices, imbs), ema_span=2)
    # buy&hold daily returns are exactly the realized next-day moves
    bh = books["buy&hold"]
    expected = [prices[i + 1] / prices[i] - 1 for i in range(len(prices) - 1)]
    assert len(bh) == len(expected)
    for a, b in zip(bh, expected):
        assert abs(a - b) < 1e-9


def test_distexit_flat_on_distribution():
    # trend up, but one day has strong distribution -> that day must be flat
    prices = [100, 101, 102, 103, 104, 105]
    imbs = [0.2, 0.2, -0.9, 0.2, 0.2, 0.2]
    books, _, _, _ = tf.run(_journal(prices, imbs), ema_span=2, dist_thr=0.15)
    # day index 2 (imb -0.9) is a distribution day -> distexit earns 0 that step
    assert books["trend+distexit"][2] == 0.0
