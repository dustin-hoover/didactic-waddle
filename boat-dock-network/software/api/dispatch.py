#!/usr/bin/env python3
"""Boat Dock Network — work-order engine + boat/truck dispatch API (doc 23). DockOS steps 4-5.

Work order lifecycle (wo_status):
  draft ─release─▶ released ─plan─▶ scheduled ─crew starts─▶ in_progress ─complete─▶ closed
     └▶ permitting (build types until the doc 12/19 permit checklist clears)     (builds: asbuilt)
  released + blocked_reason = awaiting parts (shortfall -> draft PO) until inventory arrives
  cant_complete (no dock access, member away...) -> back to released for re-planning

What it connects:
  * signup/billing (doc 22): every pending service gets an install WO with the right BOM
    kit; when the crew completes it in the field PWA, billing.activate_service() runs —
    the member's first (prorated) bill is issued by the boat crew closing the job.
  * BOM kits (doc 10) -> work_order_items -> warehouse reservation -> PO shortfall (doc 11)
    -> consumption + capitalized assets + CPE records on completion (doc 09).
  * dispatch: NWS weather go/no-go per boat class; a day planner that assigns crews and
    picks boat vs truck per leg from real water routes (waterroute.py) and real OSM
    drive times (roadroute.py); urgent (P1 outage) insertion to the nearest crew.
  * field PWA (software/dispatch_pwa, served at /crew): offline action queue replayed
    here idempotently; arrive/start/complete/depart timestamps measure dock turnaround,
    which feeds back into the planner (the variable that decides boat vs truck, doc 23 §2).

Run (dev): DATABASE_URL=... uvicorn dispatch:app   (from software/api)
"""
from __future__ import annotations
import os, sys, csv, json, re, math, datetime as dt, urllib.request
from typing import Optional, Literal
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncpg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "dispatch"))
import waterroute, roadroute                      # noqa: E402
from billing import activate_service, norm_mac   # noqa: E402  (doc 22)

app = FastAPI(title="Boat Dock Network — Work Orders & Dispatch")
DB = os.environ.get("DATABASE_URL", "postgresql://dockos:dockos@localhost:5432/dockos")
TZ = ZoneInfo("America/Chicago")
BOM_DIR = os.path.join(REPO, "data", "bom")
PWA_DIR = os.path.join(REPO, "software", "dispatch_pwa")
LAKE = os.path.join(REPO, "data", "gis", "outputs", "lake.geojson")
NWS_POINT = os.environ.get("NWS_POINT", "36.33,-93.95")                 # mid-lake
NWS_UA = os.environ.get("NWS_USER_AGENT", "BoatDockNetwork-dispatch (ops@boatdock.network)")
DEFAULT_BOAT_TIEUP_MIN = float(os.environ.get("DEFAULT_BOAT_TIEUP_MIN", 10))  # until measured
TRUCK_TIEUP_MIN = float(os.environ.get("TRUCK_TIEUP_MIN", 10))
MIN_TURNAROUND_SAMPLES = 5
LOADOUT_MIN = 30
WALK_M_PER_MIN = 60.0
MAX_DOCK_TO_SITE_M = 600.0
STOCKED = {"radio", "optics", "fiber", "enclosure", "power", "mount", "misc"}
PARAM_DEFAULTS = {"LEN_FT": 150, "N_SECTORS": 3, "N_LOS_SECTORS": 0}

# est h = on-site hours per visit; builds are multi-day, planned as 6 h build days (travel on top)
#            kit file                    est h  skills                           heavy  prio  access       permit
WO_TYPES = {
    "survey":            ("wo-survey.csv",            1.0, ["survey"],                     False, "P4", "any",       False),
    "cpe-wireless-nlos": ("wo-cpe-wireless-nlos.csv", 2.5, ["install_wireless"],           False, "P3", "any",       False),
    "cpe-wireless-ptmp": ("wo-cpe-wireless-ptmp.csv", 2.0, ["install_wireless"],           False, "P3", "any",       False),
    "drop-aerial-fiber": ("wo-drop-aerial-fiber.csv", 4.0, ["install_fiber", "splice"],    False, "P3", "any",       False),
    "drop-ug-fiber":     ("wo-drop-ug-fiber.csv",     6.0, ["install_fiber", "splice"],    False, "P3", "road_only", False),
    "repair":            (None,                       1.5, ["repair"],                     False, "P2", "any",       False),
    "t3-relay":          ("wo-t3-relay.csv",          6.0, ["tower", "install_wireless"],  True,  "P4", "any",       True),
    "t2-docknode":       ("wo-t2-docknode.csv",       6.0, ["tower", "marine_ops"],        True,  "P4", "boat_only", True),
    "t1-core":           ("wo-t1-core.csv",           6.0, ["tower"],                      True,  "P4", "road_only", True),
    "t0-headend":        ("wo-t0-headend.csv",        6.0, ["tower", "splice"],            True,  "P4", "road_only", True),
    "lake-crossing-mw":  ("wo-lake-crossing-mw.csv",  6.0, ["tower", "marine_ops"],        True,  "P4", "boat_only", True),
    "subaqueous-fiber":  ("wo-subaqueous-fiber.csv",  6.0, ["splice", "marine_ops"],       True,  "P4", "boat_only", True),
    "fiber-aerial-mile": ("wo-fiber-aerial-mile.csv", 6.0, ["splice"],                     True,  "P4", "road_only", True),
    "fiber-ug-mile":     ("wo-fiber-ug-mile.csv",     6.0, ["splice"],                     True,  "P4", "road_only", True),
}
INSTALL_BY_MEDIUM = {"wireless_nlos": "cpe-wireless-nlos", "wireless_ptmp": "cpe-wireless-ptmp",
                     "fiber": "drop-aerial-fiber"}
