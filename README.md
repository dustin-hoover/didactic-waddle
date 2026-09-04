# tradebot — crypto day/swing signal framework

An asset-agnostic framework for day and swing trading **any** crypto with real
market data: a full panel of the critical technical signals, a screener that
ranks a universe of coins, a backtester, ATR-based risk management, a paper
engine, and a dashboard. Long/flat spot only. **Paper trading by default — no
live-order or key-custody code ships enabled.**

It grew out of an AMPL-specific rebase bot (now a plugin — see below). The same
honest ethos carries over: **backtest everything, report the real number even
when it's unflattering, and prefer the simple thing that works over the clever
thing that doesn't.**

## The critical signals

All computed in `tradebot/indicators.py` (pure functions, standard conventions
incl. Wilder smoothing), grouped by what they measure:

| Group | Signals |
| --- | --- |
| Trend / momentum | EMA(fast/slow), MACD, ADX (+DI/−DI), ROC |
| Mean reversion | RSI, Bollinger Bands + %b, Stochastic |
| Volatility | ATR, realized volatility |
| Volume | OBV, rolling VWAP |
| Structure | Donchian channels (breakouts) |

`tradebot/signals.py` turns these into per-signal votes in [−1,+1] and combines
them — but see the honest results below for how they're actually used.

## What actually works (and what doesn't) — backtested on real data

Data is real OHLCV with volume from public exchanges (Binance.US → Coinbase →
OKX fallback, no API key). Two strategies were built and backtested head-to-head
across BTC/ETH/SOL and multiple timeframes:

- **`composite`** — the full weighted signal panel, regime-adaptive (ADX-weighted
  blend of trend vs. mean reversion).
- **`trend`** — a plain EMA trend filter: fully invested when price is above a
  slow EMA (with a hysteresis buffer), cash when below.

**The simple `trend` filter won, decisively and repeatably.** The elaborate
composite chronically under-invested and mistimed entries, losing money on
several coins after fees. Representative results (1000 bars each):

| Market | `trend` (default) | Buy & Hold |
| --- | --- | --- |
| BTC 4h | **+22%, Sharpe 1.77, DD 16%** | +15%, DD ~35% |
| ETH 4h | +15%, Sharpe 0.99, DD 21% | +16%, DD ~40% |
| SOL 1h | +18%, **Sharpe 3.38, DD 11%** | +37%, deep DD |
| BTC 1d | +46%, DD 32% | +86%, DD 53% |

The honest read: **the trend filter rarely out-*returns* buy-and-hold in a raw
bull, but it delivers much better risk-adjusted performance and far lower
drawdowns**, especially on the 4h/1h timeframes day/swing traders use. That —
drawdown reduction, not magic alpha — is its real value.

