# Boat Dock Network — Build Backlog

We work these **one by one**. Status: ✅ done · 🔨 in progress · ⬜ queued.

## Foundations (done)
- ✅ Business/ops/GIS/staffing/accounting/materials/regulatory/grants plans (docs 01–15)
- ✅ Verified premises-passed from public GIS (9,571 ≤1mi) + PostGIS + DockOS schema
- ✅ 18 service zones + build order
- ✅ 30 candidate nodes, viewshed-ranked (bare-earth + canopy DSM)
- ✅ Backbone spine (41 hops, $1.37M) — *not yet a full ring; see doc 24 §2*
- ✅ 5-year pro forma (foliage base case: ~$7.5M CapEx, EBITDA+ Y2, peak ~$3.1M)
- ✅ Interactive map + financial dashboard (self-contained artifacts)
- ✅ Canopy-aware LOS refinement (NLCD DSM): 75% wireless LOS, 25% shadow

## Done (cont.)
- ✅ **Cooperative + DAO governance & tokenomics** (doc 16): non-transferable WAKE unit
  (1/mo, 1.5× host, cap 120), patronage-dividend economics, tokenomics sim, governance
  schema, explainer artifact

## Done (cont.)
- ✅ **Investor / grant deck** (dual-purpose, self-contained HTML, 13 slides, embedded
  map + charts) — `data/deck/investor_grant_deck.html`

## Done (cont.)
- ✅ **Serviceability + member signup portal** (DockOS step 3): pin-drop serviceability
  by zone, plan selection, member/reservation/founding/host signup persisted to the
  artifact `db` with an owner pipeline panel; + production FastAPI serviceability API and
  signup/pledge schema for the public launch. `data/portal/signup_portal.html`

## Done (cont.)
- ✅ **True LiDAR surface model** (3DEP point cloud → first-return DSM, `ept_build.py`):
  validated LOS — real canopy blocks ~half of clean LOS (Phase-1: 26% vs 44% NLCD proxy).
  30–45 m towers + nLOS radios recover it. Model made LiDAR-informed
  (CapEx ~$8.6M incl. land, peak ~$3.6M). `data/gis/outputs/lidar_validation.csv`

## Done (cont.)
- ✅ **Middle-mile / transit procurement package** (doc 17): found Diamond State Networks
  (13-co-op wholesale middle-mile incl. OzarksGo) as lead path A + diverse carrier path B;
  capacity sizing (`transit_sizing.py` → `transit_plan.csv`: 2×10G→2×100G, ~$58k→$213k/yr);
  ready-to-send RFQ + weighted provider scorecard (`procurement/`).

## Done (cont.)
- ✅ **Member-capital campaign tooling** (doc 18): the grant-free funding engine.
  Three instruments (reservation deposit $100 · membership share $200 · founding capital
  $500/$1,500/$5,000) + per-zone build-gate (reservations ≥ 25% of premises AND capital ≥
  premises × $75). Portal now captures pledge amounts to a `pledges` db collection and
  shows an owner **Campaign cockpit** (per-zone capital vs gate, total vs $3.6M peak,
  funding mix); Stripe-backed reference API (`software/api/capital.py`: pledge → Checkout →
  webhook → collected → enroll member/WAKE) + schema (`capital_campaigns`, `member_shares`,
  Stripe fields on `pledges`, `campaign_progress` view). Portal artifact republished (v2).

## Done (cont.)
- ✅ **Execute middle-mile** (doc 17 §6): packaged the whole path to signed transit.
  `procurement/arin_resource_request.md` (verified 2026 ARIN process/fees: ASN + IPv6 /36
  + IPv4 /24 waitlist + lease bridge, ~$275/yr RSP), `procurement/rfq_outreach.md`
  (provider contacts incl. DSN, ready-to-send cover message, outreach tracker), RFQ
  head-ends scoped to candidate NW + diverse-route POPs, and
  `procurement/path_diversity_checklist.md` (4-layer A/B diversity acceptance test +
  failover drill). Remaining steps need a human: ARIN Org (legal entity + EIN), exact POP
  sites, and actually sending the RFQ / filing with ARIN.

## Done (cont.)
- ✅ **Entity formation checklist** (doc 19): the ordered path to a chartered Arkansas
  cooperative — recommends the **Telecommunications Cooperative** vehicle (Rural Telephone
  Cooperative Act, Articles $10 at the SoS), Subchapter T tax posture, bylaws wiring WAKE +
  capped voting (doc 16) and capital≠governance (doc 18), EIN → ARIN Org, DFA/sales-tax,
  FCC FRN + BDC (Form 499/USF only if voice), and the **Beaver Lake specifics** (USACE
  shoreline permits for a dock-served network, pole attachments, ROW, 811, FAA). Critical
  path unblocks the ARIN Org and transit signing. Fees/forms verified vs AR SoS + FCC.

## Done (cont.)
- ✅ **Site acquisition & real estate** (doc 20): buy-vs-lease framework for comm huts /
  head-ends / node sites. Recommendation — **own the two T0 head-end POPs fee-simple**
  (permanent control + loan collateral), **lease/easement** T1 core and the ~30 edge nodes
  (host-a-node WAKE 1.5× covers member sites). Lakeside-parcel triple-use (head-end + boat/
  ops base + showcase), siting criteria, buy-vs-lease money model + pro-forma/collateral
  hooks, and the legal wrapper (title/survey/zoning/USACE shoreline/Phase I/flood). Cross-
  linked from doc 04 §3; sequenced after entity formation (doc 19).

