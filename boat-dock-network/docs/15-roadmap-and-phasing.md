# 15 — Roadmap & Phasing

Two tracks run in parallel: the **physical build** (outside plant) and the **software
platform** (DockOS). Software leads slightly so the build is measured, sold, and
managed from data — not guesswork. Everything is **phase-gated**: spend follows proof
and funding.

## Track A — Physical build

### Phase 0 — Foundations (months 0–4)
- Form entity + insurance; AR/SoS registration; EIN.
- Get **ARIN ASN + IP space**; sign **two transit LOIs** (your on-ramps).
- Load GIS (parcels, USACE shoreline, LiDAR) → **verify premises-passed** (replaces the
  biggest assumption).
- Design pilot zones + first lake crossing; run LOS/link budgets.
- Open **USACE Little Rock District** dialogue; start pole-attachment agreements.
- Recruit initial host nodes in pilot zones.

### Phase 1 — Pilot (months 4–12)
- Build 2 head-end POPs (the two on-ramps) + initial ring segment + **one lake
  crossing** (prove the over-water spine).
- Build 1–2 central dock nodes (e.g., Prairie Creek / Rocky Branch).
- Connect first customers (fiber where dense, nLOS wireless elsewhere).
- Capture **real costs** → refine BOM + pro forma; use as grant/loan evidence.

### Phase 2 — Central region (year 1–2)
- Complete the central Benton corridor (highest density/return).
- Close **grants + RUS/CoBank/RTFC debt** on pilot proof.
- Scale field crews per zone; formalize NOC shifts.

### Phase 3 — Ring closure (year 2–3)
- Build the spine all the way around/across so redundancy is real.
- Expand dock nodes + relays into remaining moderate-density zones.

### Phase 4 — Long tail (year 3–5)
- Upper arms + sparse coves, **demand-gated** (pre-sales threshold).
- Use grants targeted at high-cost/low-density passings.
- Selective FTTH overbuild of the densest wireless zones as they mature.

## Track B — Software (DockOS)

| Order | App | Unlocks |
|-------|-----|---------|
| 1 | PostGIS + schema + data import | Everything downstream |
| 2 | GIS analysis (serviceability, LOS, passings) | Real pro forma + grant maps |
| 3 | Signup/serviceability portal | **Pre-sales before building** |
| 4 | Work-order + BOM + procurement | Clean pilot build + CapEx capture |
| 5 | Boat-dispatch PWA | Boat-native ops |
| 6 | Billing + provisioning + RADIUS | Paying customers |
| 7 | NOC monitoring + outage | Reliable operation |
| 8 | Compliance advisor + grants scanner | Scale paperwork with AI |

Each is a self-contained Claude Code task against `software/db/schema.sql`.

## Critical path & dependencies

```
Entity+ASN+transit ─┐
GIS import ─────────┼─► passings verified ─► pilot design ─► permits ─► pilot build ─► customers
                    │                                   │
Host-node recruiting ┘                      grants+debt close ──────────► region+ring build
```

The two long-lead, start-now items: **USACE dialogue** and **pole-attachment
agreements** (doc 12) — they gate construction and are the classic schedule killers.

## Immediate next actions (this month)

1. **Confirm the two on-ramp locations** and request 10G/100G quotes.
2. **Run the GIS passings analysis** (build DockOS steps 1–2) to replace the #1
   assumption and produce the grant-ready coverage map.
3. **Pick the pilot zone(s)** from the ranked backlog.
4. **Stand up the grants pipeline** and (optionally) a recurring NOFO-scanning Routine.
5. **File entity + start USACE + pole conversations.**

## Suggested Claude Code follow-on tasks

- "Build DockOS steps 1–2: PostGIS + schema + import Benton County parcels + USACE
  shoreline + AR LiDAR, then compute premises-passed per zone."
- "Build the serviceability + signup portal against the schema."
- "Build the work-order + BOM engine that expands `data/bom/*.csv` into POs."
- "Set up a weekly grants NOFO-scanning Routine (BEAD/USDA/AR state)."
- "Generate the investor deck / grant narrative from these docs."
- "Create a live Felt map of the zones + candidate nodes for stakeholders."
