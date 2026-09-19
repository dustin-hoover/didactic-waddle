# Planning Assumptions

Every number in this plan that isn't a hard fact is an assumption listed here, with a
note on how to replace it with reality. Treat this as the master "dials" file: change
a value here and note which documents/models depend on it.

## Geography & market (verify against parcel/GIS data)

| Key | Assumed value | Source of truth to replace it |
|-----|---------------|-------------------------------|
| Shoreline length | ~449 miles | USACE Beaver Lake data / GIS shoreline measure |
| Surface area | ~28,000 acres (normal pool) | USACE |
| Normal pool elevation | ~1,120 ft MSL | USACE (matters for antenna heights over water) |
| Addressable premises (whole-lake) | 9,000 *(estimate)* | Benton + Washington + Carroll parcel + address points within service buffer |
| Share within 1 mi of shoreline | ~60% | GIS buffer analysis |
| Year-round vs seasonal mix | 55% / 45% | County parcel homestead flags + occupancy |
| Businesses/marinas/resorts | ~120 *(estimate)* | County commercial parcels + marina list |

## Adoption & revenue (verify against pilot results)

| Key | Assumed value | Notes |
|-----|---------------|-------|
| Steady-state take rate | 42% of passings | High for rural because of poor incumbent options + host-node incentive |
| Residential ARPU | $89/mo blended | Across tiers below |
| Business ARPU | $260/mo blended | SMB + marina/resort |
| Host-node discount | $25–$100/mo or free tier | Depends on node tier hosted |
| Install fee (waived w/ contract) | $99 residential / $299 business | Often promoted to $0 |
| Monthly churn | 1.3% | Low: little competition |

## Cost & build (verify against vendor quotes + survey)

| Key | Assumed value | Notes |
|-----|---------------|-------|
| Fiber aerial (make-ready + strand + cable) | $18k–$40k/mile *(estimate)* | Ozark terrain, pole make-ready heavy |
| Fiber underground (bury/bore) | $30k–$120k/mile *(estimate)* | Rock is the wildcard; micro-trench cheaper |
| FTTH drop (aerial) | $600–$1,400 ea *(estimate)* | Labor + ONT + drop |
| FTTH drop (underground) | $1,200–$3,500 ea *(estimate)* | Bore/bury dependent |
| Fixed-wireless CPE install | $350–$900 ea *(estimate)* | Radio + labor; non-LOS radio costs more |
| Dock aggregation node | $18k–$45k ea *(estimate)* | Cabinet, power, radios, backhaul, solar option |
| Licensed microwave lake-crossing hop (pair) | $30k–$90k *(estimate)* | Radios, dishes, licensing, tower/mast, install |
| Blended cost per premise passed | $1,800 *(estimate)* | Hybrid lowers this vs all-fiber |
| Cost per premise connected (on top) | $900 *(estimate)* | Drop + CPE + activation |

## Internet transit / backhaul

| Key | Assumed value | Notes |
|-----|---------------|-------|
| Wholesale transit/transport | $0.30–$1.50 per Mbps/mo *(estimate)*, tiered | From your two on-ramp providers; big drop at 10G+ |
| Initial committed capacity | 2 × 10 Gbps (diverse) | Scales to N×100G |
| Oversubscription (residential gig) | 20:1 to 40:1 planning | Tune from real utilization |

## Money & financing

| Key | Assumed value | Notes |
|-----|---------------|-------|
| Blended cost of capital | 5% *(target)* | RUS/CoBank/RTFC low-interest telecom debt + grants reduce this |
| Grant coverage of eligible CapEx | 30–70% | BEAD/USDA/state; highly location-dependent |
| Discount rate for NPV | 10% | |

## How to firm these up (in order of leverage)

1. **Run the GIS buffer + parcel join** (see `docs/05-gis-plan.md`) to get real
   premises-passed and density per zone. This replaces the single biggest guess.
2. **Get two transit quotes** from your identified on-ramps at 10G and 100G.
3. **Walk/boat one pilot cove**, price a real BOM from `data/bom/`, and record actuals.
4. Feed actuals back into `data/financial/` and re-run the pro forma.