REQUIRED_CAPTURES = {
    "cpe-wireless-nlos": ["device_mac", "speed_down_mbps", "speed_up_mbps", "rssi_dbm"],
    "cpe-wireless-ptmp": ["device_mac", "speed_down_mbps", "speed_up_mbps", "rssi_dbm"],
    "drop-aerial-fiber": ["ont_serial", "rx_power_dbm", "speed_down_mbps"],
    "drop-ug-fiber":     ["ont_serial", "rx_power_dbm", "speed_down_mbps"],
    "repair":            ["resolution"],
    "survey":            ["dock_access", "gps"],
}
CHECKLISTS = {
    "cpe-wireless-nlos": ["Confirm member + site; note dock access", "Mount CPE (eave/pole/dock mount)",
                          "Aim to base node — record RSSI", "Scan CPE MAC label", "Router + Wi-Fi walkthrough",
                          "Speed test at router", "Photos: mount + cable path", "Explain WAKE + member portal"],
    "drop-aerial-fiber": ["Confirm member + site", "Run drop from terminal", "Splice + connectorize",
                          "Mount NID/ONT — scan ONT serial", "Light level (dBm) at ONT", "Speed test",
                          "Photos: span, NID, ONT"],
    "repair":            ["Check NOC ticket + last alarms", "Diagnose on site", "Swap from spare kit if needed",
                          "Verify with NOC", "Record resolution"],
}
CHECKLISTS["cpe-wireless-ptmp"] = CHECKLISTS["cpe-wireless-nlos"]
CHECKLISTS["drop-ug-fiber"] = CHECKLISTS["drop-aerial-fiber"]
SLA_HOURS = {"P1": 4, "P2": 24, "P3": 14 * 24, "P4": None}

_pool: Optional[asyncpg.Pool] = None
async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB, min_size=1, max_size=8)
    return _pool

