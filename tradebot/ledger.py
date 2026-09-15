"""Bag ledger — the tree's memory. Track record of what survived, what died, and why.

Every bag is born under conditions (the BTC regime at the time, which chain, which
scenario) and eventually resolves to one of two honest, observable outcomes:

  * SUCCESS — it multiplied enough to spawn a child (it reproduced). A bag that can
    throw off a healthy child from protected reserve has demonstrably worked.
  * FAILURE — it was retired (culled) for missing its survival bar by the deadline.

Bags that have done neither yet are OPEN (censored) — we don't pretend to know their
fate. This module keeps an append-only journal of births and outcomes, denormalizing
each bag's BIRTH conditions onto its outcome record so we can ask the only question
that helps a future spawn: *given these conditions, how did bags born like this fare?*

`analyze()` turns the journal into base rates and plain-language lessons.
`recommend()` turns it into a verdict for a proposed spawn — with deliberate honesty
about small samples (a weak prior shrinks every rate toward the overall base rate, and
nothing is called a "lesson" below a minimum sample). It is memory, not prophecy: it
reports what happened under like conditions, never a guarantee about the next one.

Pure and file-backed; no network. The Supervisor injects an instance and calls
record_birth / record_success / record_failure at the lifecycle points.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

STRONG_THRESHOLD = 0.15          # BTC this far above its 200d SMA at birth = "strong bull"
PRIOR_STRENGTH = 5.0             # weak-prior weight: shrink small-sample rates toward base
MIN_SAMPLE = 5                   # below this, we refuse to draw a lesson / gate a spawn
CAUTION_FLOOR = 0.75             # shrunk success < base_rate * this (with enough n) => caution


def regime_bucket(regime_on: Optional[bool], strength: Optional[float]) -> str:
    """Coarse, stable label for the market backdrop a bag was born into."""
    if regime_on is None:
        return "unknown"
    if not regime_on:
        return "bear"
    return "bull_strong" if (strength or 0.0) >= STRONG_THRESHOLD else "bull"


@dataclass
class Recommendation:
    verdict: str                 # "favorable" | "neutral" | "caution" | "insufficient"
    n: int                       # resolved bags matching these conditions
    success_rate: float          # raw matching success rate (0 if n==0)
    shrunk_rate: float           # rate pulled toward the base rate by the weak prior
    base_rate: float             # overall resolved success rate
    reason: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class BagLedger:
    def __init__(self, path: str):
        self.path = path
        self.records: List[dict] = []
        self._load()

    # ---- persistence -----------------------------------------------------
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            d = json.load(open(self.path))
            self.records = d.get("records", []) if isinstance(d, dict) else list(d)
        except Exception:  # noqa: BLE001
            self.records = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        json.dump({"records": self.records}, open(self.path, "w"), indent=1)

    # ---- lookups ---------------------------------------------------------
    def _birth(self, bag_id: str) -> Optional[dict]:
        for r in self.records:
            if r.get("event") == "born" and r.get("bag") == bag_id:
                return r
        return None

    def _has(self, bag_id: str, event: str) -> bool:
        return any(r.get("bag") == bag_id and r.get("event") == event for r in self.records)

    # ---- recording (idempotent where it matters) -------------------------
    def record_birth(self, bag_id: str, scenario: str, chain: str, seed: float,
                     parent: Optional[str] = None, regime_on: Optional[bool] = None,
                     strength: Optional[float] = None, risk_regime: Optional[str] = None,
                     ts: Optional[int] = None) -> None:
        if self._has(bag_id, "born"):
            return
        self.records.append({
            "event": "born", "ts": int(ts if ts is not None else time.time()),
            "bag": bag_id, "parent": parent, "chain": chain, "scenario": scenario,
            "seed": round(float(seed), 2), "regime_on": regime_on,
            "strength": round(float(strength), 4) if strength is not None else None,
            "regime_bucket": regime_bucket(regime_on, strength), "risk_regime": risk_regime,
        })

    def _outcome(self, bag_id: str, event: str, multiple: float, final_value: float,
                 reason: str, ts: Optional[int]) -> None:
        b = self._birth(bag_id) or {}
        now = int(ts if ts is not None else time.time())
        age_days = round((now - b.get("ts", now)) / 86400.0, 2) if b else None
        self.records.append({
            "event": event, "ts": now, "bag": bag_id, "reason": reason,
            "multiple": round(float(multiple), 3), "final_value": round(float(final_value), 2),
            "age_days": age_days,
            # denormalized birth conditions — the whole point of the memory
            "born_chain": b.get("chain"), "born_scenario": b.get("scenario"),
            "born_regime_on": b.get("regime_on"), "born_strength": b.get("strength"),
            "born_regime_bucket": b.get("regime_bucket", "unknown"),
        })

    def record_success(self, bag_id: str, multiple: float, final_value: float,
                       reason: str = "reproduced (spawned a child)", ts: Optional[int] = None) -> None:
        if self._has(bag_id, "spawned"):        # first reproduction is the success marker
            return
        self._outcome(bag_id, "spawned", multiple, final_value, reason, ts)

    def record_failure(self, bag_id: str, multiple: float, final_value: float,
                       reason: str = "retired: missed survival bar", ts: Optional[int] = None) -> None:
        if self._has(bag_id, "retired"):
            return
        self._outcome(bag_id, "retired", multiple, final_value, reason, ts)

    def record_skip(self, chain: str, scenario: str, regime_on: Optional[bool],
                    strength: Optional[float], reason: str, ts: Optional[int] = None) -> None:
        """A spawn the memory gate prevented — a wasted investment avoided (or a missed one)."""
        self.records.append({
            "event": "skipped", "ts": int(ts if ts is not None else time.time()),
            "chain": chain, "scenario": scenario, "regime_on": regime_on,
            "strength": round(float(strength), 4) if strength is not None else None,
            "regime_bucket": regime_bucket(regime_on, strength), "reason": reason})

    # ---- resolved outcomes ----------------------------------------------
    def resolved(self) -> List[dict]:
        """One row per bag that reached a terminal outcome, success flag + born conditions."""
        out = []
        for r in self.records:
            if r.get("event") in ("spawned", "retired"):
                out.append({"bag": r["bag"], "success": r["event"] == "spawned",
                            "reason": r.get("reason"), "multiple": r.get("multiple"),
                            "age_days": r.get("age_days"),
                            "chain": r.get("born_chain"), "scenario": r.get("born_scenario"),
                            "regime_bucket": r.get("born_regime_bucket", "unknown")})
        return out

    # ---- analysis --------------------------------------------------------
    def _rate(self, rows: List[dict]) -> Dict[str, float]:
        n = len(rows)
        s = sum(1 for r in rows if r["success"])
        return {"n": n, "success": s, "rate": round(s / n, 3) if n else 0.0}

    def _breakdown(self, rows: List[dict], key: str, base_rate: float) -> Dict[str, dict]:
        groups: Dict[str, List[dict]] = {}
        for r in rows:
            groups.setdefault(str(r.get(key)), []).append(r)
        out = {}
        for k, g in sorted(groups.items()):
            st = self._rate(g)
            st["shrunk"] = round((st["success"] + PRIOR_STRENGTH * base_rate)
                                 / (st["n"] + PRIOR_STRENGTH), 3)
            out[k] = st
        return out

    def analyze(self, min_sample: int = MIN_SAMPLE) -> dict:
        rows = self.resolved()
        born = sum(1 for r in self.records if r.get("event") == "born")
        base = self._rate(rows)
        base_rate = base["rate"]
        by_regime = self._breakdown(rows, "regime_bucket", base_rate)
        by_chain = self._breakdown(rows, "chain", base_rate)
        by_scenario = self._breakdown(rows, "scenario", base_rate)

        # failure reasons (counts)
        reasons: Dict[str, int] = {}
        for r in self.records:
            if r.get("event") == "retired":
                reasons[r.get("reason", "?")] = reasons.get(r.get("reason", "?"), 0) + 1
        top_reasons = [{"reason": k, "count": v}
                       for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])]

        lessons = self._lessons(by_regime, by_chain, base_rate, base["n"], min_sample)
        return {
            "born": born, "resolved": base["n"], "open": max(0, born - base["n"]),
            "base_success_rate": base_rate, "successes": base["success"],
            "by_regime": by_regime, "by_chain": by_chain, "by_scenario": by_scenario,
            "top_failure_reasons": top_reasons,
            "skips": sum(1 for r in self.records if r.get("event") == "skipped"),
            "lessons": lessons, "min_sample": min_sample,
        }

    def _lessons(self, by_regime: Dict[str, dict], by_chain: Dict[str, dict],
                 base_rate: float, total_n: int, min_sample: int) -> List[str]:
        out: List[str] = []
        if total_n < min_sample:
            out.append(f"Only {total_n} bags have resolved — not enough memory yet to draw "
                       f"lessons (need {min_sample}). Recording; patterns will emerge.")
            return out
        pct = lambda x: f"{round(x * 100)}%"
        for label, groups in (("born in a BTC", by_regime), ("on chain", by_chain)):
            for k, st in groups.items():
                if st["n"] < min_sample:
                    continue
                if st["shrunk"] <= base_rate * CAUTION_FLOOR:
                    out.append(f"Bags {label} {k} succeeded {st['success']}/{st['n']} "
                               f"({pct(st['rate'])}) vs {pct(base_rate)} overall — memory cautions here.")
                elif st["shrunk"] >= base_rate * 1.25:
                    out.append(f"Bags {label} {k} succeeded {st['success']}/{st['n']} "
                               f"({pct(st['rate'])}) vs {pct(base_rate)} overall — a favorable pattern.")
        if not out:
            out.append(f"No condition deviates strongly from the {pct(base_rate)} base rate yet "
                       f"across {total_n} resolved bags.")
        return out

    # ---- the memory a future spawn consults ------------------------------
    def recommend(self, chain: Optional[str] = None, scenario: Optional[str] = None,
                  regime_on: Optional[bool] = None, strength: Optional[float] = None,
                  min_sample: int = MIN_SAMPLE) -> Recommendation:
        rows = self.resolved()
        base = self._rate(rows)
        base_rate = base["rate"]
        bucket = regime_bucket(regime_on, strength)
        match = [r for r in rows
                 if (chain is None or r.get("chain") == chain)
                 and (scenario is None or r.get("scenario") == scenario)
                 and (regime_on is None or r.get("regime_bucket") == bucket)]
        st = self._rate(match)
        n = st["n"]
        shrunk = round((st["success"] + PRIOR_STRENGTH * base_rate) / (n + PRIOR_STRENGTH), 3) \
            if (n + PRIOR_STRENGTH) else base_rate
        cond = "/".join([x for x in [chain, scenario, bucket if regime_on is not None else None] if x]) or "any"
        if base["n"] < min_sample or n < min_sample:
            return Recommendation("insufficient", n, st["rate"], shrunk, base_rate,
                                  f"only {n} resolved bags match [{cond}] "
                                  f"({base['n']} total) — too little memory to judge; not gating.")
        if shrunk <= base_rate * CAUTION_FLOOR:
            return Recommendation("caution", n, st["rate"], shrunk, base_rate,
                                  f"bags matching [{cond}] succeeded {st['success']}/{n} "
                                  f"({round(st['rate']*100)}%) vs {round(base_rate*100)}% overall — "
                                  f"track record here is weak.")
        if shrunk >= base_rate * 1.25:
            return Recommendation("favorable", n, st["rate"], shrunk, base_rate,
                                  f"bags matching [{cond}] succeeded {st['success']}/{n} "
                                  f"({round(st['rate']*100)}%) vs {round(base_rate*100)}% overall.")
        return Recommendation("neutral", n, st["rate"], shrunk, base_rate,
                              f"bags matching [{cond}] track near the {round(base_rate*100)}% base rate.")
