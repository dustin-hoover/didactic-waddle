"""Flow journal: accumulate the sample the tape backtest can't get from history.

The validation problem is real: no free source gives DEEP on-chain flow history,
and a 5-7 day live window is far too small — one symbol looked contrarian, another
looked trend-following, which is exactly how noise behaves. The honest fix is to
record flow going forward: every scheduled run logs each symbol's daily flow
imbalance and price, and once the next day's price is known we can measure whether
the flow predicted it. Over weeks this grows into a real out-of-sample dataset.

Storage (docs/tape_journal.json), deliberately tiny:
  {"days": {"2026-09-10": {"ETH": {"imb": 0.04, "net": 852812, "price": 2497.8},
                            "LINK": {...}}, ...}}

analyze() pairs each day's imbalance with the NEXT day's realized return, pools
across symbols, and reports correlation, directional hit-rate, accumulation-vs-
distribution forward returns, and a flow-following equity curve vs buy & hold —
the same lens as scripts/tape_backtest.py, but over the accumulated journal.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional


def load(path: str) -> dict:
    if os.path.exists(path):
        try:
            d = json.load(open(path))
            d.setdefault("days", {})
            return d
        except Exception:  # noqa: BLE001
            return {"days": {}}
    return {"days": {}}


def save(path: str, journal: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(journal, open(path, "w"), indent=1)


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def date_days_ago(days_ago: int, base: Optional[str] = None) -> str:
    """Calendar date ``days_ago`` before ``base`` (default today), ISO yyyy-mm-dd."""
    from datetime import date, timedelta
    b = date.fromisoformat(base) if base else datetime.now(timezone.utc).date()
    return (b - timedelta(days=days_ago)).isoformat()


def record(journal: dict, rows: List[dict], date: Optional[str] = None) -> dict:
    """Store today's flow snapshot for each ranked symbol (later runs overwrite it).

    ``rows`` are dicts as written to data.json's tape section: symbol, score,
    net_usd, price, plus buy_usd/sell_usd so we can recompute imbalance.
    """
    date = date or today_utc()
    day = journal.setdefault("days", {}).setdefault(date, {})
    for r in rows:
        if r.get("error") or not r.get("price"):
            continue
        buy, sell = r.get("buy_usd", 0.0), r.get("sell_usd", 0.0)
        tot = buy + sell
        imb = (buy - sell) / tot if tot else r.get("score", 0.0)
        day[r["symbol"]] = {"imb": round(imb, 4), "net": r.get("net_usd", 0.0),
                            "price": r["price"]}
    return journal


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (vx * vy) if vx and vy else None


def _pairs(journal: dict, field: str = "imb") -> Dict[str, List]:
    """Per-symbol list of (date, signal, forward_return) from consecutive days.

    ``field`` selects which flow signal to pair with tomorrow's return — "imb"
    (aggregate flow) or "wimb" (whale/strong-hands-only flow). Records missing the
    field are skipped, so a whale analysis simply ignores older aggregate-only days.
    """
    days = sorted(journal.get("days", {}).keys())
    by_sym: Dict[str, List] = {}
    for i in range(len(days) - 1):
        d0, d1 = days[i], days[i + 1]
        snap0, snap1 = journal["days"][d0], journal["days"][d1]
        for sym, rec in snap0.items():
            nxt = snap1.get(sym)
            if not nxt or not rec.get("price") or not nxt.get("price") or field not in rec:
                continue
            fwd = nxt["price"] / rec["price"] - 1
            by_sym.setdefault(sym, []).append((d0, rec[field], fwd))
    return by_sym


def _edge(imb: List[float], fwd: List[float]) -> dict:
    """Shared edge stats for a signal vs. forward returns."""
    n = len(imb)
    corr = _pearson(imb, fwd)
    hits = sum(1 for i, r in zip(imb, fwd) if (i > 0) == (r > 0))
    acc = [r for i, r in zip(imb, fwd) if i > 0]
    dist = [r for i, r in zip(imb, fwd) if i <= 0]
    eq_flow = eq_hold = 1.0
    for i, r in zip(imb, fwd):
        eq_hold *= (1 + r)
        if i > 0:
            eq_flow *= (1 + r)
    strong = (corr or 0) > 0.2 and hits / n > 0.55 and n >= 30
    return {
        "n_pairs": n,
        "corr": round(corr, 3) if corr is not None else None,
        "hit_rate": round(hits / n, 3),
        "mean_fwd_accumulation": round(sum(acc) / len(acc), 4) if acc else None,
        "mean_fwd_distribution": round(sum(dist) / len(dist), 4) if dist else None,
        "flow_following_return": round(eq_flow - 1, 4),
        "buyhold_return": round(eq_hold - 1, 4),
        "has_edge": bool(strong),
    }


def analyze(journal: dict) -> dict:
    """Pool all (imbalance, next-day return) pairs and measure forward edge.

    Reports two signals side by side: aggregate flow ("imb") and whale/strong-hands
    flow ("wimb", where recorded). Neither is called tradeable unless it clears the
    gate (>=30 pairs, corr>0.2, >55% hit).
    """
    by_sym = _pairs(journal)
    imb = [p[1] for lst in by_sym.values() for p in lst]
    fwd = [p[2] for lst in by_sym.values() for p in lst]
    n = len(imb)
    out = {"n_pairs": n, "n_symbols": len(by_sym), "n_days": len(journal.get("days", {}))}
    # Whale-specific analysis, if the journal carries whale flow.
    wby = _pairs(journal, field="wimb")
    wimb = [p[1] for lst in wby.values() for p in lst]
    wfwd = [p[2] for lst in wby.values() for p in lst]
    if len(wimb) >= 3:
        out["whale"] = _edge(wimb, wfwd)
    if n < 3:
        out["verdict"] = "not enough data yet — keep the journal running"
        return out
    corr = _pearson(imb, fwd)
    hits = sum(1 for i, r in zip(imb, fwd) if (i > 0) == (r > 0))
    acc = [r for i, r in zip(imb, fwd) if i > 0]
    dist = [r for i, r in zip(imb, fwd) if i <= 0]
    eq_flow = eq_hold = 1.0
    for i, r in zip(imb, fwd):
        eq_hold *= (1 + r)
        if i > 0:
            eq_flow *= (1 + r)
    out.update(
        corr=round(corr, 3) if corr is not None else None,
        hit_rate=round(hits / n, 3),
        mean_fwd_accumulation=round(sum(acc) / len(acc), 4) if acc else None,
        mean_fwd_distribution=round(sum(dist) / len(dist), 4) if dist else None,
        flow_following_return=round(eq_flow - 1, 4),
        buyhold_return=round(eq_hold - 1, 4),
    )
    strong = (corr or 0) > 0.2 and hits / n > 0.55 and n >= 30
    out["verdict"] = ("flow shows forward edge across the accumulated sample — "
                      "candidate for a position-sizing role"
                      if strong else
                      "no reliable edge yet (or sample still small) — keep the tape "
                      "as a ranking/context tool, do not size positions on it")
    return out
