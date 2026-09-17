"""Does supervised return-prediction beat trend-following? An honest head-to-head.

The Hugging Face pitch for trading is a hosted forecaster (Chronos, Lag-Llama,
TimesFM, a FinBERT-driven signal) that predicts the next move. This script tests
the PRINCIPLE behind that pitch on real price data, the same way we tested (and
killed) whale-scalp and momentum-rotation.

We can't run a 1GB transformer in this stdlib-only environment, so we use a
faithful, deliberately-STEELMANNED stand-in for the supervised-forecasting family:
a ridge-regularized linear model predicting next-day return from a rich feature
set (lagged returns, momentum, volatility, RSI), fit WALK-FORWARD (expanding
window, refit as we go, never peeking at the future), traded long/flat with a
realistic per-trade cost. Why this is a fair proxy: on near-random-walk returns,
model CAPACITY mostly buys overfitting, not out-of-sample edge — so if a properly
validated linear predictor can't beat a dumb trend rule net of cost, a heavier
nonlinear model over the same signal is not the thing that rescues it. That's the
documented result in the ML-for-returns literature, not a strawman.

Compared on identical data:
  * Buy & hold                     (benchmark)
  * Trend filter (above 200d + 20>200d)   -- our validated default
  * Supervised forecaster (the "AI predicts price" approach)

Reports total return, max drawdown, Sharpe, the forecaster's OOS directional hit
rate and R^2 (how much of next-day return it actually explains -- spoiler: ~0).
No network beyond the project's own price feed; no HF dependency.
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.ohlcv import get_feed


# ---- tiny linear algebra (stdlib only) --------------------------------------
def _solve(A, b):
    """Solve A x = b for a small symmetric system via Gauss-Jordan. A: n x n."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            M[col][col] += 1e-9  # nudge a singular pivot
            piv = col
        M[col], M[piv] = M[piv], M[col]
        d = M[col][col]
        M[col] = [v / d for v in M[col]]
        for r in range(n):
            if r != col and abs(M[r][col]) > 0:
                f = M[r][col]
                M[r] = [a - f * b_ for a, b_ in zip(M[r], M[col])]
    return [M[i][n] for i in range(n)]


def ridge_fit(X, y, lam=10.0):
    """Ridge regression coefficients (intercept handled by a bias feature)."""
    n, d = len(X), len(X[0])
    XtX = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(d)] for i in range(d)]
    for i in range(d):
        if i != 0:                      # don't regularize the bias term
            XtX[i][i] += lam
    Xty = [sum(X[k][i] * y[k] for k in range(n)) for i in range(d)]
    return _solve(XtX, Xty)


# ---- features ---------------------------------------------------------------
def sma(xs, n, i):
    if i + 1 < n:
        return sum(xs[: i + 1]) / (i + 1)
    return sum(xs[i - n + 1 : i + 1]) / n