# ---------------------------------------------------------------- helpers
def sku_for(item: str, spec: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{item} {spec}".lower()).strip("-")[:80]

def read_kit(fname: str) -> list[dict]:
    with open(os.path.join(BOM_DIR, fname), newline="") as f:
        return list(csv.DictReader(f))

def kit_qty(q: str, params: dict) -> float:
    q = (q or "").strip()
    if re.fullmatch(r"\d+(\.\d+)?", q):
        return float(q)
    return float(params.get(q, PARAM_DEFAULTS.get(q, 1)))

async def _event(c, wo_id, kind, actor=None, detail=None, client_action_id=None, vehicle_kind=None,
                 at=None, lon=None, lat=None):
    await c.execute("""INSERT INTO wo_events (wo_id, kind, actor, detail, client_action_id, vehicle_kind, at, geom)
        VALUES ($1,$2,$3,$4::jsonb,$5,$6::vehicle_kind,COALESCE($7, now()),
                CASE WHEN $8::float8 IS NULL THEN NULL ELSE ST_SetSRID(ST_Point($8,$9),4326) END)""",
        wo_id, kind, actor, json.dumps(detail or {}, default=str), client_action_id, vehicle_kind, at, lon, lat)

async def _wo(c, wo_id, lock=False) -> dict:
    r = await c.fetchrow("SELECT *, ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat "
                         "FROM work_orders WHERE wo_id=$1" + (" FOR UPDATE" if lock else ""), wo_id)
    if not r:
        raise HTTPException(404, f"work order {wo_id} not found")
    d = dict(r)
    d["params"] = json.loads(d["params"]) if isinstance(d["params"], str) else (d["params"] or {})
    d["captures"] = json.loads(d["captures"]) if isinstance(d["captures"], str) else (d["captures"] or {})
    return d

def local_dt(day: dt.date, t: dt.time) -> dt.datetime:
    return dt.datetime.combine(day, t, tzinfo=TZ)

# ---------------------------------------------------------------- catalog
async def load_catalog(c) -> int:
    n = 0
    for meta in WO_TYPES.values():
        if not meta[0]:
            continue
        for row in read_kit(meta[0]):
            await c.execute("""INSERT INTO skus (sku, description, category, unit, standard_cost_usd,
                    vendor_primary, vendor_alt, serialized)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (sku) DO UPDATE SET standard_cost_usd=EXCLUDED.standard_cost_usd,
                    vendor_primary=EXCLUDED.vendor_primary, vendor_alt=EXCLUDED.vendor_alt""",
                sku_for(row["item"], row["spec"]), f'{row["item"]} — {row["spec"]}', row["category"], row["unit"],
                float(row["unit_cost_est_usd"] or 0), row["vendor_primary"] or "TBD", row["vendor_alt"] or None,
                row["category"] in ("radio", "optics") and row["unit"] == "ea")
            n += 1
    return n

@app.on_event("startup")
async def _startup():
    waterroute.grid(); roadroute.road()        # warm the lake + road graphs (~1-2 s)

@app.post("/catalog/load")
async def catalog_load():
    async with (await pool()).acquire() as c:
        async with c.transaction():
            return {"ok": True, "kit_lines": await load_catalog(c)}

# ---------------------------------------------------------------- work orders
class WOIn(BaseModel):
    wo_type: str
    address_id: Optional[int] = None
    node_id: Optional[str] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    priority: Optional[Literal["P1", "P2", "P3", "P4"]] = None
    service_id: Optional[int] = None
    outage_id: Optional[int] = None
    params: dict = {}
    note: Optional[str] = None

async def create_wo(c, w: WOIn) -> int:
    if w.wo_type not in WO_TYPES:
        raise HTTPException(400, f"unknown wo_type {w.wo_type}")
    kit, est, skills, heavy, prio, access, _ = WO_TYPES[w.wo_type]
    prio = w.priority or prio
    if w.address_id:
        loc = await c.fetchrow("SELECT geom IS NOT NULL AS has_geom, zone_id FROM service_addresses WHERE address_id=$1", w.address_id)
    elif w.node_id:
        loc = await c.fetchrow("SELECT geom IS NOT NULL AS has_geom, zone_id FROM nodes WHERE node_id=$1", w.node_id)
    else:
        loc = None
    if w.lon is not None and w.lat is not None:
        geom_sql, gargs = "ST_SetSRID(ST_Point($11,$12),4326)", [w.lon, w.lat]
    elif loc and loc["has_geom"]:
        geom_sql, gargs = "(SELECT geom FROM service_addresses WHERE address_id=$11 UNION ALL SELECT geom FROM nodes WHERE node_id=$12 LIMIT 1)", [w.address_id, w.node_id]
    else:
        raise HTTPException(400, "work order needs a location (address, node, or lon/lat)")
    sla = SLA_HOURS[prio]
    row = await c.fetchrow(f"""INSERT INTO work_orders (wo_type, status, zone_id, node_id, address_id, params,
            priority, service_id, outage_id, est_hours, required_skills, requires_heavy, access_mode,
            sla_due, note, geom)
        VALUES ($1,'draft',$2,$3,$4,$5::jsonb,$6::wo_priority,$7,$8,$9,$10,$13,$14,
                CASE WHEN $15::float8 IS NULL THEN NULL ELSE now() + ($15 || ' hours')::interval END,
                $16, {geom_sql})
        RETURNING wo_id""",
        w.wo_type, loc["zone_id"] if loc else None, w.node_id, w.address_id, json.dumps(w.params),
        prio, w.service_id, w.outage_id, est, skills, *gargs, heavy, access, sla, w.note)
    await _event(c, row["wo_id"], "created", detail={"wo_type": w.wo_type, "priority": prio})
    return row["wo_id"]

@app.post("/work-orders")
async def post_wo(w: WOIn):
    async with (await pool()).acquire() as c:
        async with c.transaction():
            return {"ok": True, "wo_id": await create_wo(c, w)}

@app.post("/work-orders/sync-installs")
async def sync_installs():
    """Every pending/provisioned service without an open install WO gets one (kit by medium)."""
    made = []
    async with (await pool()).acquire() as c:
        rows = await c.fetch("""SELECT si.service_id, si.address_id, si.medium, sa.geom IS NOT NULL AS located
            FROM service_instances si LEFT JOIN service_addresses sa ON sa.address_id=si.address_id
            WHERE si.state IN ('pending','provisioned')
              AND NOT EXISTS (SELECT 1 FROM work_orders w WHERE w.service_id=si.service_id
                              AND w.status NOT IN ('closed','cancelled'))""")
        for r in rows:
            if not r["located"]:
                continue
            async with c.transaction():
                wid = await create_wo(c, WOIn(wo_type=INSTALL_BY_MEDIUM.get(r["medium"], "cpe-wireless-nlos"),
                                              address_id=r["address_id"], service_id=r["service_id"]))
            made.append(wid)
    return {"ok": True, "created": made}

async def _reserve(c, wo_id: int) -> list[dict]:
    """Reserve un-reserved stocked lines from the warehouse; return shortfalls."""
    short = []
    items = await c.fetch("""SELECT * FROM work_order_items WHERE wo_id=$1 AND stocked
                             AND qty_reserved < qty ORDER BY id""", wo_id)
    for it in items:
        need = float(it["qty"]) - float(it["qty_reserved"])
        inv = await c.fetchrow("""SELECT id, qty_on_hand - qty_reserved AS avail FROM inventory
            WHERE sku=$1 AND location='warehouse' FOR UPDATE""", it["sku"])
        take = max(0.0, min(need, float(inv["avail"]))) if inv else 0.0
        if take > 0:
            await c.execute("UPDATE inventory SET qty_reserved = qty_reserved + $2 WHERE id=$1", inv["id"], take)
            await c.execute("UPDATE work_order_items SET qty_reserved = qty_reserved + $2 WHERE id=$1", it["id"], take)
        if need - take > 1e-9:
            short.append({"sku": it["sku"], "qty": need - take, "unit_cost": float(it["unit_cost_usd"] or 0)})
    return short

async def _po_for_shortfall(c, wo_id: int, short: list[dict]) -> list[int]:
    pos = set()
    for s in short:
        vname = await c.fetchval("SELECT COALESCE(vendor_primary,'TBD') FROM skus WHERE sku=$1", s["sku"]) or "TBD"
        vid = await c.fetchval("""INSERT INTO vendors (name, category) VALUES ($1,'network')
            ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING vendor_id""", vname)
        po = await c.fetchval("SELECT po_id FROM purchase_orders WHERE vendor_id=$1 AND status='draft' ORDER BY po_id LIMIT 1", vid)
        if not po:
            po = await c.fetchval("INSERT INTO purchase_orders (vendor_id, status) VALUES ($1,'draft') RETURNING po_id", vid)
        await c.execute("INSERT INTO po_lines (po_id, sku, qty, unit_cost_usd, wo_id) VALUES ($1,$2,$3,$4,$5)",
                        po, s["sku"], s["qty"], s["unit_cost"], wo_id)
        pos.add(po)
    return sorted(pos)

async def release_wo(c, wo_id: int) -> dict:
    wo = await _wo(c, wo_id, lock=True)
    if wo["status"] not in ("draft", "permitting"):
        return {"wo_id": wo_id, "status": wo["status"], "unchanged": True}
    kit, *_rest = WO_TYPES[wo["wo_type"]]
    needs_permit = WO_TYPES[wo["wo_type"]][6]
    if needs_permit and not wo["params"].get("permit_approved"):
        await c.execute("""UPDATE work_orders SET status='permitting',
            blocked_reason='permit checklist not cleared (doc 12/19: USACE, ROW, FAA...)' WHERE wo_id=$1""", wo_id)
        await _event(c, wo_id, "permitting")
        return {"wo_id": wo_id, "status": "permitting"}
    await c.execute("DELETE FROM work_order_items WHERE wo_id=$1", wo_id)
    lines = 0
    for row in (read_kit(kit) if kit else []):
        await c.execute("""INSERT INTO work_order_items (wo_id, sku, category, spec, qty, unit, unit_cost_usd, stocked)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""", wo_id, sku_for(row["item"], row["spec"]), row["category"],
            f'{row["item"]} — {row["spec"]}', kit_qty(row["qty"], wo["params"]), row["unit"],
            float(row["unit_cost_est_usd"] or 0), row["category"] in STOCKED)
        lines += 1
    short = await _reserve(c, wo_id)
    pos = await _po_for_shortfall(c, wo_id, short) if short else []
    blocked = ("awaiting parts: " + ", ".join(f'{s["sku"]} x{s["qty"]:g}' for s in short)) if short else None
    await c.execute("""UPDATE work_orders SET status='released', released_at=now(), blocked_reason=$2
        WHERE wo_id=$1""", wo_id, blocked)
    await _event(c, wo_id, "released", detail={"bom_lines": lines, "shortfall": short, "draft_pos": pos})
    return {"wo_id": wo_id, "status": "released", "bom_lines": lines, "shortfall": short, "draft_pos": pos,
            "blocked": blocked}

@app.post("/work-orders/{wo_id}/release")
async def post_release(wo_id: int):
    async with (await pool()).acquire() as c:
        async with c.transaction():
            return await release_wo(c, wo_id)

class ReceiveIn(BaseModel):
    sku: str
    qty: float
    location: str = "warehouse"

@app.post("/inventory/receive")
async def receive(r: ReceiveIn):
    """Parts arrive: stock up, then re-reserve for WOs waiting on parts (priority order)."""
    unblocked = []
    async with (await pool()).acquire() as c:
        async with c.transaction():
            await c.execute("""INSERT INTO inventory (sku, location, qty_on_hand, qty_reserved) VALUES ($1,$2,$3,0)
                ON CONFLICT (sku, location) DO UPDATE SET qty_on_hand = inventory.qty_on_hand + $3""",
                r.sku, r.location, r.qty)
            waiting = await c.fetch("""SELECT wo_id FROM work_orders WHERE status='released'
                AND blocked_reason LIKE 'awaiting parts%' ORDER BY priority, created_at""")
            for w in waiting:
                if not await _reserve(c, w["wo_id"]):
                    await c.execute("UPDATE work_orders SET blocked_reason=NULL WHERE wo_id=$1", w["wo_id"])
                    await _event(c, w["wo_id"], "parts_ready")
                    unblocked.append(w["wo_id"])
    return {"ok": True, "unblocked": unblocked}

# ---------------------------------------------------------------- weather (NWS) go/no-go
def _mph(s: str) -> int:
    nums = [int(x) for x in re.findall(r"\d+", s or "")]
    return max(nums) if nums else 0

def weather_decision(periods: list[dict], day: dt.date) -> dict:
    """Go/no-go per boat class from NWS hourly periods over working hours (07-18 local)."""
    hrs = []
    for p in periods:
        t = dt.datetime.fromisoformat(p["startTime"]).astimezone(TZ)
        if t.date() == day and 7 <= t.hour < 18:
            hrs.append(p)
    if not hrs:
        return {"source": "unavailable", "advisory": "no NWS hourly data for this day — check the marine forecast",
                "classes": {k: True for k in waterroute.BOAT_CLASSES}}
    wind = max(_mph(p.get("windSpeed")) for p in hrs)
    thunder = any("thunder" in (p.get("shortForecast") or "").lower()
                  and ((p.get("probabilityOfPrecipitation") or {}).get("value") or 0) >= 30 for p in hrs)
    classes = {k: (wind <= b.max_wind_mph and not thunder) for k, b in waterroute.BOAT_CLASSES.items()}
    return {"source": "nws", "max_wind_mph": wind, "thunderstorms": thunder, "classes": classes,
            "summary": sorted({p.get("shortForecast") for p in hrs})}

def fetch_nws_hourly() -> list[dict]:
    def get(url):
        req = urllib.request.Request(url, headers={"User-Agent": NWS_UA, "Accept": "application/geo+json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    pt = get(f"https://api.weather.gov/points/{NWS_POINT}")
    return get(pt["properties"]["forecastHourly"])["properties"]["periods"]

async def weather_gate(c, day: dt.date, refresh: bool = False) -> dict:
    row = await c.fetchrow("SELECT source, data FROM weather_calls WHERE day=$1", day)
    if row and (row["source"] == "override" or not refresh):
        return json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
    try:
        data = weather_decision(fetch_nws_hourly(), day)
    except Exception as e:
        data = {"source": "unavailable", "advisory": f"NWS fetch failed ({e.__class__.__name__}) — "
                "check the marine forecast before launch", "classes": {k: True for k in waterroute.BOAT_CLASSES}}
    await c.execute("""INSERT INTO weather_calls (day, source, data) VALUES ($1,$2,$3::jsonb)
        ON CONFLICT (day) DO UPDATE SET source=EXCLUDED.source, data=EXCLUDED.data, decided_at=now()""",
        day, data["source"], json.dumps(data))
    return data

@app.get("/weather/{day}")
async def get_weather(day: dt.date, refresh: bool = False):
    async with (await pool()).acquire() as c:
        return await weather_gate(c, day, refresh)

class WeatherOverride(BaseModel):
    day: dt.date
    classes: dict[str, bool]
    reason: str

@app.post("/weather/override")
async def weather_override(w: WeatherOverride):
    """Dispatcher's call (lightning on the radar, fog) — wins over the forecast."""
    data = {"source": "override", "reason": w.reason,
            "classes": {k: w.classes.get(k, True) for k in waterroute.BOAT_CLASSES}}
    async with (await pool()).acquire() as c:
        await c.execute("""INSERT INTO weather_calls (day, source, data) VALUES ($1,'override',$2::jsonb)
            ON CONFLICT (day) DO UPDATE SET source='override', data=EXCLUDED.data, decided_at=now()""",
            w.day, json.dumps(data))
    return data

# ---------------------------------------------------------------- travel model
async def boat_tieup_min(c) -> tuple[float, str]:
    r = await c.fetchrow("SELECT stops, median_overhead_min FROM turnaround_stats WHERE vehicle_kind='boat'")
    if r and r["stops"] >= MIN_TURNAROUND_SAMPLES:
        return float(r["median_overhead_min"]), f"measured ({r['stops']} stops, 60 d)"
    return DEFAULT_BOAT_TIEUP_MIN, "default (not enough measured stops yet)"

def leg(a, b, vehicle: dict, tieup: float, arrive_site: bool = True) -> Optional[dict]:
    """Travel a->b (lon,lat) for a vehicle. None if infeasible (site too far from water)."""
    if vehicle["kind"] == "boat":
        r = waterroute.grid().route(a, b, vehicle["boat_class"] or "center_console")
        if not r.get("reachable"):
            return None
        if arrive_site and r["land_leg_b_m"] > MAX_DOCK_TO_SITE_M:
            return None
        walk = (r["land_leg_a_m"] + (r["land_leg_b_m"] if arrive_site else 0)) / WALK_M_PER_MIN
        return {"mode": "boat", "minutes": r["minutes"] + walk + (tieup if arrive_site else 0),
                "water_min": round(r["minutes"], 1), "path": r["path"],
                "dock_to_site_m": round(r["land_leg_b_m"])}
    m = float(roadroute.road().drive_minutes(a, [b])[0])
    if not math.isfinite(m):
        return None
    return {"mode": "truck", "minutes": m + (TRUCK_TIEUP_MIN if arrive_site else 0)}

# ---------------------------------------------------------------- day planner
async def _crew_vehicles(c, day: dt.date) -> list[dict]:
    crews = [dict(r) for r in await c.fetch("""SELECT c.*, ST_X(y.geom) AS ylon, ST_Y(y.geom) AS ylat
        FROM crews c JOIN yards y ON y.yard_id=c.yard_id WHERE c.active ORDER BY c.crew_id""")]
    vehicles = {r["vehicle_id"]: dict(r) for r in await c.fetch("SELECT * FROM vehicles WHERE status='available'")}
    assigned = {r["crew_id"]: r["vehicle_id"] for r in await c.fetch("SELECT * FROM crew_days WHERE day=$1", day)}
    used = set(assigned.values())
    out = []
    for cr in crews:
        vid = assigned.get(cr["crew_id"])
        if not vid:   # default: first free vehicle at the crew's yard
            vid = next((v for v, x in vehicles.items() if x["yard_id"] == cr["yard_id"] and v not in used), None)
            if vid:
                used.add(vid)
                await c.execute("INSERT INTO crew_days (crew_id, day, vehicle_id) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                                cr["crew_id"], day, vid)
        if vid and vid in vehicles:
            out.append({**cr, "vehicle": vehicles[vid]})
    return out

def _eligible(wo: dict, cv: dict, weather: dict) -> bool:
    v = cv["vehicle"]
    if not set(wo["required_skills"] or []) <= set(cv["skills"] or []):
        return False
    if wo["access_mode"] == "boat_only" and v["kind"] != "boat":
        return False
    if wo["access_mode"] == "road_only" and v["kind"] != "truck":
        return False
    if v["kind"] == "boat":
        bc = waterroute.BOAT_CLASSES.get(v["boat_class"] or "center_console")
        if not weather["classes"].get(bc.name, True):
            return False
        if wo["requires_heavy"] and not bc.heavy_ok:
            return False
    return True

async def plan_day(c, day: dt.date) -> dict:
    weather = await weather_gate(c, day)
    tieup, tieup_src = await boat_tieup_min(c)
    await c.execute("""UPDATE work_orders SET status='released', assigned_crew=NULL, vehicle_id=NULL, route_seq=NULL,
        eta=NULL, travel_mode=NULL, travel_min=NULL, scheduled_for=NULL WHERE scheduled_for=$1 AND status='scheduled'""", day)
    await c.execute("DELETE FROM dispatch_plans WHERE day=$1", day)
    wos = [dict(r) for r in await c.fetch("""SELECT w.*, ST_X(ST_Centroid(w.geom)) AS lon, ST_Y(ST_Centroid(w.geom)) AS lat
        FROM work_orders w WHERE w.status='released' AND w.blocked_reason IS NULL AND w.geom IS NOT NULL
        ORDER BY w.priority, w.sla_due NULLS LAST, w.created_at""")]
    crews = await _crew_vehicles(c, day)
    state = {}
    for cv in crews:
        start = local_dt(day, cv["shift_start"]) + dt.timedelta(minutes=LOADOUT_MIN)
        state[cv["crew_id"]] = {"cv": cv, "pos": (cv["ylon"], cv["ylat"]), "t": start,
                                "end": local_dt(day, cv["shift_start"]) + dt.timedelta(hours=float(cv["shift_hours"])),
                                "stops": []}
    unassigned = []
    for wo in wos:
        site = (wo["lon"], wo["lat"])
        best = None
        for cid, st in state.items():
            cv = st["cv"]
            if not _eligible(wo, cv, weather):
                continue
            go = leg(st["pos"], site, cv["vehicle"], tieup)
            if not go:
                continue
            back = leg(site, (cv["ylon"], cv["ylat"]), cv["vehicle"], tieup, arrive_site=False)
            if not back:
                continue
            arrive = st["t"] + dt.timedelta(minutes=go["minutes"])
            finish = arrive + dt.timedelta(hours=float(wo["est_hours"] or 1))
            if finish + dt.timedelta(minutes=back["minutes"]) > st["end"]:
                continue
            # urgent work: whoever gets there first; otherwise cheapest insertion (least added
            # travel, shift-capped) so a boat keeps working its arm and a truck its roads
            key = (arrive,) if wo["priority"] in ("P1", "P2") else (go["minutes"], finish)
            if best is None or key < best[0]:
                best = (key, cid, go, arrive, finish)
        if not best:
            unassigned.append({"wo_id": wo["wo_id"], "wo_type": wo["wo_type"], "priority": wo["priority"]})
            continue
        _, cid, go, arrive, finish = best
        st = state[cid]
        st["stops"].append({"wo": wo, "leg": go, "eta": arrive, "done": finish})
        st["pos"], st["t"] = site, finish
    # persist
    plans = []
    for cid, st in state.items():
        cv = st["cv"]; v = cv["vehicle"]
        stops_json = []
        for i, s in enumerate(st["stops"], 1):
            w = s["wo"]
            await c.execute("""UPDATE work_orders SET status='scheduled', scheduled_for=$2, assigned_crew=$3,
                vehicle_id=$4, route_seq=$5, eta=$6, travel_mode=$7, travel_min=$8 WHERE wo_id=$1""",
                w["wo_id"], day, cid, v["vehicle_id"], i, s["eta"], s["leg"]["mode"], round(s["leg"]["minutes"], 1))
            await _event(c, w["wo_id"], "scheduled", detail={"crew": cid, "seq": i, "eta": s["eta"].isoformat()})
            stops_json.append({"seq": i, "wo_id": w["wo_id"], "wo_type": w["wo_type"], "priority": w["priority"],
                               "lon": w["lon"], "lat": w["lat"], "eta": s["eta"].isoformat(),
                               "finish": s["done"].isoformat(), "travel": {k: v2 for k, v2 in s["leg"].items()}})
        back = None
        if st["stops"]:
            back = leg(st["pos"], (cv["ylon"], cv["ylat"]), v, tieup, arrive_site=False)
        load = await _load_list(c, [s["wo"]["wo_id"] for s in st["stops"]], v)
        plan = {"day": str(day), "crew_id": cid, "crew": cv["name"], "vehicle": v,
                "yard": {"lon": cv["ylon"], "lat": cv["ylat"]}, "weather": weather,
                "boat_tieup_min": tieup, "tieup_source": tieup_src, "stops": stops_json,
                "return": ({"minutes": round(back["minutes"], 1), "path": back.get("path")} if back else None),
                "load_list": load}
        await c.execute("""INSERT INTO dispatch_plans (day, crew_id, vehicle_id, plan) VALUES ($1,$2,$3,$4::jsonb)""",
                        day, cid, v["vehicle_id"], json.dumps(plan, default=str))
        plans.append({"crew_id": cid, "vehicle": v["vehicle_id"], "kind": v["kind"],
                      "stops": [s["wo_id"] for s in stops_json]})
    return {"day": str(day), "weather": weather, "boat_tieup_min": tieup, "tieup_source": tieup_src,
            "plans": plans, "unassigned": unassigned}

async def _load_list(c, wo_ids: list[int], vehicle: dict) -> list[dict]:
    rows = await c.fetch("""SELECT sku, min(spec) AS spec, sum(qty) AS qty, min(unit) AS unit
        FROM work_order_items WHERE wo_id = ANY($1::bigint[]) AND stocked GROUP BY sku ORDER BY sku""", wo_ids)
    out = [{"sku": r["sku"], "item": r["spec"], "qty": float(r["qty"]), "unit": r["unit"], "for": "jobs"} for r in rows]
    for row in read_kit("wo-spare-kit-boat.csv"):          # every vessel/truck is a rolling spares kit (doc 10 §5)
        out.append({"sku": sku_for(row["item"], row["spec"]), "item": f'{row["item"]} — {row["spec"]}',
                    "qty": kit_qty(row["qty"], {}), "unit": row["unit"], "for": "spare kit"})
    return out

class PlanIn(BaseModel):
    day: dt.date

@app.post("/dispatch/plan")
async def post_plan(p: PlanIn):
    async with (await pool()).acquire() as c:
        async with c.transaction():
            return await plan_day(c, p.day)

@app.get("/dispatch/runsheet/{crew_id}")
async def runsheet(crew_id: str, day: dt.date):
    """What the crew PWA downloads (and caches for offline): stops + routes + load list,
    enriched with live WO status, member/site details, checklist and required captures."""
    async with (await pool()).acquire() as c:
        row = await c.fetchrow("SELECT plan FROM dispatch_plans WHERE day=$1 AND crew_id=$2", day, crew_id)
        if not row:
            raise HTTPException(404, "no plan for this crew/day")
        plan = json.loads(row["plan"]) if isinstance(row["plan"], str) else row["plan"]
        for s in plan["stops"]:
            d = await c.fetchrow("""SELECT w.status, w.captures, w.priority, w.note, w.blocked_reason,
                    sa.address, cu.name AS member, cu.phone, p.name AS plan_name, si.radius_username
                FROM work_orders w LEFT JOIN service_addresses sa ON sa.address_id=w.address_id
                LEFT JOIN service_instances si ON si.service_id=w.service_id
                LEFT JOIN customers cu ON cu.customer_id=si.customer_id
                LEFT JOIN subscriptions sb ON sb.sub_id=si.sub_id LEFT JOIN plans p ON p.plan_id=sb.plan_id
                WHERE w.wo_id=$1""", s["wo_id"])
            s.update({k: d[k] for k in ("status", "priority", "note", "blocked_reason", "address", "member",
                                        "phone", "plan_name", "radius_username")})
            s["captures"] = json.loads(d["captures"]) if isinstance(d["captures"], str) else (d["captures"] or {})
            s["checklist"] = CHECKLISTS.get(s["wo_type"], ["Work the job", "Record as-built"])
            s["required_captures"] = REQUIRED_CAPTURES.get(s["wo_type"], ["asbuilt_ref"])
        return plan

@app.get("/dispatch/board")
async def board(day: Optional[dt.date] = None):
    async with (await pool()).acquire() as c:
        rows = await c.fetch("SELECT * FROM dispatch_board WHERE ($1::date IS NULL OR scheduled_for=$1 OR scheduled_for IS NULL) "
                             "ORDER BY scheduled_for NULLS LAST, assigned_crew, route_seq, priority", day)
    return [dict(r) for r in rows]

# ---------------------------------------------------------------- urgent insertion (outage -> boat)
async def _crew_now(c, st: dict, now: dt.datetime) -> tuple[tuple, dt.datetime, int]:
    """Where a crew is and when it's free: finishing its in-progress job, else at its last
    completed stop, else at the yard. Returns (pos, free_at, seq_to_insert_after)."""
    plan = st["plan"]
    for s in plan["stops"]:
        stt = await c.fetchval("SELECT status FROM work_orders WHERE wo_id=$1", s["wo_id"])
        s["_status"] = stt
    inprog = [s for s in plan["stops"] if s["_status"] == "in_progress"]
    done = [s for s in plan["stops"] if s["_status"] in ("closed", "asbuilt")]
    if inprog:
        s = inprog[0]
        return (s["lon"], s["lat"]), max(now, dt.datetime.fromisoformat(s["finish"])), s["seq"]
    if done:
        s = done[-1]
        return (s["lon"], s["lat"]), now, s["seq"]
    return (plan["yard"]["lon"], plan["yard"]["lat"]), now, 0

@app.post("/outages/{outage_id}/dispatch")
async def outage_dispatch(outage_id: int, now: Optional[dt.datetime] = None):
    """NOC opens an outage -> P1 repair WO at the root node -> inserted as the NEXT stop of
    whichever crew can get there first today (weather/skills/vehicle permitting)."""
    now = (now or dt.datetime.now(TZ)).astimezone(TZ)
    day = now.date()
    async with (await pool()).acquire() as c:
        async with c.transaction():
            o = await c.fetchrow("SELECT * FROM outages WHERE outage_id=$1 FOR UPDATE", outage_id)
            if not o or not o["root_node"]:
                raise HTTPException(400, "outage with a root node required")
            if o["wo_id"]:
                return {"ok": True, "wo_id": o["wo_id"], "already_dispatched": True}
            wo_id = await create_wo(c, WOIn(wo_type="repair", node_id=o["root_node"], priority="P1",
                                            outage_id=outage_id, note=f"Outage #{outage_id}: "
                                            f"{o['impacted_customers'] or '?'} members impacted"))
            await c.execute("UPDATE outages SET wo_id=$2 WHERE outage_id=$1", outage_id, wo_id)
            await release_wo(c, wo_id)
            wo = await _wo(c, wo_id)
            weather = await weather_gate(c, day)
            tieup, _ = await boat_tieup_min(c)
            best = None
            for r in await c.fetch("SELECT crew_id, plan FROM dispatch_plans WHERE day=$1 FOR UPDATE", day):
                plan = json.loads(r["plan"]) if isinstance(r["plan"], str) else r["plan"]
                cv = await c.fetchrow("SELECT * FROM crews WHERE crew_id=$1", r["crew_id"])
                cvd = {**dict(cv), "vehicle": plan["vehicle"]}
                if not _eligible(wo, cvd, weather):
                    continue
                pos, free_at, after = await _crew_now(c, {"plan": plan}, now)
                go = leg(pos, (wo["lon"], wo["lat"]), plan["vehicle"], tieup)
                if not go:
                    continue
                arrive = free_at + dt.timedelta(minutes=go["minutes"])
                if best is None or arrive < best[0]:
                    best = (arrive, r["crew_id"], plan, go, after)
            if not best:
                return {"ok": True, "wo_id": wo_id, "assigned": False,
                        "reason": "no crew can reach it today (weather, skills or vehicle) — escalate"}
            arrive, cid, plan, go, after = best
            finish = arrive + dt.timedelta(hours=float(wo["est_hours"]))
            new = {"seq": after + 1, "wo_id": wo_id, "wo_type": "repair", "priority": "P1", "lon": wo["lon"],
                   "lat": wo["lat"], "eta": arrive.isoformat(), "finish": finish.isoformat(), "travel": go}
            stops = [s for s in plan["stops"] if s["seq"] <= after] + [new] + \
                    [dict(s, seq=s["seq"] + 1) for s in plan["stops"] if s["seq"] > after]
            # shift everything after the insert by the time it costs
            t, pos = finish, (wo["lon"], wo["lat"])
            for s in stops[after + 1:]:
                if s.get("_status") in ("closed", "asbuilt", "in_progress"):
                    continue
                lg = leg(pos, (s["lon"], s["lat"]), plan["vehicle"], tieup) or {"minutes": s["travel"]["minutes"]}
                eta = t + dt.timedelta(minutes=lg["minutes"])
                dur = dt.datetime.fromisoformat(s["finish"]) - dt.datetime.fromisoformat(s["eta"])
                s["eta"], s["finish"] = eta.isoformat(), (eta + dur).isoformat()
                t, pos = eta + dur, (s["lon"], s["lat"])
            for s in stops:
                s.pop("_status", None)
                await c.execute("UPDATE work_orders SET route_seq=$2, eta=$3 WHERE wo_id=$1",
                                s["wo_id"], s["seq"], dt.datetime.fromisoformat(s["eta"]))
            plan["stops"] = stops
            await c.execute("""UPDATE work_orders SET status='scheduled', scheduled_for=$2, assigned_crew=$3,
                vehicle_id=$4, travel_mode=$5, travel_min=$6 WHERE wo_id=$1""",
                wo_id, day, cid, plan["vehicle"]["vehicle_id"], go["mode"], round(go["minutes"], 1))
            await c.execute("UPDATE dispatch_plans SET plan=$3::jsonb WHERE day=$1 AND crew_id=$2",
                            day, cid, json.dumps(plan, default=str))
            await _event(c, wo_id, "scheduled", detail={"crew": cid, "urgent_insert_after": after,
                                                        "eta": arrive.isoformat(), "mode": go["mode"]})
    return {"ok": True, "wo_id": wo_id, "assigned": True, "crew_id": cid, "mode": go["mode"],
            "eta": arrive.isoformat(), "travel_min": round(go["minutes"], 1), "next_stop": after + 1}

# ---------------------------------------------------------------- field actions (PWA, offline)
class FieldAction(BaseModel):
    client_action_id: str
    wo_id: int
    kind: Literal["arrived", "started", "capture", "completed", "cant_complete", "departed", "note"]
    at: Optional[dt.datetime] = None
    data: dict = {}
    lon: Optional[float] = None
    lat: Optional[float] = None
    crew_id: Optional[str] = None

class FieldBatch(BaseModel):
    actions: list[FieldAction]

async def _complete(c, wo: dict, a: FieldAction) -> dict:
    missing = [k for k in REQUIRED_CAPTURES.get(wo["wo_type"], []) if not str(wo["captures"].get(k, "")).strip()]
    if missing:
        return {"ok": False, "error": "missing captures", "missing": missing}
    at = a.at or dt.datetime.now(TZ)
    day = at.astimezone(TZ).date()
    # consume reserved stock + capitalize the serialized CPE/ONT as an asset (doc 09)
    items = await c.fetch("SELECT * FROM work_order_items WHERE wo_id=$1 AND NOT consumed", wo["wo_id"])
    for it in items:
        if it["stocked"] and float(it["qty_reserved"]) > 0:
            await c.execute("""UPDATE inventory SET qty_on_hand = qty_on_hand - $2, qty_reserved = qty_reserved - $2
                WHERE sku=$1 AND location='warehouse'""", it["sku"], it["qty_reserved"])
        await c.execute("UPDATE work_order_items SET consumed=true WHERE id=$1", it["id"])
    serial = wo["captures"].get("device_mac") or wo["captures"].get("ont_serial")
    result = {"ok": True}
    if serial:
        dev = next((it for it in items if re.search(r"\b(CPE|ONT)\b", it["spec"] or "")), None)
        if dev:
            await c.execute("""INSERT INTO assets (sku, serial, node_id, cost_basis_usd, in_service_date, asset_class)
                VALUES ($1,$2,$3,$4,$5,'cpe')""", dev["sku"], serial, wo["node_id"], dev["unit_cost_usd"], day)
    if wo["service_id"]:
        si = await c.fetchrow("SELECT * FROM service_instances WHERE service_id=$1 FOR UPDATE", wo["service_id"])
        # the CPE on the dock may not be the one registered at signup: re-key RADIUS to what was installed
        if si["access"] == "ipoe_mac" and wo["captures"].get("device_mac"):
            mac = norm_mac(wo["captures"]["device_mac"])
            if mac != si["radius_username"]:
                if await c.fetchval("SELECT 1 FROM service_instances WHERE radius_username=$1", mac):
                    return {"ok": False, "error": f"device {mac} is registered to another service"}
                await c.execute("UPDATE service_instances SET radius_username=$2, radius_password=$2 WHERE service_id=$1",
                                si["service_id"], mac)
                result["radius_rekeyed_to"] = mac
        elif si["access"] == "ont_serial" and wo["captures"].get("ont_serial"):
            ser = wo["captures"]["ont_serial"].strip().upper()
            if ser != si["radius_username"]:
                await c.execute("UPDATE service_instances SET radius_username=$2, radius_password=$2 WHERE service_id=$1",
                                si["service_id"], ser)
                result["radius_rekeyed_to"] = ser
        kind = {"cpe-wireless-nlos": "nlos", "cpe-wireless-ptmp": "ptmp"}.get(wo["wo_type"], "ont")
        cpe_id = await c.fetchval("""INSERT INTO cpe (address_id, kind, serial, node_id, status)
            VALUES ($1,$2,$3,$4,'active') RETURNING cpe_id""", wo["address_id"], kind, serial, wo["node_id"])
        await c.execute("UPDATE service_instances SET cpe_id=$2 WHERE service_id=$1", si["service_id"], cpe_id)
        result["activation"] = await activate_service(c, si["service_id"], day)   # -> first bill (doc 22)
    if wo["outage_id"]:
        await c.execute("UPDATE outages SET status='resolved', resolved_at=$2 WHERE outage_id=$1", wo["outage_id"], at)
    closes = wo["wo_type"] in ("survey", "repair") or wo["wo_type"] in INSTALL_BY_MEDIUM.values() \
        or wo["wo_type"] == "drop-ug-fiber"
    await c.execute("""UPDATE work_orders SET status=$2::wo_status, completed_at=$3,
        closed_at=CASE WHEN $2='closed' THEN $3 ELSE closed_at END WHERE wo_id=$1""",
        wo["wo_id"], "closed" if closes else "asbuilt", at)
    result["status"] = "closed" if closes else "asbuilt"
    return result

@app.post("/field/actions")
async def field_actions(b: FieldBatch):
    """Offline-first sync: the PWA queues actions with client ids and replays them here.
    Replays are idempotent; each action is applied in its own transaction, in order."""
    results = []
    async with (await pool()).acquire() as c:
        for a in b.actions:
            if await c.fetchval("SELECT 1 FROM wo_events WHERE client_action_id=$1", a.client_action_id):
                results.append({"client_action_id": a.client_action_id, "ok": True, "duplicate": True}); continue
            try:
                async with c.transaction():
                    wo = await _wo(c, a.wo_id, lock=True)
                    vk = await c.fetchval("SELECT kind FROM vehicles WHERE vehicle_id=$1", wo["vehicle_id"]) if wo["vehicle_id"] else None
                    res = {"ok": True}
                    if a.kind == "started":
                        await c.execute("UPDATE work_orders SET status='in_progress', started_at=COALESCE($2, now()) WHERE wo_id=$1",
                                        a.wo_id, a.at)
                    elif a.kind == "capture":
                        await c.execute("UPDATE work_orders SET captures = captures || $2::jsonb WHERE wo_id=$1",
                                        a.wo_id, json.dumps(a.data))
                    elif a.kind == "completed":
                        wo = await _wo(c, a.wo_id, lock=True)
                        res = await _complete(c, wo, a)
                        if not res["ok"]:
                            raise _Reject(res)
                    elif a.kind == "cant_complete":
                        await c.execute("""UPDATE work_orders SET status='released', blocked_reason=NULL, assigned_crew=NULL,
                            vehicle_id=NULL, route_seq=NULL, eta=NULL, scheduled_for=NULL,
                            note=COALESCE(note || E'\\n','') || $2 WHERE wo_id=$1""",
                            a.wo_id, "could not complete: " + str(a.data.get("reason", "unspecified")))
                    await _event(c, a.wo_id, "captured" if a.kind == "capture" else a.kind, actor=a.crew_id,
                                 detail=a.data, client_action_id=a.client_action_id, vehicle_kind=vk,
                                 at=a.at, lon=a.lon, lat=a.lat)
                results.append({"client_action_id": a.client_action_id, **res})
            except _Reject as r:
                results.append({"client_action_id": a.client_action_id, **r.res})
    return {"results": results}

class _Reject(Exception):
    def __init__(self, res): self.res = res

@app.get("/metrics/turnaround")
async def turnaround():
    async with (await pool()).acquire() as c:
        rows = await c.fetch("SELECT * FROM turnaround_stats")
        tie, src = await boat_tieup_min(c)
    return {"by_vehicle": [dict(r) for r in rows], "planner_boat_tieup_min": tie, "source": src}

# ---------------------------------------------------------------- crew PWA
@app.get("/lake.geojson")
async def lake():
    return FileResponse(LAKE, media_type="application/geo+json")

if os.path.isdir(PWA_DIR):
    app.mount("/crew", StaticFiles(directory=PWA_DIR, html=True), name="crew")

@app.get("/")
async def root():
    return RedirectResponse("/crew/")
