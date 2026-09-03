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

# Live paper trading (simulated fills, no real orders)
python tb.py paper --symbol BTC --interval 1h --once

# Dashboard: screener + per-coin signal panel + backtest
python -m tradebot.server            # http://127.0.0.1:8000
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
| `tradebot/screener.py` | Rank a coin universe by trend + conviction. |
| `tradebot/server.py` | Zero-dependency dashboard. |
| `tradebot/plugins/ampl.py` | AMPL rebase specialization (see below). |

## Risk & safety model

- **Paper only by default.** `BotConfig.mode="paper"`; the engine refuses other
  modes. No live-order path, no key custody.
- **ATR stop-loss** per position (`entry − mult·ATR`), checked intrabar at the low.
- **Drawdown circuit breaker** that *liquidates to cash* on a breach and
  re-enters only after price recovers — it de-risks, it doesn't just stop trading
  (a bug fixed in the original AMPL project and carried over correctly here).
- **Long/flat spot only** — no leverage, no shorting, no liquidation risk.

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
