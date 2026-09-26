# GIS Layer Dictionary

Layers in the DockOS PostGIS database (see `software/db/schema.sql`) and the source
data to load into them. SRID 4326 for storage/web; reproject to a projected CRS
(e.g., EPSG:6543 NAD83(2011) Arkansas North (ftUS)) for accurate distance/area.

## Operational layers (we own/maintain — in schema)

| Layer / table | Geometry | Purpose |
|---------------|----------|---------|
| `zones` | MultiPolygon | Service zones (see `zones.csv`) |
| `nodes` | Point | T0–T3 sites (`node_inventory_template.csv`) |
| `links` | LineString | Spine/backhaul/access links + path calc |
| `service_addresses` | Point | Every premises (`service_address_template.csv`) |
| `fiber_cables` | LineString | OSP fiber routes |
| `drops` | LineString | Premises drops |
| `poles` | Point | Attachment points + make-ready |
| `cpe` | (attr) | Customer premise equipment |
| `permits` | Geometry | Permit footprints (USACE/ROW/etc.) |
| `work_orders` | Geometry | Spatially-anchored jobs |
| `outages` | MultiPolygon | Impact polygons |

## Reference layers (import from authoritative sources — read-mostly)

| Layer | Source | Use |
|-------|--------|-----|
| Parcels + owners | Benton / Washington / Carroll county GIS | Premises, host-node targeting |
| Address points (E-911) | County | Service addresses |
| Lake shoreline / normal pool | USACE Beaver Lake | Zone edges, siting, permitting |
| DEM (bare earth) | AR GIS Office (GeoStor) LiDAR | Terrain, earth-curvature |
| DSM (surface w/ canopy) | AR GIS Office LiDAR | LOS, foliage (DSM−DEM), Fresnel |
| Canopy height | derived (DSM−DEM) | nLOS vs blocked decision |
| NAIP imagery | USDA | Tree cover, docks, planning |
| Roads / ROW | County + ARDOT | Fiber routes, permits |
| Floodplain | FEMA | Avoidance |
| Source-water protection | Beaver Water District / ADEQ | Environmental care |
| Navigable water + hazards | USACE + survey | Boat routing (dispatch) |

## Derived analysis products (generated — doc 05 §4)

| Product | From | Feeds |
|---------|------|-------|
| Premises-passed per zone | shoreline/plant buffer ∩ addresses | pro forma, grants |
| Serviceability + medium per address | LOS + density rules | signup portal |
| LOS / link budget per candidate link | DSM sampling + Fresnel | node/link design |
| Viewshed per candidate node | DEM/DSM | node siting rank |
| Build backlog ranking | passings × demand ÷ cost | construction queue |
| Outage impact polygon | topology walk | NOC + dispatch |

## CRS & conventions
- Store: EPSG:4326. Measure/analyze: EPSG:6543 (or UTM 15N, EPSG:26915).
- Node naming: `BDN-{zone}-{tier}-{seq}`.
- Elevations in ft MSL; note Beaver Lake normal pool ~1,120 ft when computing over-water
  clearances at min/max pool.
