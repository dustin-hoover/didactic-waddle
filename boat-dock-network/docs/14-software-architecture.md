# 14 — Software Architecture: DockOS

DockOS is the platform that **runs the company** — one integrated system for GIS/OSP,
serviceability + signup, billing, NOC/monitoring, outage management, boat dispatch,
procurement, and Arkansas/county compliance. Design priority: **most cost-effective**,
so it's **open-source-first**, runs small at pilot scale, and scales without a rewrite.

## 1. Design principles

1. **One source of truth = PostGIS.** The network, the customers, the money, and the
   map are the same database. No drift between "the plan" and "the operation."
2. **Open-source-first.** Avoid per-subscriber SaaS fees that crush a rural ISP's
   margins. Buy only what's cheaper than building (payments, mapping tiles at scale).
3. **API-first modular monolith → services later.** Start as one deployable app with
   clean modules; split into services only when scale demands. Cheapest path that
   stays clean.
4. **Boat-native.** The field app works offline, routes by water, and closes work
   orders with GPS/serials/photos.
5. **Claude-in-the-loop.** Use the Claude API for the compliance advisor, procurement
   RFQ drafting, grant scanning, and support triage — leverage, not headcount.

## 2. Recommended stack (cost-effective)

| Concern | Choice | Why |
|---------|--------|-----|
| Database | **PostgreSQL + PostGIS + TimescaleDB** | Spatial + relational + time-series (telemetry) in one |
| Backend | **Python + FastAPI** (SQLAlchemy/GeoAlchemy2) | Best GIS ecosystem (geopandas, rasterio, shapely) for LOS/viewshed |
| Frontend/admin | **React + MapLibre GL** | Free maps, no per-map fees |
| Field app | **PWA (React)** with offline tiles + IndexedDB sync | Installable on rugged tablets/phones; works mid-lake |
| Vector tiles | **pg_tileserv / Martin** | Serve PostGIS straight to the map |
| Auth | **Keycloak** or Auth.js | Staff + customer portals |
| Billing/payments | **Stripe** (custom BSS logic on top) | Cheap, reliable; avoid heavy ISP-BSS license fees at start |
| Monitoring (NOC) | **LibreNMS/Zabbix + Prometheus + Grafana**; vendor controllers (UISP, cnMaestro, Tarana) | Free, proven |
| Queue/jobs | **Redis + RQ/Celery** | LOS jobs, billing runs, alerts |
| Hosting | 1–2 VPS (e.g., Hetzner) + object storage, Docker Compose → k3s later | Pennies vs. hyperscaler at this scale |
| AI | **Claude API** | Compliance advisor, RFQ/grant/support assist |

> Alternative: a TypeScript-everywhere stack (NestJS + Prisma). We recommend Python for
> the GIS/analytics core because the LOS/viewshed/link-budget work leans on the Python
> geospatial stack; the frontend is React either way.

## 3. Modules (the modular monolith)

```
DockOS
├── gis/            OSP inventory + spatial analysis (LOS, viewshed, serviceability)
├── crm-signup/     serviceability lookup, plan select, pre-sales, host-node apps
├── billing/        subscribers, plans, invoices, payments, host-node credits
├── provisioning/   RADIUS/AAA, CPE/ONT activation, rate limits (billing<->network sync)
├── noc/            device inventory, monitoring ingest, alerts, status page
├── outage/         event->topology->impacted customers->tickets->comms
├── dispatch/       work orders, scheduling, boat routing, field PWA sync
├── procurement/    BOM expansion, inventory, POs, receiving, assets
├── compliance/     AR/Benton/Washington rules + Claude advisor + permit checklists
├── grants/         pipeline tracker + NOFO scanner (Claude/Routine)
└── core/           auth, users, audit, notifications, reporting/dashboards
```

## 4. Data model (anchors — full DDL in `software/db/schema.sql`)

- **GIS/OSP:** `zones`, `service_addresses`, `nodes`, `node_equipment`, `links`,
  `fiber_cables`, `fiber_splices`, `poles`, `drops`, `cpe`, `permits` (doc 05).
