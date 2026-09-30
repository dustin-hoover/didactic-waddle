"""Scenarios: the validated model, tuned by a few important variables.

A *scenario* is the data-driven strategy with a specific dial-setting — like the
fund choices in a 401k. Every wallet's bag runs a scenario; different scenarios
accrue value differently over time on the SAME real data, so you can compare
"what would this have returned?" and rebalance between them on demand.

Design rules that keep the comparison honest:
  * All scenarios run on the SAME symbol + interval + data window, so their
    returns are directly comparable — the only thing that differs is the profile
    (how much beta it keeps, how hard it protects, how it compounds).
  * The variables are all things the BACKTEST actually reflects (trend style,
    stop distance, exposure floor, drawdown breaker, skim rate, flywheel) — so a
    scenario's shadow return is real, not a story. The live-only flow de-risk
    overlay is deliberately NOT a scenario variable, because a historical
    backtest can't reflect it.

`compare()` runs the whole library forward on real data and returns each
scenario's realized paper performance — the numbers the UI shows so you can pick
or rebalance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .backtest import run_backtest
from .config import BotConfig, RiskConfig, StrategyConfig
from .ohlcv import Bar
from .protection import ProtectionConfig


@dataclass
class Scenario:
    key: str                     # short id used by the UI + bag specs
    name: str                    # human name
    blurb: str                   # one-line description of the profile
    risk_level: str              # "low" | "medium" | "high" — for UI sorting/color
    symbol: str = "BTC"
    interval: str = "1d"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    protection: ProtectionConfig = field(default_factory=ProtectionConfig)

    def config(self, starting_cash: float = 1000.0, state_path: str = "data/scn_state.json") -> BotConfig:
        return BotConfig(mode="paper", symbol=self.symbol, interval=self.interval,
                         starting_cash=starting_cash, strategy=self.strategy,
                         risk=self.risk, protection=self.protection, state_path=state_path)


# ---- the curated library -----------------------------------------------------
# One recommended default plus tunings across the risk spectrum. Same asset/
# interval so a wallet can compare and rebalance apples-to-apples.
LIBRARY: List[Scenario] = [
    Scenario(
        key="steady", name="Steady (recommended)", risk_level="medium",
        blurb="The validated trend + capital-preservation model at its default dials.",
        strategy=StrategyConfig(kind="trend", style="swing"),
        risk=RiskConfig(atr_stop_mult=3.0, max_drawdown_frac=0.30),
        protection=ProtectionConfig(),
    ),
    Scenario(
        key="guardian", name="Guardian", risk_level="low",
        blurb="Protect first: tighter stop, earlier drawdown breaker, bank more profit.",
        strategy=StrategyConfig(kind="trend", style="swing", min_long_exposure=0.5),
        risk=RiskConfig(atr_stop_mult=2.0, max_drawdown_frac=0.20, per_trade_frac=0.40),
        protection=ProtectionConfig(skim_rate=0.75),
    ),
    Scenario(
        key="runner", name="Runner", risk_level="high",
        blurb="Keep more beta: looser stop, higher exposure floor, skim less.",
        strategy=StrategyConfig(kind="trend", style="swing", min_long_exposure=0.8),
        risk=RiskConfig(atr_stop_mult=4.0, max_drawdown_frac=0.40, max_position_frac=1.0),
        protection=ProtectionConfig(skim_rate=0.40),
    ),
    Scenario(
        key="compounder", name="Compounder", risk_level="medium",
        blurb="Spin the flywheel: bank profit, then recycle it back into trading sooner.",
        strategy=StrategyConfig(kind="trend", style="swing"),
        risk=RiskConfig(atr_stop_mult=3.0, max_drawdown_frac=0.30),
        protection=ProtectionConfig(skim_rate=0.60, reinvest_trigger_mode="ratio",
                                    reinvest_ratio=0.35, protect_principal=True),
    ),
    Scenario(
        key="scout", name="Scout", risk_level="high",
        blurb="Faster hands: the day-tuned trend filter reacts quicker to turns.",
        strategy=StrategyConfig(kind="trend", style="day"),
        risk=RiskConfig(atr_stop_mult=2.5, max_drawdown_frac=0.30),
        protection=ProtectionConfig(skim_rate=0.60),
    ),
]

_BY_KEY = {s.key: s for s in LIBRARY}
DEFAULT_KEY = "steady"


def by_key(key: str) -> Optional[Scenario]:
    return _BY_KEY.get(key)


def run_scenario(scn: Scenario, bars: List[Bar], starting_cash: float = 1000.0) -> Dict:
    """Backtest one scenario on real bars; return the numbers the UI displays."""
    r = run_backtest(bars, scn.config(starting_cash))
    final_total = starting_cash * (1 + r.strategy_return)
    return {
        "key": scn.key, "name": scn.name, "blurb": scn.blurb,
        "risk_level": scn.risk_level, "symbol": scn.symbol, "interval": scn.interval,
        "return": round(r.strategy_return, 4),
        "buyhold_return": round(r.buyhold_return, 4),
        "sharpe": round(r.sharpe, 2),
        "max_drawdown": round(r.max_drawdown, 4),
        "reserve_frac": round(r.reserve_frac, 4),
        "exposure_avg": round(r.exposure_avg, 4),
        "skims": r.num_skims, "reinvests": r.num_reinvests,
        "final_total": round(final_total, 2),
    }


def compare(bars: List[Bar], starting_cash: float = 1000.0) -> List[Dict]:
    """Run the whole library on the same real data; best realized return first.

    This is the 401k-style board: "$X in each scenario would be worth $Y today."
    """
    rows = [run_scenario(s, bars, starting_cash) for s in LIBRARY]
    rows.sort(key=lambda r: r["return"], reverse=True)
    return rows


def _pctile(sorted_vals: List[float], q: float) -> float:
    """Nearest-rank percentile of an already-sorted list (q in [0,1])."""
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def compare_distribution(bars: List[Bar], starting_cash: float = 1000.0,
                         window_frac: float = 0.8, samples: int = 12) -> List[Dict]:
    """Honest scenario board: each scenario's return as a DISTRIBUTION, not a point.

    A single full-window return is fragile — path-dependent scenarios (tight stops,
    early drawdown breakers, heavy skimming) swing wildly as the rolling data window
    shifts day to day, so the "leader" reshuffles on noise. To tell the truth, we
    slide a sub-window (``window_frac`` of the bars) across the history ``samples``
    times and report each scenario's MEDIAN return plus a 10th–90th-percentile range
    and stdev. Ranking is by median (robust), and the spread exposes which scenarios
    are stable (narrow) vs fragile (wide).

    Each row is a SUPERSET of a `run_scenario` row (full-window ``return``, ``sharpe``,
    ``max_drawdown``, etc. are kept for continuity) plus: ``median_return``,
    ``lo_return`` (p10), ``hi_return`` (p90), ``spread`` (p90−p10), ``stdev``,
    ``n_windows``. Falls back to the point estimate when there aren't enough bars.
    """
    full = {s.key: run_scenario(s, bars, starting_cash) for s in LIBRARY}
    n = len(bars)
    w = int(n * window_frac)
    dist: Dict[str, List[float]] = {s.key: [] for s in LIBRARY}

    if w >= 200 and n - w >= 1:
        step = max(1, (n - w) // max(1, samples - 1))
        for off in range(0, n - w + 1, step):
            win = bars[off:off + w]
            for s in LIBRARY:
                dist[s.key].append(run_backtest(win, s.config(starting_cash)).strategy_return)

    rows: List[Dict] = []
    for s in LIBRARY:
        row = dict(full[s.key])
        vals = sorted(dist[s.key])
        if vals:
            mean = sum(vals) / len(vals)
            sd = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** 0.5
            row.update(median_return=round(_pctile(vals, 0.5), 4),
                       lo_return=round(_pctile(vals, 0.1), 4),
                       hi_return=round(_pctile(vals, 0.9), 4),
                       spread=round(_pctile(vals, 0.9) - _pctile(vals, 0.1), 4),
                       stdev=round(sd, 4), n_windows=len(vals))
        else:                                   # too few bars — degrade to the point estimate
            pt = row["return"]
            row.update(median_return=pt, lo_return=pt, hi_return=pt,
                       spread=0.0, stdev=0.0, n_windows=1)
        rows.append(row)
    rows.sort(key=lambda r: r["median_return"], reverse=True)
    return rows
