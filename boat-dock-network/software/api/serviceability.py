#!/usr/bin/env python3
"""Boat Dock Network — production serviceability + signup API (FastAPI + PostGIS).

The public launch backend behind the signup portal. Unlike the org-internal artifact
prototype, this accepts anonymous public submissions, geocodes addresses, and does
true per-point serviceability against PostGIS. Deploy behind the DockOS stack
(docs/14). This file is the reference implementation / contract.

Run (dev):
  pip install fastapi uvicorn asyncpg pydantic
  DATABASE_URL=postgresql://dockos:dockos@localhost:5432/dockos \
    uvicorn serviceability:app --reload

Endpoints:
  GET  /serviceability?lat=&lon=        -> zone, phase, medium, LOS%, nearest node
  GET  /serviceability?address=         -> geocode then as above (geocoder pluggable)
  POST /signup                          -> persist a lead/reservation/member/founding/host
  GET  /zones/demand                    -> per-zone demand rollup (for build gating)
"""
from __future__ import annotations
import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import asyncpg

app = FastAPI(title="Boat Dock Network API")
DB = os.environ.get("DATABASE_URL", "postgresql://dockos:dockos@localhost:5432/dockos")
_pool: Optional[asyncpg.Pool] = None

async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB, min_size=1, max_size=8)
    return _pool

def medium_for(pct_los: Optional[float]) -> str:
    if pct_los is None: return "fiber or fixed wireless (confirmed at survey)"
    if pct_los >= 80:   return "mostly fixed wireless, fiber where dense"
    if pct_los >= 60:   return "a mix of fixed wireless and fiber/relay"
    return "fiber and relays for many homes (tree-heavy)"

PHASE_LABEL = {1: "Building now", 2: "Next up", 3: "Planned", 4: "Future (demand-gated)"}

class Serviceable(BaseModel):
    serviceable: bool
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    county: Optional[str] = None
    phase: Optional[int] = None
    phase_label: Optional[str] = None
    likely_medium: Optional[str] = None
    pct_los: Optional[float] = None
    nearest_node: Optional[int] = None

async def _geocode(address: str) -> Optional[tuple[float, float]]:
    """Pluggable geocoder. Wire to a licensed geocoder or the county E-911
    address points (loaded into PostGIS) for production. Returns (lon, lat)."""
    async with (await pool()).acquire() as c:
        row = await c.fetchrow(
            "SELECT ST_X(geom) lon, ST_Y(geom) lat FROM service_addresses "
            "WHERE address ILIKE $1 ORDER BY address LIMIT 1", f"%{address}%")
    return (row["lon"], row["lat"]) if row else None

@app.get("/serviceability", response_model=Serviceable)
async def serviceability(lat: Optional[float] = None, lon: Optional[float] = None,
                         address: Optional[str] = None):
    if address and (lat is None or lon is None):
        g = await _geocode(address)
        if not g:
            return Serviceable(serviceable=False)
        lon, lat = g
    if lat is None or lon is None:
        raise HTTPException(400, "provide lat/lon or address")
    async with (await pool()).acquire() as c:
        # containing zone (or nearest if the pin is just off a zone polygon)
        z = await c.fetchrow("""
            SELECT z.zone_id, z.name, zr.county, zr.phase, zr.pct_los,
                   ST_Contains(z.geom, ST_SetSRID(ST_Point($1,$2),4326)) AS inside
            FROM zones z JOIN zone_rank zr ON zr.zone_id=z.zone_id
            ORDER BY (NOT ST_Contains(z.geom, ST_SetSRID(ST_Point($1,$2),4326))),
                     z.geom <-> ST_SetSRID(ST_Point($1,$2),4326)
            LIMIT 1""", lon, lat)
        if not z:
            return Serviceable(serviceable=False)
        node = await c.fetchrow("""
            SELECT node_id FROM nodes
            ORDER BY geom <-> ST_SetSRID(ST_Point($1,$2),4326) LIMIT 1""", lon, lat)
    return Serviceable(
        serviceable=True, zone_id=z["zone_id"], zone_name=z["name"], county=z["county"],
        phase=z["phase"], phase_label=PHASE_LABEL.get(z["phase"]),
        likely_medium=medium_for(z["pct_los"]), pct_los=z["pct_los"],
        nearest_node=int(node["node_id"].split("-")[-1]) if node else None)

class SignupIn(BaseModel):
    zone_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = None
    name: str
    email: EmailStr
    phone: Optional[str] = None
    plan_id: Optional[str] = None
    want_reservation: bool = False
    want_member: bool = False
    want_founding: bool = False
    want_host: bool = False
    consent: bool = False   # explicit consent to store contact info

@app.post("/signup")
async def signup(s: SignupIn):
    if not s.consent:
        raise HTTPException(400, "consent required to store contact information")
    async with (await pool()).acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO signups (zone_id,address,geom,name,email,phone,plan_id,
                want_reservation,want_member,want_founding,want_host,consent_ts,source)
            VALUES ($1,$2, CASE WHEN $3::float8 IS NULL THEN NULL
                        ELSE ST_SetSRID(ST_Point($3,$4),4326) END,
                    $5,$6,$7,$8,$9,$10,$11,$12, now(), 'portal')
            RETURNING signup_id""",
            s.zone_id, s.address, s.lon, s.lat, s.name, s.email, s.phone, s.plan_id,
            s.want_reservation, s.want_member, s.want_founding, s.want_host)
    return {"ok": True, "signup_id": row["signup_id"]}

@app.get("/zones/demand")
async def zones_demand():
    async with (await pool()).acquire() as c:
        rows = await c.fetch("SELECT * FROM zone_demand ORDER BY reservations DESC")
    return [dict(r) for r in rows]
