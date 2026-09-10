"""Does on-chain flow improve the VALIDATED trend strategy — as a confirmation filter?

Standalone flow has ~no forward edge (scripts/tape_backtest.py). But that's a
different question from: given we already trade the validated trend filter, does
adding a flow condition make it BETTER — higher risk-adjusted return, or lower
drawdown? Flow could still help at the margin (only go long when the trend AND the
tape agree; step aside when whales distribute) even if it can't predict alone.

We test four books over the accumulated flow window (docs/tape_journal.json), using
that journal's own on-chain daily prices so price and flow share one source. Each
symbol runs its own signal; daily strategy returns are pooled equal-weight.

  1. buy & hold            — always long
  2. trend-only            — long when price > EMA (the validated baseline)
  3. trend + accumulation  — long only when trend up AND flow imbalance > 0
  4. trend + distrib-exit  — trend long, but flat when flow distributes (imb < -thr)

No lookahead: the signal on day t uses only prices/flow known by the close of t;
the position earns day t -> t+1's return. Reports total return, annualized Sharpe,
max drawdown, and time-in-market. HONEST caveat: flow history is only ~60 days —
too short for a slow trend and far too short to conclude. This is a sniff test of
whether the overlay even helps directionally, not a validation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _series(journal):
    """Per-symbol date-sorted [(price, imb)] from the journal."""
    days = sorted(journal.get("days", {}).keys())
    by_sym = {}
    for d in days:
        for sym, rec in journal["days"][d].items():
            if rec.get("price"):
                by_sym.setdefault(sym, []).append((rec["price"], rec.get("imb", 0.0)))
    return by_sym


def _ema(xs, span):
    a = 2 / (span + 1)
    out = [xs[0]]
    for x in xs[1:]:
        out.append(a * x + (1 - a) * out[-1])
    return out


def _stats(daily_rets):
    """total return, annualized Sharpe, max drawdown from a list of daily returns."""
    if not daily_rets:
        return {"ret": 0.0, "sharpe": 0.0, "maxdd": 0.0, "n": 0}
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in daily_rets:
        eq *= (1 + r)
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    n = len(daily_rets)
    mean = sum(daily_rets) / n
    var = sum((r - mean) ** 2 for r in daily_rets) / n if n > 1 else 0.0
    sd = var ** 0.5
    sharpe = (mean / sd * (365 ** 0.5)) if sd else 0.0
    return {"ret": eq - 1, "sharpe": sharpe, "maxdd": mdd, "n": n}


def run(journal, ema_span=10, dist_thr=0.15):
    by_sym = _series(journal)
    books = {"buy&hold": [], "trend": [], "trend+accum": [], "trend+distexit": []}
    exposure = {"trend": 0, "trend+accum": 0, "trend+distexit": 0}
    total_days = 0
    per_symbol = {}
    for sym, ser in by_sym.items():
        if len(ser) < ema_span + 3:
            continue
        prices = [p for p, _ in ser]
        imbs = [i for _, i in ser]
        ema = _ema(prices, ema_span)
        sym_books = {k: [] for k in books}
        for t in range(len(ser) - 1):
            fwd = prices[t + 1] / prices[t] - 1
            trend_up = prices[t] > ema[t]
            acc = imbs[t] > 0
            dist = imbs[t] < -dist_thr
            sym_books["buy&hold"].append(fwd)
            sym_books["trend"].append(fwd if trend_up else 0.0)
            sym_books["trend+accum"].append(fwd if (trend_up and acc) else 0.0)
            sym_books["trend+distexit"].append(fwd if (trend_up and not dist) else 0.0)
            if trend_up:
                exposure["trend"] += 1
            if trend_up and acc:
                exposure["trend+accum"] += 1
            if trend_up and not dist:
                exposure["trend+distexit"] += 1
            total_days += 1
        for k in books:
            books[k].extend(sym_books[k])
        per_symbol[sym] = {k: _stats(sym_books[k])["ret"] for k in books}
    return books, exposure, total_days, per_symbol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="docs/tape_journal.json")
    ap.add_argument("--ema", type=int, default=10)
    ap.add_argument("--dist-thr", type=float, default=0.15, dest="dist_thr")
    a = ap.parse_args()
    journal = json.load(open(a.journal))
    books, exposure, total_days, per_symbol = run(journal, a.ema, a.dist_thr)
    print(f"Trend + on-chain-flow overlay — journal {a.journal}  (EMA{a.ema}, dist<{-a.dist_thr})")
    print(f"pooled across {len(per_symbol)} symbols, {total_days} symbol-days\n")
    print(f"{'book':<18}{'return':>10}{'sharpe':>9}{'maxDD':>9}{'expo':>8}")
    print("-" * 54)
    for k, rets in books.items():
        s = _stats(rets)
        expo = (exposure[k] / total_days) if k in exposure and total_days else 1.0
        print(f"{k:<18}{s['ret']:>+9.2%}{s['sharpe']:>9.2f}{s['maxdd']:>+9.2%}{expo:>8.0%}")
    print("\nper-symbol total return:")
    print(f"{'sym':<7}{'b&h':>10}{'trend':>10}{'+accum':>10}{'+distexit':>11}")
    for sym, d in per_symbol.items():
        print(f"{sym:<7}{d['buy&hold']:>+9.1%}{d['trend']:>+9.1%}"
              f"{d['trend+accum']:>+9.1%}{d['trend+distexit']:>+10.1%}")
    # honest read
    base = _stats(books["trend"])
    print("\nread: compare each overlay to trend-only. An overlay 'helps' only if it "
          "lifts Sharpe or cuts maxDD without gutting return. Flow history is ~60 "
          "days, so treat any gap as a hint, not a result.")


if __name__ == "__main__":
    main()
