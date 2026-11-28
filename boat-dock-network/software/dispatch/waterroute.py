#!/usr/bin/env python3
"""Water routing over Beaver Lake — "the lake is the road" (doc 07, doc 23).

Turns the NHD lake polygon (islands as holes) into a navigable grid and answers:
  * how long does it take a given boat to get from A to B by water?
  * what's the route (polyline, for the crew map)?
  * boat or truck for this job?

Model (planning-grade, all knobs are parameters):
  - Rasterize the lake at `cell_m` (default 50 m) with an even-odd scanline fill;
    keep the largest 8-connected water body (drops slivers the simplified shoreline
    can't really navigate).
  - Shoreline no-wake band: cells within `no_wake_m` of land run at `no_wake_kn`
    (default 50 m / 5 kn) — docks, coves and ramps are slow; open water is fast.
  - 8-neighbour graph, no corner-cutting across land; edge time = length / speed.
  - Dijkstra (scipy) per source, cached; a site is snapped to its nearest navigable
    cell and the snap distance becomes the on-foot "land leg" (dock -> house).
  - Truck alternative: crow-flies x road circuity at an average road speed — lake
    roads detour around every arm, which is exactly why the boat often wins.
"""
from __future__ import annotations
import json, math, os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy import ndimage
from scipy.spatial import cKDTree

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LAKE_GEOJSON = os.path.join(REPO, "data", "gis", "outputs", "lake.geojson")
KN_TO_M_PER_MIN = 1852.0 / 60.0
MPH_TO_M_PER_MIN = 1609.344 / 60.0

@dataclass(frozen=True)
class BoatClass:
    name: str
    cruise_kn: float
    max_wind_mph: float        # weather go/no-go (sustained)
    heavy_ok: bool             # can carry node builds / mast sections / cable reels

BOAT_CLASSES = {
    "center_console": BoatClass("center_console", 25.0, 25.0, False),  # fast service/repair
    "jon":            BoatClass("jon",            15.0, 15.0, False),  # tight coves, CPE
    "pontoon":        BoatClass("pontoon",        12.0, 20.0, True),   # builds, material haul
    "barge":          BoatClass("barge",           5.0, 15.0, True),   # dock-node sets, cable lay
}

def _rings(path: str) -> list[list[tuple[float, float]]]:
    g = json.load(open(path))
    geom = g["features"][0]["geometry"] if "features" in g else g.get("geometry", g)
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [[(float(x), float(y)) for x, y in ring] for poly in polys for ring in poly]

