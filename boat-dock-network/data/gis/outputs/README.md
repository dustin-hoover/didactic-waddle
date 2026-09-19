# GIS Analysis — Results (premises, zones, node siting)

**Generated from live public GIS data** (not estimates). Reproduce end-to-end with
[`../../software/gis/setup_and_run.sh`](../../software/gis/setup_and_run.sh) then
[`node_siting_and_map.sh`](../../software/gis/node_siting_and_map.sh).

**Interactive map:** `beaver_lake_network_map.html` (self-contained; open in any
browser) — also published as an artifact for inline viewing.

## Data sources
- **Shoreline:** USGS NHD large-scale waterbody (`GNIS_NAME='Beaver Lake'`). Validated
  **28,026 acres / ~445 mi** (matches known figures).
- **Premises:** AR GIS Office statewide CAMA parcel centroids — a parcel with
  `impvalue > 0` (improvement value) = a structure = a premises. Covers Benton,
  Washington, Carroll, Madison uniformly.
- **Elevation / viewshed:** USGS 3DEP (~30 m), warped to UTM 15N.
- **Place names (zone labels):** USGS GNIS via AR GIS.

---

## 1. Premises passed

> **9,571 improved premises within 1 mile of shoreline; 6,144 within ¼ mile.**

| Band | Premises | | County | Premises ≤1mi | Vacant ≤1mi |
|------|----------|-|--------|---------------|-------------|
| 0–0.25 mi | 6,144 | | Benton | 7,190 | 6,933 |
| 0.25–0.5 mi | 1,544 | | Washington | 1,318 | 925 |
| 0.5–1 mi | 1,883 | | Carroll | 1,044 | 1,063 |
| **≤1 mi total** | **9,571** | | Madison | 19 | 35 |

- Types: **7,831 residential + 1,361 ag-residential + ~162 commercial** (+134 multi).
- Shoreline (≤¼mi) value: **median $410k, 2,417 over $500k, 522 over $1M**.
- **5,943 vacant shoreline parcels** = growth + host-node land.

## 2. Service zones (18)

K-means clustering of premises → 18 zones, named from nearest GNIS place, with
concave-hull polygons. See `zones_summary.csv` / `zone_build_order.csv`.

Largest: Beaver Shores (1,272), Prairie Creek (1,134, 58 commercial — marina hub),
Monte Ne (935), Creech (851), Lost Bridge Village (596).

## 3. Candidate node siting (viewshed)

For each zone, the 6 highest near-shore parcels were tested with `gdal_viewshed`
(10 m mast, 4 m CPE, 8 km range). Then a **greedy set-cover** picked the node build
order. See `proposed_nodes.csv` / `.geojson` and `node_coverage_curve.csv`.

> **8,279 of 9,571 premises (87%) are wireless line-of-sight-reachable** from shoreline
> high points. The other ~13% sit in RF shadow → relays or fiber.

Node coverage curve (greedy):

| Nodes built | Premises covered | % of all 9,571 |
|-------------|------------------|----------------|
| 1 | 1,695 | 18% |
| 3 | 4,043 | 42% |
| 6 | 5,706 | 60% |
| 10 | 6,742 | 70% |
| 30 | 8,050 | 84% |

A handful of dominant sites (in Ventris, Creech, Vista Shores, Blue Springs, Beaver
Shores) blanket the majority — that's the backbone build order.

> **Caveat:** 3DEP is bare-earth (no tree canopy), so LOS here is an optimistic upper
> bound. Real foliage reduces clean LOS — which is exactly why the design uses
> non-line-of-sight radios (Tarana) and concentrates fiber/relays in the shadow set.
> Re-run with the AR LiDAR **DSM** (surface + canopy) to model foliage explicitly.

## 4. Build order (per zone)

Composite score (0.40 premises + 0.20 value + 0.25 %LOS + 0.15 commercial) → phases.
Full table in `zone_build_order.csv`.

- **Phase 1:** Prairie Creek, Beaver Shores, Monte Ne (dense central Benton corridor).
- **Phase 2:** Creech, Mundell, Lost Bridge Village, Walnut, Ventris.
- **Phase 3–4:** remaining Benton/Carroll/Washington zones, demand-gated.

## Files
| File | Contents |
|------|----------|
| `beaver_lake_network_map.html` | **Interactive map** — zones, premises (LOS vs shadow), nodes, spine |
| `spine.geojson` / `spine_edges.csv` | Backbone spine: 41 hops (25 over-water), 140 km, $1.37M; over-water long hops = licensed microwave |
| `premises_passed_by_county.csv` | County × distance-band premises + vacant |
| `premises_by_parceltype.csv` | Premises by CAMA type |
| `premises_value_profile.csv` | Value stats by band |
| `premises_points.csv` | 9,571 premises (owner, county, type, value, lat/lon) — host-node targeting + signup seeding |
| `zones_summary.csv` | 18 zones: premises, value, commercial, centroid |
| `zone_build_order.csv` | Zones ranked + phased for build |
| `proposed_nodes.csv` / `.geojson` | 30 ranked candidate nodes: coverage, elevation, owner, site type |
| `node_coverage_curve.csv` | Cumulative premises covered vs nodes built |
| `zones.geojson` / `premises.geojson` / `lake.geojson` | Map layers |

## Caveats
- CAMA vintage varies by county; counts are planning-grade current. Refine with Benton
  E-911 address points for sub-address precision.
- Marinas count as one parcel but are larger opportunities → business accounts.
- Node siting uses bare-earth DEM (see §3 caveat); DSM refinement is a next step.
