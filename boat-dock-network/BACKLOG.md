# Boat Dock Network — Build Backlog

We work these **one by one**. Status: ✅ done · 🔨 in progress · ⬜ queued.

## Foundations (done)
- ✅ Business/ops/GIS/staffing/accounting/materials/regulatory/grants plans (docs 01–15)
- ✅ Verified premises-passed from public GIS (9,571 ≤1mi) + PostGIS + DockOS schema
- ✅ 18 service zones + build order
- ✅ 30 candidate nodes, viewshed-ranked (bare-earth + canopy DSM)
- ✅ Redundant backbone spine (41 hops, $1.37M)
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
  (CapEx ~$8.3M, peak ~$3.3M). `data/gis/outputs/lidar_validation.csv`

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
  shows an owner **Campaign cockpit** (per-zone capital vs gate, total vs $3.3M peak,
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

## Queued (recommended order — next up)
- ⬜ **Governance module in DockOS** (unit ledger, proposals, Snapshot-style voting)
- ⬜ **Billing + provisioning + RADIUS** (DockOS step 6)
- ⬜ **Boat-dispatch PWA + work-order engine** (DockOS steps 4–5)
- ⬜ **NOC monitoring + outage management** (DockOS step 7)
- ⬜ **AR/Benton/Washington compliance advisor** (DockOS step 8) — grants NOFO scanner
  deferred (no government money in the base case; revisit only if programs return)
- ⬜ **Entity formation checklist** (AR cooperative filing, bylaws, ASN/IP, transit LOIs)

_Update this file as items complete._
