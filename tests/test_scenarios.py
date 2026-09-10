"""Tests for the scenario library + shadow comparison."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot import scenarios as sc
from tradebot.ohlcv import Bar


def _bars(closes):
    return [Bar(i * 86_400_000, c, c * 1.01, c * 0.99, c, 1000.0) for i, c in enumerate(closes)]


def _series():
    # deterministic uptrend -> dip -> recovery, long enough for the trend filter
    closes = []
    p = 100.0
    for i in range(300):
        p *= 1.004 if i < 120 else (0.99 if i < 170 else 1.005)
        closes.append(p)
    return _bars(closes)


def test_library_keys_unique_and_default_present():
    keys = [s.key for s in sc.LIBRARY]
    assert len(keys) == len(set(keys))          # unique
    assert sc.DEFAULT_KEY in keys
    assert sc.by_key(sc.DEFAULT_KEY) is not None
    assert sc.by_key("nope") is None


def test_run_scenario_shape():
    row = sc.run_scenario(sc.by_key("steady"), _series(), starting_cash=1000)
    for k in ("key", "name", "return", "sharpe", "max_drawdown", "reserve_frac",
              "final_total", "risk_level"):
        assert k in row
    assert row["final_total"] > 0


def test_compare_sorted_and_complete():
    rows = sc.compare(_series(), starting_cash=1000)
    assert len(rows) == len(sc.LIBRARY)                 # one row per scenario
    returns = [r["return"] for r in rows]
    assert returns == sorted(returns, reverse=True)     # best first


def test_scenarios_actually_differ():
    rows = {r["key"]: r for r in sc.compare(_series(), starting_cash=1000)}
    # Guardian protects harder than Runner -> banks a larger reserve fraction
    assert rows["guardian"]["reserve_frac"] >= rows["runner"]["reserve_frac"]
    # the profiles are not all identical
    assert len({r["final_total"] for r in rows.values()}) > 1


def test_config_is_paper_and_carries_params():
    scn = sc.by_key("guardian")
    cfg = scn.config(starting_cash=500)
    assert cfg.mode == "paper" and cfg.starting_cash == 500
    assert cfg.risk.atr_stop_mult == 2.0             # scenario param flowed through
