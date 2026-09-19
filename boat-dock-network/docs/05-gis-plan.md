# 05 — GIS / OSP Plan

GIS is the spine of the *company*, not just the map. Every serviceability decision,
work order, BOM, outage impact, and financial model traces back to spatial data. This
plan defines the data sources, the data model, the analyses, and the tooling — all
open-source-first to keep cost near zero.

## 1. Tooling (cost-effective)

| Need | Tool | Cost |
|------|------|------|
| Spatial database (source of truth) | **PostgreSQL + PostGIS** | Free |
| Desktop design/editing | **QGIS** | Free |
| Web map / field map | **MapLibre GL JS** (+ vector tiles via `pg_tileserv`/Martin) | Free |
| Raster/LiDAR analysis (LOS, viewshed) | **GDAL, rasterio, GRASS, WhiteboxTools** | Free |
| Elevation/LOS scripting | **Python (geopandas, rasterio, shapely, pyproj)** | Free |
| Collaboration / quick shared maps | **Felt** (this project has a Felt connector) | Freemium |
| Optional commercial OSP | Sonar/Vetro/IQGeo | $$ (defer) |

We can start entirely on free tools and one small VPS. Felt is available in this
workspace and is great for fast, shareable planning maps and stakeholder/grant visuals.

## 2. Authoritative data sources

| Layer | Source | Use |
|-------|--------|-----|
| Parcels + owners | **Benton County** and **Washington County** GIS/assessor (Carroll Co. for east shore) | Premises passed, host-node targeting, easements |
| Address points | County / E-911 datasets | Service addresses, serviceability |
| Shoreline & lake boundary | **USACE** Beaver Lake data / normal-pool contour | Zone edges, node siting, permitting |
| Elevation / LiDAR (DEM/DSM) | **Arkansas GIS Office (GeoStor)** statewide LiDAR | LOS, viewshed, Fresnel clearance, foliage (DSM−DEM) |
| Aerial imagery / NAIP | USDA NAIP / state | Tree cover, dock locations, planning |
| Roads / ROW | County + ARDOT | Fiber routes, permits, crossings |
| Utility poles | Ozarks Electric / Carroll Electric / SWEPCO (via attachment process) | Aerial fiber, make-ready |
| Floodplain / environmental | FEMA, ADEQ, Beaver Water District source-water zones | Permitting, avoidance |

> You said we have access to **Benton County geodata** — that's the primary parcel/
> address layer. We'll add Washington and Carroll similarly.

## 3. Core spatial data model (feeds DockOS, doc 14)

Tables (PostGIS geometries in EPSG:6543 / NAD83(2011) Arkansas North ft, or 4326 for
web). This is the OSP inventory:

- **zones** — service zone polygons (`zone_id`, name, phase, status).
- **service_addresses** — every addressable premises (point): address, parcel_id,
  owner, occupancy (year-round/seasonal), building type, serviceability status,
  chosen medium (fiber/wireless), assigned node, demand flag (pre-sale), customer_id.
- **nodes** — T0–T3 sites (point): `node_id`, tier, zone, status
  (candidate/permitted/built/live), power type, host_property flag, elevation,
  as-built ref.
- **node_equipment** — modules installed at a node (radio/OLT/switch/UPS/solar): make,
  model, serial, install_date, WO ref (the "swappable module" record).
- **links** — spine/backhaul/access links (line): endpoints, band, licensed?, capacity,
  LOS status, fresnel_ok, fade_margin_db, path_calc ref.
- **fiber_cables / fiber_splices / fiber_strands** — OSP fiber records (line/point):
  route, count, splice closures, strand assignments.
- **poles** — attachment points: owner, make-ready status, permit ref.
- **drops** — premises drops (line): type (aerial/underground), length, WO ref.
- **cpe** — customer premise equipment: type, serial, node/OLT port, customer_id.
- **permits** — USACE/county/ARDOT/pole permits (see doc 12): type, status, geometry,
  linked node/link/drop.
