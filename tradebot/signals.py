"""Composite signal engine for day/swing trading any crypto.

Each indicator casts a vote in [-1, +1] (bearish..bullish). Votes are split into
a TREND group and a MEAN-REVERSION group, then blended *adaptively by trend
strength (ADX)* rather than naively averaged — because averaging lets an
"overbought" RSI cancel a valid uptrend and leaves the bot chronically
under-invested. In strong trends we follow the trend; in quiet/ranging markets
we mean-revert. The result maps to a LONG/FLAT target exposure in [0, 1] (no
shorting). A per-signal breakdown is returned for transparency.

Two presets:
  * SWING (daily / 4h): longer indicator lengths, trend-led.
  * DAY (15m / 1h): shorter lengths, breakout/momentum-led.

Nothing here promises an edge. The weighting and blending are hypotheses to be
backtested, not guarantees; TA is hard and fees are real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from . import indicators as ind
from .ohlcv import Bar

# Group membership for the adaptive blend.
_TREND = {"ema_trend", "macd", "adx_dir", "donchian", "roc", "vwap", "obv"}
_MEANREV = {"rsi", "percent_b"}

SWING_WEIGHTS: Dict[str, float] = {
    "ema_trend": 1.4, "macd": 1.0, "adx_dir": 1.0, "donchian": 0.8,
    "rsi": 1.0, "percent_b": 1.0, "vwap": 0.5, "obv": 0.5, "roc": 0.6,
}
DAY_WEIGHTS: Dict[str, float] = {
    "ema_trend": 0.8, "macd": 1.0, "adx_dir": 0.6, "donchian": 1.4,
    "rsi": 1.0, "percent_b": 1.0, "vwap": 1.0, "obv": 0.9, "roc": 1.2,
}

SWING_PARAMS = dict(ema_fast=21, ema_slow=55, rsi_n=14, bb_n=20, atr_n=14,
                    adx_n=14, donchian_n=20, vwap_n=20, roc_n=10, obv_slope=10)
DAY_PARAMS = dict(ema_fast=9, ema_slow=21, rsi_n=14, bb_n=20, atr_n=14,
                  adx_n=14, donchian_n=20, vwap_n=20, roc_n=6, obv_slope=8)


def _last(series: List):
    for v in reversed(series):
        if v is not None:
            return v
    return None


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Signal:
    target_exposure: float
    score: float
    votes: Dict[str, float] = field(default_factory=dict)
    atr_pct: float | None = None
    adx: float | None = None
    reason: str = ""


class CompositeStrategy:
    def __init__(self, style: str = "swing", weights: Dict[str, float] | None = None,
                 aggressiveness: float = 1.2, entry_threshold: float = 0.03,
                 min_long_exposure: float = 0.6):
        style = style.lower()
        self.style = style
        self.params = DAY_PARAMS if style == "day" else SWING_PARAMS
        self.weights = weights or (DAY_WEIGHTS if style == "day" else SWING_WEIGHTS)
        self.aggressiveness = aggressiveness
        self.entry_threshold = entry_threshold
        self.min_long_exposure = min_long_exposure

    def _votes(self, bars: List[Bar]):
        close = [b.close for b in bars]
        high = [b.high for b in bars]
        low = [b.low for b in bars]
        vol = [b.volume for b in bars]
        p = self.params
        price = close[-1]
        v: Dict[str, float] = {}

        ef = _last(ind.ema(close, p["ema_fast"]))
        es = _last(ind.ema(close, p["ema_slow"]))
        if ef and es and es != 0:
            v["ema_trend"] = _clamp((ef / es - 1.0) / 0.05)

        _, _, macd_hist = ind.macd(close)
        h = _last(macd_hist)
        if h is not None and price > 0:
            v["macd"] = _clamp((h / price) / 0.01)

        pdi, mdi, adx_s = ind.adx(high, low, close, p["adx_n"])
        a, pd, md = _last(adx_s), _last(pdi), _last(mdi)
        if a is not None and pd is not None and md is not None and (pd + md) > 0:
            v["adx_dir"] = _clamp((pd - md) / (pd + md) * min(a / 40.0, 1.0))

        r = _last(ind.roc(close, p["roc_n"]))
        if r is not None:
            v["roc"] = _clamp(r / 0.10)

        up, lo = ind.donchian(high, low, p["donchian_n"])
        if len(up) >= 2 and up[-2] is not None and lo[-2] is not None:
            if price >= up[-2]:
                v["donchian"] = 1.0
            elif price <= lo[-2]:
                v["donchian"] = -1.0
            else:
                span = up[-2] - lo[-2]
                v["donchian"] = _clamp(2.0 * (price - lo[-2]) / span - 1.0) if span > 0 else 0.0

        rsi_v = _last(ind.rsi(close, p["rsi_n"]))
        if rsi_v is not None:
            v["rsi"] = _clamp((50.0 - rsi_v) / 30.0)

        pb = _last(ind.percent_b(close, p["bb_n"]))
        if pb is not None:
            v["percent_b"] = _clamp((0.5 - pb) * 2.0)

        vw = _last(ind.rolling_vwap(high, low, close, vol, p["vwap_n"]))
        if vw and vw != 0:
            v["vwap"] = _clamp((price / vw - 1.0) / 0.03)

        obv_series = ind.obv(close, vol)
        n = p["obv_slope"]
        vals = [x for x in obv_series if x is not None]
        if len(vals) > n:
            base = abs(vals[-n]) or 1.0
            v["obv"] = _clamp((vals[-1] - vals[-n]) / base)

        atr_v = _last(ind.atr(high, low, close, p["atr_n"]))
        atr_pct = (atr_v / price) if (atr_v and price > 0) else None
        return v, atr_pct, a

    def _group_score(self, votes: Dict[str, float], group: set) -> float:
        wsum = sum(self.weights.get(k, 0.0) for k in votes if k in group)
        if wsum == 0:
            return 0.0
        return sum(val * self.weights.get(k, 0.0) for k, val in votes.items() if k in group) / wsum

    def generate(self, bars: List[Bar]) -> Signal:
        min_bars = max(self.params["ema_slow"], self.params["adx_n"] * 2, self.params["donchian_n"]) + 5
        if len(bars) < min_bars:
            return Signal(0.0, 0.0, reason="warming up (insufficient history)")

        votes, atr_pct, adx = self._votes(bars)
        trend = self._group_score(votes, _TREND)
        meanrev = self._group_score(votes, _MEANREV)

        # Adaptive blend: ADX ~ trendiness. High ADX -> follow trend; low ADX ->
        # mean-revert. w_trend in [0.25, 1.0] so trend never fully vanishes.
        w_trend = 0.5 if adx is None else _clamp(0.25 + 0.75 * min(adx / 40.0, 1.0), 0.25, 1.0)
        score = w_trend * trend + (1.0 - w_trend) * meanrev

        # Decisive mapping: below the regime threshold -> cash. Above it -> hold a
        # meaningful exposure FLOOR (keep bull-market beta) and scale up with
        # conviction. This is what a timid fractional dial got wrong.
        if score <= self.entry_threshold:
            exposure = 0.0
        else:
            exposure = _clamp(self.min_long_exposure + score * self.aggressiveness,
                              self.min_long_exposure, 1.0)

        top = sorted(votes.items(), key=lambda kv: -abs(kv[1] * self.weights.get(kv[0], 0)))[:3]
        drivers = ", ".join(f"{k}={val:+.2f}" for k, val in top)
        reason = (f"[{self.style}] score={score:+.2f} (trend={trend:+.2f}*{w_trend:.2f}, "
                  f"mr={meanrev:+.2f}) -> {exposure:.0%} | {drivers}")
        return Signal(exposure, score, votes, atr_pct, adx, reason)


class TrendFilterStrategy:
    """The robust workhorse: fully invested when the trend is up, cash when down.

    Regime = price vs. a slow EMA, with a hysteresis buffer to cut whipsaw
    (enter above ema*(1+buf), exit below ema*(1-buf)). In backtests across BTC/
    ETH/SOL this delivered near buy-and-hold returns with much lower drawdowns —
    outperforming the richer CompositeStrategy, which mistimes and pays fees. The
    full signal panel is still computed for the screener/dashboard; it just isn't
    what you trade on.
    """

    def __init__(self, style: str = "swing", ema_len: int | None = None, buffer: float = 0.01):
        self.style = style.lower()
        params = DAY_PARAMS if self.style == "day" else SWING_PARAMS
        self.ema_len = ema_len or params["ema_slow"]
        self.atr_n = params["atr_n"]
        self.buffer = buffer
        self._in = False

    def generate(self, bars: List[Bar]) -> Signal:
        if len(bars) < self.ema_len + 5:
            return Signal(0.0, 0.0, reason="warming up")
        close = [b.close for b in bars]
        high = [b.high for b in bars]
        low = [b.low for b in bars]
        price = close[-1]
        e = _last(ind.ema(close, self.ema_len))
        atr_v = _last(ind.atr(high, low, close, self.atr_n))
        atr_pct = (atr_v / price) if (atr_v and price > 0) else None
        if e is None:
            return Signal(0.0, 0.0, atr_pct=atr_pct, reason="warming up")

        if self._in:
            self._in = price >= e * (1.0 - self.buffer)
        else:
            self._in = price >= e * (1.0 + self.buffer)
        exposure = 1.0 if self._in else 0.0
        score = (price / e - 1.0) if e else 0.0
        reason = f"[{self.style}/trend] px {'>' if self._in else '<'} EMA{self.ema_len} -> {exposure:.0%}"
        return Signal(exposure, score, {"ema_regime": 1.0 if self._in else -1.0}, atr_pct, None, reason)


def build_strategy(scfg):
    """Factory from a StrategyConfig (duck-typed: .kind, .style, ...)."""
    kind = getattr(scfg, "kind", "trend")
    if kind == "trend":
        return TrendFilterStrategy(scfg.style)
    if kind == "composite":
        return CompositeStrategy(scfg.style, scfg.weights, scfg.aggressiveness,
                                 scfg.entry_threshold, scfg.min_long_exposure)
    raise ValueError(f"unknown strategy kind: {kind!r}")
