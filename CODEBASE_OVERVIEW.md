# Saatgut — Codebase Overview & QC Guide

> **Purpose of this document.** A complete, human-readable map of the Saatgut
> codebase for an external reviewer ("QC bot") to analyze. It explains what every
> part does, how data flows, the security model, what is *validated* vs. *paper
> only*, and where a reviewer should focus scrutiny. Written to be read top-to-bottom
> or used as a reference.
>
> **Repo:** `dustin-hoover/didactic-waddle` · working branch `claude/ampl-trading-bot-rebase-3hjbos`
> **Size:** ~6,700 lines of Python across 35 `tradebot/` modules (+ `__init__`) · 28 test files (296 tests) · 13 scripts · 5 HTML frontends.
> **Runtime dependencies:** none (Python 3.10+ standard library only). Dev dependency: `pytest`.

---

## 0. TL;DR — what this system is

Saatgut is a **non-custodial, multi-chain crypto trading research system** that runs
entirely on **GitHub Actions (compute) + GitHub Pages (static dashboard)** — no
server, no database, no hosted backend. It:

1. Pulls real market + on-chain data on a schedule.
2. Computes a **BTC-primary "bull-market regime gate"** that governs whether to trade.
3. Runs a **paper (simulated) trading engine** with capital-preservation mechanics.
4. Manages an **evolutionary tree of "bags"** (stashes) that spawn, adapt, and cull.
5. Surfaces everything on a phone-first dashboard and offers **propose-and-sign**
   live execution the user signs in their own wallet (CoW on EVM, Jupiter on Solana,
   NEAR Intents cross-chain).

**Critical framing for QC:** The system is deliberately **honest-first**. It is
**paper/dry-run by default**; every live-execution path is **kill-switch gated,
capped, and non-custodial**. Multiple "promising" strategies were built, *tested*,
and found to have **no edge** — they are kept in the tree as negative results, not
removed. The reviewer should treat "this strategy is in the repo" as **not** implying
"this strategy is believed profitable." See §9 (Honest findings) and §10 (Caveats).

---

## 1. Core doctrine (why the code is shaped this way)

These principles are encoded throughout and explain design choices a reviewer might
otherwise flag as overly conservative:

- **BTC is the market-wide regime signal.** BTC leads crypto, so one BTC-based gate
  (`regime.py`) governs trading on *every* chain. In a confirmed bull it allows longs;
  otherwise it blocks new longs but always permits de-risking to cash.
- **Trend-following is a drawdown-reducer, not a return-booster.** Validated on real
  data: it gives up some upside in bulls to cut drawdowns in bears. It is *not* sold
  as a money-printer.
- **Capital preservation over maximization.** The `protection.py` layer skims profit
  into a ring-fenced reserve on new highs and never lets drawdowns claw it back.
- **Non-custodial by construction.** No module ever holds a key, signs, or broadcasts.
  Execution layers produce *proposals* the user signs in their own wallet.
- **Guardrails refuse, they don't clamp silently.** A proposal that breaks a rule
  raises an error (except per-order caps, which clamp intentionally and visibly).
- **Value is conserved.** In the bag tree, money is never minted or lost on internal
  moves (spawn/retire/morph) — only real trading fees leak. This is an invariant the
  reviewer should verify (see §11).
- **Test before trust.** Every strategy claim is backed by a backtest script; several
  were killed when the data said no edge.

Doctrine docs in the repo: `STRATEGY.md` (trading doctrine), `MISSION.md` (give-back
tithe plan), `README.md`, `SETUP_PHONE.md`.

---

## 2. Architecture & data flow

```
            GitHub Actions (cron, every ~2–3h)
                        │
            scripts/build_site.py  ← the orchestrator
                        │
   ┌────────────────────┼─────────────────────────────┐
   │ pull data          │ compute                      │ render
   │  • ohlcv feed       │  • indicators/signals        │  • docs/data.json
   │  • onchain context  │  • regime gate               │  • docs/*.html (copied
   │  • universe discover│  • paper engine + bags       │     from static/)
   │  • carry (funding)  │  • scenarios (windowed)      │  • phone push (ntfy)
   │  • cross-chain quote│  • autopilot DRY-RUN         │
   └────────────────────┴─────────────────────────────┘
                        │
            git commit docs/  →  GitHub Pages serves the dashboard
                        │
     Phone browser loads docs/data.json → dashboards + wallet panel
                        │
     User signs live canary trades IN THEIR OWN WALLET (CoW / Jupiter / NEAR Intents)
```

