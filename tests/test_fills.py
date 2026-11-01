"""Tests for Phase 0.5 fill logging + realized-cost reconciliation."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.config import CostModel
from tradebot.fills import (Fill, adverse_slippage_bps, load_fills, realized_costs,
                            record_fill)


def test_record_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "fills.jsonl")
    record_fill(Fill(1.0, 2.0, "base", "cow", "USDC", "CBBTC", 100.0, 77000.0, 77050.0,
                     fee_usd=0.1, gas_usd=0.05, slippage_bps=6.5, latency_s=12.0), path)
    record_fill(Fill(3.0, 4.0, "base", "cow", "USDC", "CBBTC", 100.0, 77000.0, 0.0,
                     ok=False, error="reverted"), path)
    rows = load_fills(path)
    assert len(rows) == 2 and rows[0]["slippage_bps"] == 6.5 and rows[1]["ok"] is False


def test_load_tolerates_missing_and_corrupt(tmp_path):
    assert load_fills(str(tmp_path / "nope.jsonl")) == []
    path = tmp_path / "f.jsonl"
    path.write_text('{"ok": true, "notional_usd": 100}\n{ this is not json\n')
    rows = load_fills(str(path))
    assert len(rows) == 1                               # corrupt line skipped, good one kept


def test_adverse_slippage_direction():
    # Buying above the quote is a cost; buying below is favorable (negative).
    assert adverse_slippage_bps(100.0, 101.0, "buy") == 100.0
    assert adverse_slippage_bps(100.0, 99.0, "buy") == -100.0
    # Selling below the quote is a cost.
    assert adverse_slippage_bps(100.0, 99.0, "sell") == 100.0


def test_realized_costs_over_ok_fills_only():
    fills = [
        {"ok": True, "notional_usd": 100.0, "fee_usd": 0.1, "gas_usd": 0.1, "slippage_bps": 10.0, "latency_s": 5},
        {"ok": True, "notional_usd": 100.0, "fee_usd": 0.3, "gas_usd": 0.1, "slippage_bps": 30.0, "latency_s": 15},
        {"ok": False, "notional_usd": 100.0, "fee_usd": 0.0, "gas_usd": 0.0, "slippage_bps": 0.0},
    ]
    rc = realized_costs(fills)
    assert rc.n_fills == 3 and rc.n_ok == 2 and rc.n_failed == 1
    assert rc.failure_rate == round(1 / 3, 4)
    # median (fee+gas)/notional over the two OK fills = median(0.002, 0.004) = 0.003
    assert abs(rc.fee_frac - 0.003) < 1e-9
    # median adverse slippage = median(10bps, 30bps) = 20bps = 0.002
    assert abs(rc.slippage_frac - 0.002) < 1e-9


def test_negative_slippage_floored_to_zero():
    # A favorable fill is not a cost to budget for.
    rc = realized_costs([{"ok": True, "notional_usd": 100.0, "slippage_bps": -25.0}])
    assert rc.slippage_frac == 0.0


def test_empty_log_gives_zero_costs():
    rc = realized_costs([])
    assert rc.n_fills == 0 and rc.fee_frac == 0.0 and rc.slippage_frac == 0.0


def test_cost_model_worse_of_takes_higher():
    m = CostModel(fee_frac=0.001, slippage_frac=0.0007)
    # Realized fee cheaper, slippage worse -> keep modelled fee, take realized slippage.
    eff = m.worse_of({"fee_frac": 0.0005, "slippage_frac": 0.0025})
    assert eff.fee_frac == 0.001 and eff.slippage_frac == 0.0025
