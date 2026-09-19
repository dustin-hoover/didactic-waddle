# Premises-Passed Analysis — Results

**Generated from live public GIS data** (not estimates). Reproduce with
[`../../software/gis/setup_and_run.sh`](../../software/gis/setup_and_run.sh).

## Data sources
- **Beaver Lake shoreline:** USGS NHD large-scale waterbody (`GNIS_NAME='Beaver Lake'`).
  Validated: **28,026 acres / ~445 mi shoreline** (matches known ~28,000 ac / ~449 mi).
- **Premises:** Arkansas GIS Office statewide CAMA parcel centroids
  (`FEATURESERVICES/Planning_Cadastre/FeatureServer/0`), which cover Benton, Washington,
  Carroll, and Madison counties uniformly. **A parcel with `impvalue > 0` (improvement
  value) = a structure = a premises.**
- Cross-check available from Benton County's own address points + tax parcels
  (`gis.bentonvillear.com/.../Benton_County_Data`).

## Headline result

> **9,571 improved (structure-bearing) premises within 1 mile of Beaver Lake shoreline;
> 6,144 within a quarter-mile.** This replaces the ~9,000 planning estimate — and lands
> almost exactly on it.

| Distance band | Improved premises | Notes |
|---------------|-------------------|-------|
| 0–0.25 mi (shoreline) | 6,144 | Core lakeshore market |
| 0.25–0.5 mi | 1,544 | |
| 0.5–1 mi | 1,883 | |
| **Total ≤ 1 mi** | **9,571** | Whole-lake addressable envelope |

## By county (≤1 mi)

| County | Premises ≤1mi | Vacant parcels ≤1mi |
|--------|---------------|---------------------|
| Benton | 7,190 | 6,933 |
| Washington | 1,318 | 925 |
| Carroll | 1,044 | 1,063 |
| Madison | 19 | 35 |

Benton is ~75% of the market (central + north shoreline) — confirming the phasing that
starts in the Benton central corridor. The upper White River arm clips **Madison
County** (not previously listed) — a small addition to the service map.

## By property type (≤1 mi, improved)
- **Residential (RI): 7,831** — the core market.
- **Ag-residential (AI): 1,361** — rural homes on acreage.
- **Commercial (CI/CG/CR/CP): ~162** — marinas, resorts, businesses (≈ the ~120 est.).
- Residential multi (RM): 134.

## Value profile (shoreline ≤0.25 mi, improved)
- Median total value **$410,288**; average **$484,351**.
- **2,417 premises over $500k; 522 over $1M.**
- Confirms the premium-service thesis: this is a high-value, reliability-sensitive market.

## Opportunity signal
- **5,943 vacant parcels within 0.25 mi** = future growth and host-node candidate land.

## Files
| File | Contents |
|------|----------|
| `premises_passed_by_county.csv` | County × distance-band premises + vacant parcels |
| `premises_by_parceltype.csv` | Premises by CAMA parcel type |
| `premises_value_profile.csv` | Value stats by distance band |
| `premises_points.csv` | 9,571 improved premises (parcelid, owner, county, type, value, lat/lon) — reusable for Felt/GIS/signup seeding + host-node targeting |
| `beaver_lake_premises_map.svg` | Map of premises over the lake, by distance band |

## Caveats
- CAMA parcel data vintage varies by county; treat counts as planning-grade current,
  not survey-exact. Refine with Benton County E-911 address points (342k statewide) for
  sub-address/unit precision where needed.
- "Premises" here = improved parcels; multi-unit buildings count as one parcel. Marinas
  with many slips are one parcel but a larger opportunity — handle as business accounts.
- Per-**zone** breakdown requires drawing zone polygons (next step); this pass reports
  by county + distance band, and the points file supports any later zone bucketing.