**Key properties:**
- **Stateless compute.** Each scheduled run clones fresh, computes, commits generated
  files to `docs/`, exits. Persistent state lives in committed JSON under `docs/`
  (paper engine state, bag tree, ledger, alert state).
- **The dashboard is static.** `docs/*.html` are plain files that `fetch('data.json')`
  client-side. No server-side rendering.
- **Secrets** are GitHub Actions secrets (`${{ secrets.* }}`), never in the repo.
  Confirmed: the only 64-hex string in the code is a public Uniswap event-topic hash.

---

## 3. Repository layout

| Path | What's there |
|---|---|
| `tradebot/` | All library code (pure logic + injectable data fetchers). 34 modules. |
| `tests/` | 28 offline test files, 296 tests. Network is always injected/mocked. |
| `scripts/` | `build_site.py` (the orchestrator) + 12 research/backtest scripts. |
| `static/` | HTML frontends (source). Copied to `docs/` by the build. |
| `docs/` | GitHub Pages site: generated `data.json`, copied HTML, persisted state (`bags/`, `alert_state.json`). |
| `.github/workflows/` | `tradebot.yml` (scheduled build), `tape-backfill.yml`. |
| `*.md` | `README`, `STRATEGY`, `MISSION`, `SETUP_PHONE`, this file. |

---

## 4. Module-by-module (the `tradebot/` package)

Grouped by concern. Every "fetcher" is injectable (a `fetch=`/`*_fn=` parameter), so
tests run fully offline — a pattern the reviewer will see everywhere.

### 4.1 Market data, indicators, backtest core
- **`ohlcv.py`** — `Bar` dataclass + `ExchangeFeed`: real OHLCV with multi-venue
  fallback (Binance.US → Coinbase → OKX → CoinGecko) and **pagination for deep
  history** (`start_ms`). `get_feed()` is the singleton accessor; `cg_resolve_id()`
  maps symbols → CoinGecko ids. Daily bars carry real volume.
- **`indicators.py`** — pure technical indicators (SMA, EMA, RSI, ATR, etc.) over
  lists of closes. No state, no network.
- **`signals.py`** — `TrendFilterStrategy` (the validated default: trend regime via
  moving-average structure) and `CompositeStrategy` (multi-indicator conviction
  score). `_last()` helper. Produces a `target_exposure` in [0,1].
- **`config.py`** — `BotConfig`, `StrategyConfig`, `RiskConfig` dataclasses; the
  parameter surface for a backtest/engine run.
- **`backtest.py`** — `run_backtest(bars, cfg) → BacktestResult` with
  `strategy_return`, `buyhold_return`, `sharpe`, `max_drawdown`, reserve stats, skim
  counts. The core simulator used by scenarios and research scripts.
- **`portfolio.py`** — `Portfolio` (cash/units/fills) and `PaperExecutor`
  (rebalance-to-target with fees). Pure accounting.
- **`engine.py`** — `TradingEngine`: the *live paper* engine that persists its state
  to a JSON file and advances one candle per scheduled run. Wraps portfolio + protector.
- **`risk.py`** — position sizing, ATR stops, drawdown circuit-breaker parameters.

### 4.2 Capital preservation
- **`protection.py`** — `ProfitProtector` / `ProtectionConfig` / `ReserveState`.
  Implements: **profit skim** (bank a fraction of each new equity high into a stable
  reserve), **ratchet** (reserve only grows), **reserve floor**, and a **flywheel**
  (recycle reserve back into trading once it grows past a threshold, with
  principal-protection so the seed is never re-risked). *Every move here is a conserved
  internal transfer; only trading fees leak — a key invariant.*

### 4.3 Regime & strategy selection
- **`regime.py`** — the **BTC-primary bull-market gate**. `RegimeConfig`
  (200d/20d SMA structure, buffer/hysteresis, `confirm_days`), `detect()`, `gate()`,
  `sweep()` (parameter sweep), and `apply_umbrella()` (the alt-handling doctrine:
  in a bull an alt can own its trend; in a bear, no new longs but de-risk allowed).
  This is the chain-agnostic master switch.
- **`scenarios.py`** — a curated library of "dial settings" of the validated model:
  `steady` (default), `guardian` (defensive), `runner` (aggressive), `compounder`
  (flywheel-heavy), `scout` (faster trend). `run_scenario()`, `compare()`, and
  **`compare_distribution()`** which reports each scenario's return as a MEDIAN +
  p10–p90 range across sliding windows (because a single point estimate is fragile —
  see the fragility finding in §9).
