"""Build the static dashboard site for GitHub Pages, and fire phone alerts.

Runs on a schedule inside GitHub Actions (the "computer" in a phone-only setup):
  1. pulls live signals across a coin universe + on-chain market context,
  2. backtests each coin and a featured chart,
  3. pushes BUY/EXIT alerts to your phone via ntfy.sh (topic from NTFY_TOPIC),
  4. writes docs/ (index.html explainer, app.html dashboard, data.json) which
     GitHub Pages serves.

State (last long/flat per coin) persists in docs/alert_state.json, committed by
the workflow, so alerts fire only on genuine changes.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tradebot.alerts import push_ntfy  # noqa: E402
from tradebot.backtest import run_backtest  # noqa: E402
from tradebot.config import BotConfig, StrategyConfig  # noqa: E402
from tradebot.ohlcv import get_feed  # noqa: E402
from tradebot.onchain import fetch as fetch_onchain  # noqa: E402
from tradebot.screener import DEFAULT_UNIVERSE  # noqa: E402
from tradebot.signals import CompositeStrategy, TrendFilterStrategy, _last  # noqa: E402
from tradebot import indicators as ind  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
# On-chain data is daily-only, so force a 1d screener interval in on-chain mode.
ONCHAIN = os.environ.get("TB_DATA_SOURCE", "auto").lower() == "onchain"
INTERVAL = "1d" if ONCHAIN else os.environ.get("TB_INTERVAL", "4h")
STYLE = os.environ.get("TB_STYLE", "swing")
NTFY = os.environ.get("NTFY_TOPIC", "").strip()


def load_state():
    p = os.path.join(DOCS, "alert_state.json")
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def build():
    os.makedirs(DOCS, exist_ok=True)
    feed = get_feed()
    state = load_state()
    rows = []
    alerts = []

    for sym in DEFAULT_UNIVERSE:
        try:
            bars = feed.history(sym, INTERVAL, 1000)
            trend = TrendFilterStrategy(STYLE).generate(bars)
            comp = CompositeStrategy(STYLE).generate(bars)
            bt = run_backtest(bars, BotConfig(symbol=sym, interval=INTERVAL,
                                              strategy=StrategyConfig(kind="trend", style=STYLE)))
            now_long = trend.target_exposure > 0
            rows.append({
                "symbol": sym, "price": bars[-1].close, "trend_up": now_long,
                "score": round(comp.score, 3), "rsi": _last(ind.rsi([b.close for b in bars], 14)),
                "atr_pct": comp.atr_pct, "reason": comp.reason,
                "ret": bt.strategy_return, "bh": bt.buyhold_return, "dd": bt.max_drawdown,
                "reserve": bt.reserve_final, "reserve_frac": bt.reserve_frac,
            })
            was = state.get(sym)
            if was is not None and was != now_long:
                action = "BUY" if now_long else "EXIT"
                msg = (f"{sym} {INTERVAL}: trend flipped {'UP → BUY' if now_long else 'DOWN → EXIT to cash'} "
                       f"@ ${bars[-1].close:,.2f}")
                alerts.append((action, sym, msg))
            state[sym] = now_long
        except Exception as e:  # noqa: BLE001
            rows.append({"symbol": sym, "error": str(e)[:80]})

    rows.sort(key=lambda r: (r.get("trend_up", False), r.get("score", -9)), reverse=True)

    # on-chain context
    try:
        m = fetch_onchain()
        onchain = {"fear_greed": m.fear_greed, "fear_greed_label": m.fear_greed_label,
                   "defi_tvl_usd": m.defi_tvl_usd, "stablecoin_mcap_usd": m.stablecoin_mcap_usd,
                   "eth_gas_gwei": m.eth_gas_gwei, "risk_regime": m.risk_regime,
                   "exposure_scale": m.exposure_scale()}
    except Exception as e:  # noqa: BLE001
        onchain = {"error": str(e)[:80]}

    # featured chart: BTC daily
    featured = {}
    try:
        fb = feed.history("BTC", "1d", 1000)
        fr = run_backtest(fb, BotConfig(symbol="BTC", interval="1d",
                                        strategy=StrategyConfig(kind="trend")))
        start = fb[0].close
        bh = [10000 * (b.close / start) for b in fb]
        step = max(1, len(fb) // 160)
        featured = {"symbol": "BTC", "interval": "1d",
                    "dates": [b.date[:10] for b in fb][::step],
                    "strategy": [round(x, 1) for x in fr.equity_curve][::step],
                    "buyhold": [round(x, 1) for x in bh][::step],
                    "stats": {"strat_ret": fr.strategy_return, "bh_ret": fr.buyhold_return,
                              "strat_dd": fr.max_drawdown, "sharpe": fr.sharpe,
                              "reserve": fr.reserve_final, "reserve_frac": fr.reserve_frac,
                              "skims": fr.num_skims}}
    except Exception as e:  # noqa: BLE001
        featured = {"error": str(e)[:80]}

    # REGIME GATE — the BTC-primary bull-market master switch. Computed at build time
    # off BTC daily; REGIME_MODE (auto|on|off) is the manual override. When the gate
    # is OFF the engine holds flat (no new longs); de-risking is always allowed.
    regime = {}
    try:
        from tradebot.regime import RegimeConfig, detect, sweep
        rmode = os.environ.get("REGIME_MODE", "auto").strip().lower()
        rmode = rmode if rmode in ("auto", "on", "off") else "auto"
        rb = feed.history("BTC", "1d", 400)
        rcloses = [b.close for b in rb]
        st = detect(rcloses, RegimeConfig(mode=rmode))
        market = detect(rcloses, RegimeConfig(mode="auto"))   # the market's own read, ignoring override
        states = sweep(rcloses)
        last_switch = None
        for i in range(len(states) - 1, 0, -1):
            if states[i] != states[i - 1]:
                last_switch = {"date": rb[i].date[:10], "to": "ON" if states[i] else "OFF",
                               "price": round(rb[i].close, 2)}
                break
        regime = {"on": st.on, "regime": st.regime, "mode": rmode,
                  "auto_on": market.on, "confirmed": st.confirmed,
                  "price": st.price, "pct_above_long": st.pct_above_long,
                  "sma_long": st.sma_long, "sma_short": st.sma_short,
                  "golden_cross": st.golden_cross, "long_rising": st.long_rising,
                  "days_in_regime": st.days_in_regime, "reason": st.reason,
                  "last_switch": last_switch}
    except Exception as e:  # noqa: BLE001
        regime = {"error": str(e)[:80]}

    # CHAIN TOGGLE — the active chain (CHAIN env) drives which chain the services run on.
    from tradebot import chains
    spec = chains.active()
    chains_block = {"active": spec.id, "active_name": spec.name,
                    "list": [c.to_dict() for c in chains.enabled()]}

    # UNIVERSE — auto-vet which tokens on the ACTIVE chain are safe/liquid enough to
    # trade (live on-chain depth via GeckoTerminal + listing + rug-screen where the
    # chain supports it). This is the MENU; the strategy (BTC-led + caps) still decides
    # what to trade. EVM vetted sets are registered into the execution token registry.
    universe = {}
    try:
        from tradebot.universe import discover, to_registry
        min_res = float(os.environ.get("TB_UNIVERSE_MIN_RESERVE", "250000"))
        if spec.can_discover:
            do_screen = (spec.can_screen and os.environ.get("TB_UNIVERSE_SCREEN", "1").strip()
                         in ("1", "true", "on"))
            # Solana screens via the SPL mint-authority check; EVM via safety.check.
            screen_fn = None
            if do_screen and spec.kind == "svm":
                from tradebot.solana import check as _sol_check
                screen_fn = _sol_check
            vetted = discover(
                spec.gt_network,
                pages=int(os.environ.get("TB_UNIVERSE_PAGES", "4")),
                min_reserve_usd=min_res, screen=do_screen, screen_fn=screen_fn,
                screen_chain=spec.id)
            if spec.kind == "evm":
                from tradebot.execution import register_tokens
                register_tokens(spec.id, to_registry(vetted))
            else:
                from tradebot.solana_exec import register_tokens as _sol_register
                _sol_register({v.symbol: (v.address, v.decimals) for v in vetted})
            universe = {"chain": spec.id, "count": len(vetted), "min_reserve_usd": min_res,
                        "screened": do_screen, "tokens": [v.to_dict() for v in vetted]}
        else:
            universe = {"chain": spec.id, "count": 0, "note": "discovery not available for this chain"}
    except Exception as e:  # noqa: BLE001
        universe = {"error": str(e)[:120]}

    # AUTOPILOT — DRY RUN, on the active chain (only where execution is wired). Each
    # cycle decides what the regime-gated engine WOULD trade (vehicle's own trend under
    # the BTC umbrella -> guardrails), logs it, and on a genuine transition alerts the
    # phone. Base trades cbBTC via CoW; Solana trades SOL via Jupiter. live=False, so
    # nothing is ever signable here.
    autopilot = {}
    try:
        if not spec.can_execute:
            autopilot = {"chain": spec.id, "supported": False,
                         "note": f"trade execution not yet wired for {spec.name} "
                                 f"(venue: {spec.exec_venue or 'n/a'})"}
        else:
            from tradebot.autopilot import Autopilot, AutopilotConfig
            base = spec.primary_vehicle
            allowed = tuple(dict.fromkeys([spec.stable, "WETH", base] if spec.kind == "evm"
                                          else [spec.stable, base]))
            apcfg = AutopilotConfig(
                enabled=True, live=False,
                max_notional_usd=float(os.environ.get("TB_AP_MAX", "100")),
                daily_cap_usd=float(os.environ.get("TB_AP_DAILY", "300")),
                cooldown_min=int(os.environ.get("TB_AP_COOLDOWN", "60")),
                chain=spec.id, stable=spec.stable, allowed_tokens=allowed)
            # Per-chain proposal builder: Jupiter for Solana, EVM execution otherwise.
            proposer = None
            if spec.kind == "svm":
                from tradebot import solana_exec as _sx
                _solpol = _sx.SolanaExecPolicy(enabled=False, max_notional_usd=apcfg.max_notional_usd,
                                               allowed_tokens=allowed)
                def proposer(bag_id, wallet, sell, buy, notional, price_usd):  # noqa: E306
                    return _sx.propose(wallet, sell, buy, notional, price_usd, _solpol)
            ap = Autopilot(apcfg, os.path.join(DOCS, f"autopilot_{spec.id}.json"), propose_fn=proposer)
            logp = os.path.join(DOCS, f"autopilot_log_{spec.id}.json")
            book = json.load(open(logp)) if os.path.exists(logp) else {"exposure": {}, "decisions": []}
            regime_on = bool(regime.get("on"))
            now_ts = int(time.time())
            eb = feed.history(spec.vehicle_coin, "1d", 400)   # the vehicle's OWN trend
            price = eb[-1].close
            from tradebot.signals import TrendFilterStrategy as _TF
            tgt = _TF(STYLE).generate(eb).target_exposure
            cur = float(book["exposure"].get(base, 0.0))
            prices = {base: price, spec.stable: 1.0}
            d = ap.decide("paper", "dry-run", tgt, cur, apcfg.max_notional_usd,
                          base, prices, now_ts, regime_on=regime_on)
            entry = {"ts": now_ts, "asset": base, "action": d.action,
                     "notional": round(d.notional_usd, 2), "target": round(tgt, 3),
                     "current": round(cur, 3), "gate": "ON" if regime_on else "OFF",
                     "price": round(price, 2), "reason": d.reason, "blocked": d.blocked}
            latest = [entry]
            if d.action in ("buy", "sell"):          # a genuine transition: simulate the paper fill
                book["exposure"][base] = tgt if (d.action == "sell" or regime_on) else cur
                ap.record_fill(d.notional_usd, now_ts)
                book["decisions"] = ([entry] + book.get("decisions", []))[:60]
                alerts.append((d.action.upper(), spec.vehicle_coin,
                               f"[DRY-RUN] autopilot WOULD {d.action} ${d.notional_usd:,.0f} {base} "
                               f"on {spec.name} @ ${price:,.0f} (gate {'ON' if regime_on else 'OFF'})"))
            json.dump(book, open(logp, "w"), indent=1)
            autopilot = {"enabled": apcfg.enabled, "live": apcfg.live, "gate_on": regime_on,
                         "chain": spec.id, "max_notional": apcfg.max_notional_usd,
                         "daily_cap": apcfg.daily_cap_usd,
                         "spent_today": round(ap.state.spent_usd, 2),
                         "trades_today": ap.state.trades_today,
                         "latest": latest, "recent": book["decisions"][:8],
                         "exposure": book["exposure"]}
    except Exception as e:  # noqa: BLE001
        autopilot = {"error": str(e)[:120]}

    # LIVE PAPER BAGS — one supervised tree of stashes (the root bag IS the paper
    # portfolio). Each run advances every bag and lets the tree spawn fractally.
    # State persists under docs/bags/ (committed) across scheduled runs.
    paper, bag_tree = {}, {}
    try:
        from tradebot.bags import Supervisor, SpawnPolicy, RetirePolicy, MorphPolicy
        bars_cache = {}
        def bars_for(sym, interval):
            k = f"{sym}:{interval}"
            if k not in bars_cache:
                bars_cache[k] = feed.history(sym, interval, 400)
            return bars_cache[k]
        # Spawn policy is operator-set (envs): how much a bag must multiply before it
        # spins off a child, and which scenario that child runs (default: inherit).
        policy = SpawnPolicy(
            trigger_multiple=float(os.environ.get("TB_SPAWN_TRIGGER", "2.0")),
            fraction=float(os.environ.get("TB_SPAWN_FRACTION", "0.5")),
            child_scenario=(os.environ.get("TB_SPAWN_CHILD", "").strip() or None),
            cross_chain=os.environ.get("TB_CROSS_CHAIN", "").strip() in ("1", "true", "on"),
            # Memory gate: let the ledger VETO a spawn whose birth conditions have a weak
            # track record. Off by default — it only bites once there's enough history,
            # but it's a deliberate opt-in (TB_BAG_MEMORY_GATE=1).
            consult_memory=os.environ.get("TB_BAG_MEMORY_GATE", "").strip() in ("1", "true", "on"))
        # Cross-chain selector: on a spawn, pick the most opportunistic executable chain
        # (opportunity.best_chain over live per-chain breadth/liquidity, gated by the BTC
        # regime). Lazy — only runs when a bag actually reproduces, so normal runs stay fast.
        chain_selector = None
        if policy.cross_chain:
            from tradebot import opportunity as _opp
            from tradebot.universe import discover as _disc
            _minres = float(os.environ.get("TB_UNIVERSE_MIN_RESERVE", "250000"))
            def chain_selector():   # noqa: E306
                sig = {}
                for c in chains.enabled():
                    if not c.can_execute:
                        continue
                    try:
                        u = _disc(c.gt_network, pages=1, min_reserve_usd=_minres) if c.can_discover else []
                    except Exception:  # noqa: BLE001
                        u = []
                    avg_liq = (sum(v.reserve_usd for v in u) / len(u)) if u else 0.0
                    sig[c.id] = dict(executable=True, regime_on=bool(regime.get("on")),
                                     universe_count=len(u),
                                     vehicle_trend=1.0 if regime.get("on") else 0.0,
                                     avg_liquidity_usd=avg_liq)
                return _opp.best_chain(sig, default=spec.id)
        # Evolutionary retirement: a bag that hasn't reached TB_SURVIVAL_TARGET x its
        # seed by TB_SURVIVAL_DEADLINE_DAYS is culled; the strongest always survive
        # (keep_min=1) and absorb the culled value. Default target 1.0 = "don't lose
        # money" (realistic). Crank TB_SURVIVAL_TARGET toward 1000 and the tree prunes
        # to just its single strongest bag — an honest demo that a 1000x bar terminates
        # almost everything. Off unless TB_RETIRE is set, so it's a deliberate choice.
        retire = RetirePolicy(
            enabled=os.environ.get("TB_RETIRE", "").strip() in ("1", "true", "on"),
            survival_target=float(os.environ.get("TB_SURVIVAL_TARGET", "1.0")),
            deadline_days=float(os.environ.get("TB_SURVIVAL_DEADLINE_DAYS", "90")),
            keep_min=int(os.environ.get("TB_SURVIVAL_KEEP_MIN", "1")))
        # Morph policy: a bag adapts its own strategy to the BTC regime (defensive in a
        # bear, growth/aggressive in a confirmed bull). Gated by TB_MORPH.
        morph = MorphPolicy(enabled=os.environ.get("TB_MORPH", "").strip() in ("1", "true", "on"),
                            cooldown_days=float(os.environ.get("TB_MORPH_COOLDOWN_DAYS", "7")))
        # The tree's MEMORY — an append-only ledger of births + outcomes (survived by
        # reproducing, or culled) with the conditions at birth, persisted under
        # docs/bags/ledger.json across runs so lessons accumulate over weeks.
        from tradebot.ledger import BagLedger
        ledger = BagLedger(os.path.join(DOCS, "bags", "ledger.json"))
        sup = Supervisor(os.path.join(DOCS, "bags"), policy, retire=retire,
                         chain_selector=chain_selector, morph=morph, ledger=ledger)
        if not sup.specs:
            sup._signals = {"regime_on": bool(regime.get("on")),
                            "strength": float(regime.get("pct_above_long") or 0.0),
                            "risk_regime": onchain.get("risk_regime")}
            sup.add_bag("steady", seed=1000.0)      # root bag = the paper portfolio
        # Backfill births for bags that predate the ledger (idempotent). Their true
        # birth regime is unknown, so record it as such rather than fabricating it —
        # future outcomes still link to them; new spawns carry the live conditions.
        for _s in sup.specs.values():
            ledger.record_birth(_s.id, scenario=_s.scenario, chain=getattr(_s, "chain", "base"),
                                seed=_s.seed, parent=_s.parent, regime_on=None, strength=None,
                                ts=_s.created_ts or None)
        bag_tree = sup.advance(bars_for, signals={"regime_on": bool(regime.get("on")),
                                                  "strength": float(regime.get("pct_above_long") or 0.0),
                                                  "risk_regime": onchain.get("risk_regime")})
        root = next((b for b in bag_tree["bags"] if b["parent"] is None), None)
        if root:                                     # map root -> the existing paper panel
            paper = {"symbol": "BTC", "interval": "1d", "trading_equity": root["trading"],
                     "reserve": root["reserve"], "total": root["total"],
                     "exposure": root["exposure"], "total_return": root["total_return"],
                     "start": root["seed"], "trades": root["trades"],
                     "reinvests": 0, "skims": 0}
    except Exception as e:  # noqa: BLE001
        paper = bag_tree = {"error": str(e)[:80]}

    # ON-CHAIN TAPE — strongest block-order flow of the day. Gated behind TB_TAPE=1
    # because reading a day of Uniswap V3 swaps across the universe is heavy on
    # public RPC; keep it off for fast/reliable default runs. Set your own
    # ETH_RPC_URL and TB_TAPE=1 to enable. It ranks/reads flow; it does NOT trade.
    tape = {}
    if os.environ.get("TB_TAPE", "").strip() in ("1", "true", "on"):
        try:
            from tradebot.tape import rank_universe
            blk = int(os.environ.get("TB_TAPE_BLOCKS", "3600"))  # ~12h default
            tape = {"blocks": blk, "rows": [
                {"symbol": t.symbol, "score": round(t.score, 3), "bias": t.bias,
                 "net_usd": round(t.net_usd), "buy_usd": round(t.buy_usd),
                 "sell_usd": round(t.sell_usd), "whale_share": round(t.whale_share, 3),
                 "n_prints": t.n_prints, "price": t.price,
                 "largest": ({"side": t.largest.side, "usd": round(t.largest.usd_size),
                              "price": t.largest.price} if t.largest else None),
                 "error": t.error}
                for t in rank_universe(blocks=blk, top=10)]}
        except Exception as e:  # noqa: BLE001
            tape = {"error": str(e)[:80]}
        # Accumulate the forward-validation sample: log today's flow, then measure
        # whether past flow predicted realized returns. Grows over weeks.
        if tape.get("rows"):
            try:
                from tradebot import tape_journal as tj
                jpath = os.path.join(DOCS, "tape_journal.json")
                journal = tj.record(tj.load(jpath), tape["rows"])
                tj.save(jpath, journal)
                tape["edge"] = tj.analyze(journal)
            except Exception as e:  # noqa: BLE001
                tape["edge"] = {"error": str(e)[:80]}

    # SCENARIO BOARD — the 401k-style comparison: each scenario's realized paper
    # return on the same real data, so a wallet can pick or rebalance between them.
    scenarios = {}
    try:
        from tradebot import scenarios as sc
        sbars = feed.history("BTC", "1d", 1000)
        scenarios = {"symbol": "BTC", "interval": "1d", "cash": 1000,
                     "span": f"{sbars[0].date[:10]} -> {sbars[-1].date[:10]}",
                     "rows": sc.compare(sbars, starting_cash=1000)}
    except Exception as e:  # noqa: BLE001
        scenarios = {"error": str(e)[:80]}

    # CROSS-CHAIN COST — live NEAR Intents dry quotes for the moves our doctrine
    # cares about (spawn a bag onto another chain, relocate a stable, exit home).
    # Read-only: every quote is `dry` (price only), nothing signable. Fully
    # defensive — a rate-limit or outage yields {error} and never breaks the build.
    # Disable with TB_CROSSCHAIN=0.
    crosschain = {}
    if os.environ.get("TB_CROSSCHAIN", "1").strip() not in ("0", "false", "off"):
        try:
            from tradebot import near_intents as ni
            toks = ni.fetch_tokens()
            sol_px = 0.0
            try:
                sol_px = feed.history("SOL", "1d", 5)[-1].close
            except Exception:  # noqa: BLE001
                pass
            px = {"USDC": 1.0, "SOL": sol_px}
            routes = [("base", "solana", "USDC", "SOL", "spawn → Solana"),
                      ("base", "avalanche", "USDC", "USDC", "relocate stable → Avalanche"),
                      ("base", "arbitrum", "USDC", "USDC", "relocate stable → Arbitrum"),
                      ("solana", "base", "SOL", "USDC", "exit Solana → Base")]
            legs = []
            for oc, dc, os_, ds, label in routes:
                try:
                    q = ni.quote(oc, dc, os_, ds, 50.0, price_usd=px, tokens=toks)
                    legs.append({"label": label, "origin": oc, "dest": dc,
                                 "sell": os_, "buy": ds, "in_usd": q.amount_in_usd,
                                 "out": q.amount_out, "out_usd": q.amount_out_usd,
                                 "cost_usd": q.cost_usd, "cost_bps": q.cost_bps,
                                 "eta_s": q.time_estimate_s})
                except Exception as e:  # noqa: BLE001
                    legs.append({"label": label, "origin": oc, "dest": dc,
                                 "sell": os_, "buy": ds, "error": str(e)[:80]})
            ok = [l for l in legs if "cost_bps" in l]
            crosschain = {"venue": "NEAR Intents (1Click)", "notional_usd": 50,
                          "dry": True, "legs": legs,
                          "assumed_bridge_bps": 100,  # arbitrage.py's static assumption
                          "median_cost_bps": (sorted(l["cost_bps"] for l in ok)[len(ok)//2]
                                              if ok else None)}
        except Exception as e:  # noqa: BLE001
            crosschain = {"error": str(e)[:120]}

    data = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "interval": INTERVAL, "style": STYLE, "onchain": onchain, "regime": regime,
            "chains": chains_block, "autopilot": autopilot, "universe": universe,
            "rows": rows, "featured": featured, "paper": paper, "tape": tape,
            "scenarios": scenarios, "bag_tree": bag_tree, "crosschain": crosschain}
    json.dump(data, open(os.path.join(DOCS, "data.json"), "w"), indent=1)
    json.dump(state, open(os.path.join(DOCS, "alert_state.json"), "w"))

    # copy explainer -> docs/index.html (rewrite the in-app app link to a relative one)
    landing = open(os.path.join(ROOT, "static", "landing.html")).read().replace('href="/app"', 'href="app.html"')
    open(os.path.join(DOCS, "index.html"), "w").write(landing)
    # copy the static dashboard template -> docs/app.html
    app = open(os.path.join(ROOT, "static", "app_static.html")).read()
    open(os.path.join(DOCS, "app.html"), "w").write(app)
    # copy the wallet control panel -> docs/wallet.html (reads docs/data.json)
    wallet = open(os.path.join(ROOT, "static", "wallet.html")).read()
    open(os.path.join(DOCS, "wallet.html"), "w").write(wallet)
    open(os.path.join(DOCS, ".nojekyll"), "w").write("")

    # push phone alerts
    pushed = 0
    if NTFY:
        for action, sym, msg in alerts:
            if push_ntfy(NTFY, f"{action} {sym}", msg, priority="high"):
                pushed += 1

    gate = ("?" if regime.get("on") is None else ("ON" if regime["on"] else "OFF"))
    print(f"built docs/ · chain {spec.id} · {len([r for r in rows if 'error' not in r])} coins · "
          f"{len(alerts)} flips · {pushed} pushed · risk {onchain.get('risk_regime')} · "
          f"bull-gate {gate} ({regime.get('mode','?')}) · universe {universe.get('count','?')}")


if __name__ == "__main__":
    build()
