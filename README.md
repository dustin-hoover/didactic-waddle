# AMPL Rebase Bot

A rebase-aware trading bot for [Ampleforth (AMPL)](https://www.ampleforth.org/),
built around the protocol's actual supply mechanics. It ships as a runnable
Python project with a strategy engine, backtester, risk management, a
paper-trading engine, and a zero-dependency web dashboard.

## What this is — and what it deliberately is not

**It is:** an algorithm that trades **one account's own capital** on public,
observable signals (price vs. the CPI-adjusted target, rebase zone,
mean-reversion z-score), with disciplined risk controls and honest backtesting
against a buy-and-hold baseline.

**It is not**, and will not be built to be:

- a **wash-trading** or **fake-volume** generator (trading with yourself to
  inflate volume),
- a **pump / "make it too hot to ignore"** coordination engine,
- anything that claims to *guarantee* a price increase or guaranteed profit.

Those were part of the original ask, and they're left out on purpose. They are
illegal market manipulation under CFTC/securities rules (crypto included), and —
just as important — **they don't work for the person running them**: you pay
fees and slippage on every fake trade while the price round-trips straight back.
A single actor cannot engineer a "positive feedback loop that increases the
price." The only durable flywheel is a strategy that is genuinely profitable and
transparent enough that others independently choose to copy it, which is why
this code is readable and the backtest reports the honest number even when it
loses to buy-and-hold.

> **No profits are promised.** Mean reversion fails during regime breaks (a
> sustained AMPL de-peg is the obvious one). The risk module exists precisely
> because the thesis can be wrong.

## The strategy

AMPL's price tends to mean-revert toward its target because the daily rebase
pushes supply to move it there. So the bot:

- holds **more** AMPL when price is stretched **below** target (contraction
  zone — reversion up expected),
- holds **less** when stretched **above** target (expansion zone — reversion
  down expected),
- measures "stretched" with a **rolling z-score of the deviation from target**
  so it adapts to changing volatility,
- sizes every move through the risk layer (position cap, per-trade cap,
  stop-loss, drawdown circuit breaker).

The rebase itself is value-neutral at the instant it happens (your balance
scales up/down while price scales the opposite way); the edge being sought is
the *reversion after*, not the rebase.

## Quick start

```bash
python scripts/gen_sample_data.py      # writes data/sample_ampl.csv (synthetic)
python run_backtest.py                 # backtest strategy vs. buy & hold
python -m ampl_bot.server              # dashboard at http://127.0.0.1:8000
```

No third-party packages are required to run it (Python 3.10+ stdlib only).
`pytest` is only needed for the test suite:

```bash
pip install pytest && python -m pytest -q
```

## Architecture

| Module | Responsibility |
| --- | --- |
| `ampl_bot/mechanics.py` | Faithful, parameterised AMPL rebase math (target, ±5% dead band, lag, supply delta). |
| `ampl_bot/strategy.py` | Rebase-aware mean-reversion signal → desired exposure. |
| `ampl_bot/risk.py` | Position/trade caps, stop-loss, drawdown circuit breaker. |
| `ampl_bot/executor.py` | Portfolio + paper fills with fees/slippage; state persistence. |
| `ampl_bot/engine.py` | Live-ish paper loop, one tick at a time (paper-only by default). |
| `ampl_bot/backtest.py` | Day-by-day backtest with rebases; metrics vs. buy & hold. |
| `ampl_bot/yields.py` | Transparent "stake vs. hold" math (no auto-deposit). |
| `ampl_bot/data.py` | CSV / synthetic / (stub) live price providers. |
| `ampl_bot/server.py` | Zero-dependency read-only dashboard. |

## Using real data

Replace `data/sample_ampl.csv` with real AMPL/USD history in `timestamp,price`
format and re-run the backtest. The sample series is **synthetic** (a
mean-reverting-around-target generator) so everything runs out of the box — it
is not real market data and must not be treated as such.

## Safety model

- **Paper mode only by default.** `BotConfig.mode` is `"paper"`; the engine
  raises if asked to run any other mode. There is no live-order code path in
  this repo — adding one is a deliberate, auditable step.
- **No custody of keys** anywhere in the default code.
- **Circuit breaker** halts trading past the configured max drawdown.
- **Yield/vault decisions stay with the operator** — `yields.py` only computes
  and compares; it never moves funds.

## Roadmap (opt-in, operator-driven)

These are intentionally *not* enabled and would each be added deliberately:

1. **Live data adapter** — on-chain TWAP oracle or a CEX ticker
   (e.g. via an [EVM MCP server](https://www.quicknode.com/guides/ai/evm-mcp-server)
   for on-chain reads).
2. **Live execution adapter** — a specific venue behind an explicit flag, with
   its own tests and dry-run mode, plus key management the operator controls.
3. **Staking integration** — read positions and surface real APRs from the
   Ampleforth ecosystem (see [spot.cash](https://www.spot.cash/)); auto-deposit
   only ever behind explicit operator confirmation.

## Disclaimer

Educational software. Not financial advice. Trading crypto assets — AMPL
especially, given its elastic supply — can lose money quickly. You are
responsible for legal compliance in your jurisdiction.
