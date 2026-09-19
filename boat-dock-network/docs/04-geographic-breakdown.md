# 04 — Geographic Breakdown

Beaver Lake is a dendritic (branching) reservoir on the White River in NW Arkansas,
operated by the USACE Little Rock District — roughly 28,000 acres of surface water and
~449 miles of shoreline across **Benton, Washington, and Carroll** counties. Its shape
(long main channel plus many coves, fingers, and named creek arms) is exactly why a
zoned, boat-served, hybrid network fits.

> **UPDATE — this is now done with real data.** The GIS analysis (doc 05) produced
> **18 data-derived service zones** with real premises counts, values, and a build
> order, plus **30 viewshed-ranked candidate node sites**. See
> [`../data/gis/outputs/README.md`](../data/gis/outputs/README.md), the CSVs there
> (`zones_summary.csv`, `zone_build_order.csv`, `proposed_nodes.csv`), and the
> interactive map (`beaver_lake_network_map.html`). The named planning zones below are
> retained as regional context; the operational zones are Z-01…Z-18 in the outputs.
>
> Headline: **9,571 premises ≤1mi**; build **Phase 1 = Prairie Creek, Beaver Shores,
> Monte Ne**; **6 nodes cover 60% of premises, 30 cover 84%**; **~13% of premises are
> in RF shadow** and need relays/fiber.

## 1. Zoning method

We cut the shoreline into **service zones** where each zone:
- is anchored by a high, boat-reachable point suitable for a **T2 dock node**;
- has RF/terrain coherence (a node can plausibly see most of the zone, or a relay can);
- maps to real communities/marinas so marketing and host-node recruiting are local;
- rolls up to a **build phase** (doc 15) by density and pre-sales demand.

Each zone gets an ID like `Z-RB` (Rocky Branch) used across GIS, BOM, and finance.

## 2. Planning zones (anchor-based)

Anchors are recognizable Beaver Lake public areas/marinas; actual zone extents will be
drawn in GIS. Grouped by region:

### North / Dam region (near the dam, Carroll/Benton line)
| Zone | Anchor | Notes |
|------|--------|-------|
| Z-DAM | Dam Site area | Near the dam; potential T1 core + on-ramp landing candidate |
| Z-STK | Starkey | Marina/park anchor |
| Z-INC | Indian Creek | Cove cluster |

### Central / Rogers–Lowell region (Benton Co, densest demand)
| Zone | Anchor | Notes |
|------|--------|-------|
| Z-PC  | Prairie Creek | Major marina/park; high demand, strong FTTH candidate |
| Z-RB  | Rocky Branch | Marina/park; large residential shoreline |
| Z-HC  | Hickory Creek | Marina/park; residential coves |
| Z-LB  | Lost Bridge | Marina; north-shore residential |
| Z-HB  | Horseshoe Bend | Residential-heavy area |

### South / War Eagle & upper arms (Washington/Benton)
| Zone | Anchor | Notes |
|------|--------|-------|
| Z-WE  | War Eagle arm | Long finger; relay-heavy |
| Z-WR  | White River arm (upper) | Sparse; wireless-first |
| Z-CC  | Coves/creeks (misc. upper) | Long tail; demand-driven |

### East / Eureka Springs side (Carroll)
| Zone | Anchor | Notes |
|------|--------|-------|
| Z-BT  | Beaver Town / Ventris | East-shore residential/resort |
| Z-ES  | Eureka Springs approach | Tourism/resort demand |

> This is ~13 planning zones as a starting frame. GIS will likely refine to 15–25
> operational zones. Add/rename freely in `data/gis/zones.csv`.

## 3. On-ramp landing strategy (your two internet buys)

You've identified two dedicated-internet locations. In the architecture they become
**T0 head-end POPs** and should ideally be:
- **on diverse sides of the lake** (e.g., one near the Rogers/Lowell/central corridor
  where regional fiber is rich, one near the dam/Eureka side), so the ring is fed from
  two directions;
- close to a spine entry point (a T1 core node) to minimize expensive first-mile.

If neither of your two locations is ideally placed to anchor the ring, that's the
scenario where **buying a small lakeside parcel near a fiber-rich provider** (your
"OzarksGo-adjacent" idea) pays off — it becomes a permanent T0/T1 asset and a
host-node showcase. Evaluate this as a real-estate + network decision jointly (doc 09
carries a line item for it).

## 4. Phasing by geography (summary; full plan in doc 15)

1. **Pilot** — one or two central, high-demand zones with the cleanest economics
   (e.g., Z-PC / Z-RB) **plus one lake crossing** to prove the over-water spine.
2. **Region** — complete the central Benton corridor (highest density/return).
3. **Ring closure** — build the spine all the way around so redundancy is real.
4. **Long tail** — upper arms and sparse coves, demand-driven (pre-sales gate).

## 5. Terrain & RF notes per region (to refine with LiDAR)

- **Central coves (Prairie Creek/Rocky Branch/Hickory Creek):** highest premises
  density, best FTTH candidates, good ridge points for T1/T2.
- **Long fingers (War Eagle, upper White River):** relay-heavy, wireless-first,
  over-water shortcuts valuable.
- **Dam/Eureka side:** resort/tourism demand, elevation good for core nodes.
- **Everywhere:** heavy tree cover ⇒ favor nLOS radios (Tarana) + fiber in density.

## 6. What GIS will produce for this doc (doc 05 deliverables)

- Exact zone polygons + premises-passed per zone (parcel/address join).
- Ranked candidate node sites per zone (high points, host-node offers).
- LOS/viewshed + link-budget per candidate link (over-water clearances included).
- A build backlog ranked by demand density and cost-per-passing.
