#!/usr/bin/env python3
"""Network topology engine for the NOC (doc 24).

The NOC's core question is not "what is down?" (collectors answer that) but "what
BROKE, and who does it affect?" This module answers it from the topology:

  * reachability: which nodes still reach a head-end (T0) given failed nodes/links —
    everything else is isolated, and the failed elements on the boundary are the root cause;
  * single points of failure: bridges (links) and articulation points (nodes) whose loss
    isolates part of the lake, with the members behind each;
  * redundancy plan: the cheapest added hops (same class/cost model as the spine) that
    remove every bridge — i.e. make "the ring" actually a ring.

Graph = head-ends + the 30 spine nodes (T2/T3) + the 41 spine links (GIS outputs).
Pure Python + numpy; no graph library needed.
"""
from __future__ import annotations
import os, json, math, collections
from dataclasses import dataclass, field
from typing import Iterable, Optional
import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(REPO, "data", "gis", "outputs")
HEADENDS = {"HE-NW": (-94.0579, 36.3548), "HE-E": (-93.8394, 36.4009)}   # candidate yards (doc 20)
# spine hop cost model (from spine.geojson: flat per class)
HOP_COST = {"water_long": 55000, "water_short": 9000, "land": 8000}
MAX_HOP_KM = 7.0
FIBER_AERIAL_PER_KM = 23299     # data/bom/wo-fiber-aerial-mile.csv ($37,488/mi)

def km(a, b) -> float:
    kx = math.cos(math.radians((a[1] + b[1]) / 2)) * 111.32
    return math.hypot((a[0] - b[0]) * kx, (a[1] - b[1]) * 110.54)

def node_id(priority: int, zone: str) -> str:
    return f"BDN-{zone}-N{priority:02d}"

@dataclass
class Link:
    link_id: str
    a: str
    b: str
    kind: str          # water_long | water_short | land | headend_fiber
    km: float
    cost: float = 0.0

