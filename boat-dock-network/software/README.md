# DockOS — Software Platform

The system that runs Boat Dock Network. See
[`../docs/14-software-architecture.md`](../docs/14-software-architecture.md) for the
full design. This directory holds the plan, schema, and (as we build) the code.

## Status: foundation laid, apps to be built

This is a **scaffold + plan**, not yet a running application. The architecture,
database schema, and build order are defined so each app can be built as a discrete
Claude Code task on a solid base.

## Contents

| Path | What |
|------|------|
| `db/schema.sql` | PostGIS core schema (v0.1) — the single source of truth |
| `gis/` | GIS analysis scripts (LOS/link-budget) — to be built |
| (future) `api/` | FastAPI backend modules (gis, crm-signup, billing, dispatch, ...) |
| (future) `web/` | React + MapLibre admin + customer/host portals |
| (future) `field/` | Offline-first boat-dispatch PWA |

## Recommended stack (cost-effective, open-source-first)

- **DB:** PostgreSQL + PostGIS (+ TimescaleDB for telemetry)
- **Backend:** Python + FastAPI (GeoAlchemy2, geopandas, rasterio, shapely)
- **Frontend:** React + MapLibre GL; tiles via pg_tileserv/Martin
- **Field:** React PWA, offline tiles + IndexedDB sync
- **Billing:** Stripe + custom BSS logic
- **NOC:** LibreNMS/Zabbix + Prometheus + Grafana; vendor controllers
- **AI:** Claude API (compliance advisor, RFQ/grant/support assist)
- **Hosting:** 1–2 VPS + object storage, Docker Compose → k3s

## Quick start (once building)

```bash
# 1. Spin up PostGIS
docker run -d --name dockos-db -e POSTGRES_PASSWORD=dev -p 5432:5432 postgis/postgis:16-3.4

# 2. Load the schema
psql "postgresql://postgres:dev@localhost:5432/postgres" -f db/schema.sql

# 3. Seed reference data from the BOM + GIS templates
#    (loader script to be added: data/bom/*.csv -> skus + work_order_items templates)
```

## Build order (each = one Claude Code task; see docs/15)

1. PostGIS + schema + import Benton/Washington parcels, USACE shoreline, LiDAR.
2. GIS analysis: serviceability, LOS/link budget, passings (feeds pro forma + grants).
3. Signup/serviceability portal (start pre-sales).
4. Work-order + BOM + procurement engine.
5. Boat-dispatch PWA.
6. Billing + provisioning + RADIUS.
7. NOC monitoring + outage management.
8. Compliance advisor + grants scanner (Claude).

Say which one to build next and I'll implement it against this schema.
