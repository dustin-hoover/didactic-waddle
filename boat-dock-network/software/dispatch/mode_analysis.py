#!/usr/bin/env python3
"""Boat vs truck, measured (doc 23 §2). Tests the "lake is the road" premise (doc 07)
against the real road network (OSM) and the real lake (NHD), for every premises.

Two questions, because a crew's day has two kinds of legs:
  1. Yard -> first job: best of the two yards, center-console boat vs truck.
  2. Job -> next job inside a zone (a crew works a zone for the day): water hop vs
     road hop between sampled pairs of premises in the same zone.
Plus the trailer option: tow the boat to the zone's best public ramp, then work by water.

Outputs: data/gis/outputs/dispatch_mode_by_zone.csv + dispatch_mode_summary.json
"""
import os, json, csv
import numpy as np
from waterroute import LakeGrid, ModeParams
from roadroute import RoadGraph

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(REPO, "data", "gis", "outputs")
YARDS = {"BASE-NW": (-94.06, 36.35), "BASE-E": (-93.84, 36.40)}   # candidate ops yards (doc 20)
TOW_FACTOR = 1.15            # towing a boat is slower than driving
LAUNCH_MIN = 20.0            # launch + load at a ramp (once per day)
PAIRS_PER_ZONE, SEED = 60, 7

def ramps(g):
    raw = os.path.join(REPO, "data", "gis", "raw", "osm_slipways.json")
    out = []
    if os.path.exists(raw):
        for e in json.load(open(raw))["elements"]:
            lon = e.get("lon", e.get("center", {}).get("lon")); lat = e.get("lat", e.get("center", {}).get("lat"))
            if lon is None:
                continue
            k, d = g.snap(lon, lat)
            if d <= 300:                       # on Beaver Lake (not Sequoyah / below the dam)
                out.append((lon, lat))
    return out

