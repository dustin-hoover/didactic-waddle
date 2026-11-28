# 08 — Staffing Plan

Full, ready-to-post job descriptions live in [`../job-descriptions/`](../job-descriptions/).
This document is the org design and hiring sequence.

## 1. Org structure

```
                         Owner / CEO
                              │
     ┌───────────────┬────────┴────────┬───────────────┬───────────────┐
  Network &        Field Ops         Software /       Business Ops     Growth /
  GIS Engineering  (Marine)          DevOps           (Finance,        Sales &
                                                       Procurement,     Support
                                                       Compliance)
```

Lean at pilot; each box is a hat before it's a headcount. DockOS lets a small team
run a big network.

## 2. Hiring sequence (mapped to phases, doc 15)

### Phase 0 — Foundations (pre-build)
| Role | Why now | FT/PT |
|------|---------|-------|
| Owner/CEO | Vision, capital, relationships, the two transit deals | FT |
| Network Architect / RF & OSP Engineer | Spine + node design, link budgets, vendor selection | FT |
| GIS Analyst / OSP Records | Parcels, LOS, passings, build backlog | FT |
| Software/DevOps Engineer | Stand up DockOS (GIS, signup, billing, NOC) | FT (or contract) |
| Regulatory & Permitting Lead | USACE, FCC, pole attachments, county (doc 12) | FT/PT or contract |
| Grants & Financing Manager | BEAD/USDA/state + telecom loans (doc 13) | PT/contract |
| Bookkeeper/CPA | Chart of accounts, grant compliance | Contract |

### Phase 1 — Pilot build & first customers
| Role | Adds |
|------|------|
| Marine Field Operations Lead | Runs boat crews, safety, fleet |
| Fiber/Wireless Field Technician (Marine) ×2–3 | Node builds, drops, CPE, splicing |
| NOC / Support Technician ×1–2 | Monitoring, tickets, customer support |
| Procurement / Inventory Coordinator | POs, BOM kits, reorder (doc 11) |
| Sales / Community Manager | Pre-sales, host-node recruiting, marinas |

### Phase 2+ — Region & ring
Scale field crews per zone, add NOC shifts, add customer-support reps, add a
Construction Manager, add an Accountant/Controller, formalize HR.

## 3. Roles at a glance (JDs in `job-descriptions/`)

| Role | Core skills | JD file |
|------|-------------|---------|
| Network Architect / RF & OSP Engineer | RF path design, MPLS/BGP, PON, licensed µW, over-water links | `network-architect.md` |
| GIS Analyst / OSP Records Specialist | PostGIS, QGIS, LiDAR LOS, parcels | `gis-analyst.md` |
| Software / DevOps Engineer (DockOS) | Python/TS, PostGIS, APIs, PWA, monitoring | `software-devops-engineer.md` |
| Marine Field Operations Lead | Boat ops, crew mgmt, safety, construction | `marine-field-ops-lead.md` |
| Fiber/Wireless Field Technician (Marine) | Fusion splicing, radio install, boating, climbing | `field-technician-marine.md` |
| NOC / Support Technician | NMS, networking, ticketing, customer comms | `noc-support-technician.md` |
| Procurement / Inventory Coordinator | Purchasing, inventory, vendor mgmt | `procurement-inventory-coordinator.md` |
| Regulatory & Permitting Lead | USACE, FCC, ROW, pole attachments | `regulatory-permitting-lead.md` |
| Grants & Financing Manager | Grant writing, telecom finance | `grants-financing-manager.md` |
| Sales / Community Manager | Local sales, host-node, marinas | `sales-community-manager.md` |
| Bookkeeper / Controller | Telecom accounting, grant compliance | `bookkeeper-controller.md` |

## 4. Compensation approach (planning)

- Benchmark to NW Arkansas telecom/construction market; verify with current data.
- Field techs: base + on-call + boat/marine premium; safety-tied bonuses.
- Equity/profit-share option for early key hires.
- Host-node/marina partners can offset labor via the discount program (not staff, but
  reduces site-access cost).

## 5. Training & certification

- Marine safety (USCG boating safety; consider a licensed captain on staff for the work
  pontoon/barge).
- Fiber (FOA CFOT/CFOS), tower/climbing + fall protection, RF safety.
- Vendor certs: Tarana, Cambium, Ubiquiti, licensed-microwave vendor.
- 811/locate and OSHA construction safety.
- Cross-train field techs on both fiber and wireless (the "specialized boat tech").

## 6. Culture & retention

Small, high-trust, well-documented team. The mission ("best internet on the lake,
delivered by boat") is a genuine recruiting hook. Document everything in DockOS so the
company isn't hostage to any one person's memory.