- **work_orders** — spatially-anchored jobs (see doc 14) linked to any feature.

Full DDL lives in `software/db/schema.sql`. Field templates in `data/gis/`.

## 4. Key analyses (the GIS "products")

### 4a. Serviceability & premises-passed
Buffer the shoreline / built plant, join to address points + parcels → count and
classify every premises. Output: premises-passed per zone (replaces the biggest
assumption) and a per-address serviceability status.

### 4b. Line-of-sight, Fresnel & link budget (the RF brain)
For each candidate link (node↔node, node↔premises):
1. Sample the **DSM** (surface incl. trees) along the path.
2. Check clearance vs. the **Fresnel zone + earth curvature**; for over-water hops,
   evaluate at **min and max lake pool** and flag the reflection point for **space
   diversity**.
3. Estimate **foliage loss** from `DSM − DEM` (canopy height) where the path grazes
   trees; decide LOS vs nLOS (Tarana) vs blocked.
4. Compute **link budget + fade margin**; store on the `links`/candidate record.

This is scripted in Python (`software/gis/los.py`) and re-runnable as new nodes are
proposed — it directly powers the per-address medium-selection rule (doc 03 §5).

### 4c. Viewshed for node siting
Run viewsheds from candidate high points/host offers to rank which sites cover the
most premises per dollar. Output: ranked candidate `nodes`.

### 4d. Build-backlog ranking
Combine premises-passed × demand (pre-sales) × (1/cost-per-passing) to rank what to
build next. Output: the prioritized construction queue (feeds doc 15 + finance).

### 4e. Outage impact
Given a down device, walk the topology (`links`/`nodes`/`cpe`) to list affected
customers and draw the outage polygon → feeds the NOC + boat dispatch (doc 14).

## 5. Boat-native GIS features (your requirement)

- **Water-routing layer:** navigable-water polygon + hazard points (shallows, stumps,
  no-wake, ramps) so the dispatch app routes techs *by water*, with launch-ramp
  origins and dock destinations.
- **Dock-access attributes** on `service_addresses`/`nodes`: dock present? depth?
  boat-reachable? preferred launch ramp? — captured during survey.
- **Offline tiles** for the field PWA (coverage is spotty mid-lake).

## 6. Workflow (design → build → as-built)

1. **Plan** in QGIS/PostGIS: draw zones, propose nodes/links, run LOS/viewshed.
2. **Validate**: link budgets pass, permits identified (auto-checklist from doc 12
   rules), host-node offers matched.
3. **Release to build**: create work orders + BOM (doc 10/14).
4. **As-built**: field PWA captures GPS, serials, photos → updates PostGIS; node marked
   live only when its record is complete.
5. **Operate**: monitoring + outage impact read from the same model.

## 7. Deliverables checklist (what "GIS is done for v1" means)

Status as of the first analysis run (see `data/gis/outputs/` and the reproducible
scripts `software/gis/setup_and_run.sh` + `node_siting_and_map.sh`):

- [x] PostGIS up; schema loaded (`software/db/schema.sql`).
- [x] Benton + Washington + Carroll (+ Madison) parcels imported (AR GIS CAMA).
- [x] Shoreline imported (USGS NHD); **3DEP DEM** imported for viewshed.
- [x] Zones derived (18) via clustering; **premises-passed computed (9,571 ≤1mi)**.
- [x] Candidate nodes (30) selected + **viewshed-ranked** with greedy set-cover.
- [x] Ranked build backlog (`zone_build_order.csv`) — feeds the pro forma next.
- [x] Interactive web map published (`beaver_lake_network_map.html` + artifact).
- [ ] **Refine LOS with AR LiDAR DSM** (canopy) — bare-earth DEM is optimistic.
- [ ] Benton E-911 address points for sub-address precision.
- [ ] Full link budgets (fade margin) per spine hop; Felt map for stakeholders.
