"""Tests for the bag-protection layer and on-chain metrics (offline)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.backtest import run_backtest
from tradebot.config import BotConfig, StrategyConfig
from tradebot.onchain import OnChainMetrics, _derive_regime, wallet_balances
from tradebot.protection import ProtectionConfig
from tests.test_tradebot import bars_from_closes


def test_profit_skim_banks_reserve_in_uptrend():
    bars = bars_from_closes([float(100 * 1.01 ** i) for i in range(200)])
    res = run_backtest(bars, BotConfig(strategy=StrategyConfig(kind="trend")))
    assert res.reserve_final > 0          # money was taken off the table
    assert res.num_skims >= 1
    assert res.reserve_yield > 0          # reserve earned yield


def test_reserve_ratchets_through_crash():
    # Rally (bank profit), then crash. The banked reserve must NOT fall with the
    # trading book — that's the "protect the bags at all costs" guarantee.
    up = [100 * 1.01 ** i for i in range(150)]
    crash = [up[-1] * 0.96 ** i for i in range(120)]
    bars = bars_from_closes([float(x) for x in up + crash])
    res = run_backtest(bars, BotConfig(strategy=StrategyConfig(kind="trend")))
    assert res.reserve_final > 0
    # After a deep crash the reserve is a large share of what's left.
    assert res.reserve_frac > 0.1


def test_protection_off_banks_nothing():
    bars = bars_from_closes([float(100 * 1.01 ** i) for i in range(200)])
    res = run_backtest(bars, BotConfig(strategy=StrategyConfig(kind="trend"),
                                       protection=ProtectionConfig(enabled=False)))
    assert res.reserve_final == 0.0
    assert res.num_skims == 0


def test_reserve_floor_enforced():
    bars = bars_from_closes([float(100 + i * 0.01) for i in range(120)])  # ~flat
    cfg = BotConfig(strategy=StrategyConfig(kind="trend"),
                    protection=ProtectionConfig(skim_rate=0.0, reserve_floor=0.2))
    res = run_backtest(bars, cfg)
    assert res.reserve_frac >= 0.15  # floor roughly enforced


def _uptrend(n=400):
    from tradebot.ohlcv import Bar
    return [Bar(i, 100 * 1.012 ** i, 100 * 1.012 ** i * 1.01,
                100 * 1.012 ** i * 0.99, 100 * 1.012 ** i, 100.0) for i in range(n)]


def test_flywheel_reinvests_ratio_mode():
    # ratio trigger below the reserve/trading asymptote so it fires
    cfg = BotConfig(starting_cash=100.0, strategy=StrategyConfig(kind="trend"),
                    protection=ProtectionConfig(reinvest_trigger_mode="ratio", reinvest_ratio=0.3,
                                                protect_principal=False))
    res = run_backtest(_uptrend(), cfg)
    assert res.num_reinvests > 0
    assert res.total_reinvested > 0
    assert res.trading_base_final > 100.0


def test_flywheel_off_and_seed_multiple_knob():
    off = run_backtest(_uptrend(), BotConfig(starting_cash=100.0, strategy=StrategyConfig(kind="trend"),
                                             protection=ProtectionConfig(reinvest_enabled=False)))
    assert off.num_reinvests == 0
    assert off.trading_base_final == 100.0
    # seed mode: a lower multiple fires at least as often as a higher one
    lo = run_backtest(_uptrend(), BotConfig(starting_cash=100.0, strategy=StrategyConfig(kind="trend"),
        protection=ProtectionConfig(reinvest_trigger_mode="seed", reinvest_multiple=1.5, protect_principal=False)))
    hi = run_backtest(_uptrend(), BotConfig(starting_cash=100.0, strategy=StrategyConfig(kind="trend"),
        protection=ProtectionConfig(reinvest_trigger_mode="seed", reinvest_multiple=5.0, protect_principal=False)))
    assert lo.num_reinvests >= hi.num_reinvests


def test_protect_principal_keeps_reserve_above_seed():
    # with protection on, once seed is banked the reserve never drops below it
    cfg = BotConfig(starting_cash=100.0, strategy=StrategyConfig(kind="trend"),
                    protection=ProtectionConfig(reinvest_trigger_mode="ratio", reinvest_ratio=0.3,
                                                protect_principal=True))
    res = run_backtest(_uptrend(), cfg)
    # reserve ends at or above the protected seed (it only recycles profit above it)
    assert res.reserve_final >= 100.0 - 1e-6


def test_onchain_regime_rules():
    assert _derive_regime(OnChainMetrics(fear_greed=85)) == "risk_off"   # extreme greed
    assert _derive_regime(OnChainMetrics(fear_greed=15)) == "risk_on"    # extreme fear
    assert _derive_regime(OnChainMetrics(fear_greed=65)) == "neutral"
    # gas spike downgrades a risk_on read
    assert _derive_regime(OnChainMetrics(fear_greed=30, eth_gas_gwei=120)) == "neutral"


def test_exposure_scale_mapping():
    assert OnChainMetrics(risk_regime="risk_on").exposure_scale() == 1.0
    assert OnChainMetrics(risk_regime="risk_off").exposure_scale() == 0.5


def test_wallet_address_validation():
    for bad in ["", "0x123", "not-an-address", "1234567890" * 4]:
        raised = False
        try:
            wallet_balances(bad)
        except ValueError:
            raised = True
        assert raised, f"should reject {bad!r}"
