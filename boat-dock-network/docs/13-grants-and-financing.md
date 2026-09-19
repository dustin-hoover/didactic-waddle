# 13 — Grants & Low-Interest Financing

> Program details, funding levels, and deadlines change frequently. Everything here is a
> planning map as of early 2026 — **verify current NOFOs, eligibility, and rules** with
> each program before relying on them. A dedicated Grants & Financing Manager (doc 08)
> owns this.

Grants are the single biggest lever on the raise and on payback (doc 09). The strategy
is a **blended stack** — non-dilutive grants for the high-cost/low-density passings,
low-interest telecom debt for the bulk of CapEx, and equity as first-in risk capital
and grant match.

## 1. Federal grant programs

| Program | Agency | Fit | Notes |
|---------|--------|-----|-------|
| **BEAD** (Broadband Equity, Access & Deployment) | NTIA → **Arkansas State Broadband Office** | Primary target for unserved/underserved shoreline | ~$1B+ AR allocation; program rules revised in 2025 ("Benefit of the Bargain"). State-run subgrants; **verify current AR NOFO, match, and tech-neutrality rules** |
| **USDA ReConnect** | USDA RUS | Rural build grants/loans | Rounds recur; rural eligibility by service level |
| **USDA RUS Telecom Infrastructure / Farm Bill Broadband** | USDA RUS | Low-interest **loans** | Telecom-specialized, long term |
| **FCC RDOF** | FCC | Mostly awarded | Check for defaults/re-auctions in your census blocks |
| **Treasury Capital Projects Fund / ARPA remnants** | State | Possible state sub-programs | Verify availability |
| **EDA / CDBG / ARC** | EDA/HUD | Ancillary (facilities, econ dev) | Situational |

## 2. Arkansas state programs

- **Arkansas State Broadband Office (Arkansas Department of Commerce)** administers
  **BEAD** subgrants and prior **Arkansas Rural Connect (ARC)** grants. Register as a
  provider, submit to the state challenge/map process, and target eligible shoreline
  census blocks.
- Watch for **state matching** and **middle-mile** sub-programs.

## 3. Low-interest telecom lenders (the debt layer)

| Lender | Role |
|--------|------|
| **USDA RUS loans** | Long-term, low-rate infrastructure debt |
| **CoBank** | Rural/telecom cooperative bank; construction + term debt |
| **RTFC / CFC** (Rural Telephone Finance Cooperative / National Rural Utilities Cooperative Finance Corp) | Telecom-specialized lending |
| **Equipment finance / leasing** | Radios, OLT, fleet — preserve cash |
| **Local/regional banks** | Working capital, SBA (504/7a) for facilities |

Target blended cost of capital ~5% by leaning on RUS/CoBank/RTFC + grants.

## 4. Equity & community capital

- **Owner/private equity:** first-in risk capital and the **grant match** most programs
  require; funds the pilot before grants/debt close.
- **Host-node / member model:** deposits and site contributions reduce passing cost;
  a **co-op structure** can turn hosts into members (community capital + loyalty).
- **PropCo:** an entity that owns strategic lakeside parcels/towers can raise
  real-estate-backed capital and lease sites to the OpCo (tax/financing flexibility —
  confirm with CPA/counsel).

## 5. What wins broadband grants (the playbook)

1. **A defensible map** of unserved/underserved passings (your GIS output, doc 05, is
   exactly the evidence reviewers want) and accurate cost-per-passing per zone.
2. **Community support:** letters from lake associations, marinas, counties, chambers.
3. **Matching funds committed** (equity/debt LOIs).
4. **Technical + financial credibility:** the architecture (doc 03), pro forma (doc 09),
   and a real team (doc 08).
5. **Compliance readiness:** segregated accounting (doc 09), BABA/domestic-content plan
   (doc 11), environmental (doc 12), and reporting capacity.
6. **Speed + coverage commitments** that meet program thresholds (symmetric gig helps).

## 6. Funding sequence (match to phases, doc 15)

1. **Equity** funds entity + GIS + pilot design + first pilot zone.
2. **Pilot proof** (customers, actual costs) → strengthens grant apps + debt underwriting.
3. **Grants + RUS/CoBank/RTFC debt** close to fund region + ring build.
4. **Equipment finance** smooths radio/OLT/fleet CapEx.
5. **Refinance** to lower-cost long-term debt once cash-flowing.

## 7. Grants pipeline (run it like a sales pipeline)

Track every opportunity as a record: program, deadline, eligible zones, ask amount,
match required, status, owner, next action. Fields defined for DockOS in doc 14; a
simple CSV/board works at first.

**Automation:** set up a recurring **Claude Code Routine** (see roadmap, doc 15) to scan
for new/updated NOFOs (BEAD state updates, USDA ReConnect rounds, state programs),
summarize eligibility changes, and flag deadlines — a near-free "grant seeker." Ask and
I'll configure it.

## 8. Compliance reminders (do not skip)

- **Segregated fund accounting + documented match** before drawing any grant dollar.
- **BABA / Build America Buy America** sourcing checks *before* buying grant-funded gear.
- **Environmental & historic-preservation** reviews (NEPA/Section 106) can apply to
  federally funded construction — bake into timelines.
- **Reporting cadence** per program; DockOS captures the CapEx-by-work-order evidence.
