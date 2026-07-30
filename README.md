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
# Real data
python scripts/fetch_ampl_history.py           # real AMPL history -> data/ampl_history.csv
python run_backtest.py --csv data/ampl_history.csv

# Live paper trading on real prices (no real orders)
python run_paper.py --source onchain --once    # one tick from Ethereum
python run_paper.py --source onchain            # hourly loop

# Dashboard (shows live on-chain spot + backtest)
python -m ampl_bot.server                       # http://127.0.0.1:8000

# Or run fully offline on synthetic demo data
python scripts/gen_sample_data.py && python run_backtest.py
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

## Real data & live on-chain price (`ampl_bot/feeds.py`)

Two real feeds are wired in, stdlib-only, no API key required:

- **`CoinGeckoFeed`** — real AMPL/USD **daily history** for backtesting.
  `scripts/fetch_ampl_history.py` pulls it to a CSV. The free public API caps
  history at ~365 days; pass `--api-key` (or `COINGECKO_API_KEY`) for more.
- **`OnChainFeed`** — **live AMPL/USD spot read directly from Ethereum**: the
  Uniswap V2 AMPL/WETH pool reserves priced in ETH, times the Chainlink ETH/USD
  aggregator. Falls back across several public JSON-RPC endpoints; point it at
  your own (e.g. a [QuickNode](https://www.quicknode.com/) endpoint) by passing
  `rpc_urls`. On-chain *history* is intentionally not implemented — a public
  node can't cheaply serve it — so history comes from CoinGecko/CSV.

The dashboard's `/api/live` endpoint and the top "Live On-Chain Spot" card use
`OnChainFeed`; `run_paper.py --source onchain` steps the paper engine on it.

### What one year of real data showed

On the trailing ~year of real AMPL (a strong bull run), the mean-reversion
strategy returned well but **underperformed buy-and-hold**, because it trimmed
exposure as price ran far above target — with a much lower max drawdown. That's
the honest tradeoff: this is a *lower-volatility* profile, not a return
maximiser, and mean reversion loses in a sustained trend. Re-run the backtest
yourself; the numbers move with the market.

The bundled `data/sample_ampl.csv` is **synthetic** (a mean-reverting generator)
so the project runs fully offline — it is not real market data.

## Safety model

- **Paper mode only by default.** `BotConfig.mode` is `"paper"`; the engine
  raises if asked to run any other mode. There is no live-order code path in
  this repo — adding one is a deliberate, auditable step.
- **No custody of keys** anywhere in the default code.
- **Circuit breaker** halts trading past the configured max drawdown.
- **Yield/vault decisions stay with the operator** — `yields.py` only computes
  and compares; it never moves funds.

## Roadmap (opt-in, operator-driven)

1. **Live data adapter** — ✅ done: `CoinGeckoFeed` (history) and `OnChainFeed`
   (live spot from Uniswap V2 + Chainlink). Swap in your own RPC for
   reliability/rate limits.

The following remain intentionally *not* enabled and would each be added
deliberately:

2. **Live execution adapter** — a specific venue behind an explicit flag, with
   its own tests and dry-run mode, plus key management the operator controls.
3. **Staking integration** — read positions and surface real APRs from the
   Ampleforth ecosystem (see [spot.cash](https://www.spot.cash/)); auto-deposit
   only ever behind explicit operator confirmation.

## Disclaimer

Educational software. Not financial advice. Trading crypto assets — AMPL
especially, given its elastic supply — can lose money quickly. You are
responsible for legal compliance in your jurisdiction.