- **`screener.py`** — ranks a coin universe by current signals (`ScreenRow`): trend,
  composite score, RSI/ATR. Ranks, does not auto-trade.

### 4.4 Multi-chain abstraction, discovery, safety
- **`chains.py`** — the **chain registry / master toggle**. `ChainSpec` declares each
  chain's capabilities honestly (`can_discover`/`can_screen`/`can_execute`), venue,
  vehicle token, etc. `active()` reads the `CHAIN` env var; `enabled()` lists toggled
  chains. Base, Solana, Avalanche, Arbitrum are wired; Robinhood is data-only; Ethereum
  is defined-but-disabled.
- **`universe.py`** — `discover(network, …)`: auto-vets a tradeable universe from
  GeckoTerminal pool depth; `screen_vetted()` (drops rug-screen AVOID, keeps UNKNOWN);
  `to_registry()`. Base58 (Solana) addresses are preserved (not lowercased).
- **`safety.py`** — chain-aware EVM **rug-screen** via Etherscan V2 (owner powers,
  mint authority, proxy, verified source, contract age). `KNOWN_SAFE_*` short-circuits
  for majors. Returns OK/CAUTION/AVOID/UNKNOWN — **never a false clean bill** when it
  can't audit (UNKNOWN, not OK).
- **`solana.py`** — SPL-token rug-screen via `getAccountInfo` (freeze authority = big
  red flag, mint authority = caution). Non-EVM analog of `safety.py`.

### 4.5 Execution (propose-and-sign — NON-CUSTODIAL)
*All three layers NEVER hold a key, sign, or broadcast. They build proposals.*
- **`execution.py`** — EVM propose-and-sign (CoW Protocol / 1inch). `TOKENS` registry
  (verified addresses per chain), `VENUE_SPENDER`, `ExecutionPolicy` (**kill switch
  default off**, per-order cap, slippage bounds, allowlist), `propose()` which raises
  `PolicyError` on a hard-guardrail violation and returns an `OrderProposal` whose
  `ok` is True only when the kill switch is on AND all guardrails pass.
- **`solana_exec.py`** — Solana propose-and-sign via Jupiter. Same guardrail pattern;
  `build_swap_tx()` returns an **unsigned** base64 transaction for the wallet to sign.
- **`near_intents.py`** — cross-chain settlement via the **NEAR Intents 1Click API**.
  Read-only *dry* quotes by default (price discovery, no commitment); reports cost
  honestly as `amountInUsd − amountOutUsd` (all fees folded in). `bridge_cost_bps()`
  plugs a *live* cross-chain cost into the arbitrage scanner. Asset ids resolve against
  the canonical token list, not a guessed formula.
- **`autopilot.py`** — `Autopilot`/`AutopilotConfig`/`Decision`: the **gated dry-run
  decision engine**. `decide()` enforces the regime gate (no new longs when gate OFF),
  a cooldown, a rolling daily cap, a min-move filter, and per-order caps, then calls an
  injectable proposer (EVM default; Solana/Jupiter injectable). `live=False` by default
  — it logs what it *would* do and signs nothing.

### 4.6 Evolutionary bags (the "fractal tree")
- **`bags.py`** — `BagSpec` (reproducible recipe), `Supervisor` (runs the whole tree),
  and three policies:
  - **`SpawnPolicy`** — when a bag multiplies past a trigger (default 2× its seed), it
    carves a fraction of its *protected reserve* into a new child bag (optionally on
    the most opportunistic chain). Value moves, never minted. Optional memory gate
    (`consult_memory`) lets the ledger veto a spawn into weak conditions.
  - **`RetirePolicy`** — natural selection. Two culls: a **deadline** cull (didn't hit
    `survival_target` by `deadline_days`) and a **drawdown** cull (`max_loss_frac`,
    default 10% below seed → cull *now*). A culled bag's capital is swept into the
    strongest survivor (`keep_min` always protected). "Cut the loser, feed the winner."
  - **`MorphPolicy`** — a bag adapts its own scenario to the regime (defensive in a
    bear, growth/aggressive in a confirmed bull), cooldown-gated, value preserved.
  - `advance()` steps every bag, then runs morph/spawn/retire; `snapshot()` reports the
    tree (+ ledger memory summary). **Value-conservation invariants live here.**
