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
pushes supply to move it there. The **mean-reversion core** (`name="mr"`):

- holds **more** AMPL when price is stretched **below** target (contraction
  zone — reversion up expected),
- holds **less** when stretched **above** target (expansion zone),
- measures "stretched" with a **rolling z-score of the deviation from target**,
- sizes every move through the risk layer (position cap, per-trade cap,
  stop-loss, drawdown circuit breaker).

The rebase itself is value-neutral at the instant it happens; the edge sought is
the *reversion after*, not the rebase.

The default is **pure mean reversion** (`name="mr"`). That is a conclusion from
real data, arrived at the honest way — by trying fancier things and watching
them lose.

### What the real full-cycle data showed (reproduce with `scripts/regime_test.py`)

Tested on real AMPL history (DefiLlama, 2019→present, incl. the 2020 $3.83 peak
and the 2021–22 de-peg), sliced into three regimes:

| Regime | **Pure MR (default)** | trend_mr | Buy & Hold |
| --- | --- | --- | --- |
| Bull (recent ~1yr) | +902%, DD **12.6%** | +645%, DD 14.6% | **+1226%**, DD 18.6% |
| Crash (2020–22, real) | **+840%**, DD **49%** | +237%, DD 54% | +176%, DD 84% |
| Full cycle (2019→now) | +105264%, DD **77%** | +3002%, DD 82% | **+261270%**, DD 96% |

Reading this honestly:

- **Pure MR is the best strategy on real data** — lowest drawdown in every
  regime, and it *beats buy-and-hold outright through the real crash* (+840% vs
  +176%). AMPL genuinely mean-reverts, so buying its recurrent dips works.
- **Buy-and-hold's edge is bull-only and comes with brutal drawdowns** (84–96%).
  Its higher raw return over the full cycle is not something a human survives —
  nobody holds through a 96% drawdown.

### Two honest corrections baked into this default

1. **The trend filter (`trend_mr`) was a mistake.** An earlier version made it
   the default after it looked great on a *synthetic* de-peg. On **real** choppy
   crash data it underperforms pure MR everywhere — stepping aside in downtrends
   skips exactly the bounces AMPL mean-reversion profits from. It's kept for
   study, not used by default. (Volatility-targeted sizing was also tested and
   rejected — AMPL is too volatile, it keeps you underexposed and you miss the
   move.)
2. **The drawdown circuit breaker was broken** — it "halted" by *freezing* the
   position, which rode the crash down (a 72% drawdown that was invisible until
   real data). It now **liquidates to cash** on a breach and **re-enters after
   price bounces** `reenter_bounce_frac` off the halt price. That is real
   protection, validated on the real crash (drawdown cut, strategies now behave
   distinctly).

> **Caveat, stated plainly:** the full-cycle *absolute* returns are not
> trustworthy — the model uses a fixed CPI target, but AMPL's real target
> drifted over seven years, and rebase compounding dominates long spans. Trust
> the *relative* comparisons and the *drawdowns*, especially in the crash window
> where the fixed target is roughly right. Even the "winning" MR still takes a
> painful 49–77% drawdown in a real crash; this smooths the ride, it does not
> make AMPL safe.

### Position sizing

The original 0.60 position cap — not the signal — was a big drag on returns; it
clamped the strategy below what the data justified. It's now **0.85** (keeping a
cash buffer for rebalancing/stops). Tune it in `RiskConfig`; compare strategies
with `scripts/compare_strategies.py`.

## Quick start

```bash
# Real data — full multi-year history (2019->now), free, no API key
python scripts/fetch_ampl_history.py --source defillama --out data/ampl_full.csv
python run_backtest.py --csv data/ampl_full.csv
python scripts/regime_test.py                  # bull / real-crash / full-cycle
python scripts/compare_strategies.py --csv data/ampl_full.csv   # mr vs trend_mr

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
| `ampl_bot/data.py` | CSV / synthetic price providers (offline core). |
| `ampl_bot/feeds.py` | Real feeds: DefiLlama + CoinGecko history, live on-chain spot. |
| `ampl_bot/server.py` | Zero-dependency read-only dashboard. |

## Real data & live on-chain price (`ampl_bot/feeds.py`)

Three real feeds are wired in, stdlib-only, no API key required:

- **`DefiLlamaFeed`** — real AMPL/USD **full multi-year daily history**
  (2019→present) by paginating DefiLlama's on-chain price chart. This is the
  recommended source and how `data/ampl_full.csv` is produced.
- **`CoinGeckoFeed`** — real AMPL/USD daily history too, but the free public API
  caps at ~365 days; pass `--api-key` (or `COINGECKO_API_KEY`) for more.
- **`OnChainFeed`** — **live AMPL/USD spot read directly from Ethereum**: the
  Uniswap V2 AMPL/WETH pool reserves priced in ETH, times the Chainlink ETH/USD
  aggregator. Falls back across several public JSON-RPC endpoints; point it at
  your own (e.g. a [QuickNode](https://www.quicknode.com/) endpoint) by passing
  `rpc_urls`. On-chain *history* is intentionally not implemented — a public
  node can't cheaply serve it — so history comes from CoinGecko/CSV.

The dashboard's `/api/live` endpoint and the top "Live On-Chain Spot" card use
`OnChainFeed`; `run_paper.py --source onchain` steps the paper engine on it.

See "What the real full-cycle data showed" above for the headline results across
bull / crash / full-cycle regimes. The bundled `data/ampl_full.csv` is the real
DefiLlama history; `data/sample_ampl.csv` is **synthetic** (a mean-reverting
generator) so the project also runs fully offline.

## Safety model

- **Paper mode only by default.** `BotConfig.mode` is `"paper"`; the engine
  raises if asked to run any other mode. There is no live-order code path in
  this repo — adding one is a deliberate, auditable step.
- **No custody of keys** anywhere in the default code.
- **Circuit breaker** liquidates to cash past the configured max drawdown and
  re-enters only after price recovers — it de-risks, it doesn't just stop trading.
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
