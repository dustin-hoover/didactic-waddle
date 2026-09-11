"""Tests for the whale-follow detector + forward-return backtest (offline).

Synthetic tapes drive every case, so no RPC is touched. We build price paths where
we KNOW the answer (edge / no-edge / not enough data) and check the backtest reports
it honestly.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.whales import (WhaleBacktestConfig, backtest, detect_whales,
                             forward_return, run_backtest)


@dataclass
class P:  # duck-types tape.Block
    block: int
    price: float
    usd_size: float = 100.0
    side: str = "BUY"
    tx: str = "0x"


def test_detect_whales_threshold():
    prints = [P(1, 1.0, 5_000), P(2, 1.0, 30_000, "BUY"), P(3, 1.0, 26_000, "SELL")]
    ev = detect_whales(prints, min_usd=25_000, symbol="X")
    assert [e.usd_size for e in ev] == [30_000, 26_000]
    assert ev[0].side == "BUY" and ev[1].side == "SELL"


def test_forward_return_buy_uses_later_entry_no_lookahead():
    # whale buys at block 10 (price 1.00). We can't fill until block 12 (price 1.02),
    # exit 5 blocks later at block 17 (price 1.10). Gross = (1.10-1.02)/1.02 for a BUY.
    prints = [P(10, 1.00, 30_000), P(12, 1.02), P(17, 1.10)]
    ev = detect_whales(prints, 25_000, "X")[0]
    g = forward_return(prints, ev, horizon_blocks=5, entry_lag_blocks=2)
    assert abs(g - (1.10 - 1.02) / 1.02) < 1e-9


def test_forward_return_sell_direction_inverts():
    # SELL whale: we profit when price FALLS, so a drop is a positive return.
    prints = [P(10, 1.00, 30_000, "SELL"), P(12, 1.00), P(17, 0.90)]
    ev = detect_whales(prints, 25_000, "X")[0]
    g = forward_return(prints, ev, horizon_blocks=5, entry_lag_blocks=2)
    assert g > 0 and abs(g - 0.10) < 1e-9


def test_forward_return_none_when_window_runs_off_end():
    prints = [P(10, 1.00, 30_000), P(12, 1.02)]  # no exit print after horizon
    ev = detect_whales(prints, 25_000, "X")[0]
    assert forward_return(prints, ev, horizon_blocks=50, entry_lag_blocks=2) is None


def _edge_tape(n=40, step=200):
    """Every whale BUY is followed by a clean +3% move — a strong (fake) edge."""
    prints = []
    b = 0
    for _ in range(n):
        prints.append(P(b, 1.00, 30_000, "BUY"))       # whale print
        prints.append(P(b + 2, 1.00))                   # our entry (lag 2)
        prints.append(P(b + 2 + 150, 1.03))             # +3% at the horizon
        b += step
    return prints


def test_backtest_reports_possible_edge_net_of_cost():
    res = backtest(_edge_tape(), WhaleBacktestConfig(min_whale_usd=25_000, cost_bps=100), "EDGE")
    assert res.n_evaluated >= 20
    assert res.hit_rate == 1.0                # every follow won
    assert res.avg_gross > 0.029              # ~+3% gross
    assert abs(res.avg_net - (0.03 - 0.01)) < 1e-6   # net of 100bps => ~+2%
    assert res.verdict.startswith("POSSIBLE EDGE")


def test_backtest_no_edge_when_cost_exceeds_move():
    # Same +3% move but a brutal 400bps round-trip cost => net negative.
    res = backtest(_edge_tape(), WhaleBacktestConfig(min_whale_usd=25_000, cost_bps=400), "COSTLY")
    assert res.avg_net < 0 and res.verdict == "NO EDGE"


def test_backtest_insufficient_data_refuses_to_conclude():
    res = backtest(_edge_tape(n=5), WhaleBacktestConfig(min_whale_usd=25_000, min_events=20), "THIN")
    assert res.verdict == "INSUFFICIENT DATA"


def test_backtest_no_edge_on_adverse_drift():
    # Price DROPS 2% after every whale BUY => following loses even before costs.
    prints = []
    b = 0
    for _ in range(40):
        prints += [P(b, 1.00, 30_000, "BUY"), P(b + 2, 1.00), P(b + 152, 0.98)]
        b += 200
    res = backtest(prints, WhaleBacktestConfig(min_whale_usd=25_000, cost_bps=50), "DRIFT")
    assert res.hit_rate == 0.0 and res.avg_net < 0 and res.verdict == "NO EDGE"


def test_events_per_day_computed_from_span():
    # 2 whale events, 7200 blocks apart => span 7200 => ~2 events/day.
    prints = [P(0, 1.0, 30_000), P(3, 1.0), P(160, 1.0),
              P(7200, 1.0, 30_000), P(7203, 1.0), P(7360, 1.0)]
    res = backtest(prints, WhaleBacktestConfig(min_whale_usd=25_000, min_events=1), "FREQ")
    assert res.n_events == 2
    # span is 7360 blocks (0..7360) => 2 / (7360/7200) ≈ 1.96 events/day
    assert abs(res.events_per_day - 2 / (7360 / 7200)) < 1e-3


def test_run_backtest_injected_fetcher_no_network():
    tape = _edge_tape()

    def fake_get_swaps(sym, blocks):
        assert blocks == 43_200
        return tape

    res = run_backtest("PEPE", cfg=WhaleBacktestConfig(min_whale_usd=25_000),
                       get_swaps_fn=fake_get_swaps)
    assert res.symbol == "PEPE" and res.n_evaluated >= 20 and res.hit_rate == 1.0
