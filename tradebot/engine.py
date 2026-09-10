"""Live paper-trading engine — the full machine, one candle at a time.

Each new closed candle: read the trend, manage risk (ATR stop + drawdown
breaker), fill, then run the capital-preservation layer (skim profit into the
protected reserve, and spin the flywheel when it's grown enough). ALL state —
portfolio, reserve, risk, and the last processed bar — persists to disk, so a
scheduled runner (e.g. GitHub Actions every few hours) advances one real paper
portfolio across runs instead of starting fresh each time.

Paper-only. No live-order or key-custody path.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import List, Optional

from .config import BotConfig
from .ohlcv import Bar
from .portfolio import Fill, PaperExecutor, Portfolio
from .protection import ProfitProtector, ReserveState
from .risk import RiskManager, RiskState
from .signals import build_strategy

_BARS_PER_YEAR = {"1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520, "1h": 8760,
                  "2h": 4380, "4h": 2190, "6h": 1460, "12h": 730, "1d": 365}


@dataclass
class TickReport:
    ts: int
    price: float
    equity: float          # trading pool
    reserve: float         # banked, protected
    total: float           # trading + reserve
    exposure: float
    action: str
    halted: bool
    reason: str


class TradingEngine:
    def __init__(self, cfg: BotConfig):
        if cfg.mode != "paper":
            raise ValueError(f"mode={cfg.mode!r} unsupported; only 'paper' ships enabled.")
        self.cfg = cfg
        self.strategy = build_strategy(cfg.strategy)
        self.risk = RiskManager(cfg.risk)
        self.execu = PaperExecutor(cfg.costs)
        bpy = _BARS_PER_YEAR.get(cfg.interval, 365)
        self.protector = ProfitProtector(cfg.protection, self.execu, bpy, seed=cfg.starting_cash)
        self.last_ts = 0
        self.started_ts = 0

        st = self._load()
        if st:
            self.pf = Portfolio(cash=st["cash"], units=st.get("units", 0.0))
            self.pf.fills = [Fill(**x) for x in st.get("fills", [])]
            self.rstate = RiskState(**st["risk"])
            self.protector.state = ReserveState(**st["reserve"])
            self.last_ts = st.get("last_ts", 0)
            self.started_ts = st.get("started_ts", 0)
        else:
            self.pf = Portfolio(cash=cfg.starting_cash)
            self.rstate = RiskState(peak_equity=cfg.starting_cash)

    # ---- persistence -----------------------------------------------------
    def _load(self) -> Optional[dict]:
        p = self.cfg.state_path
        if os.path.exists(p):
            try:
                return json.load(open(p))
            except Exception:  # noqa: BLE001
                return None
        return None

    def _save(self) -> None:
        p = self.cfg.state_path
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        json.dump({
            "cash": self.pf.cash, "units": self.pf.units,
            "fills": [asdict(f) for f in self.pf.fills[-200:]],
            "risk": asdict(self.rstate),
            "reserve": asdict(self.protector.state),
            "last_ts": self.last_ts, "started_ts": self.started_ts,
        }, open(p, "w"), indent=1)

    # ---- flow confirmation (experimental, opt-in) ------------------------
    def _flow_gate(self, target: float, price: float):
        """When enabled, only permit a trend-long if the on-chain tape confirms.

        Reads the live tape score for this symbol. "accum" mode requires net
        buying (score > 0); "distexit" only stands aside on strong distribution.
        DEFENSIVE: any flow-fetch failure permits the trade — we never block the
        validated trend strategy on a flaky RPC read.
        """
        fc = self.cfg.strategy
        if not fc.flow_confirm or target <= 0:
            return target, ""
        try:
            from .tape import read_tape
            score = read_tape(self.cfg.symbol, blocks=fc.flow_blocks).score
        except Exception:  # noqa: BLE001
            return target, ""
        if fc.flow_mode == "distexit":
            if score < -fc.flow_dist_thr:
                return 0.0, " | flow: distribution -> stand aside"
        elif score <= 0:
            return 0.0, " | flow: no accumulation -> stay flat"
        return target, ""

    # ---- stepping --------------------------------------------------------
    def _step(self, window: List[Bar]) -> TickReport:
        bar = window[-1]
        price = bar.close
        self.rstate = self.risk.update_and_check(self.rstate, self.pf.equity(price), price)

        action = "hold"
        sig = self.strategy.generate(window)
        if self.rstate.halted:
            self.execu.rebalance_to(self.pf, 0.0, price, bar.ts)
            self.rstate.entry_price = self.rstate.stop_price = None
            action = "HALT -> cash (drawdown breaker)"
        else:
            target = self.risk.clamp_exposure(sig.target_exposure)
            if self.risk.stop_triggered(self.rstate, bar.low) and self.pf.units > 0:
                self.execu.rebalance_to(self.pf, 0.0, price, bar.ts)
                self.rstate.entry_price = self.rstate.stop_price = None
                action = "stop-loss -> cash"
                target = 0.0
            target, flow_note = self._flow_gate(target, price)
            if flow_note:
                action += flow_note
            current = self.pf.exposure(price)
            if not (target > 0 and abs(target - current) < self.cfg.strategy.rebalance_band):
                target = current + self.risk.limit_trade_size(target - current)
                fill = self.execu.rebalance_to(self.pf, target, price, bar.ts)
                if fill is not None:
                    action = f"{fill.side} {fill.units:.6f} @ {fill.price:.4f}"
                    if fill.side == "buy" and self.rstate.entry_price is None:
                        self.risk.set_stop(self.rstate, price, sig.atr_pct)
            if self.pf.units <= 1e-12:
                self.rstate.entry_price = self.rstate.stop_price = None

        # capital-preservation layer: skim to reserve + flywheel reinvest
        reinvests_before = self.protector.state.reinvests
        self.protector.step(self.pf, price, bar.ts)
        if self.protector.state.reinvests > reinvests_before:
            action += " | flywheel: reinvested reserve -> trading"

        return TickReport(bar.ts, price, self.pf.equity(price), self.protector.state.reserve,
                          self.protector.total_equity(self.pf, price), self.pf.exposure(price),
                          action, self.rstate.halted, sig.reason)

    def advance(self, bars: List[Bar]) -> List[TickReport]:
        """Process every new candle since the last run, then persist once.

        Fresh start = forward from NOW: on the first run we take only the current
        candle's position (not a replay of history — that would be a backtest, not
        paper trading), then advance one candle per run thereafter.
        """
        if self.last_ts == 0 and len(bars) >= 2:
            self.last_ts = bars[-2].ts        # only the latest candle counts as "new"
            self.started_ts = bars[-1].ts
        reports: List[TickReport] = []
        for i, b in enumerate(bars):
            if b.ts > self.last_ts:
                reports.append(self._step(bars[: i + 1]))
                self.last_ts = b.ts
        self._save()
        return reports

    def step(self, bars: List[Bar]) -> TickReport:
        """Process the latest candle (compat helper); no-op returns last state."""
        reps = self.advance(bars)
        if reps:
            return reps[-1]
        price = bars[-1].close
        return TickReport(bars[-1].ts, price, self.pf.equity(price), self.protector.state.reserve,
                          self.protector.total_equity(self.pf, price), self.pf.exposure(price),
                          "no new candle", self.rstate.halted, "")

    def snapshot(self, price: float) -> dict:
        s = self.protector.state
        return {
            "symbol": self.cfg.symbol, "interval": self.cfg.interval,
            "price": price, "trading_equity": self.pf.equity(price),
            "reserve": s.reserve, "total": self.protector.total_equity(self.pf, price),
            "exposure": self.pf.exposure(price), "start": self.cfg.starting_cash,
            "total_return": self.protector.total_equity(self.pf, price) / self.cfg.starting_cash - 1.0,
            "skims": s.skims, "reinvests": s.reinvests, "trading_base": s.trading_base,
            "halted": self.rstate.halted, "trades": len(self.pf.fills),
            "started_ts": self.started_ts,
        }
