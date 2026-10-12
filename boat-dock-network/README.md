# Boat Dock Network (BDN)

**A hybrid fiber + fixed-wireless ISP serving the entire perimeter of Beaver Lake, Arkansas — designed, built, serviced, and repaired by boat.**

> Mission: give every home, business, marina, and resort around Beaver Lake the best
> internet available, using a physically adaptable outside-plant design and a
> software platform that runs the whole operation cost-effectively. Property owners
> who host a network node get a discount on service.

---

## 0. Read this first

This repository is both the **business plan** and the **engineering + software plan**
for the company. It is organized so a founder, an investor, a field tech, a GIS
analyst, and a software engineer can each find what they need.

Everything here is a **planning-grade v1**. Numbers labeled *(estimate)* are
planning assumptions, not quotes — they exist to size the business and are meant to
be replaced with real vendor quotes, real parcel counts, and real survey data as we
go. Every assumption is listed in [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md).

### The three big ideas

1. **Hybrid, adaptable outside plant.** Fiber where density and terrain make it
   cheap; licensed/unlicensed fixed wireless (including non-line-of-sight radios that
   punch through Ozark tree cover) where fiber is uneconomic. We cross the lake
   *wirelessly* on a redundant licensed-microwave spine, and land drops from boat
   docks — aerial, underground, or over-water — to the premises.
2. **Boat-native operations.** The lake is the road. Field techs are specialized and
   dispatched by water. Every node is sited, powered, and cabled to be reachable and
   serviceable from a boat.
3. **A software platform that runs the company.** One integrated system — code-named
   **DockOS** — handles GIS/OSP records, serviceability + signup, billing, the NOC,
   outage management, boat dispatch, procurement, and Arkansas/Benton/Washington
   regulatory decisions. Built open-source-first to keep OpEx low.

---

## 1. Document map

| # | Document | What it covers |
|---|----------|----------------|
| — | [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) | Every planning assumption + how to replace it |
| 01 | [`docs/01-technology-review.md`](docs/01-technology-review.md) | Best available fiber + wireless tech, vendor-by-vendor, with recommendations |
| 02 | [`docs/02-comparable-networks.md`](docs/02-comparable-networks.md) | Real-world precedents: co-ops, WISPs, lake/island networks, over-water links |
| 03 | [`docs/03-network-architecture.md`](docs/03-network-architecture.md) | The hybrid design, node taxonomy, over-water RF engineering, redundancy |
| 04 | [`docs/04-geographic-breakdown.md`](docs/04-geographic-breakdown.md) | Beaver Lake divided into service zones, POP siting, phasing |
| 05 | [`docs/05-gis-plan.md`](docs/05-gis-plan.md) | GIS/OSP data model, data sources (Benton/Washington/USACE/LiDAR), workflows |
| 06 | [`docs/06-business-plan.md`](docs/06-business-plan.md) | Market, product, pricing, host-node program, go-to-market, risks |
| 07 | [`docs/07-operations-plan.md`](docs/07-operations-plan.md) | Boat-based field ops, NOC, install/repair workflows, safety |
| 08 | [`docs/08-staffing-plan.md`](docs/08-staffing-plan.md) | Org chart, hiring sequence; full JDs in `job-descriptions/` |
| 09 | [`docs/09-accounting-plan.md`](docs/09-accounting-plan.md) | Unit economics, 5-year pro forma, funding stack, chart of accounts |
| 10 | [`docs/10-materials-and-bom.md`](docs/10-materials-and-bom.md) | Adaptable BOM system, work-order kits (data in `data/bom/`) |
| 11 | [`docs/11-procurement-process.md`](docs/11-procurement-process.md) | Vendors, POs, reorder logic, inventory, materials-by-work-order |
| 12 | [`docs/12-regulatory-permitting.md`](docs/12-regulatory-permitting.md) | USACE shoreline, FCC, AR-811, pole attachments, county permits |
| 13 | [`docs/13-grants-and-financing.md`](docs/13-grants-and-financing.md) | BEAD, USDA ReConnect/RUS, state grants, low-interest telecom loans, pipeline |
| 14 | [`docs/14-software-architecture.md`](docs/14-software-architecture.md) | DockOS platform, services, stack, the AR compliance "brain" |
| 15 | [`docs/15-roadmap-and-phasing.md`](docs/15-roadmap-and-phasing.md) | Sequenced build: pilot → region → whole lake, plus software milestones |
| 16 | [`docs/16-governance-and-tokenomics.md`](docs/16-governance-and-tokenomics.md) | Member cooperative + DAO: the non-transferable, tenure-earned WAKE governance unit, patronage-dividend economics, voting design |
| 17 | [`docs/17-middle-mile-transit.md`](docs/17-middle-mile-transit.md) | Middle-mile / transit procurement, sizing, RFQ, path diversity |
| 18 | [`docs/18-member-capital-campaign.md`](docs/18-member-capital-campaign.md) | Grant-free funding: reservations, shares, founding capital, per-zone build gate |
| 19 | [`docs/19-entity-formation-checklist.md`](docs/19-entity-formation-checklist.md) | Arkansas telecom cooperative formation, tax, FCC, Beaver Lake permits |
| 20 | [`docs/20-site-acquisition-and-real-estate.md`](docs/20-site-acquisition-and-real-estate.md) | Own the head-ends, lease the edge; huts vs cabinets |
| 21 | [`docs/21-network-architecture-specs.md`](docs/21-network-architecture-specs.md) | Engineering design spec: equipment, addressing, routing, power, acceptance |
| 22 | [`docs/22-billing-provisioning-radius.md`](docs/22-billing-provisioning-radius.md) | Billing lifecycle, provisioning, RADIUS as views over billing (DockOS 6) |
| 23 | [`docs/23-dispatch-and-work-orders.md`](docs/23-dispatch-and-work-orders.md) | Work orders, boat/truck dispatch, crew PWA; boat vs truck measured (DockOS 4–5) |
| 24 | [`docs/24-noc-and-outage-management.md`](docs/24-noc-and-outage-management.md) | NOC root cause, outages, dispatch, member credits; the spine SPOF finding (DockOS 7) |
| WP | [`docs/whitepaper/`](docs/whitepaper/) | White paper: the whole plan in one living document, with the open-decisions register |
| — | [`BACKLOG.md`](BACKLOG.md) | Live build backlog we work through one by one |

