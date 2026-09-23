#!/usr/bin/env python3
"""Load the network topology into PostGIS for the NOC (doc 24).

zones (zones.geojson) + head-ends + the 30 spine nodes + the 41 spine links (topology.py,
from the GIS outputs) -> zones / nodes / links, and one monitored device per element:
  rtr-<node>      router at every node (NodeDown = blackbox ICMP/BFD from the head-ends)
  lnk-<link>      radio / optic pair per link (LinkDown = interface oper-status, both ends)
  pwr-<node>      solar charge controller at T3 sites (SOC telemetry, OnBattery/BatteryLow)
Upserts, so it is safe to re-run after a design change. `--status live` marks the sites
as live (for a lab or the test); the default keeps the doc 04 lifecycle ('candidate').

Run: python3 software/noc/load_topology.py [--status live] [--with-plan]
"""
from __future__ import annotations
import os, sys, json, asyncio, argparse
import asyncpg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import topology as T   # noqa: E402

DB = os.environ.get("DATABASE_URL", "postgresql://dockos:dockos@localhost:5432/dockos")

async def load(c, topo: T.Topology, status: str = "candidate", planned: list[T.Link] = ()) -> dict:
    zones = json.load(open(os.path.join(T.OUT, "zones.geojson")))["features"]
    for f in zones:
        p = f["properties"]
        await c.execute("""INSERT INTO zones (zone_id, name, geom)
            VALUES ($1,$2,ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON($3),4326)))
            ON CONFLICT (zone_id) DO UPDATE SET name=EXCLUDED.name, geom=EXCLUDED.geom""",
            p["zone_id"], p["name"], json.dumps(f["geometry"]))
    power_map = {"grid_ups": "grid_ups", "solar_battery": "solar_battery", "grid_generator": "grid"}
    for nid, n in topo.nodes.items():
        await c.execute("""INSERT INTO nodes (node_id, zone_id, tier, status, power, geom)
            VALUES ($1,$2,$3::node_tier,$4::node_status,$5::power_type,ST_SetSRID(ST_Point($6,$7),4326))
            ON CONFLICT (node_id) DO UPDATE SET zone_id=EXCLUDED.zone_id, tier=EXCLUDED.tier,
              status=EXCLUDED.status, power=EXCLUDED.power, geom=EXCLUDED.geom""",
            nid, n["zone"], n["tier"], status, power_map[n["power"]], n["lon"], n["lat"])
    links = list(topo.links.values()) + [(l, True) for l in planned]
    for item in links:
        l, is_plan = (item if isinstance(item, tuple) else (item, False))
        band = {"water_long": "licensed_uW", "water_short": "60GHz/5GHz", "land": "fiber_or_PtP",
                "headend_fiber": "fiber"}[l.kind]
        await c.execute("""INSERT INTO links (link_id, a_node, b_node, band, licensed, kind, km, cost_usd, planned, geom)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,
                    ST_MakeLine((SELECT geom FROM nodes WHERE node_id=$2),(SELECT geom FROM nodes WHERE node_id=$3)))
            ON CONFLICT (link_id) DO UPDATE SET a_node=EXCLUDED.a_node, b_node=EXCLUDED.b_node, band=EXCLUDED.band,
              kind=EXCLUDED.kind, km=EXCLUDED.km, cost_usd=EXCLUDED.cost_usd, planned=EXCLUDED.planned, geom=EXCLUDED.geom""",
            l.link_id, l.a, l.b, band, l.kind == "water_long", l.kind, l.km, l.cost, is_plan)
    ndev = 0
    for nid, n in topo.nodes.items():
        ndev += await _device(c, f"rtr-{nid}", "router", node_id=nid)
        if n["power"] == "solar_battery":
            ndev += await _device(c, f"pwr-{nid}", "solar_ctrl", node_id=nid)
    for l in topo.links.values():
        ndev += await _device(c, f"lnk-{l.link_id}", "optic" if l.kind in ("land", "headend_fiber") else "radio",
                              node_id=l.a, link_id=l.link_id)
    return {"zones": len(zones), "nodes": len(topo.nodes), "links": len(topo.links), "planned_links": len(planned),
            "devices": ndev}

async def _device(c, name, role, node_id=None, link_id=None) -> int:
    await c.execute("""INSERT INTO devices (name, role, node_id, link_id, kind) VALUES ($1,$2,$3,$4,$2)
        ON CONFLICT (name) DO UPDATE SET role=EXCLUDED.role, node_id=EXCLUDED.node_id, link_id=EXCLUDED.link_id""",
        name, role, node_id, link_id)
    return 1

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", default="candidate")
    ap.add_argument("--with-plan", action="store_true", help="also load the redundancy-plan hops (planned=true)")
    a = ap.parse_args()
    topo = T.from_gis()
    planned = []
    if a.with_plan:
        sys.path.insert(0, os.path.join(HERE, "..", "dispatch"))
        import waterroute
        mb = T.members_by_node_from_premises(topo)
        plan = topo.plan_redundancy(T.classify_with_lake(waterroute.grid()), mb)
        planned = [l for lid, l in plan["topology_after"].links.items() if lid not in topo.links]
    c = await asyncpg.connect(DB)
    try:
        async with c.transaction():
            print(await load(c, topo, a.status, planned))
    finally:
        await c.close()

if __name__ == "__main__":
    asyncio.run(main())