def rsi(closes, i, n=14):
    if i < n:
        return 50.0
    gains = losses = 0.0
    for k in range(i - n + 1, i + 1):
        ch = closes[k] - closes[k - 1]
        gains += max(ch, 0.0); losses += max(-ch, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100.0 - 100.0 / (1.0 + rs)


def features(closes, rets, i):
    """Causal feature vector at day i (uses only data up to and including i)."""
    r1 = rets[i]
    r5 = sum(rets[i - 4 : i + 1]) / 5 if i >= 4 else r1
    r10 = sum(rets[i - 9 : i + 1]) / 10 if i >= 9 else r1
    mom = closes[i] / sma(closes, 20, i) - 1.0
    win = rets[i - 9 : i + 1] if i >= 9 else rets[: i + 1]
    mu = sum(win) / len(win)
    vol = math.sqrt(sum((x - mu) ** 2 for x in win) / len(win)) if len(win) > 1 else 0.0
    rsimid = rsi(closes, i) / 100.0 - 0.5
    return [r1, r5, r10, mom, vol, rsimid]


# ---- metrics ----------------------------------------------------------------
def stats(equity, daily_rets):
    total = equity[-1] / equity[0] - 1.0
    peak = equity[0]; mdd = 0.0
    for v in equity:
        peak = max(peak, v); mdd = max(mdd, (peak - v) / peak)
    if len(daily_rets) > 1:
        mu = sum(daily_rets) / len(daily_rets)
        sd = math.sqrt(sum((x - mu) ** 2 for x in daily_rets) / (len(daily_rets) - 1))
        sharpe = (mu / sd * math.sqrt(365)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    return total, mdd, sharpe


def run(symbol="BTC", bars=1000, warmup=200, refit_every=5, cost_bps=10.0,
        thr=0.0, lam=10.0):
    feed = get_feed()
    hist = feed.history(symbol, "1d", bars)
    closes = [b.close for b in hist]
    n = len(closes)
    rets = [0.0] + [closes[i] / closes[i - 1] - 1.0 for i in range(1, n)]
    cost = cost_bps / 10_000.0

    # precompute causal features
    feats = [features(closes, rets, i) for i in range(n)]
    dim = len(feats[0]) + 1  # + bias

    # ---- strategies, stepped together, no lookahead ----
    eq_bh = [1.0]; dr_bh = []
    eq_tr = [1.0]; dr_tr = []; pos_tr = 0
    eq_fc = [1.0]; dr_fc = []; pos_fc = 0
    coeffs = None; mean = None; std = None
    hits = 0; hit_n = 0; sse = 0.0; sst = 0.0; ybar_run = []

    for t in range(warmup, n - 1):
        rnext = rets[t + 1]

        # buy & hold
        eq_bh.append(eq_bh[-1] * (1 + rnext)); dr_bh.append(rnext)

        # trend: long iff above 200d and 20>200d (causal)
        long_tr = 1 if (closes[t] > sma(closes, 200, t) and sma(closes, 20, t) > sma(closes, 200, t)) else 0
        c_tr = cost if long_tr != pos_tr else 0.0
        r_tr = long_tr * rnext - c_tr
        eq_tr.append(eq_tr[-1] * (1 + r_tr)); dr_tr.append(r_tr); pos_tr = long_tr

        # forecaster: refit walk-forward on [30, t-1] (features known, target=r[i+1])
        if coeffs is None or (t - warmup) % refit_every == 0:
            Xtr = []; ytr = []
            for i in range(30, t):          # target r[i+1] must be in the past (<= t)
                Xtr.append(feats[i]); ytr.append(rets[i + 1])
            # standardize using train stats only
            d = len(Xtr[0])
            mean = [sum(row[j] for row in Xtr) / len(Xtr) for j in range(d)]
            std = []
            for j in range(d):
                v = sum((row[j] - mean[j]) ** 2 for row in Xtr) / len(Xtr)
                std.append(math.sqrt(v) or 1.0)
            Xs = [[1.0] + [(row[j] - mean[j]) / std[j] for j in range(d)] for row in Xtr]
            coeffs = ridge_fit(Xs, ytr, lam=lam)

        xf = [1.0] + [(feats[t][j] - mean[j]) / std[j] for j in range(len(feats[t]))]
        pred = sum(c * x for c, x in zip(coeffs, xf))
        long_fc = 1 if pred > thr else 0
        c_fc = cost if long_fc != pos_fc else 0.0
        r_fc = long_fc * rnext - c_fc
        eq_fc.append(eq_fc[-1] * (1 + r_fc)); dr_fc.append(r_fc); pos_fc = long_fc

        # forecaster quality: directional hit + R^2 on the realized next return
        if pred != 0:
            hit_n += 1; hits += 1 if (pred > 0) == (rnext > 0) else 0
        ybar_run.append(rnext); sse += (rnext - pred) ** 2

    ybar = sum(ybar_run) / len(ybar_run)
    sst = sum((y - ybar) ** 2 for y in ybar_run)
    r2 = 1 - sse / sst if sst > 0 else 0.0
    hit = hits / hit_n if hit_n else 0.0

    span = f"{hist[warmup].date[:10]} → {hist[-1].date[:10]}  ({n-warmup-1} test days)"
    print(f"\n=== {symbol} daily — {span} ===")
    print(f"cost {cost_bps:.0f}bps/turn, ridge λ={lam}, refit every {refit_every}d\n")
    rows = [("Buy & hold", eq_bh, dr_bh), ("Trend (200d gate)", eq_tr, dr_tr),
            ("Supervised forecaster", eq_fc, dr_fc)]
    print(f"{'strategy':<24}{'return':>10}{'maxDD':>9}{'Sharpe':>9}")
    for name, eq, dr in rows:
        tot, mdd, sh = stats(eq, dr)
        print(f"{name:<24}{tot*100:>9.1f}%{mdd*100:>8.1f}%{sh:>9.2f}")
    print(f"\nforecaster diagnostics: directional hit rate {hit*100:.1f}% "
          f"(50% = coin flip), out-of-sample R² {r2:.4f} (0 = explains nothing)")


if __name__ == "__main__":
    for sym in (sys.argv[1:] or ["BTC", "SOL"]):
        try:
            run(sym)
        except Exception as e:  # noqa: BLE001
            print(f"{sym}: could not run ({e})")