def _rdp(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker in metres (display only)."""
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1e-9
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / L
        if d > dmax:
            dmax, idx = d, i
    if dmax <= tol:
        return [pts[0], pts[-1]]
    return _rdp(pts[: idx + 1], tol)[:-1] + _rdp(pts[idx:], tol)

class LakeGrid:
    def __init__(self, lake_path: str = LAKE_GEOJSON, cell_m: float = 50.0,
                 no_wake_m: float = 50.0, no_wake_kn: float = 5.0):
        self.cell, self.no_wake_m, self.no_wake_kn = cell_m, no_wake_m, no_wake_kn
        rings = _rings(lake_path)
        lons = [p[0] for r in rings for p in r]; lats = [p[1] for r in rings for p in r]
        self.lon0, self.lat0 = min(lons), min(lats)
        latc = (min(lats) + max(lats)) / 2
        self.kx = 111320.0 * math.cos(math.radians(latc)); self.ky = 110540.0
        W = int(math.ceil((max(lons) - self.lon0) * self.kx / cell_m)) + 1
        H = int(math.ceil((max(lats) - self.lat0) * self.ky / cell_m)) + 1
        self.W, self.H = W, H
        water = self._rasterize(rings, W, H)
        lab, n = ndimage.label(water, structure=np.ones((3, 3), bool))
        if n > 1:   # keep the main navigable body
            sizes = ndimage.sum(water, lab, index=range(1, n + 1))
            water = lab == (int(np.argmax(sizes)) + 1)
        self.water = water
        self.shore_m = ndimage.distance_transform_edt(water) * cell_m   # metres to nearest land
        ys, xs = np.nonzero(water)
        self.node_rc = np.stack([ys, xs], axis=1)
        self.idx = -np.ones((H, W), dtype=np.int64)
        self.idx[ys, xs] = np.arange(len(ys))
        self.n = len(ys)
        self.cx = (xs + 0.5) * cell_m; self.cy = (ys + 0.5) * cell_m     # metres
        self._tree = cKDTree(np.stack([self.cx, self.cy], axis=1))
        self._graphs: dict = {}

    # -- geometry helpers
    def to_m(self, lon: float, lat: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky
    def to_ll(self, x: float, y: float) -> tuple[float, float]:
        return self.lon0 + x / self.kx, self.lat0 + y / self.ky

    def _rasterize(self, rings, W, H) -> np.ndarray:
        segs = []
        for r in rings:
            pts = [self.to_m(*p) for p in r]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
                if y1 != y2:
                    segs.append((x1, y1, x2, y2))
        s = np.array(segs)
        x1, y1, x2, y2 = s[:, 0], s[:, 1], s[:, 2], s[:, 3]
        out = np.zeros((H, W), dtype=bool)
        for i in range(H):
            y = (i + 0.5) * self.cell
            m = ((y1 <= y) & (y < y2)) | ((y2 <= y) & (y < y1))
            if not m.any():
                continue
            xs = np.sort(x1[m] + (y - y1[m]) * (x2[m] - x1[m]) / (y2[m] - y1[m]))
            for a, b in zip(xs[0::2], xs[1::2]):              # even-odd: holes = islands
                c0 = max(0, int(math.ceil(a / self.cell - 0.5)))
                c1 = min(W - 1, int(math.floor(b / self.cell - 0.5)))
                if c1 >= c0:
                    out[i, c0:c1 + 1] = True
        return out

    # -- graph per boat class (edge weights = minutes)
    def _graph(self, boat: BoatClass):
        if boat.name in self._graphs:
            return self._graphs[boat.name]
        v_open = boat.cruise_kn * KN_TO_M_PER_MIN
        v_slow = min(boat.cruise_kn, self.no_wake_kn) * KN_TO_M_PER_MIN
        speed = np.where(self.shore_m < self.no_wake_m, v_slow, v_open)     # m/min per cell
        rows, cols, w = [], [], []
        Wt = self.water
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
            a = np.zeros_like(Wt); b = np.zeros_like(Wt)
            ys0, ys1 = max(0, -dy), self.H - max(0, dy)
            xs0, xs1 = max(0, -dx), self.W - max(0, dx)
            src = Wt[ys0:ys1, xs0:xs1] & Wt[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
            if dy and dx:    # diagonal: both orthogonal neighbours must be water (no corner cutting)
                src &= Wt[ys0 + dy:ys1 + dy, xs0:xs1] & Wt[ys0:ys1, xs0 + dx:xs1 + dx]
            yy, xx = np.nonzero(src)
            yy += ys0; xx += xs0
            u = self.idx[yy, xx]; v = self.idx[yy + dy, xx + dx]
            length = self.cell * (math.sqrt(2) if (dy and dx) else 1.0)
            t = length / np.minimum(speed[yy, xx], speed[yy + dy, xx + dx])
            rows += [u, v]; cols += [v, u]; w += [t, t]
        G = coo_matrix((np.concatenate(w), (np.concatenate(rows), np.concatenate(cols))),
                       shape=(self.n, self.n)).tocsr()
        self._graphs[boat.name] = G
        return G

    def snap(self, lon: float, lat: float) -> tuple[int, float]:
        """Nearest navigable cell to a point -> (node, metres from point to that water)."""
        d, k = self._tree.query(self.to_m(lon, lat))
        return int(k), float(d)

    def snap_many(self, lonlats) -> tuple[np.ndarray, np.ndarray]:
        a = np.asarray(lonlats, dtype=float)
        xy = np.stack([(a[:, 0] - self.lon0) * self.kx, (a[:, 1] - self.lat0) * self.ky], axis=1)
        d, k = self._tree.query(xy)
        return k, d

    def water_point(self, lon: float, lat: float) -> tuple[float, float]:
        """The navigable water nearest a point (e.g. put a boat base at its dock)."""
        k, _ = self.snap(lon, lat)
        return self.to_ll(float(self.cx[k]), float(self.cy[k]))

    def _los(self, a, b) -> bool:
        """Straight segment between two cells stays entirely over navigable water."""
        n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) * 2 + 1
        rs = np.rint(np.linspace(a[0], b[0], n)).astype(int)
        cs = np.rint(np.linspace(a[1], b[1], n)).astype(int)
        return bool(self.water[rs, cs].all())

    def _string_pull(self, nodes: list[int]) -> list[int]:
        """Greedy line-of-sight shortcutting of a grid path -> a natural boat track."""
        rc = self.node_rc[nodes]
        out, i, N = [0], 0, len(nodes)
        while i < N - 1:
            j = i + 1
            while j + 1 < N and self._los(rc[i], rc[j + 1]):
                j += 1
            out.append(j); i = j
        return [nodes[k] for k in out]

    @lru_cache(maxsize=128)
    def _sssp(self, boat_name: str, src: int):
        return dijkstra(self._graph(BOAT_CLASSES[boat_name]), directed=False, indices=src,
                        return_predecessors=True)

    def travel_minutes(self, boat: str, src_node: int, dst_nodes) -> np.ndarray:
        dist, _ = self._sssp(boat, int(src_node))
        return dist[np.asarray(dst_nodes)]

    def route(self, a: tuple[float, float], b: tuple[float, float], boat: str = "center_console",
              simplify: bool = True) -> dict:
        """Water route A->B (lon,lat). minutes = water time only; land legs reported."""
        na, la = self.snap(*a); nb, lb = self.snap(*b)
        dist, pred = self._sssp(boat, na)
        if not np.isfinite(dist[nb]):
            return {"reachable": False}
        path, k = [], nb
        while k != -9999 and k >= 0:
            path.append(k)
            if k == na:
                break
            k = int(pred[k])
        path.reverse()
        if simplify:                                    # smoothed track (display + distance);
            path = self._string_pull(path)              # minutes stay the grid's conservative time
        pts = [(float(self.cx[k]), float(self.cy[k])) for k in path]
        water_m = sum(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(pts, pts[1:]))
        return {"reachable": True, "minutes": float(dist[nb]), "water_km": water_m / 1000,
                "crow_km": math.hypot(*(np.subtract(self.to_m(*b), self.to_m(*a)))) / 1000,
                "land_leg_a_m": la, "land_leg_b_m": lb,
                "path": [list(self.to_ll(x, y)) for x, y in pts]}

# ---------------------------------------------------------------- boat vs truck
def haversine_km(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))

@dataclass
class ModeParams:
    road_circuity: float = 1.6      # lake roads detour around arms (conservative: favours truck)
    road_mph: float = 35.0
    truck_overhead_min: float = 10.0
    boat_overhead_min: float = 15.0  # launch/tie-up/unload per leg
    walk_m_per_min: float = 60.0     # carrying gear, dock -> house
    max_land_leg_m: float = 600.0    # beyond this the boat isn't practical for that site

def truck_minutes(a, b, p: ModeParams = ModeParams()) -> float:
    return haversine_km(a, b) * 1000 * p.road_circuity / (p.road_mph * MPH_TO_M_PER_MIN) + p.truck_overhead_min

def choose_mode(grid: LakeGrid, origin, site, boat: str, p: ModeParams = ModeParams(),
                boat_ok: bool = True) -> dict:
    """Pick boat or truck for origin -> site (both lon,lat). Weather/no-go passes boat_ok=False."""
    t_truck = truck_minutes(origin, site, p)
    no, _ = grid.snap(*origin); ns, leg = grid.snap(*site)
    t_water = float(grid.travel_minutes(boat, no, [ns])[0])
    t_boat = t_water + p.boat_overhead_min + leg / p.walk_m_per_min
    boat_feasible = boat_ok and np.isfinite(t_water) and leg <= p.max_land_leg_m
    mode = "boat" if boat_feasible and t_boat <= t_truck else "truck"
    return {"mode": mode, "boat_min": round(t_boat, 1) if boat_feasible else None,
            "truck_min": round(t_truck, 1), "land_leg_m": round(leg),
            "minutes": round(t_boat if mode == "boat" else t_truck, 1)}

_GRID: Optional[LakeGrid] = None
def grid() -> LakeGrid:
    """Process-wide grid (built once, ~seconds)."""
    global _GRID
    if _GRID is None:
        _GRID = LakeGrid()
    return _GRID