def main():
    g, rg, p = LakeGrid(), RoadGraph(), ModeParams()
    yards = {k: g.water_point(*v) for k, v in YARDS.items()}
    feats = json.load(open(os.path.join(OUT, "premises.geojson")))["features"]
    pts = np.array([f["geometry"]["coordinates"][:2] for f in feats])
    zone = np.array([f["properties"].get("z") for f in feats])
    k, leg = g.snap_many(pts)
    reach = leg <= p.max_land_leg_m

    # 1) yard -> job
    tw = np.full(len(pts), np.inf); tt = np.full(len(pts), np.inf)   # water-only minutes, truck
    for y in yards.values():
        ny, _ = g.snap(*y); dist, _ = g._sssp("center_console", ny)
        tw = np.minimum(tw, dist[k])
        tt = np.minimum(tt, rg.drive_minutes(y, pts) + p.truck_overhead_min)
    def boat_time(tieup):
        b = tw + tieup + leg / p.walk_m_per_min
        b[~reach] = np.inf
        return b
    tb = boat_time(p.boat_overhead_min)
    # the variable that decides it: dock turnaround (tie-up + unload) per stop
    sensitivity = {f"tieup_{t}min": round(float(np.mean(boat_time(t) < tt) * 100), 1) for t in (15, 10, 8, 5)}

    # 2) job -> job within a zone, and 3) the best ramp per zone
    rng = np.random.default_rng(SEED)
    rmp = ramps(g)
    rows = []
    for z in sorted(set(zone) - {None}):
        idx = np.where((zone == z) & reach)[0]
        allz = np.where(zone == z)[0]
        hop_b, hop_t = [], []
        if len(idx) >= 2:
            for _ in range(PAIRS_PER_ZONE):
                a, b = rng.choice(idx, 2, replace=False)
                wb = g.travel_minutes("center_console", k[a], [k[b]])[0]
                hop_b.append(wb + p.boat_overhead_min + (leg[a] + leg[b]) / p.walk_m_per_min)
                hop_t.append(rg.drive_minutes(tuple(pts[a]), [tuple(pts[b])])[0] + p.truck_overhead_min)
        hop_b, hop_t = np.array(hop_b), np.array(hop_t)
        best_ramp = None
        if rmp and len(idx):
            cz = pts[idx].mean(axis=0)
            opts = []
            for r in rmp:
                tow = min(rg.drive_minutes(y, [r])[0] for y in yards.values()) * TOW_FACTOR
                nr, _ = g.snap(*r)
                water = float(np.median(g.travel_minutes("center_console", nr, k[idx])))
                opts.append((tow + LAUNCH_MIN + water, tow, water, r))
            best_ramp = min(opts)
        m = zone == z
        yard_win = float(np.mean(tb[m] < tt[m]) * 100)
        hop_win = float(np.mean(hop_b < hop_t) * 100) if len(hop_b) else 0.0
        rows.append({
            "zone": z, "premises": int(m.sum()), "dock_reachable_pct": round(float(reach[m].mean() * 100), 1),
            "yard_to_job_boat_wins_pct": round(yard_win, 1),
            "median_truck_from_yard_min": round(float(np.median(tt[m])), 1),
            "median_boat_from_yard_min": round(float(np.median(tb[m][np.isfinite(tb[m])])), 1) if np.isfinite(tb[m]).any() else None,
            "intra_zone_hop_boat_wins_pct": round(hop_win, 1),
            "median_hop_truck_min": round(float(np.median(hop_t)), 1) if len(hop_t) else None,
            "median_hop_boat_min": round(float(np.median(hop_b)), 1) if len(hop_b) else None,
            "best_ramp_lonlat": [round(best_ramp[3][0], 5), round(best_ramp[3][1], 5)] if best_ramp else None,
            "ramp_day_start_min": round(best_ramp[0], 1) if best_ramp else None,
            "recommended_mode": ("boat-first" if (hop_win >= 50 or yard_win >= 50)
                                 else "mixed" if (hop_win >= 25 or yard_win >= 25) else "truck-first"),
        })
    with open(os.path.join(OUT, "dispatch_mode_by_zone.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    win = tb < tt
    summary = {
        "premises": int(len(pts)), "yards": {k: [round(v[0], 5), round(v[1], 5)] for k, v in yards.items()},
        "ramps_used": len(rmp),
        "yard_to_job_boat_wins_pct": round(float(win.mean() * 100), 1),
        "yard_to_job_boat_wins_count": int(win.sum()),
        "median_saving_where_boat_wins_min": round(float(np.median((tt - tb)[win])), 1) if win.any() else 0,
        "dock_reachable_pct": round(float(reach.mean() * 100), 1),
        "median_truck_from_yard_min": round(float(np.median(tt)), 1),
        "boat_wins_pct_by_dock_turnaround": sensitivity,
        "zones_boat_first": [r["zone"] for r in rows if r["recommended_mode"] == "boat-first"],
        "zones_mixed": [r["zone"] for r in rows if r["recommended_mode"] == "mixed"],
        "zones_truck_first": [r["zone"] for r in rows if r["recommended_mode"] == "truck-first"],
        "assumptions": {"boat": "center console 25 kn, 5 kn no-wake within 50 m of shore, 15 min tie-up/leg, "
                                "walk 60 m/min, dock-to-house <= 600 m",
                        "truck": "OSM network, posted x0.85 or class defaults, 10 min/leg",
                        "trailer": f"tow x{TOW_FACTOR}, {LAUNCH_MIN:.0f} min launch, OSM slipways within 300 m of lake"},
    }
    json.dump(summary, open(os.path.join(OUT, "dispatch_mode_summary.json"), "w"), indent=2)
    return summary, rows

if __name__ == "__main__":
    s, rows = main()
    print(json.dumps({k: v for k, v in s.items() if k != "assumptions"}, indent=1))
    print(f"{'zone':6}{'prem':>6}{'dock%':>7}{'yard boat%':>11}{'hop boat%':>10}{'hop truck':>10}{'hop boat':>9}  mode")
    for r in rows:
        print(f"{r['zone']:6}{r['premises']:>6}{r['dock_reachable_pct']:>7}{r['yard_to_job_boat_wins_pct']:>11}"
              f"{r['intra_zone_hop_boat_wins_pct']:>10}{str(r['median_hop_truck_min']):>10}{str(r['median_hop_boat_min']):>9}  {r['recommended_mode']}")
