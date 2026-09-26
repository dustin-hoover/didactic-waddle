# 23 — Dispatch, Work Orders & the Crew App (DockOS steps 4–5)

> The operating engine behind doc 07: every job — install, repair, survey, build — is a work
> order with a BOM kit, reserved stock, a crew, a vehicle, a route and a run sheet; the crew
> closes it from the dock in an offline-first app, and closing an install starts the member's
> billing. Tested end-to-end (43 checks, §6). **It also tests the "lake is the road" premise
> against real roads — and refines it (§2).**

## 1. What was built
| Piece | File | What it does |
|-------|------|--------------|
| Water routing | `software/dispatch/waterroute.py` | NHD lake → 50 m navigable grid (islands as holes; area checks out at ~28,300 acres), no-wake shoreline band, per-boat-class Dijkstra, line-of-sight smoothed tracks |
| Road routing | `software/dispatch/roadroute.py` | OpenStreetMap → contracted graph (56,602 junctions, 8,368 km), posted/class speeds → real drive times (`data/gis/outputs/road_graph.npz`) |
| Boat-vs-truck analysis | `software/dispatch/mode_analysis.py` | Every premises, both modes, per zone, with sensitivity → `dispatch_mode_by_zone.csv`, `dispatch_mode_summary.json` |
| Schema | `software/db/dispatch_schema.sql` | yards, vehicles, crews, crew-days, WO extensions, field events, day plans, weather calls, measured turnaround views |
| Work-order engine + dispatch API | `software/api/dispatch.py` | install WOs from sign-ups, BOM → reservation → PO, permits gate, NWS weather gate, day planner, P1 outage insertion, field actions, completion → billing |
| Crew app (PWA) | `software/dispatch_pwa/` | offline-first run sheet, water-route chart, checklists, readings, barcode scan, outbox; served at `/crew` |
| Preview | artifact "DockOS Crew" | the app with a real planned day, demo mode |

## 2. Boat or truck? Measured, not assumed
Doc 07 says *"the lake is the road."* With a flat road-detour factor the truck beat the boat
to **every** premises — so the model was wrong, not necessarily the premise. Rebuilt with the
**real OSM road network** and the **real lake**, from two candidate yards (NW / east, doc 20),
center-console boat (25 kn, 5 kn no-wake within 50 m of shore) vs truck:

- **Yard → job: the boat is faster for 23.8% of premises (2,281)**, saving a median 14 min where it wins.
- **The deciding variable is dock turnaround** (tie up, unload, walk up — per stop), not boat speed or yard count:

| Dock turnaround per stop | Boat faster (yard → job) | Boat faster (dock-to-dock hops in a zone) |
|---|---|---|
| 15 min | 24% | ~21% |
| 10 min | 37% | — |
| 8 min | 44% | — |
| **5 min** | **52%** | **69%** |

  Adding a third (south) yard moves the number only ~3 points.

**Per zone** (15-min turnaround, conservative):

| Zone | Premises | Near water (≤600 m) | Boat faster from yard | Hop: truck / boat (median min) | Mode |
|------|---------:|------:|------:|------|------|
| Z-05 Lost Bridge Village | 596 | 94% | 90% | 17 / 24 | **boat-first** |
| Z-16 Township of Prairie | 234 | 76% | 65% | 30 / 33 | **boat-first** |
| Z-14 Huffman Ford | 280 | 84% | 64% | 18 / 24 | **boat-first** |
| Z-13 Vista Shores | 285 | 60% | 60% | 16 / 26 | **boat-first** |
| Z-08 Ventris Public Use Area | 510 | 88% | 44% | 37 / 26 | **boat-first** |
| Z-11 Puckett | 432 | 51% | 47% | 18 / 30 | mixed |
| Z-09 Mundell | 462 | 100% | 37% | 15 / 27 | mixed |
| Z-17 Rambo Riviera | 228 | 69% | 36% | 18 / 25 | mixed |
| Z-04 Creech | 851 | 64% | 13% | 25 / 32 | mixed |
| Z-18 Cook Ford | 179 | 23% | 0% | 33 / 31 | mixed |
| Z-06 Township of Walnut | 538 | 95% | 14% | 17 / 28 | truck-first |
| Z-03 Monte Ne | 935 | 62% | 13% | 23 / 28 | truck-first |
| Z-02 Prairie Creek | 1,134 | 45% | 11% | 19 / 26 | truck-first |
| Z-12 Beaver Dam | 405 | 83% | 11% | 18 / 37 | truck-first |
| Z-10 War Eagle Cove | 440 | 62% | 10% | 17 / 26 | truck-first |
| Z-01 Beaver Shores | 1,272 | 83% | 4% | 17 / 28 | truck-first |
| Z-07 Blue Springs Village | 531 | 73% | 0% | 17 / 26 | truck-first |
| Z-15 Blue Springs Use Area | 259 | 54% | 0% | 19 / 26 | truck-first |

Totals: **boat-first 1,905 premises · mixed 2,152 · truck-first 5,514.**

**What this means for the plan (recommendation):**
1. **Run a hybrid fleet, boat-native where it earns it.** Boats own the five boat-first arms
   (mostly the northeast arms across from the NW yard), all **waterside work** (dock-mounted
   CPE and nodes, T2 dock-node builds, lake crossings, subaqueous cable, shoreline host sites),
   and repairs where the water route is shorter. Service trucks are the primary install/repair
   vehicle in the eight truck-first zones, which include the three largest.
