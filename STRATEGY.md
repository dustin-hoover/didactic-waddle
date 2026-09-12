# Strategy doctrine

The design rules the trading engine is built around. Each is backed by a
reproducible experiment in `scripts/`, not by narrative. Re-run them on fresh
data any time — results are regime-dependent and stated with their window.

## 1. BTC is the market's macro trend anchor

Crypto trades as one risk asset, and **BTC leads it**. Alts are effectively
*levered BTC*: they amplify BTC's moves (more upside in bulls, deeper crashes in
bears) and rarely sustain their own trend against a BTC downtrend. So the market
regime is confirmed on **BTC**, and that one switch governs everything.

We read the regime from **BTC's price-trend structure** (price vs the 200-day, a
20d>200d cross, a rising long MA — see `tradebot/regime.py`), **not** from
stock-to-flow. S2F captures the halving/scarcity *rhythm* but failed badly as a
*price predictor* (it projected six figures straight through the 2022 crash). The
trend-structure gate captures "is BTC in a bull" without betting on a discredited
valuation formula.

Evidence: `scripts/regime_validation.py` — the BTC gate captured **95% of
bull-period upside** while cutting full-cycle drawdown **53% → 27%**.

## 2. Alts trade under the BTC umbrella, on their own trend

"Alts follow BTC" and "gating an alt on BTC's exact daily timing hurts the alt"
are both true — it's a lead/lag nuance. Alts follow BTC's *direction* but lag and
overshoot it, so hard-gating an alt to BTC's precise switch clips some of the
alt's own move (ETH: own-trend +108% vs ETH-gated-by-BTC +8% in one window).

The doctrine that resolves it:

> **BTC regime is the risk-on umbrella. Never hold new alt longs while BTC is in
> a confirmed bear. When BTC is bull, trade each alt on its OWN trend.**
> De-risking (selling toward cash) is *always* allowed — the umbrella never traps
> a position.

This deliberately prioritizes capital preservation (no alts in a BTC bear) over
squeezing every last alt point. Encoded as `regime.apply_umbrella()`.

The cleanest way to avoid the lead/lag mismatch entirely is to **trade BTC
itself** — which is what the live vehicle does (cbBTC on Base), so the gate and
the traded asset are the same thing.

## 3. Lower frequency beats higher frequency here

Every time we traded *faster*, results got worse, net of costs: intraday
"day"-style trend, composite over-trading, and the whale-scalp all underperformed
the slower swing trend. The realizable edge in a non-custodial, spot, CoW-executed
setup is **low-turnover trend-timing**, not scalping.

Evidence: `scripts/momentum_experiment.py` (rotation & trend vs buy&hold),
`tradebot/whales.py` (whale-follow backtest: no edge net of cost).

## 4. Everything is gated and paper-first

Kill switch off by default, per-order + daily notional caps, dry-run before live,
and no key/signing in the decision or research code. Live execution is a
deliberate, revocable session-key add-on — never the main wallet.