## 2. Data & code map

| Path | Purpose |
|------|---------|
| `data/bom/` | Adaptable bill-of-materials, one CSV per work-order type |
| `data/gis/` | GIS layer dictionary, node inventory + service-address templates |
| `data/financial/` | 5-year pro forma inputs and outputs (CSV) |
| `software/` | DockOS platform plan, database schema, and app scaffolding |
| `job-descriptions/` | Ready-to-post JDs for every role |

## 3. Snapshot (planning-grade)

- **Service area:** ~449 miles of Beaver Lake shoreline; Benton, Washington, and
  Carroll counties, NW Arkansas.
- **Target passings:** whole-lake, phased. **VERIFIED from live GIS: 9,571 improved
  premises within 1 mile of shoreline (6,144 within ¼ mile)** — Benton 7,190 ·
  Washington 1,318 · Carroll 1,044 · Madison 19. See
  [`data/gis/outputs/README.md`](data/gis/outputs/README.md).
- **On-ramps:** two diverse dedicated-internet handoffs (locations you've identified)
  form a protected core; the transport spine rings the lake.
- **Access:** XGS-PON fiber where economic; non-LOS + PtMP fixed wireless elsewhere.
- **Funding:** blended — private/owner equity, grants (BEAD/USDA/state), low-interest
  telecom debt (RUS/CoBank/RTFC), and an optional member/co-op host-node incentive.
- **Software:** open-source-first DockOS; PostGIS core; boat-dispatch PWA.

## 4. How to work in this repo with Claude Code

This plan was written to be *executable* by Claude Code sessions. Suggested next
builds (each a self-contained task):

1. Stand up the PostGIS + DockOS schema (`software/`) and load Benton/Washington
   parcels + USACE shoreline.
2. Build the serviceability + signup portal.
3. Build the boat-dispatch PWA and work-order engine wired to the BOM data.
4. Set up a recurring grants-scanning Routine (BEAD/USDA/state NOFOs).

See [`docs/15-roadmap-and-phasing.md`](docs/15-roadmap-and-phasing.md) for the full
sequence.
