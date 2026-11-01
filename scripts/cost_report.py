#!/usr/bin/env python3
"""cost_report.py — reconcile real canary fills against modelled backtest costs.

Phase 0.5. Reads docs/fills.jsonl (every logged live fill), computes realized fee
and slippage, and compares them to the backtester's modelled CostModel. It writes
docs/cost_model.json holding modelled, realized, and EFFECTIVE (the worse of the two)
costs. The backtester reads that file via CostModel.from_report(), so a backtest can
never assume execution cheaper than reality has delivered.

Usage:
    python3 scripts/cost_report.py                 # read docs/fills.jsonl, write report
    python3 scripts/cost_report.py --fills PATH --out PATH

Exit code is 0 whether or not fills exist yet (an empty log just means the effective
costs equal the modelled defaults — honest, not an error).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.config import CostModel                     # noqa: E402
from tradebot.fills import DEFAULT_FILLS_PATH, load_fills, realized_costs  # noqa: E402


def build_report(fills_path: str, modelled: CostModel) -> dict:
    fills = load_fills(fills_path)
    rc = realized_costs(fills)
    effective = modelled.worse_of(rc.to_dict())
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "fills_path": fills_path,
        "n_fills": rc.n_fills,
        "n_ok": rc.n_ok,
        "n_failed": rc.n_failed,
        "failure_rate": rc.failure_rate,
        "median_latency_s": rc.median_latency_s,
        "modelled": {"fee_frac": modelled.fee_frac, "slippage_frac": modelled.slippage_frac},
        "realized": {"fee_frac": rc.fee_frac, "slippage_frac": rc.slippage_frac,
                     "p90_slippage_frac": rc.p90_slippage_frac},
        # EFFECTIVE = worse-of; this is what the backtester uses.
        "effective": {"fee_frac": effective.fee_frac, "slippage_frac": effective.slippage_frac},
    }


def _bps(x: float) -> str:
    return f"{x * 10_000:.1f} bps"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fills", default=DEFAULT_FILLS_PATH, help="path to fills.jsonl")
    ap.add_argument("--out", default="docs/cost_model.json", help="report output path")
    args = ap.parse_args(argv[1:])

    modelled = CostModel()
    rep = build_report(args.fills, modelled)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(rep, fh, indent=2)
        fh.write("\n")

    m, r, e = rep["modelled"], rep["realized"], rep["effective"]
    print(f"Cost reconciliation  ({rep['n_ok']} ok / {rep['n_failed']} failed fills, "
          f"failure rate {rep['failure_rate']:.1%})")
    print(f"  fee       modelled {_bps(m['fee_frac'])}  realized {_bps(r['fee_frac'])}"
          f"  -> effective {_bps(e['fee_frac'])}")
    print(f"  slippage  modelled {_bps(m['slippage_frac'])}  realized {_bps(r['slippage_frac'])}"
          f"  (p90 {_bps(r['p90_slippage_frac'])})  -> effective {_bps(e['slippage_frac'])}")
    if rep["n_ok"] == 0:
        print("  (no fills yet — effective costs equal the modelled defaults.)")
    elif e["fee_frac"] > m["fee_frac"] or e["slippage_frac"] > m["slippage_frac"]:
        print("  NOTE: reality is costlier than modelled — backtests will use the worse numbers.")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