2. **Engineer dock turnaround down to ≤ 8 min** — it's worth ~20 points of boat share. That means
   quick-tie dock hardware, pre-kitted install bags, dock access captured at survey, and a
   two-person crew where one stays with the boat. Every stop in the crew app records arrive /
   start / complete / depart, so this is **measured**, and once there are ≥ 5 samples the
   planner uses the measured median instead of the default (tested).
3. **Re-cut the fleet line in the model** (doc 09 `COST_FLEET_START`) toward trucks + fewer,
   better-equipped boats — a decision for you; I haven't changed the model.

Caveats: the truck model uses OSM (driveways and private lake roads may be missing; speeds are
planning averages); only 12 public ramps are in OSM (the USACE ramp inventory should replace
them); the lake is the simplified NHD shoreline at normal pool.

## 3. Work orders: sign-up to first bill
```
member signs up (billing, doc 22) ─▶ install WO (kit by medium: nLOS / PtMP / fiber drop)
  ─release─▶ BOM expanded from data/bom kits ─▶ warehouse reserved ─▶ shortfall = draft PO (doc 11)
  ─plan─▶ crew + boat/truck + ETA + route  ─▶ crew app: tie up → start → readings → complete
  ─▶ stock consumed, CPE capitalized (doc 09), CPE record, RADIUS re-keyed to the unit installed
  ─▶ billing.activate_service(): service live, prorated FIRST BILL (doc 22)  ─▶ WO closed
```
- **Build WOs** (dock nodes, relays, crossings, cable) are held in `permitting` until the doc
  12/19 checklist clears (USACE, ROW, FAA), then planned as 6-hour build days.
- **Parts:** a shortfall blocks scheduling and raises a draft PO to the kit's vendor; receiving
  stock re-reserves and unblocks in priority order.
- **Readings required to close:** wireless — CPE MAC, speed down/up, RSSI; fiber — ONT serial,
  light level, speed; repair — what fixed it; survey — dock access + GPS.
- **"Can't complete"** (no dock access, member away, weather, parts) sends the job back to
  dispatch with the reason.

## 4. Dispatch
- **Weather gate:** NWS hourly forecast for mid-lake (Tulsa office grid), working hours only:
  per boat class, go if max sustained wind ≤ class limit (jon 15, pontoon 20, center console
  25 mph) and no thunderstorms at ≥ 30% chance. Dispatcher overrides win (lightning on radar).
  No-go boats stay home; road-capable jobs go by truck; boat-only jobs wait.
- **Day planner:** jobs by priority (P1 outage/business same-day → P4 builds); each goes to the
  eligible crew (skills, vehicle, heavy-lift, weather) where it adds the **least travel**,
  capped by shift length including the trip home — so a boat keeps working its arm and a
  truck its roads. Urgent jobs go to whoever gets there first.
- **Outage → boat:** the NOC opens an outage; a P1 repair WO is created at the root node and
  inserted as the **next stop** of the crew that can reach it first; the rest of that run re-times.
- **Run sheet:** ordered stops with ETAs (lake time), mode and minutes, water-route tracks,
  dock-to-site walk, member/plan details, checklist, required readings, and a **load list**
  (job BOMs + the standard spare kit every vessel/truck carries, doc 10 §5).

## 5. The crew app (DockOS Crew)
Phone-first, glove-friendly (56 px actions), light/dark. **Offline on the lake:** the run
sheet and lake chart are cached by a service worker; every tap is queued with a client id and
replayed when there's signal — the server applies each once (replays are no-ops). Scans CPE /
ONT labels with the camera where the device supports it; shows GPS on the chart.
Preview (demo mode, real planned day): the "DockOS Crew" artifact.

## 6. Verified (`software/tests/test_dispatch_e2e.py`, 43 checks)
Real API server, real lake + OSM routing, PostGIS, billing, and the **app driven in headless
Chromium at phone width**: four sign-ups → WOs with the right kits → reservation, CPE shortfall
→ Tarana PO → receive → unblocked; permits gate; a no-go day (boats home, boat-only build
waits, installs by truck until the shift is full); a go day (Lost Bridge by boat, Beaver
Shores by truck, dock-node build by pontoon); an outage inserted as next stop; the crew ties up,
starts, enters readings, completes → **service live and first bill issued**, RADIUS re-keyed to
the CPE actually installed, stock 7 → 6, asset + CPE records; an offline tap queued and
replayed; duplicate replay ignored; completion refused without readings; send-back; outage
resolved; measured turnaround (9.0 min) adopted by the next day's plan. Billing's own 46-check
RADIUS suite still passes after the shared-activation refactor.

Building it surfaced and fixed: **15 malformed BOM kit rows** (unquoted commas — no software
had parsed them yet), and a crew-app bug where tapping *Complete* right after typing a reading
was swallowed by a re-render.

## 7. Next steps
- Load the USACE ramp/park inventory and real yard sites (doc 20) into `yards`; re-run §2.
- Vendor adapters for the chosen OLT / radios (provisioning, doc 22) and the NOC feed that
  opens outages automatically (DockOS step 7).
- Dispatcher board UI (the `dispatch_board` view exists) and member appointment windows.
