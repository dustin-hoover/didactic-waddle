"""Live paper engine: persistence, forward-only start, protector integration."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.config import BotConfig, StrategyConfig
from tradebot.engine import TradingEngine
from tests.test_tradebot import bars_from_closes


def _cfg(path):
    return BotConfig(mode="paper", symbol="BTC", interval="1d", starting_cash=1000.0,
                     strategy=StrategyConfig(kind="trend"), state_path=str(path))


def test_only_paper_mode(tmp_path):
    raised = False
    try:
        TradingEngine(BotConfig(mode="live", state_path=str(tmp_path / "s.json")))
    except ValueError:
        raised = True
    assert raised


def test_starts_from_now_not_replay(tmp_path):
    bars = bars_from_closes([float(100 + i) for i in range(120)])
    eng = TradingEngine(_cfg(tmp_path / "s.json"))
    reps = eng.advance(bars)
    assert len(reps) == 1                      # only today's candle, not a 120-bar replay
    assert eng.started_ts == bars[-1].ts


def test_persists_and_no_double_processing(tmp_path):
    p = tmp_path / "s.json"
    bars = bars_from_closes([float(100 + i) for i in range(120)])
    e1 = TradingEngine(_cfg(p))
    e1.advance(bars)
    total1 = e1.snapshot(bars[-1].close)["total"]
    assert p.exists()
    # reload with identical bars -> no new candle processed, state intact
    e2 = TradingEngine(_cfg(p))
    reps = e2.advance(bars)
    assert len(reps) == 0
    assert abs(e2.snapshot(bars[-1].close)["total"] - total1) < 1e-6


def test_advances_on_new_candles(tmp_path):
    p = tmp_path / "s.json"
    bars = bars_from_closes([float(100 + i) for i in range(120)])
    TradingEngine(_cfg(p)).advance(bars)             # start from now
    more = bars_from_closes([float(100 + i) for i in range(125)])  # 5 new candles
    reps = TradingEngine(_cfg(p)).advance(more)
    assert len(reps) == 5


def test_reserve_and_flywheel_state_persist(tmp_path):
    p = tmp_path / "s.json"
    # steep uptrend so the machine skims and (with ratio trigger) can reinvest
    up = bars_from_closes([float(100 * 1.03 ** i) for i in range(200)])
    TradingEngine(_cfg(p)).advance(up[:2])           # activate from near the start
    reps = TradingEngine(_cfg(p)).advance(up)        # process the rest
    snap = TradingEngine(_cfg(p)).snapshot(up[-1].close)
    assert snap["reserve"] > 0                        # profit was banked
    assert snap["total"] >= snap["trading_equity"]   # reserve adds to total
