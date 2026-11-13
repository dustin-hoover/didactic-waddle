#!/usr/bin/env python3
"""Is the backbone "ring" actually a ring? (doc 24 §2)

Designed topology (topology.from_gis) weighted by Year-5 members (premises x 44% take,
nearest spine node) -> bridges, cut nodes, members behind each -> greedy redundancy plan
(cheapest added hop that removes the worst remaining single point of failure).

Writes data/noc/spof_report.json and data/noc/redundancy_plan.csv.
Run: python3 software/noc/spof_analysis.py
"""
import os, sys, csv, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "dispatch")]
import topology as T, waterroute   # noqa: E402

OUT = os.path.join(T.REPO, "data", "noc")

def main():
    os.makedirs(OUT, exist_ok=True)
    topo = T.from_gis()
    mb = T.members_by_node_from_premises(topo)
    before = topo.spof_report(mb)
    plan = topo.plan_redundancy(T.classify_with_lake(waterroute.grid()), mb)
    after = plan["topology_after"].spof_report(mb)
    raw_bridges = len(T.Topology({n: x for n, x in topo.nodes.items() if n not in topo.heads},
                                 {k: l for k, l in topo.links.items() if not k.startswith("HF-")}, []).bridges_and_cuts()[0])
    rep = {"members_total": sum(mb.values()), "spine_links": sum(1 for k in topo.links if k.startswith("SP-")),
           "spine_bridges_without_headends": raw_bridges,
           "headend_homing": {h: [v for v, _ in topo.adj[h]] for h in topo.heads},
           "before": before, "plan": {k: v for k, v in plan.items() if k != "topology_after"}, "after": after}
    json.dump(rep, open(os.path.join(OUT, "spof_report.json"), "w"), indent=1, default=list)
    with open(os.path.join(OUT, "redundancy_plan.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step", "removes_spof", "spof_type", "members_protected", "add_hop_a", "add_hop_b", "kind", "km",
                    "cost_radio_or_class_usd", "cost_if_aerial_fiber_usd"])
        for i, a in enumerate(plan["added"], 1):
            h = a.get("add_hop")
            w.writerow([i, a.get("removes_spof", a.get("spof")), a.get("spof_type", ""), a.get("members_protected", ""),
                        *( [h["a"], h["b"], h["kind"], h["km"], h["cost_radio_or_class"], h["cost_if_aerial_fiber"]]
                           if h else ["", "", "none within %.0f km" % T.MAX_HOP_KM, "", "", ""])])
    print(f"members {rep['members_total']:,}; before: {before['bridges']} bridges, {before['cut_nodes']} cut nodes, "
          f"{before['members_behind_a_spof']:,} behind a SPOF")
    for s in before["spofs"]:
        print(f"  {s['element']:<16} {s['type']:<5} {s['kind']:<12} isolates {len(s['isolates_nodes']):>2} nodes, {s['members']:>5,} members")
    print(f"plan: +{plan['hops']} hops ${plan['total_cost_low']:,} .. ${plan['total_cost_high']:,}; "
          f"after: {after['bridges']} bridges, {after['cut_nodes']} cut nodes, {after['members_behind_a_spof']:,} behind; "
          f"remaining {plan['spofs_remaining']}")
    for a in plan["added"]:
        print("  ", a)

if __name__ == "__main__":
    main()