@dataclass
class Topology:
    nodes: dict[str, dict]                       # node_id -> {lon, lat, tier, zone, power}
    links: dict[str, Link]
    heads: list[str]
    adj: dict[str, list[tuple[str, str]]] = field(default_factory=dict)   # node -> [(nbr, link_id)]

    def __post_init__(self):
        self.adj = collections.defaultdict(list)
        for l in self.links.values():
            self.adj[l.a].append((l.b, l.link_id)); self.adj[l.b].append((l.a, l.link_id))

    # ---------------------------------------------------------------- reachability
    def reachable(self, failed_nodes: Iterable[str] = (), failed_links: Iterable[str] = ()) -> set[str]:
        fn, fl = set(failed_nodes), set(failed_links)
        seen = {h for h in self.heads if h not in fn}
        stack = list(seen)
        while stack:
            u = stack.pop()
            for v, lid in self.adj[u]:
                if lid in fl or v in fn or v in seen:
                    continue
                seen.add(v); stack.append(v)
        return seen

    def impact(self, failed_nodes: Iterable[str] = (), failed_links: Iterable[str] = ()) -> dict:
        """Isolated = not failed, not reachable. Root causes = failed elements adjacent to the
        isolated set or themselves down. Ring-open = failed links that isolate nothing."""
        fn, fl = set(failed_nodes), set(failed_links)
        reach = self.reachable(fn, fl)
        isolated = set(self.nodes) - reach - fn
        # which failures actually matter: remove each alone and see if it isolates anything
        return {"reachable": reach, "isolated": isolated, "down": fn, "failed_links": fl,
                "dark": isolated | fn}

    # ---------------------------------------------------------------- root cause
    def correlate(self, down_nodes: Iterable[str] = (), down_links: Iterable[str] = ()) -> dict:
        """Alarm storm -> root cause. Observed: nodes not answering (D) and links reported down (L).
        R = what still reaches a head-end. A down node with a working path to R (or a down
        head-end) is a ROOT; down nodes behind it are merely unreachable (SUPPRESSED). A down link
        from R into the dark side is a root unless its far end is itself a root; a down link with
        both ends in R isolates nobody (RING OPEN = degraded, not an outage). Nodes in the dark
        set that have not alarmed yet are SILENT (predicted dark). One component = one event."""
        fn = set(down_nodes) & set(self.nodes)
        fl = set(down_links) & set(self.links)
        R = self.reachable(fn, fl)
        dark = set(self.nodes) - R
        root_nodes = {n for n in fn if n in self.heads
                      or any(v in R and lid not in fl for v, lid in self.adj[n])}
        root_links, ring_open, supp_links = set(), set(), set()
        for lid in fl:
            l = self.links[lid]
            ia, ib = l.a in R, l.b in R
            if ia and ib:
                ring_open.add(lid)
            elif ia or ib:
                far = l.b if ia else l.a
                (supp_links if far in root_nodes else root_links).add(lid)
            else:
                supp_links.add(lid)
        comps, seen = [], set()
        for s in sorted(dark):
            if s in seen:
                continue
            comp, stack = {s}, [s]
            seen.add(s)
            while stack:
                u = stack.pop()
                for v, _ in self.adj[u]:
                    if v in dark and v not in seen:
                        seen.add(v); comp.add(v); stack.append(v)
            roots = sorted(root_nodes & comp) + sorted(
                lid for lid in root_links if self.links[lid].a in comp or self.links[lid].b in comp)
            comps.append({"dark": comp, "roots": roots, "silent": comp - fn})
        return {"reachable": R, "dark": dark, "root_nodes": root_nodes, "root_links": root_links,
                "ring_open": ring_open, "suppressed_nodes": fn - root_nodes, "suppressed_links": supp_links,
                "components": comps}

    def far_end(self, link_id: str, reachable: set) -> str:
        """The dark-side end of a cut link (where the crew goes first)."""
        l = self.links[link_id]
        return l.b if l.a in reachable else l.a

    # ---------------------------------------------------------------- SPOFs (Tarjan)
    def bridges_and_cuts(self) -> tuple[list[str], list[str]]:
        disc, low, parent_link = {}, {}, {}
        bridges, cuts, t = [], set(), [0]
        def dfs(u, root):
            disc[u] = low[u] = t[0]; t[0] += 1
            kids = 0
            for v, lid in self.adj[u]:
                if lid == parent_link.get(u):
                    continue
                if v not in disc:
                    parent_link[v] = lid; kids += 1
                    dfs(v, root)
                    low[u] = min(low[u], low[v])
                    if low[v] > disc[u]:
                        bridges.append(lid)
                    if u != root and low[v] >= disc[u]:
                        cuts.add(u)
                else:
                    low[u] = min(low[u], disc[v])
            if u == root and kids > 1:
                cuts.add(u)
        import sys
        sys.setrecursionlimit(10000)
        for s in self.nodes:
            if s not in disc:
                dfs(s, s)
        return bridges, sorted(cuts)

    def spof_report(self, members_by_node: dict[str, int]) -> dict:
        bridges, cuts = self.bridges_and_cuts()
        rows = []
        for lid in bridges:
            iso = self.impact(failed_links=[lid])["isolated"]
            if iso:
                rows.append({"element": lid, "type": "link", "kind": self.links[lid].kind,
                             "isolates_nodes": sorted(iso), "members": sum(members_by_node.get(n, 0) for n in iso)})
        for n in cuts:
            if n in self.heads:
                continue
            iso = self.impact(failed_nodes=[n])["isolated"]
            if iso:
                rows.append({"element": n, "type": "node", "kind": self.nodes[n]["tier"],
                             "isolates_nodes": sorted(iso), "members": sum(members_by_node.get(x, 0) for x in iso)})
        rows.sort(key=lambda r: -r["members"])
        return {"bridges": len([r for r in rows if r["type"] == "link"]),
                "cut_nodes": len([r for r in rows if r["type"] == "node"]),
                "members_behind_a_spof": sum(members_by_node.get(n, 0) for n in {n for r in rows for n in r["isolates_nodes"]}),
                "spofs": rows}

    # ---------------------------------------------------------------- redundancy plan
    def _spofs(self) -> list[tuple[str, str, set]]:
        bridges, cuts = self.bridges_and_cuts()
        out = [("link", l, self.impact(failed_links=[l])["isolated"]) for l in bridges]
        out += [("node", n, self.impact(failed_nodes=[n])["isolated"]) for n in cuts if n not in self.heads]
        return [x for x in out if x[2]]

    def plan_redundancy(self, classify, members_by_node: dict[str, int], max_rounds: int = 25) -> dict:
        """Greedy: while any single link or node can isolate members, add the cheapest hop that
        reconnects the isolated side around it (worst SPOF first). Head-ends may be dual-homed by
        a fiber lateral. Each fix carries the radio price (spine cost classes; needs a LOS/path
        survey) and an aerial-fiber fallback price (BOM kit, per km)."""
        added, topo = [], self
        for _ in range(max_rounds):
            spofs = topo._spofs()
            if not spofs:
                break
            spofs.sort(key=lambda x: -sum(members_by_node.get(n, 0) for n in x[2]))
            typ, el, iso = spofs[0]
            rest = set(topo.nodes) - iso - ({el} if typ == "node" else set())
            best = None
            for u in iso:
                for v in rest:
                    if any(nb == v for nb, _ in topo.adj[u]):
                        continue
                    d = km(self._ll(u), self._ll(v))
                    if d > MAX_HOP_KM:
                        continue
                    if v in topo.heads:
                        kind, cost = "headend_fiber", round(FIBER_AERIAL_PER_KM * d)
                    else:
                        kind = classify(self._ll(u), self._ll(v), d); cost = HOP_COST[kind]
                    cand = (cost, d, u, v, kind)
                    if best is None or cand < best:
                        best = cand
            if not best:
                added.append({"spof": el, "fix": None, "note": f"no candidate hop <= {MAX_HOP_KM} km"})
                break
            cost, d, u, v, kind = best
            fallback = cost if kind in ("water_long", "headend_fiber") else round(FIBER_AERIAL_PER_KM * d)
            new = Link(f"NEW-{u.split('-')[-1]}-{v.split('-')[-1]}", u, v, kind, round(d, 2), cost)
            links = dict(topo.links); links[new.link_id] = new
            topo = Topology(topo.nodes, links, topo.heads)
            added.append({"removes_spof": el, "spof_type": typ,
                          "members_protected": sum(members_by_node.get(n, 0) for n in iso),
                          "add_hop": {"a": u, "b": v, "kind": kind, "km": round(d, 2),
                                      "cost_radio_or_class": cost, "cost_if_aerial_fiber": fallback}})
        fixes = [a for a in added if a.get("add_hop")]
        return {"added": added, "hops": len(fixes),
                "total_cost_low": sum(a["add_hop"]["cost_radio_or_class"] for a in fixes),
                "total_cost_high": sum(a["add_hop"]["cost_if_aerial_fiber"] for a in fixes),
                "spofs_remaining": [e for _, e, _ in topo._spofs()], "topology_after": topo}

    def _ll(self, n):
        x = self.nodes[n]; return (x["lon"], x["lat"])

