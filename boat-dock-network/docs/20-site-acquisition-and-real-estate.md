# 20 — Site Acquisition & Real Estate (Comm Huts, Head-Ends, Node Sites)

> Where the network physically lives: the **comm huts / head-end POPs** (T0), the core/
> aggregation node sites (T1/T2), and the tower/relay sites. The core question here —
> **should the cooperative *own* land (fee simple) for a comm hut, or lease/easement it?**
> Answer up front, then the framework, siting criteria, money model, and legal wrapper.
> Not legal/financial advice — run purchases past real-estate + co-op counsel; title to
> the co-op entity only **after formation** (doc 19).

## 1. Recommendation (decision)
**Own the two head-end POPs in fee simple; lease or take recorded easements for
everything else.**

| Site tier | What it is | Own / Lease / Easement | Why |
|-----------|-----------|------------------------|-----|
| **T0 head-end POP × 2** (comm huts) | Border router, ASN/BGP edge, transit handoff, DWDM/OLT, UPS+generator, DNS/CGNAT (doc 03) | **Fee-simple purchase** | Permanent control of the network's heart; **collateral** for co-op debt; no eviction/escalation risk; can co-locate tower + ops/boat base |
| **T1 core / aggregation** | Ring core nodes, key ridge sites | **Long-term ground lease** (10–25 yr, renewals) or fee-simple if it doubles as a hut | Control without full capital; buy only if strategic |
| **T2/T3 edge nodes** (~30 sites) | Dishes/cabinets on high points & member docks | **Recorded easement / member-host** | Cheap, fast; the **host-a-node WAKE 1.5× bonus (doc 16)** already incentivizes members to host |

**Why own the head-ends specifically:** they are single points the whole lake depends on,
they carry the most expensive gear, and — critically for a grant-free, debt-financed co-op
(doc 13) — **owned real estate + facilities are the collateral** that unlocks CoBank / RTFC
/ RUS lending on good terms. Leasing the heart of the network puts it at a landlord's mercy.

## 2. The boat-served synergy (why a lakeside parcel is worth more to us)
A single owned lakeside parcel can be **three assets at once**:
1. a **T0 head-end comm hut** (if fiber-reachable / short lateral),
2. the **marine ops base** — boat slip, dock, staging yard, gear/warehouse for the
   boat-delivered install & repair model (doc 07/08), and
3. a **member-facing showcase / host-node** site.

That triple-use is unusual and it changes the buy-vs-lease math: the parcel earns its
keep across network, operations, and membership — not just as a rack location. This is the
"OzarksGo-adjacent lakeside parcel" idea in doc 04 §3, made concrete.

## 3. What makes a good comm-hut parcel (siting criteria)
Score candidates on:
- **Fiber reach** — on-net or a short lateral to DSN/OzarksGo/Cox (doc 17); lateral cost
  can dominate. This is the #1 driver.
- **Diverse routing** — POP A and POP B parcels must sit on **physically separate fiber
  paths** (doc 17 / `path_diversity_checklist.md`), ideally opposite sides of the lake.
- **Commercial power + backup room** — reliable grid drop plus space for generator/propane
  and fuel; solar/battery option for resilience.
- **Elevation / LOS** — height for microwave lake-crossings and to seed wireless zones
  (validated against the LiDAR DSM, doc 07/18).
- **Dual access** — **all-weather road** access **and** **boat/dock** access (this network
  is serviced by boat); a slip or buildable shoreline is a plus.
- **Buildable & clean** — zoned/permittable for a utility/comm structure, **out of the
  floodplain**, no wetlands blocker, clean title, reasonable soils for a slab/tower.
- **Not in restricted USACE shoreline** unless a permit/easement is in hand (see §5).

A GIS pass can rank parcels by fiber proximity + elevation + road/shore access + zoning +
flood zone — same machinery as the node-siting model (doc 05/07); add a `parcels` layer
with ownership/price when we have it.

## 4. Money model — buy vs. lease (planning-grade)
| | **Own (fee simple)** | **Ground lease** | **Easement / member-host** |
|---|---|---|---|
| Upfront | Land ~$50k–250k/parcel (higher lakeside) + hut/site build | Low (first/last, deposit) | Very low (recording, small stipend) |
| Recurring | Property tax, insurance, maint. | Rent (escalators) | ~$0 / WAKE 1.5× (doc 16) |
| Balance sheet | **Asset + collateral** (lowers cost of capital) | Expense | Expense/none |
| Control | **Permanent** | Term-limited, renewal risk | Limited to the granted use |
| Best for | 2 head-ends (+ ops base) | T1 core sites | ~30 edge nodes |

- **Pro-forma hook (doc 09):** carry a **land-acquisition CapEx line for the 2 head-ends**
  (+ optional ops-base parcel); model the rest as site-lease OpEx. Owned facilities also
  raise the **collateralizable asset base** in the financing model (doc 13). Fold the
  chosen figures into `docs/ASSUMPTIONS.md` and re-run `software/finance/model.py`.
- **Rule of thumb:** buy when the site is strategic, hard to replace, or doubles as the ops
  base; lease/easement when it's one of many and swappable.

## 5. Legal wrapper (per purchase)
Title to the **cooperative entity** (so this follows formation, doc 19). With counsel:
- **Title search + title insurance**; **ALTA/boundary survey**.
- **Zoning / conditional-use permit** for a utility/communications structure + tower;
  local building permits for the shelter/slab (doc 12/19).
- **FAA** review on tower height (30–45 m nodes) per site (doc 19 §6).
- **USACE (Little Rock District)** — Beaver Lake is a **federal Corps reservoir**; any
  shoreline structure, dock/slip, or lake cable crossing needs **Shoreline Management
  permits/easements** (doc 19 §6). Central to the lakeside-parcel idea — start early.
- **Phase I Environmental Site Assessment** — usually required by the lender before a
  real-estate-backed loan; also protects the co-op.
- **Floodplain check** (FEMA) + elevation of critical gear; property + equipment insurance.
- **Recorded easements** for access, power, and fiber laterals crossing neighboring land.

## 6. Sequencing
1. **Form the entity** (doc 19) — only the co-op can hold title/sign.
2. **Finalize the two head-end sites** (doc 17 needs them for the RFQ POP addresses) using
   the §3 criteria; decide own-vs-lease per §1.
3. **Line up financing** (doc 13) — owned parcels become collateral; get the Phase I / title
   / survey a lender will want.
4. **Close + permit** (USACE / zoning / building) — long leads; start at entity formation.
5. **Build the hut**, land transit (doc 17), stand up the head-end, and — if lakeside —
   the boat/ops base with it.

## 7. Open decisions for you
- Are your **two known internet-buy locations** on land you can **own**, or only lease? If
  lease-only, evaluate buying an adjacent/nearby parcel per §2–§3.
- Do we want **one lakeside parcel to double as head-end + boat/ops base**, or keep the ops
  base separate from the POP? (Combining saves capital and shortens dispatch.)
- Buy-vs-lease dollar figures to fold into the model (`ASSUMPTIONS.md`).

---
_Generated by [Claude Code](https://claude.ai/code)_