So the **default strategy is `trend`**. The composite panel is kept for two
things it's genuinely good at: **the screener** (ranking many coins by signal)
and **the dashboard** (surfacing what's setting up). It's available as
`--kind composite` for experimentation, documented as the weaker trader. This is
the same lesson the AMPL work taught: complexity that loses to a simple baseline
is not an improvement.

> No edge is promised. TA is hard, fees are real, and every number here moves
> with the sample. Backtest your own symbols/timeframes before trusting anything.

## Quick start

```bash
# Backtest any coin (real exchange data, no key needed)
python tb.py backtest --symbol BTC --interval 4h --style swing
python tb.py backtest --symbol ETH --interval 1d --kind composite   # experimental

# Screen a universe of coins by their live signals
python tb.py screen --interval 4h --style swing

# Live on-chain market context (Fear & Greed, TVL, stablecoins, gas, risk regime)
python tb.py onchain

# Read-only wallet balances (self-custody view — no keys, public chain state)
python tb.py wallet 0xYourAddress

# Never miss a move: check for signal flips, optionally push to your phone
python tb.py alert --interval 4h --ntfy your-secret-topic

# Live paper trading (simulated fills, no real orders)
python tb.py paper --symbol BTC --interval 1h --once

# Dashboard: strategy explainer at /, the app at /app
python -m tradebot.server            # http://127.0.0.1:8000
```

The dashboard opens on a **strategy explainer page** (the graph + why the
approach works, grounded in real trend-following and capital-preservation
theory) at `/`, with the live screener/wallet/backtest app at `/app`.

## Never miss an opportunity — alerts & push (`tradebot/alerts.py`)

The bot runs the same rule every candle and fires an alert when the actionable
state *changes* (flat→long = BUY, long→flat = EXIT). Run `tb.py alert` on a
schedule (cron, or a Claude Code routine) and pass `--ntfy <topic>` to get a
**free push to your phone** via [ntfy.sh](https://ntfy.sh) — pick a hard-to-guess
topic and subscribe to it in the ntfy app. You keep custody and place the trade;
the bot just guarantees you see the signal. Example cron (hourly):

```cron
0 * * * * cd /path/to/repo && python tb.py alert --interval 4h --ntfy your-secret-topic
```

Python 3.10+, standard library only. `pytest` is only needed for the tests.

## Architecture

| Module | Responsibility |
| --- | --- |
| `tradebot/ohlcv.py` | Real OHLCV with volume; multi-venue fallback + pagination. |
| `tradebot/indicators.py` | The technical-indicator library (pure functions). |
| `tradebot/signals.py` | Votes → `TrendFilterStrategy` (default) and `CompositeStrategy`. |
| `tradebot/risk.py` | ATR stop-loss, position caps, liquidate-and-re-enter breaker. |
| `tradebot/portfolio.py` | Portfolio + paper fills (fees/slippage), persistence. |
| `tradebot/backtest.py` | OHLCV backtest with intrabar ATR stop; metrics vs. buy & hold. |
| `tradebot/engine.py` | Live paper loop, one candle at a time. |
| `tradebot/protection.py` | Bag protection: profit skim → stable reserve + yield. |
| `tradebot/onchain.py` | On-chain metrics, risk regime, read-only wallet balances. |
| `tradebot/alerts.py` | Signal-flip alerts + free phone push (ntfy.sh). |
| `tradebot/screener.py` | Rank a coin universe by trend + conviction. |
| `tradebot/server.py` | Dashboard: strategy explainer (`/`) + app (`/app`). |
| `static/landing.html` | The strategy explainer / landing page. |
| `tradebot/plugins/ampl.py` | AMPL rebase specialization (see below). |

## Risk & safety model

- **Paper only by default.** `BotConfig.mode="paper"`; the engine refuses other
  modes. No live-order path, no key custody.
- **ATR stop-loss** per position (`entry − mult·ATR`), checked intrabar at the low.
- **Drawdown circuit breaker** that *liquidates to cash* on a breach and
  re-enters only after price recovers — it de-risks, it doesn't just stop trading
  (a bug fixed in the original AMPL project and carried over correctly here).
- **Long/flat spot only** — no leverage, no shorting, no liquidation risk.

## Protect the bags — capital preservation (`tradebot/protection.py`)

Trading isn't just entries; it's taking money off the table and ring-fencing it.
The protection layer does this automatically:

- **Profit skim**: each time total equity makes a new high by a tier, a fraction
  of the *new* gain is realized (sold into strength) and swept into a stable
  **reserve** (think USDC).
- **Ratchet**: the reserve only grows. A drawdown in the trading book can never
  claw back banked profit — that's the "at all costs" guarantee.
- **Yield**: the reserve is assumed to earn a stable APY (a stablecoin lending
  position, or SPOT/AMPL staking). Accounting only — a real deposit is a signed
  action you authorize; the bot never moves funds.
- **Reserve floor**: an optional minimum always kept in stable/cash.

The strategy only trades the *unreserved* book, so safety compounds. In backtests
this took money off the table without hurting returns (e.g. BTC 1d: banked ~24%
of equity into the reserve, drawdown 32%→28%). Configure in `ProtectionConfig`.

## On-chain metrics & how they reach Claude (`tradebot/onchain.py`)

Real, free, no-key market-structure context: **Fear & Greed** (alternative.me),
**DeFi TVL** and **stablecoin market cap** (DefiLlama), **ETH gas** (JSON-RPC).
These derive a coarse **risk regime** (`risk_on` / `neutral` / `risk_off`) that
can optionally scale exposure (`BotConfig.onchain_gate`). It's context, not a
standalone signal.

**How on-chain data integrates with Claude** — the pattern, three layers:

1. **Source** — raw chain data comes from an RPC/indexer: a public JSON-RPC node
   (what this repo uses), or a provider like QuickNode/Alchemy, or aggregated
   APIs (DefiLlama, The Graph subgraphs, Dune).
2. **Adapter/tool** — that data is exposed as callable tools. Either a plain
   Python module you call (this repo's `onchain.py`), or an **MCP server** (e.g.
   QuickNode's EVM MCP) that presents `eth_call`, balances, logs, etc. as tools.
3. **Agent** — Claude (Claude Code, or an app using the Agent SDK) calls those
   tools, reasons over the metrics, and either reports or feeds them into the
   bot. In this repo the same functions power the CLI (`tb.py onchain`), the
   dashboard (`/api/onchain`), and the optional engine gate — so "integrating
   on-chain metrics with Claude" here means: Claude runs `onchain.fetch()` (or an
   MCP tool), reads the regime, and the strategy scales exposure accordingly.

## Self-custody: connect a wallet the safe way

`tb.py wallet 0x…` and the dashboard's wallet panel read balances **read-only**
from public chain state — **no keys, no signing, ever**. That is the safe first
step. Automated *execution* from your own wallet is a separate, deliberate
decision with a real security trade-off — see the honest note in the project
discussion; the short version:

- **"Fee-free" DEXs are real-ish**: CoW Swap, 1inch Fusion, and Jupiter charge
  no explicit platform fee and are **gasless** (a solver pays gas), with strong
  **MEV protection** (orders never hit the public mempool). But nothing is truly
  free — you still pay via the spread/price impact baked into execution and the
  underlying pool's LP fee. "No trading fee," not "no cost."
- **Automation vs. custody is a genuine trade-off.** Full "never miss"
  automation requires the bot to sign transactions, which means it holds a key
  or a scoped permission — a real risk to the funds it can reach. The safe
  designs keep your main bags in a wallet the bot can never touch and expose only
  a small, capped trading slice (or use propose-and-sign, where you approve each
  order). This repo ships **none** of that enabled by choice.

## AMPL plugin (the original project)

The original rebase-aware AMPL bot lives on in `ampl_bot/` and as
`tradebot/plugins/ampl.py`. AMPL is special — its supply rebases daily toward a
CPI target, so price mean-reverts and a holder's *units* change with the rebase.
The plugin overlays that on the trend filter (trimming exposure deep in the
"expansion" zone). The full rebase-aware backtester, its real 2019→present data
(via DefiLlama), and the findings — including that pure mean-reversion beat
buy-and-hold *through AMPL's real 2020–22 crash* while a fixed CPI target makes
full-cycle absolute returns unreliable — are documented in `ampl_bot/` and its
scripts (`scripts/regime_test.py`, `scripts/compare_strategies.py`).

## Disclaimer

Educational software, not financial advice. Crypto trading can lose money fast.
You are responsible for legal compliance in your jurisdiction. Backtests are not
forecasts.