- **`ledger.py`** — `BagLedger`: the tree's **memory**. Append-only journal of each
  bag's birth conditions (regime/chain/scenario) and outcome (SUCCESS = it spawned a
  child; FAILURE = it was culled; OPEN = neither yet). `analyze()` produces base rates +
  plain-language lessons; `recommend()` gives a verdict for a proposed spawn — with
  deliberate small-sample honesty (weak-prior shrinkage, minimum sample, "insufficient"
  until there's real evidence).

### 4.7 Opportunity, arbitrage, carry, fundamentals
- **`opportunity.py`** — cross-chain scoring (`best_chain()`): requires a chain be
  executable AND the regime be ON, then ranks by breadth/trend/liquidity. Drives
  cross-chain spawning.
- **`arbitrage.py`** — `find_arbitrage()`: same-asset cross-venue spread **net of real
  costs** (both legs' fees, gas/MEV drag, bridge). Honest by design — usually reports
  net ≤ 0. Accepts a live `bridge_bps_fn` (from NEAR Intents) to replace the static
  bridge assumption. `scan_token()` pulls pools from GeckoTerminal.
- **`carry.py`** — the **funding-carry monitor**. Delta-neutral income idea: long spot
  + short perp earns the funding rate. `realized()` annualizes funding + computes
  persistence (% of periods positive); `is_attractive()` flags coins clearing a
  net-APR AND persistence bar; `fetch_carry()` pulls OKX realized funding +
  `hl_cross_section()` reads Hyperliquid. **Monitor only — no execution.**
- **`fundamentals.py`** — the **quality screener**. Ranks a top-100–150 universe by
  rank-normalized factors: usage (DefiLlama TVL incl. chain-ecosystem TVL + fees),
  liquidity (volume), trend, with a hard safety filter and stablecoin/wrapped exclusion.
  **Candidate generator, not a validated allocator** (see §9).

### 4.8 Research-grade / negative-result modules (kept for honesty)
- **`whales.py`** — whale-transaction detector + forward-return backtest. **Result: no
  edge net of cost** (hit rate ~coin-flip). Kept as a documented negative result.
- **`scalp.py`** — scalp-strategy scaffold. **Result: no edge.** Kept likewise.
- **`tape.py` / `tape_journal.py`** — on-chain block-order-flow ranking and a
  forward-validation journal (does today's flow predict tomorrow's return?). Gated off
  by default (`TB_TAPE`) because it's RPC-heavy; it ranks/records, never trades.

### 4.9 Context, accounting, I/O
- **`onchain.py` / `onchain_feed.py`** — market context: fear/greed, DeFi TVL,
  stablecoin mcap, gas, risk-regime scaling, Chainlink oracle reads. Context, not a
  standalone signal.
- **`tax.py`** — FIFO/HIFO realized-gain lot tracking, estimated-tax computation, and a
  one-transaction estimated-tax **sweep proposal** (unsigned transfer the user signs).
- **`alerts.py`** — trend-flip detection + ntfy phone-push helper.
- **`server.py`** — a small stdlib HTTP server for running the app locally (dev
  convenience; the production dashboard is static Pages).

---

## 5. The orchestrator — `scripts/build_site.py`

The heart of the running system. On each scheduled run it:
1. Loads the feed and alert state.
2. Screens the default universe; computes on-chain context.
3. Computes the **regime gate** (with `REGIME_MODE` auto/on/off override).
4. Discovers + rug-screens the **active chain's** tradeable universe; registers vetted
   tokens into the execution registries.
5. Runs the **autopilot DRY-RUN** on the active chain's vehicle.
6. Advances the **bag tree** (spawn/morph/retire) with the injected `BagLedger`, and
   backfills ledger births for pre-existing bags.
7. Computes the **windowed scenario board**, **cross-chain cost** (NEAR Intents dry
   quotes), and the **carry monitor**.
8. Writes `docs/data.json` (+ `alert_state.json`, bag state), copies `static/*.html` →
   `docs/*.html`, writes `.nojekyll`, and sends phone push alerts.

Everything is wrapped defensively (per-section `try/except`) so one failing data source
never breaks the build. Most heavy/optional features are env-gated (see §8).

**Research scripts** (not run in production; reproduce the honest findings):
`regime_validation.py`, `momentum_experiment.py`, `hf_forecast_experiment.py`,
`screen_backtest.py`, `screen_backtest_long.py`, `screen_opportunities.py`,
`carry_scan.py`, `analyze_reinvest.py`, `tape_backtest.py`, `signal_test.py`,
`trend_flow_test.py`, `portfolio_test.py`.

---

## 6. Frontend (`static/` → `docs/`)

- **`landing.html` → `index.html`** — strategy explainer / entry page.
- **`app_static.html` → `app.html`** — the **dashboard**: regime banner, autopilot
  dry-run, universe (with safety), cross-chain cost, **carry monitor**, paper
  portfolio, scenario board, market context, featured backtest, signal screener. Pure
  client-side; reads `data.json`.
- **`wallet.html` → `wallet.html`** — the **control panel + live execution**: wallet
  connect, the fractal bag tree, **bag memory** panel, and the gated canary panels:
  multi-chain **CoW** (Base/Avax/Arb), **Jupiter** (Solana, Phantom), and
  **NEAR Intents** cross-chain (EVM→EVM). Hardened with a strict **Content-Security-
  Policy** (`connect-src` locked to the exact APIs).
- **`live.html` → `live.html`** — a canvas **live-engine visualization** (regime gate
  as an hourglass pinch, bags as nodes, carry ticker) driven entirely by `data.json`.
- **`tradebot.html`** — an older/auxiliary page.

Security note for QC: the wallet page's live-execution JS re-fetches a fresh quote
immediately before every deposit, reads the recipient from the connected wallet (never
typed), verifies the echoed recipient/amount, and enforces per-move/day/lifetime caps
in `localStorage`. The real hard boundary is the user's in-wallet confirmation + small
balances; the caps are a UX guardrail layered on top.

---

## 7. Testing

- **296 tests across 28 files**, all offline (network injected). Run: `pytest -q`.
- Coverage spans: engine/backtest/portfolio math, protection invariants, regime gate,
  scenarios (+ windowed distribution), chains registry, universe discovery, both EVM
  and Solana rug-screens, EVM/Solana/NEAR execution guardrails, bags (spawn/retire incl.
  drawdown cull/morph), ledger memory, opportunity, arbitrage (incl. live-bridge hook),
  carry math, fundamentals ranking, tax lots, tape journal, and the negative-result
  modules (whales/scalp).
- **Testing philosophy the reviewer should note:** pure logic is separated from I/O;
  fetchers are injected; guardrail tests assert **refusal** (raising) not clamping;
  value-conservation tests assert money is conserved to the cent across spawn/retire.

---

## 8. Configuration & environment variables

All optional; sensible defaults. Set as GitHub Actions `vars`/`secrets`.

| Env var | Effect | Default |
|---|---|---|
| `CHAIN` | Active chain (`base`/`solana`/`avalanche`/`arbitrum`) | `base` (workflow sets `solana`) |
| `REGIME_MODE` | Gate override: `auto`/`on`/`off` | `auto` |
| `TB_RETIRE` | Enable bag retirement/culling | `1` (on) |
| `TB_MAX_LOSS_FRAC` | Drawdown-cull threshold (fraction below seed) | `0.10` |
| `TB_SURVIVAL_*` | Deadline/target/grace/keep-min for retirement | see `bags.py` |
| `TB_SPAWN_*` | Spawn trigger multiple / fraction / child scenario | 2.0 / 0.5 |
| `TB_CROSS_CHAIN` | Allow cross-chain spawning | off |
| `TB_BAG_MEMORY_GATE` | Let the ledger veto weak spawns | off |
| `TB_MORPH` | Enable scenario morphing | off |
| `TB_CARRY` | Build the carry monitor | `1` (on) |
| `TB_CROSSCHAIN` | Build cross-chain cost quotes | `1` (on) |
| `TB_UNIVERSE_*` | Discovery pages / min reserve / screen toggle | see `build_site.py` |
| `TB_TAPE` | Enable on-chain tape analysis (RPC-heavy) | off |
| Secrets | `ETH_RPC_URL`, `SOLANA_RPC_URL`, `ETHERSCAN_API_KEY`, `COINGECKO_API_KEY`, `NTFY_TOPIC` | — |

---

## 9. Honest findings baked into the codebase (important QC context)

These are *empirical results from the repo's own backtests*. "Present in the code"
≠ "believed profitable":

- **Trend + regime gate:** validated as a **drawdown reducer**. Over a full 2021–2026
  cycle (incl. the 2022 bear), the BTC gate turned a −64% 2022 into ~0% and halved
  full-cycle max drawdown — but plain buy-and-hold BTC had the best raw return and
  Sharpe in-sample. Honest conclusion: run the gate for drawdown control, not alpha.
- **Momentum rotation / whale-following / scalp:** **no edge** net of cost. Killed.
- **Supervised price prediction (HF-forecaster stand-in):** directional hit rate ~50%,
  out-of-sample R² ≈ 0 (slightly negative). The "AI predicts the market" thesis fails.
- **Fundamental quality screen (top-100–150):** over a full cycle, the screened basket
  ≈ equal-weight-all and both lose to BTC-only — **no demonstrated selection edge.**
  Kept as a *watchlist/candidate generator*, not an allocator.
- **Scenario leaderboard is fragile:** single-window returns swing wildly (e.g.
  Guardian 11%–158% depending on the window start), which is why the board now reports a
  **median + p10–p90 range** and flags "noisy" vs "stable."
- **Carry (delta-neutral funding):** **real but modest** — ~3–6% net APR on majors,
  persistent (~80–97% of periods positive), market-neutral. Currently **monitored, not
  executed**; it decays as froth fades and needs a perp venue with liquidation risk.

---

## 10. Honest caveats / known limitations

- **Paper, not live, for strategy.** The autopilot and bags are simulated. The only
  real funds that have moved are small manual canary trades the user signed.
- **No unattended live trading.** That would require a hot signing key — deliberately
  **not built** (it's the biggest attack surface). "Automation" means the system
  prepares and the user taps once.
- **Carry needs a perp venue** (Hyperliquid fits the non-custodial model) — not yet
  built; monitor only.
- **Fundamental history is survivorship-biased** (today's survivors) and not fully
  point-in-time for universe membership.
- **Short data history.** Crypto has few independent cycles; treat all backtests as
  necessary-not-sufficient evidence.
- **Live-execution caps in the browser are a UX guardrail**, not a cryptographic
  boundary — the real boundary is in-wallet confirmation + canary-sized balances.

---

## 11. Where the QC bot should focus

Suggested scrutiny, highest-value first:

1. **Value-conservation invariants** (`bags.py` `_maybe_spawn`/`_maybe_retire`,
   `protection.py` `_bank`/flywheel): confirm that on spawn, retire (both deadline and
   drawdown cull), morph, skim, and reinvest, **total value is conserved** (only
   trading fees leak) and nothing is minted. Tests exist; verify the logic too.
2. **Execution guardrails** (`execution.py`, `solana_exec.py`, `near_intents.py`,
   `autopilot.py`): confirm kill switches default **off**, caps clamp/refuse as
   intended, allowlists are enforced, and `ok=True` requires both the switch on AND all
   guardrails passing. Verify no path signs or broadcasts.
3. **The live wallet JS** (`static/wallet.html`): the deposit/sign flows, the CSP, the
   fresh-quote-before-deposit logic, recipient verification, and that the displayed
   deposit address equals the calldata target.
4. **Token-address correctness** (`execution.py` TOKENS, `solana_exec.py`,
   `near_intents.py`, `fundamentals.py`): every hardcoded contract address — a wrong
   address is a real-funds hazard. (They were verified against CoinGecko/GeckoTerminal.)
5. **Rug-screen honesty** (`safety.py`, `solana.py`): confirm it never returns a clean
   bill (OK) when it couldn't actually audit — UNKNOWN must not read as safe.
6. **Regime gate logic** (`regime.py`): hysteresis/`confirm_days` correctness; the
   gate blocks new longs but always allows de-risking.
7. **Defensive I/O**: every network fetcher is wrapped; a failing source degrades
   gracefully and never crashes `build_site.py` or writes a misleading clean result.
8. **Secret hygiene**: confirm no secrets/keys committed (only GitHub Actions secrets;
   the single 64-hex literal is a public Uniswap event-topic hash in `tape.py`).

---

## 12. How to run / reproduce

```bash
# Tests (offline, ~3s)
python3 -m pytest -q

# Static analysis (bug-focused)
python3 -m ruff check tradebot/ scripts/ --select F,E9,B

# Build the dashboard locally (hits live data sources)
python3 scripts/build_site.py      # writes docs/data.json + docs/*.html

# Reproduce an honest finding, e.g. the bear-inclusive selection backtest
python3 scripts/screen_backtest_long.py
```

---

*Generated as a QC handoff document. The codebase's guiding value is honesty: it
reports what is validated, what isn't, and what moves real money — and it keeps its
negative results in the open rather than hiding them.*
