import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ampl_bot.backtest import run_backtest
from ampl_bot.config import BotConfig
from ampl_bot.data import SyntheticPriceProvider
from ampl_bot.engine import TradingEngine
from ampl_bot.executor import PaperExecutor, Portfolio
from ampl_bot.mechanics import PolicyParams
from ampl_bot.strategy import (
    RebaseMeanReversionStrategy,
    TrendAwareRebaseStrategy,
    build_strategy,
)
from ampl_bot.config import StrategyConfig


def test_build_strategy_factory():
    policy = PolicyParams()
    assert isinstance(build_strategy(StrategyConfig(name="mr"), policy), RebaseMeanReversionStrategy)
    assert isinstance(build_strategy(StrategyConfig(name="trend_mr"), policy), TrendAwareRebaseStrategy)
    raised = False
    try:
        build_strategy(StrategyConfig(name="nope"), policy)
    except ValueError:
        raised = True
    assert raised


def test_trend_mr_falls_back_to_mr_without_history():
    cfg = StrategyConfig(name="trend_mr")
    policy = PolicyParams(target_price=1.0)
    trend = TrendAwareRebaseStrategy(cfg, policy)
    mr = RebaseMeanReversionStrategy(cfg, policy)
    prices = [1.0, 0.9, 1.1]  # far too short for the slow MA
    assert trend.generate(prices).target_exposure == mr.generate(prices).target_exposure


def test_trend_mr_protects_in_confirmed_downtrend():
    cfg = StrategyConfig(name="trend_mr")
    policy = PolicyParams(target_price=1.0)
    trend = TrendAwareRebaseStrategy(cfg, policy)
    mr = RebaseMeanReversionStrategy(cfg, policy)
    # A long, steady decline: price well below target (MR wants to buy) but the
    # slow MA is falling, so the trend filter must cap exposure BELOW what MR
    # wants — the knife-catch protection.
    prices = [max(0.2, 2.0 - 0.01 * i) for i in range(150)]
    mr_expo = mr.generate(prices).target_exposure
    trend_expo = trend.generate(prices).target_exposure
    assert trend_expo <= mr_expo
    assert trend_expo < 0.5  # capped defensively


def test_strategy_leans_long_below_target():
    cfg = StrategyConfig()
    policy = PolicyParams(target_price=1.0)
    strat = RebaseMeanReversionStrategy(cfg, policy)
    # Prices trending well below target -> expect above-baseline exposure.
    prices = [1.0] * 20 + [0.75] * 5
    sig = strat.generate(prices)
    assert 0.0 <= sig.target_exposure <= 1.0
    assert sig.target_exposure >= cfg.target_exposure


def test_strategy_leans_out_above_target():
    cfg = StrategyConfig()
    policy = PolicyParams(target_price=1.0)
    strat = RebaseMeanReversionStrategy(cfg, policy)
    prices = [1.0] * 20 + [1.35] * 5
    sig = strat.generate(prices)
    assert sig.target_exposure <= cfg.target_exposure


def test_exposure_always_bounded():
    cfg = StrategyConfig()
    policy = PolicyParams(target_price=1.0)
    strat = RebaseMeanReversionStrategy(cfg, policy)
    for prices in ([0.1] * 40, [5.0] * 40, [1.0, 2.0, 0.5, 3.0, 0.2] * 8):
        sig = strat.generate(prices)
        assert 0.0 <= sig.target_exposure <= 1.0


def test_paper_executor_conserves_value_minus_costs():
    execu = PaperExecutor.__init__  # noqa: F841  (import smoke)
    from ampl_bot.config import CostModel

    pf = Portfolio(cash=1000.0)
    ex = __import__("ampl_bot.executor", fromlist=["PaperExecutor"]).PaperExecutor(CostModel())
    before = pf.equity(1.0)
    ex.rebalance_to(pf, 0.5, 1.0, "t0")
    after = pf.equity(1.0)
    # value should only drop by fees/slippage, never increase from a rebalance
    assert after <= before + 1e-9
    assert after > before * 0.98


def test_backtest_runs_and_reports():
    bars = SyntheticPriceProvider(days=200, seed=3).history()
    cfg = BotConfig()
    res = run_backtest(bars, cfg)
    assert len(res.equity_curve) == len(bars)
    assert res.num_trades >= 0
    assert isinstance(res.summary(), str)


def test_engine_only_paper_mode():
    cfg = BotConfig(mode="live")
    raised = False
    try:
        TradingEngine(cfg)
    except ValueError:
        raised = True
    assert raised, "engine must refuse non-paper modes by default"


def test_engine_step_persists(tmp_path):
    state = tmp_path / "state.json"
    cfg = BotConfig(state_path=str(state))
    eng = TradingEngine(cfg)
    bars = SyntheticPriceProvider(days=10, seed=1).history()
    for b in bars:
        rep = eng.step(b.timestamp, b.price)
    assert state.exists()
    assert rep.equity > 0
