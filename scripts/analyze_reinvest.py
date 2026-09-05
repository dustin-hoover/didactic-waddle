"""Find the real sweet spot for the flywheel — trigger first, then fraction.

Honest framing: no setting makes the system "never lose." Monte Carlo over
block-bootstrapped real BTC daily returns (includes crashes and chop) measures
the trade-offs:
  Part A: sweep the TRIGGER (how big the reserve must get to fire). This is what
          decides whether the flywheel engages at all.
  Part B: at a trigger that actually fires, sweep the reinvest FRACTION.
  Part C: principal protection on vs off — its effect on P(ending below seed).
"""

import math
import os
import random
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tradebot.backtest import run_backtest  # noqa: E402
from tradebot.config import BotConfig, StrategyConfig  # noqa: E402
from tradebot.ohlcv import Bar, ExchangeFeed  # noqa: E402
from tradebot.protection import ProtectionConfig  # noqa: E402

SEED = 100.0
N_PATHS = 60
PATH_LEN = 1000
BLOCK = 20


def paths():
    closes = [b.close for b in ExchangeFeed().history("BTC", "1d", 1000)]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    rng = random.Random(42)
    out = []
    for _ in range(N_PATHS):
        series, price = [], 100.0
        while len(series) < PATH_LEN:
            s = rng.randrange(0, len(rets) - BLOCK)
            for r in rets[s:s + BLOCK]:
                price *= math.exp(r)
                series.append(price)
                if len(series) >= PATH_LEN:
                    break
        out.append([Bar(i, p, p, p, p, 100.0) for i, p in enumerate(series)])
    return out


def evaluate(P, **prot):
    rets, dds, injs, below = [], [], [], 0
    for bars in P:
        cfg = BotConfig(starting_cash=SEED, strategy=StrategyConfig(kind="trend"),
                        protection=ProtectionConfig(**prot))
        r = run_backtest(bars, cfg)
        rets.append(r.strategy_return)
        dds.append(r.max_drawdown)
        injs.append(r.num_reinvests)
        if (1 + r.strategy_return) * SEED < SEED:
            below += 1
    rets.sort()
    p = lambda q: rets[int(q * (len(rets) - 1))]
    return dict(med=statistics.median(rets), p5=p(0.05), dd=statistics.median(dds),
                below=below / len(P), inj=statistics.mean(injs))


def line(tag, m):
    print(f"{tag:>10}  median {m['med']*100:>+5.0f}%  worst {m['p5']*100:>+5.0f}%  "
          f"medDD {m['dd']*100:>3.0f}%  P(loss) {m['below']*100:>3.0f}%  inj/path {m['inj']:>4.1f}", flush=True)


def main():
    P = paths()
    print(f"Monte Carlo: {N_PATHS} bootstrapped BTC paths x {PATH_LEN} days, seed ${SEED:.0f}\n", flush=True)

    # Aggressive skim (60%) so the reserve grows big enough for the flywheel to
    # actually fire — only then does the reinvest fraction have a sweet spot.
    print("PART A — REINVEST FRACTION sweep (skim 60%, ratio trigger 0.3, protection ON):", flush=True)
    for frac in [0.0, 0.25, 0.5, 0.667, 0.8, 1.0]:
        line(f"{frac*100:.0f}%", evaluate(P, skim_rate=0.6, reinvest_trigger_mode="ratio",
                                          reinvest_ratio=0.3, reinvest_fraction=frac, protect_principal=True))

    print("\nPART B — SKIM RATE sweep (the real safety dial; fraction 2/3, ratio 0.3):", flush=True)
    for skim in [0.2, 0.3, 0.45, 0.6, 0.8]:
        line(f"skim {skim*100:.0f}%", evaluate(P, skim_rate=skim, reinvest_trigger_mode="ratio",
                                               reinvest_ratio=0.3, reinvest_fraction=2/3, protect_principal=True))

    print("\nPART C — principal protection off vs on (skim 60%, ratio 0.3, fraction 2/3):", flush=True)
    line("protect off", evaluate(P, skim_rate=0.6, reinvest_trigger_mode="ratio", reinvest_ratio=0.3,
                                 reinvest_fraction=2/3, protect_principal=False))
    line("protect on", evaluate(P, skim_rate=0.6, reinvest_trigger_mode="ratio", reinvest_ratio=0.3,
                                reinvest_fraction=2/3, protect_principal=True))

    print("\nBaseline — flywheel OFF (skim 30%):", flush=True)
    line("no flywheel", evaluate(P, reinvest_enabled=False))


if __name__ == "__main__":
    main()
