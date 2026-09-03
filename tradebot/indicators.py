"""Technical indicators — the critical signals for day/swing trading.

Pure functions over price/volume lists. Each returns a full series aligned to the
input length, padded with ``None`` until it has enough data, so a backtester can
read the last element at each step and a chart can plot the whole thing.

Grouped by what they measure:
  trend/momentum : ema, sma, macd, adx, roc
  mean reversion : rsi, bollinger (+ percent_b), stochastic
  volatility     : true_range, atr, realized_vol
  volume         : obv, rolling_vwap
  structure      : donchian

Smoothing follows the standard conventions (Wilder's smoothing for RSI/ATR/ADX)
so values match what traders and charting tools show.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

Series = List[Optional[float]]


def sma(values: List[float], n: int) -> Series:
    out: Series = [None] * len(values)
    if n <= 0:
        return out
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= n:
            run -= values[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def ema(values: List[float], n: int) -> Series:
    out: Series = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    k = 2.0 / (n + 1.0)
    prev = sum(values[:n]) / n  # seed with SMA
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def roc(values: List[float], n: int) -> Series:
    out: Series = [None] * len(values)
    for i in range(n, len(values)):
        if values[i - n] != 0:
            out[i] = (values[i] / values[i - n] - 1.0)
    return out


def rsi(values: List[float], n: int = 14) -> Series:
    out: Series = [None] * len(values)
    if len(values) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        ch = values[i] - values[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    avg_gain = gains / n
    avg_loss = losses / n
    out[n] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1 + avg_gain / avg_loss)
    for i in range(n + 1, len(values)):
        ch = values[i] - values[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(ch, 0.0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-ch, 0.0)) / n
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1 + avg_gain / avg_loss)
    return out


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Series, Series, Series]:
    ef, es = ema(values, fast), ema(values, slow)
    line: Series = [None if (a is None or b is None) else a - b for a, b in zip(ef, es)]
    vals = [x for x in line if x is not None]
    sig_vals = ema(vals, signal)
    sig: Series = [None] * len(values)
    # align signal EMA back onto the full-length series
    j = 0
    for i in range(len(line)):
        if line[i] is not None:
            sig[i] = sig_vals[j]
            j += 1
    hist: Series = [None if (l is None or s is None) else l - s for l, s in zip(line, sig)]
    return line, sig, hist


def bollinger(values: List[float], n: int = 20, k: float = 2.0) -> Tuple[Series, Series, Series]:
    mid = sma(values, n)
    upper: Series = [None] * len(values)
    lower: Series = [None] * len(values)
    for i in range(n - 1, len(values)):
        window = values[i - n + 1:i + 1]
        mean = mid[i]
        var = sum((x - mean) ** 2 for x in window) / n
        sd = math.sqrt(var)
        upper[i] = mean + k * sd
        lower[i] = mean - k * sd
    return mid, upper, lower


def percent_b(values: List[float], n: int = 20, k: float = 2.0) -> Series:
    mid, up, lo = bollinger(values, n, k)
    out: Series = [None] * len(values)
    for i in range(len(values)):
        if up[i] is not None and lo[i] is not None and up[i] != lo[i]:
            out[i] = (values[i] - lo[i]) / (up[i] - lo[i])
    return out


def true_range(high: List[float], low: List[float], close: List[float]) -> Series:
    out: Series = [None] * len(close)
    for i in range(len(close)):
        if i == 0:
            out[i] = high[i] - low[i]
        else:
            out[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return out


def atr(high: List[float], low: List[float], close: List[float], n: int = 14) -> Series:
    tr = [x if x is not None else 0.0 for x in true_range(high, low, close)]
    out: Series = [None] * len(close)
    if len(close) <= n:
        return out
    prev = sum(tr[1:n + 1]) / n  # Wilder seed (skip the first TR, which has no prev close)
    out[n] = prev
    for i in range(n + 1, len(close)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def adx(high: List[float], low: List[float], close: List[float], n: int = 14) -> Tuple[Series, Series, Series]:
    length = len(close)
    plus_di: Series = [None] * length
    minus_di: Series = [None] * length
    adx_s: Series = [None] * length
    if length <= 2 * n:
        return plus_di, minus_di, adx_s

    tr = [0.0] * length
    plus_dm = [0.0] * length
    minus_dm = [0.0] * length
    for i in range(1, length):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

    atr_w = sum(tr[1:n + 1])
    pdm_w = sum(plus_dm[1:n + 1])
    mdm_w = sum(minus_dm[1:n + 1])
    dx_list = []
    for i in range(n + 1, length):
        atr_w = atr_w - atr_w / n + tr[i]
        pdm_w = pdm_w - pdm_w / n + plus_dm[i]
        mdm_w = mdm_w - mdm_w / n + minus_dm[i]
        if atr_w == 0:
            continue
        pdi = 100.0 * pdm_w / atr_w
        mdi = 100.0 * mdm_w / atr_w
        plus_di[i] = pdi
        minus_di[i] = mdi
        denom = pdi + mdi
        dx = 0.0 if denom == 0 else 100.0 * abs(pdi - mdi) / denom
        dx_list.append((i, dx))
        if len(dx_list) == n:
            adx_s[i] = sum(d for _, d in dx_list) / n
        elif len(dx_list) > n:
            adx_s[i] = (adx_s[i - 1] * (n - 1) + dx) / n
    return plus_di, minus_di, adx_s


def obv(close: List[float], volume: List[float]) -> Series:
    out: Series = [None] * len(close)
    if not close:
        return out
    run = 0.0
    out[0] = 0.0
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            run += volume[i]
        elif close[i] < close[i - 1]:
            run -= volume[i]
        out[i] = run
    return out


def rolling_vwap(high: List[float], low: List[float], close: List[float], volume: List[float], n: int = 20) -> Series:
    out: Series = [None] * len(close)
    tp = [(high[i] + low[i] + close[i]) / 3.0 for i in range(len(close))]
    for i in range(n - 1, len(close)):
        vol_sum = sum(volume[i - n + 1:i + 1])
        if vol_sum > 0:
            out[i] = sum(tp[j] * volume[j] for j in range(i - n + 1, i + 1)) / vol_sum
    return out


def donchian(high: List[float], low: List[float], n: int = 20) -> Tuple[Series, Series]:
    up: Series = [None] * len(high)
    lo: Series = [None] * len(low)
    for i in range(n - 1, len(high)):
        up[i] = max(high[i - n + 1:i + 1])
        lo[i] = min(low[i - n + 1:i + 1])
    return up, lo


def stochastic(high: List[float], low: List[float], close: List[float], k: int = 14, d: int = 3) -> Tuple[Series, Series]:
    kk: Series = [None] * len(close)
    for i in range(k - 1, len(close)):
        hh = max(high[i - k + 1:i + 1])
        ll = min(low[i - k + 1:i + 1])
        kk[i] = 50.0 if hh == ll else 100.0 * (close[i] - ll) / (hh - ll)
    kvals = [x for x in kk if x is not None]
    dsm = sma(kvals, d)
    dd: Series = [None] * len(close)
    j = 0
    for i in range(len(kk)):
        if kk[i] is not None:
            dd[i] = dsm[j]
            j += 1
    return kk, dd


def realized_vol(values: List[float], n: int = 20) -> Series:
    """Stdev of daily log returns over the window (not annualised)."""
    out: Series = [None] * len(values)
    rets = [None] + [math.log(values[i] / values[i - 1]) if values[i - 1] > 0 else 0.0 for i in range(1, len(values))]
    for i in range(n, len(values)):
        window = [r for r in rets[i - n + 1:i + 1] if r is not None]
        if len(window) >= 2:
            mean = sum(window) / len(window)
            out[i] = math.sqrt(sum((r - mean) ** 2 for r in window) / len(window))
    return out