# ---------------------------------------------------------------- builders
def classify_with_lake(grid):
    """Hop class from how much of the straight segment is over water (LakeGrid)."""
    def f(a, b, d):
        xs = np.linspace(a[0], b[0], 40); ys = np.linspace(a[1], b[1], 40)
        k, dist = grid.snap_many(np.stack([xs, ys], axis=1))
        water = float(np.mean(dist < grid.cell * 0.75))
        if water < 0.3:
            return "land"
        return "water_short" if d <= 3.0 else "water_long"
    return f

def from_gis() -> Topology:
    spine = json.load(open(os.path.join(OUT, "spine.geojson")))["features"]
    nf = json.load(open(os.path.join(OUT, "proposed_nodes.geojson")))["features"]
    nodes, pid = {}, {}
    for f in nf:
        p = f["properties"]; nid = node_id(p["priority"], p["zone"])
        pid[p["priority"]] = nid
        lon, lat = f["geometry"]["coordinates"][:2]
        nodes[nid] = {"lon": lon, "lat": lat, "tier": "T2" if p.get("primary") else "T3", "zone": p["zone"],
                      "power": "grid_ups" if p.get("primary") else "solar_battery"}
    links = {}
    kind_of = {"water long: licensed MW + diversity": "water_long", "land: fiber/unlicensed PtP": "land",
               "water short: unlicensed 60/5GHz PtP": "water_short"}
    for f in spine:
        p = f["properties"]; a, b = pid[p["a"]], pid[p["b"]]
        lid = f"SP-{p['a']:02d}-{p['b']:02d}"
        links[lid] = Link(lid, a, b, kind_of.get(p["class"], "land"), p["km"], p["cost"])
    heads = []
    for h, (lon, lat) in HEADENDS.items():
        nodes[h] = {"lon": lon, "lat": lat, "tier": "T0", "zone": None, "power": "grid_generator"}
        near = min((n for n in nodes if n not in HEADENDS), key=lambda n: km((lon, lat), (nodes[n]["lon"], nodes[n]["lat"])))
        links[f"HF-{h}"] = Link(f"HF-{h}", h, near, "headend_fiber", round(km((lon, lat), (nodes[near]["lon"], nodes[near]["lat"])), 2), 0)
        heads.append(h)
    return Topology(nodes, links, heads)

def members_by_node_from_premises(topo: Topology, take_rate: float = 0.44) -> dict[str, float]:
    """Planning view: each premises served by its nearest spine node; members = passings x take."""
    feats = json.load(open(os.path.join(OUT, "premises.geojson")))["features"]
    ids = [n for n in topo.nodes if n not in topo.heads]
    xy = np.array([[topo.nodes[n]["lon"], topo.nodes[n]["lat"]] for n in ids])
    kx = math.cos(math.radians(36.3))
    cnt = collections.Counter()
    for f in feats:
        lon, lat = f["geometry"]["coordinates"][:2]
        i = int(np.argmin(((xy[:, 0] - lon) * kx) ** 2 + (xy[:, 1] - lat) ** 2))
        cnt[ids[i]] += 1
    return {n: round(c * take_rate) for n, c in cnt.items()}
