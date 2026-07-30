"""Circuit-breaker behaviour: it must de-risk, not merely stop trading."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ampl_bot.feeds as feeds
from ampl_bot.backtest import run_backtest
from ampl_bot.config import BotConfig
from ampl_bot.data import PriceBar
from ampl_bot.feeds import DefiLlamaFeed
from ampl_bot.risk import RiskManager, RiskState


def test_breaker_trips_and_records_halt_price():
    cfg = BotConfig().risk
    rm = RiskManager(cfg)
    st = RiskState(peak_equity=100.0)
    st = rm.update_and_check(st, equity=100.0, price=10.0, exposure=1.0)
    assert not st.halted
    # 40% drawdown > 35% threshold -> halt and record the price.
    st = rm.update_and_check(st, equity=60.0, price=6.0, exposure=1.0)
    assert st.halted
    assert st.halt_price == 6.0


def test_breaker_reenters_after_bounce():
    cfg = BotConfig().risk  # reenter_bounce_frac = 0.15
    rm = RiskManager(cfg)
    st = RiskState(peak_equity=100.0, halted=True, halt_price=6.0)
    # Small bounce: still halted.
    st = rm.update_and_check(st, equity=60.0, price=6.5, exposure=0.0)
    assert st.halted
    # +15% off halt price (6.9) -> re-enter.
    st = rm.update_and_check(st, equity=60.0, price=6.9, exposure=0.0)
    assert not st.halted
    assert st.halt_price is None


def test_breaker_liquidates_to_cash_in_backtest():
    # A realistic de-peg: price starts near target and falls well below it, so
    # negative rebases + falling price wreck a holder. The breaker must cap the
    # strategy's drawdown far short of buy-and-hold's by moving to cash.
    from datetime import date, timedelta

    d0 = date(2020, 1, 1)
    bars = [
        PriceBar((d0 + timedelta(days=i)).isoformat(), round(1.20 * (0.955 ** i), 6))
        for i in range(90)
    ]
    res = run_backtest(bars, BotConfig())
    assert res.max_drawdown < 0.60  # protected vs a near-total wipeout
    assert res.buyhold_return < res.strategy_return  # holding is worse in a de-peg


def test_defillama_paginates_and_dedupes(monkeypatch):
    # Two pages; second advances the cursor. Expect merged, de-duped daily bars.
    page1 = {"coins": {DefiLlamaFeed.AMPL_COIN: {"prices": [
        {"timestamp": 1_561_593_600, "price": 1.0},
        {"timestamp": 1_561_680_000, "price": 1.1},
    ]}}}
    page2 = {"coins": {DefiLlamaFeed.AMPL_COIN: {"prices": [
        {"timestamp": 1_561_766_400, "price": 1.2},
    ]}}}
    pages = [page1, page2, {"coins": {DefiLlamaFeed.AMPL_COIN: {"prices": []}}}]
    calls = {"n": 0}

    def fake(url, data=None, tries=4, timeout=30):
        i = min(calls["n"], len(pages) - 1)
        calls["n"] += 1
        return pages[i]

    monkeypatch.setattr(feeds, "_http_json", fake)
    monkeypatch.setattr(feeds.time, "time", lambda: 1_561_900_000)
    bars = DefiLlamaFeed().history(start_ts=1_561_593_600)
    assert [b.price for b in bars] == [1.0, 1.1, 1.2]
