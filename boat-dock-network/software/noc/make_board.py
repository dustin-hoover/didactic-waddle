#!/usr/bin/env python3
"""DockOS NOC board preview -> data/noc/noc_board.html (self-contained artifact).

Renders the snapshot the NOC e2e test writes at the alarm-storm moment
(data/noc/demo_board.json: /noc/board, /status, the queued SMS, the P1 work order, and
the full run's incident log) plus the ring audit (data/noc/spof_report.json) on the lake.
Run after: python3 software/tests/test_noc_e2e.py && python3 software/noc/spof_analysis.py
"""
import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
D = os.path.join(REPO, "data")

def main():
    snap = json.load(open(os.path.join(D, "noc", "demo_board.json")))
    spof = json.load(open(os.path.join(D, "noc", "spof_report.json")))
    lake = json.load(open(os.path.join(D, "gis", "outputs", "lake.geojson")))
    polys = []
    geoms = [f["geometry"] for f in lake["features"]] if "features" in lake else [lake]
    for g in geoms:
        for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
            polys.append([[[round(x, 5), round(y, 5)] for x, y in ring] for ring in p])
    data = {
        "now": snap["now"], "board": snap["board"], "status": snap["status"]["zones"], "overall": snap["status"]["overall"],
        "notice": snap["notice_sms"], "wo": snap["wo"], "log": snap["log"], "lake": polys,
        "spof": {"members_total": spof["members_total"], "spine_bridges": spof["spine_bridges_without_headends"],
                 "homing": spof["headend_homing"],
                 "before": {k: spof["before"][k] for k in ("bridges", "cut_nodes", "members_behind_a_spof")},
                 "after": {k: spof["after"][k] for k in ("bridges", "cut_nodes", "members_behind_a_spof")},
                 "rows": [{k: r[k] for k in ("element", "type", "kind", "members")} | {"n": len(r["isolates_nodes"])}
                          for r in spof["before"]["spofs"]],
                 "plan": [a for a in spof["plan"]["added"]], "low": spof["plan"]["total_cost_low"],
                 "high": spof["plan"]["total_cost_high"], "remaining": spof["plan"]["spofs_remaining"]},
    }
    html = open(os.path.join(HERE, "board_template.html")).read().replace(
        "/*__DATA__*/null", json.dumps(data, separators=(",", ":"), default=str))
    out = os.path.join(D, "noc", "noc_board.html")
    open(out, "w").write(html)
    print(out, f"{len(html) / 1024:.0f} KB")

if __name__ == "__main__":
    main()