## Done (cont.)
- ✅ **Network architecture specs** (doc 21): engineering design spec behind doc 03 —
  tier-by-tier equipment classes, IPv6 /36 hierarchical addressing + IPv4 CGNAT, BGP
  multihoming/IS-IS/SR-MPLS-or-EVPN routing, XGS-PON + licensed-µW + nLOS-CBRS transport/
  access with loss/link budgets & tower heights, site power/grounding/environmental (NEMA,
  solar autonomy), capacity/latency/availability targets, QoS, AAA/telemetry/provisioning,
  security (RPKI/MANRS/CoPP/DDoS), and per-tier commissioning tests. Vendor-neutral,
  standards-referenced. Enclosure hut-vs-cabinet spectrum added to doc 20 §1.5.

## Done (cont.)
- ✅ **Governance module in DockOS** (doc 16): `software/api/governance.py` — WAKE ledger
  mechanics (monthly accrual idempotent per period, host ×1.5, forfeiture→Commons Pool on
  exit, 50% annual redistribution) + Snapshot-style proposals with tenure-weighted,
  anti-whale-capped voting and quorum/pass finalization. Anti-whale rule refined to
  max(2%, one equal share) so it's coherent at any membership size (unit-tested N=2→4000).
  SQL validated on PostGIS. Member voting portal artifact (`db`+`user`, auto-enroll,
  steward tools) published + verified. `data/governance/governance_portal.html`

## Done (cont.)
- ✅ **Billing + provisioning + RADIUS** (DockOS step 6, doc 22): FreeRADIUS authorize tables
  are **views over billing state** (no sync, no drift); `billing.py` lifecycle (prorated first
  bill w/ doc 18 deposit credit + host credit + taxed equipment, monthly run, Stripe payments,
  dunning 10/21/60 d → walled garden → terminate, seasonal hold that keeps WAKE, instant plan
  changes, cancel w/ WAKE forfeit); provisioning engine (SKIP LOCKED queue, OLT/CPE adapters,
  RFC 5176 CoA); IPv6 /56-from-zone-/44 allocator; least-privilege radius role. **46-check
  e2e vs live FreeRADIUS 3.2.5** (`software/tests/test_billing_e2e.py`). Fixed doc 21 IPv6
  zone size (/48 → /44).

## Done (cont.)
- ✅ **Work-order engine + boat/truck dispatch + crew PWA** (DockOS steps 4–5, doc 23):
  water routing on the real lake (50 m grid, no-wake band, smoothed tracks) + real OSM drive
  times; install WOs from sign-ups with BOM kits → reservation → PO shortfall; permits gate;
  NWS weather go/no-go per boat class (live-tested); least-added-travel day planner; P1 outage
  inserted as next stop; offline-first crew app (run sheet, chart, checklists, readings, scan,
  outbox) whose install completion starts billing. **43-check e2e** incl. the app in headless
  Chromium. **Finding:** boat beats truck for ~24% of premises at 15-min dock turnaround,
  ~52% at 5 min → hybrid fleet; dock turnaround ≤ 8 min is the KPI (measured, fed back to the
  planner). Repaired 15 malformed BOM kit rows. Preview artifact: "DockOS Crew".

## Done (cont.)
- ✅ **NOC monitoring + outage management** (DockOS step 7, doc 24): topology engine turns
  alarm storms into a single root cause (reachability from head-ends; root, suppressed,
  silent, ring-open), with hold-down and flap damping. Outage → active members only
  (seasonal holds excluded) → P1 inserted as the next stop of the fastest crew → SMS/email
  notices with ETA → public status page (no PII) → closes on **telemetry** recovery, cancels
  un-started crew visits → **automatic SLA credits** (business 2× > 4 h, residential ≥ 24 h)
  into billing. Also: access-sector outages, single-radio P3 tickets that self-clear, and a
  solar-battery SOC forecast that sends a crew *before* the site dies. **52-check e2e** on
  the real topology; dispatch 43 + billing 46 still green.
  **Finding:** the spine is **not a ring**: 5 bridges + 8 cut nodes, and 2,367 of 4,211
  members behind a SPOF (SP-06-13 alone carries 2,243). **+5 hops ($40k radio … $689k
  fiber)** leave 553 behind two cut nodes; the NW head-end also needs dual-homing. Docs
  03/21 corrected; pro forma unchanged (your call). Board artifact: "DockOS NOC".

## Done (cont.)
- ✅ **White paper** (`docs/whitepaper/`): every aspect of the plan in one living document
  (executive summary through appendix, 20 sections), with a register of 20 open decisions
  and a list of inconsistencies between docs to reconcile. Editable in place; each save is a
  new version, and a Draft → Final switch marks the plan finalized. Artifact: "Boat Dock
  Network White Paper".

## Queued (recommended order — next up)
- ⬜ **Close the ring** (doc 24 §2): path survey on the 5 hops, dual-home HE-NW, decide
  on the N11/N05 cut nodes; then fold the cost into the pro forma
- ⬜ **AR/Benton/Washington compliance advisor** (DockOS step 8) — grants NOFO scanner
  deferred (no government money in the base case; revisit only if programs return)

_Update this file as items complete._
