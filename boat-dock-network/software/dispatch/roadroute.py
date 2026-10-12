#!/usr/bin/env python3
"""Road routing around Beaver Lake from OpenStreetMap (doc 23).

Replaces the flat "crow-flies x circuity" truck assumption with real drive times:
lake roads wrap every arm, and a single detour factor can't capture that.

Build once (from the Overpass download, see __main__):
  python3 roadroute.py build   -> data/gis/outputs/road_graph.npz  (compact, committed)

Graph: OSM highway ways -> contracted to junctions (shape points folded into edge
length) -> largest connected component. Edge time = length / speed, where speed is
the posted maxspeed x 0.85 when tagged, else a rural-Ozark default by road class.
Undirected (one-ways are rare off the interstate; fine for planning).
"""
from __future__ import annotations
import os, sys, json, math, re
from functools import lru_cache
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra, connected_components
from scipy.spatial import cKDTree

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(REPO, "data", "gis", "raw", "osm_roads.json")
GRAPH = os.path.join(REPO, "data", "gis", "outputs", "road_graph.npz")
MPH_TO_M_PER_MIN = 1609.344 / 60.0

# average travel speeds (mph) when no maxspeed tag — winding rural Ozark roads
CLASS_MPH = {"motorway": 65, "trunk": 55, "primary": 48, "secondary": 42, "tertiary": 38,
             "unclassified": 30, "residential": 24, "living_street": 15, "service": 12,
             "track": 8, "motorway_link": 35, "trunk_link": 30, "primary_link": 28,
             "secondary_link": 25, "tertiary_link": 25}
POSTED_FACTOR = 0.85   # real average vs posted limit (curves, hills, towns)
SNAP_MPH = 8.0         # driveway / off-network leg

def _hav_m(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * np.arcsin(np.sqrt(h))

def _speed_mph(tags: dict) -> float:
    ms = tags.get("maxspeed", "")
    m = re.match(r"^\s*(\d+)\s*(mph)?", ms)
    if m:
        v = float(m.group(1))
        # OSM convention: a bare number is km/h; US ways normally say "45 mph"
        return v * POSTED_FACTOR if m.group(2) else v * 0.621371 * POSTED_FACTOR
    return float(CLASS_MPH.get(tags.get("highway", ""), 20))

def build(raw: str = RAW, out: str = GRAPH) -> dict:
    d = json.load(open(raw))["elements"]
    coords = {e["id"]: (e["lon"], e["lat"]) for e in d if e["type"] == "node"}
    ways = [e for e in d if e["type"] == "way" and len(e.get("nodes", [])) >= 2]
    use = {}
    for w in ways:                                   # junction = used by >1 way or an endpoint
        for i, n in enumerate(w["nodes"]):
            use[n] = use.get(n, 0) + (2 if i in (0, len(w["nodes"]) - 1) else 1)
    junction = {n for n, c in use.items() if c >= 2}
    nid, lon, lat = {}, [], []
    def node(n):
        if n not in nid:
            nid[n] = len(lon); lon.append(coords[n][0]); lat.append(coords[n][1])
        return nid[n]
    eu, ev, elen, etime = [], [], [], []
    for w in ways:
        v_mpm = _speed_mph(w.get("tags", {})) * MPH_TO_M_PER_MIN
        ns = [n for n in w["nodes"] if n in coords]
        if len(ns) < 2:
            continue
        seg_start, acc = ns[0], 0.0
        for a, b in zip(ns, ns[1:]):
            acc += float(_hav_m(*coords[a], *coords[b]))
            if b in junction or b == ns[-1]:
                if seg_start != b:
                    eu.append(node(seg_start)); ev.append(node(b))
                    elen.append(acc); etime.append(acc / v_mpm)
                seg_start, acc = b, 0.0
    lon, lat = np.array(lon), np.array(lat)
    eu, ev, elen, etime = map(np.array, (eu, ev, elen, etime))
    n = len(lon)
    G = coo_matrix((etime, (eu, ev)), shape=(n, n)).tocsr()
    ncomp, lab = connected_components(G, directed=False)
    keep_lab = np.bincount(lab).argmax()
    keep = lab == keep_lab
    remap = -np.ones(n, dtype=np.int64); remap[keep] = np.arange(keep.sum())
    m = keep[eu] & keep[ev]
    np.savez_compressed(out, lon=lon[keep].astype(np.float64), lat=lat[keep].astype(np.float64),
                        u=remap[eu[m]].astype(np.int32), v=remap[ev[m]].astype(np.int32),
                        length_m=elen[m].astype(np.float32), minutes=etime[m].astype(np.float32))
    return {"ways": len(ways), "junction_nodes": int(keep.sum()), "edges": int(m.sum()),
            "components_dropped": int(ncomp - 1), "km": float(elen[m].sum() / 1000)}

class RoadGraph:
    def __init__(self, path: str = GRAPH):
        z = np.load(path)
        self.lon, self.lat = z["lon"], z["lat"]
        n = len(self.lon)
        self.G = coo_matrix((z["minutes"], (z["u"], z["v"])), shape=(n, n)).tocsr()
        self.latc = float(np.mean(self.lat))
        self.kx = 111320.0 * math.cos(math.radians(self.latc)); self.ky = 110540.0
        self._tree = cKDTree(np.stack([self.lon * self.kx, self.lat * self.ky], axis=1))

    def snap(self, lon, lat):
        d, k = self._tree.query((lon * self.kx, lat * self.ky))
        return int(k), float(d)

    def snap_many(self, lonlats):
        a = np.asarray(lonlats, dtype=float)
        d, k = self._tree.query(np.stack([a[:, 0] * self.kx, a[:, 1] * self.ky], axis=1))
        return k, d

    @lru_cache(maxsize=256)
    def _sssp(self, src: int):
        return dijkstra(self.G, directed=False, indices=src)

    def drive_minutes(self, origin, dests) -> np.ndarray:
        """origin (lon,lat) -> many (lon,lat): network time + off-network legs at SNAP_MPH."""
        so, lo = self.snap(*origin)
        k, legs = self.snap_many(dests)
        return self._sssp(so)[k] + (lo + legs) / (SNAP_MPH * MPH_TO_M_PER_MIN)

_RG = None
def road() -> RoadGraph:
    global _RG
    if _RG is None:
        _RG = RoadGraph()
    return _RG

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "build":
    print(build())
