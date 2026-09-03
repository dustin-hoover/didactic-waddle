"""Offline tests for the generic tradebot framework (no network)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot import indicators as ind
from tradebot.backtest import run_backtest
from tradebot.config import BotConfig, StrategyConfig
from tradebot.ohlcv import Bar, read_csv, write_csv
from tradebot.risk import RiskManager, RiskState
from tradebot.signals import CompositeStrategy, TrendFilterStrategy, build_strategy


def bars_from_closes(closes, start_ts=1_600_000_000_000, step=86_400_000, vol=100.0):
    out = []
    for i, c in enumerate(closes):
        out.append(Bar(start_ts + i * step, c, c * 1.01, c * 0.99, c, vol))
    return out


# ---- indicators ----
def test_ema_and_sma_last():
    vals = [float(i) for i in range(1, 21)]
    assert abs(ind.sma(vals, 5)[-1] - 18.0) < 1e-9  # mean of 16..20
    e = ind.ema(vals, 5)[-1]
    assert 15 < e < 20  # trails an increasing series


def test_rsi_bounds_and_direction():
    up = ind.rsi([float(i) for i in range(1, 40)], 14)[-1]
    down = ind.rsi([float(i) for i in range(40, 1, -1)], 14)[-1]
    assert up > 90 and down < 10
    assert 0 <= up <= 100 and 0 <= down <= 100


def test_atr_positive_and_donchian():
    closes = [10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 17, 18, 17, 19, 20, 19, 21]
    bars = bars_from_closes([float(c) for c in closes])
    high = [b.high for b in bars]
    low = [b.low for b in bars]
    close = [b.close for b in bars]
    a = ind.atr(high, low, close, 5)[-1]
    assert a is not None and a > 0
    up, lo = ind.donchian(high, low, 5)
    assert up[-1] == max(high[-5:]) and lo[-1] == min(low[-5:])


def test_macd_and_percent_b_run():
    vals = [10 + (i % 5) for i in range(60)]
    line, sig, hist = ind.macd([float(v) for v in vals])
    assert any(x is not None for x in hist)
    pb = ind.percent_b([float(v) for v in vals], 20)
    assert pb[-1] is not None


# ---- signals ----
def test_trend_filter_regime():
    up = bars_from_closes([float(100 + i) for i in range(80)])
    down = bars_from_closes([float(180 - i) for i in range(80)])
    s = TrendFilterStrategy("swing")
    assert s.generate(up).target_exposure == 1.0
    s2 = TrendFilterStrategy("swing")
    assert s2.generate(down).target_exposure == 0.0


def test_composite_warmup_and_bounds():
    s = CompositeStrategy("swing")
    assert s.generate(bars_from_closes([100.0, 101.0])).target_exposure == 0.0
    sig = s.generate(bars_from_closes([100 + (i % 7) for i in range(120)]))
    assert 0.0 <= sig.target_exposure <= 1.0
    assert -1.0 <= sig.score <= 1.0


def test_build_strategy_factory():
    assert isinstance(build_strategy(StrategyConfig(kind="trend")), TrendFilterStrategy)
    assert isinstance(build_strategy(StrategyConfig(kind="composite")), CompositeStrategy)
    raised = False
    try:
        build_strategy(StrategyConfig(kind="nope"))
    except ValueError:
        raised = True
    assert raised


# ---- backtest ----
def test_backtest_invests_in_uptrend():
    bars = bars_from_closes([float(100 * 1.01 ** i) for i in range(200)])
    res = run_backtest(bars, BotConfig(strategy=StrategyConfig(kind="trend")))
    assert res.strategy_return > 0
    assert res.exposure_avg > 0.5  # should be mostly long in a clean uptrend
    assert len(res.equity_curve) == len(bars)


def test_backtest_circuit_breaker_protects_in_crash():
    # rally then a deep crash; breaker + regime exit must cap the drawdown.
    up = [100 * 1.01 ** i for i in range(120)]
    peak = up[-1]
    crash = [peak * 0.97 ** i for i in range(120)]
    bars = bars_from_closes([float(x) for x in up + crash])
    res = run_backtest(bars, BotConfig(strategy=StrategyConfig(kind="trend")))
    assert res.max_drawdown < 0.55  # far short of buy-and-hold's near-total loss
    assert res.buyhold_return < res.strategy_return


# ---- risk ----
def test_breaker_trip_and_reenter():
    rm = RiskManager(BotConfig().risk)
    st = RiskState(peak_equity=100.0)
    st = rm.update_and_check(st, 100.0, 10.0)
    st = rm.update_and_check(st, 65.0, 6.5)  # 35% dd > 30% threshold
    assert st.halted and st.halt_price == 6.5
    st = rm.update_and_check(st, 65.0, 6.5 * 1.13)  # +13% > 12% reenter
    assert not st.halted


def test_atr_stop():
    rm = RiskManager(BotConfig().risk)
    st = RiskState(peak_equity=100.0)
    rm.set_stop(st, entry_price=100.0, atr_pct=0.02)  # stop at 100*(1-3*0.02)=94
    assert st.stop_price is not None and abs(st.stop_price - 94.0) < 1e-6
    assert rm.stop_triggered(st, 93.9)
    assert not rm.stop_triggered(st, 95.0)


# ---- ohlcv csv ----
def test_ohlcv_csv_roundtrip(tmp_path):
    bars = bars_from_closes([1.0, 2.0, 3.0])
    p = tmp_path / "x.csv"
    write_csv(bars, str(p))
    back = read_csv(str(p))
    assert [b.close for b in back] == [1.0, 2.0, 3.0]
    assert back[0].volume == 100.0


# ---- ampl plugin ----
def test_ampl_plugin_trims_in_expansion():
    from tradebot.plugins.ampl import AmplTrendStrategy
    # Uptrend that pushes far above the ~1.02 CPI target -> should trim vs base.
    closes = [float(1.0 + 0.02 * i) for i in range(80)]  # ends ~2.58, deep expansion
    bars = bars_from_closes(closes)
    base = TrendFilterStrategy("swing").generate(bars).target_exposure
    trimmed = AmplTrendStrategy("swing").generate(bars).target_exposure
    assert base == 1.0
    assert trimmed < base