- **Customers/billing:** `customers`, `subscriptions`, `plans`, `invoices`, `payments`,
  `host_node_agreements`, `credits`.
- **Ops:** `work_orders`, `work_order_items` (BOM lines), `dispatch_assignments`,
  `field_visits`, `outages`, `tickets`.
- **Procurement:** `vendors`, `skus`, `inventory`, `purchase_orders`, `po_lines`,
  `receipts`, `assets`.
- **NOC:** `devices`, `device_metrics` (Timescale hypertable), `alerts`.
- **Compliance/grants:** `permit_rules`, `grant_opportunities`, `grant_tasks`.

The BOM CSVs in `data/bom/` seed `skus` + `work_order_items` templates. The GIS
templates in `data/gis/` define the spatial tables.

## 5. Key workflows in software

- **Serviceability + signup:** address → PostGIS lookup → medium-selection rule
  (doc 03 §5) → plan → schedule install (creates a work order) or add to demand backlog.
- **Host-node application:** owner applies → GIS scores the site (viewshed) → offer →
  agreement (access/power/easement + discount) → node candidate.
- **Provision ↔ bill sync:** activating service creates subscription + RADIUS entry +
  rate limit; suspension for non-pay flips network state. One truth.
- **Outage → boat dispatch:** device down → impacted-customer set + polygon → auto
  ticket + status-page + SMS/email → dispatch nearest qualified crew (water-routed)
  with the right BOM spare kit → as-built closes it.
- **WO → procurement → asset:** release WO → expand BOM → reserve/PO shortfall →
  receive → consume on install → asset + CapEx captured (doc 11).
- **Compliance gate:** WO cannot be released to build until its auto-generated permit
  checklist (compliance module + Claude) is satisfied (doc 12).

## 6. The Arkansas / county compliance "brain"

- A **rules base** (`permit_rules`) encodes doc 12: which permits attach to which
  work-order type, geometry (e.g., in USACE shoreline buffer? in ARDOT ROW? which pole
  owner?), and thresholds (FAA/ASR height, BABA for grant-funded).
- The **Claude-API advisor** reads a work order + its geometry + the rules and produces:
  a permit checklist, required forms, responsible owner, and flags (USACE touchpoint,
  grant/BABA condition, 811 needed). It **drafts** applications and blocks release until
  permits are logged. Deterministic rules do the gating; Claude does the drafting and
  the "did we miss anything?" review. It never bypasses a human sign-off.

## 7. Boat-dispatch specifics

- **Water routing:** route over the navigable-water layer (doc 05 §5) from nearest
  launch ramp to the dock/site; account for no-wake zones and hazards.
- **Offline-first PWA:** cached tiles + queued edits; syncs when back in coverage.
- **Field capture:** GPS-stamped photos, serial scans, BOM consumption, customer
  sign-off signature; enforces as-built completeness before "live."

## 8. Build order (cheapest path to value)

1. **PostGIS + schema** + import Benton/Washington parcels, USACE shoreline, LiDAR.
2. **GIS analysis** (serviceability, LOS/link budget, passings) — unlocks the pro forma
   and grant maps immediately.
3. **Signup/serviceability portal** — start pre-sales before building.
4. **Work-order + BOM + procurement** — run the pilot build cleanly.
5. **Field dispatch PWA** — boat-native ops.
6. **Billing + provisioning + RADIUS** — turn on paying customers. ✅ **Built** — doc 22
   (RADIUS authorize tables are views over billing state; 46-check e2e vs live FreeRADIUS).
7. **NOC monitoring + outage** — operate reliably.
8. **Compliance advisor + grants scanner** — scale the paperwork with AI, not hires.

Each is a self-contained Claude Code task; see doc 15.

## 9. Security, backups, resilience

- Segmented management network; least-privilege; audited actions.
- Nightly encrypted backups (DB + object storage), tested restores.
- IaC + Docker Compose (→ k3s) so the whole platform is reproducible.
- Status page + monitoring independent of the primary hosting where feasible.
