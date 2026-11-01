"""Tests for scripts/cost_report.py and CostModel.from_report wiring (Phase 0.5)."""

import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.config import BotConfig, CostModel
from tradebot.fills import Fill, record_fill
from tradebot.ohlcv import Bar

_HERE = os.path.dirname(os.path.abspath(__file__))
_CR = os.path.join(os.path.dirname(_HERE), "scripts", "cost_report.py")
_spec = importlib.util.spec_from_file_location("cost_report", _CR)
cost_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cost_report)


def test_report_written_with_worse_of_costs(tmp_path):
    fills = str(tmp_path / "fills.jsonl")
    out = str(tmp_path / "cost_model.json")
    # Realized slippage much worse than modelled (7bps default); fee cheaper.
    record_fill(Fill(1, 2, "base", "cow", "USDC", "CBBTC", 100.0, 77000.0, 77300.0,
                     fee_usd=0.02, gas_usd=0.0, slippage_bps=40.0), fills)
    rc = cost_report.main(["cost_report.py", "--fills", fills, "--out", out])
    assert rc == 0 and os.path.exists(out)
    rep = json.loads(open(out).read())
    assert rep["n_ok"] == 1
    # effective = worse-of: slippage from reality (40bps), fee stays modelled (10bps).
    assert abs(rep["effective"]["slippage_frac"] - 0.004) < 1e-9
    assert abs(rep["effective"]["fee_frac"] - 0.001) < 1e-9


def test_report_on_empty_log_equals_modelled(tmp_path):
    out = str(tmp_path / "cost_model.json")
    cost_report.main(["cost_report.py", "--fills", str(tmp_path / "none.jsonl"), "--out", out])
    rep = json.loads(open(out).read())
    assert rep["n_fills"] == 0
    assert rep["effective"] == rep["modelled"]          # honest: no fills, no penalty


def test_backtester_reads_cost_report(tmp_path):
    # A report with costly slippage must change backtest results vs cfg.costs alone.
    out = str(tmp_path / "cost_model.json")
    json.dump({"realized": {"fee_frac": 0.02, "slippage_frac": 0.02}}, open(out, "w"))
    from tradebot.backtest import run_backtest
    bars = [Bar(ts=i * 3600, open=100, high=105, low=95, close=float(100 + i), volume=10)
            for i in range(60)]
    cfg = BotConfig()
    cheap = run_backtest(bars, cfg)                      # modelled costs only
    dear = run_backtest(bars, cfg, cost_report=out)      # worse-of from the report
    # Heavier costs can only reduce (or equal) the strategy return; here it must drop.
    assert dear.strategy_return <= cheap.strategy_return
    # And CostModel.from_report independently yields the worse-of numbers.
    eff = CostModel.from_report(out, base=cfg.costs)
    assert eff.fee_frac == 0.02 and eff.slippage_frac == 0.02


def test_from_report_missing_file_falls_back_to_base():
    base = CostModel(fee_frac=0.003, slippage_frac=0.001)
    eff = CostModel.from_report("/nonexistent/cost_model.json", base=base)
    assert eff == base
