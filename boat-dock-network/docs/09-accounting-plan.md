# 09 — Accounting & Financial Plan

This is a **planning-grade** model to size the business and the raise. Every figure is
an *(estimate)* to be replaced by GIS-verified passings, vendor quotes, and pilot
actuals (see `docs/ASSUMPTIONS.md`). Raw numbers live in
[`../data/financial/pro_forma.csv`](../data/financial/pro_forma.csv) and
[`../data/financial/capex_detail.csv`](../data/financial/capex_detail.csv) so you can
re-run them.

## 1. Key accounting principle: capitalize construction, expense operations

- **Labor and materials that build plant** (node builds, drops, spine) are
  **capitalized** into fixed assets and depreciated — they're in the CapEx-per-passing
  and per-connection figures.
- **OpEx payroll** counts only the run-the-business team (NOC, support, sales, G&A,
  ongoing engineering/GIS) — *not* construction crews.
- This is why EBITDA turns positive well before cumulative cash does: the heavy spend is
  capital, funded by the blended stack (§6), not operating expense.

> **VERIFIED MODEL — foliage base case (supersedes the fiber-default estimate).**
> Regenerate with `python3 software/finance/model.py` (reads the GIS outputs). A
> **canopy-aware (NLCD/LiDAR) viewshed** shows **75% of premises are reachable by
> wireless line-of-sight through Ozark foliage** (bare-earth optimistic is 87%). Even
> so, cost-per-passing is **~$460**, not the ~$1,800 a fiber overbuild assumes — holding
> whole-lake CapEx to **~$7.5M** and the peak funding need to **~$3.1M**. The remaining
> ~25% RF-shadow set (~2,417 premises) is served by relays or fiber; non-line-of-sight
> radios (Tarana) recover part of that gap (upside toward the 87% case).

## 2. Unit economics (verified, foliage base case)

| Metric | Value | Note |
|--------|-------|------|
| Cost per premises passed | **~$460** | Wireless-first; infra shared across a zone's premises |
| Cost per connection (CPE + install) | **~$725** | Blended 75% wireless @ $500 / 25% fiber-relay @ $1,400 |
| All-in cost per subscriber (5-yr) | **~$1,769** | Total CapEx ÷ Year-5 subscribers |
| ARPU (blended res + business/marina) | $105/mo ($1,260/yr) | Premium market: median home $410k, 522 >$1M |
| Annual contribution/sub (~70% margin) | ~$882 | |
| Simple payback per sub | **~2.0 yrs** | vs ~6.2 yrs in the fiber-default estimate |

The premium shoreline market (verified median home value $410k) supports the $105 ARPU
and a high ultimate take; the host-node program lowers site cost and lifts take further.

## 3. 5-year pro forma (verified, $000s)

Whole-lake, phased by the GIS build order (doc 04): P1 3,341 premises / 3 nodes,
P2 2,957 / 10, P3 1,933 / 8, P4 1,340 / 9. Machine-readable in
[`../data/financial/pro_forma.csv`](../data/financial/pro_forma.csv).

| Line | Y1 | Y2 | Y3 | Y4 | Y5 |
|------|----|----|----|----|----|
| Premises passed (cum) | 3,341 | 6,298 | 8,231 | 9,571 | 9,571 |
| Subscribers (cum) | 835 | 1,889 | 2,963 | 3,828 | 4,211 |
| Take rate | 25% | 30% | 36% | 40% | 44% |
| **Revenue** | 558 | 1,819 | 3,240 | 4,536 | 5,369 |
| **Total OpEx** | 710 | 1,180 | 1,750 | 2,300 | 2,820 |
| **EBITDA** | (152) | 639 | 1,490 | 2,236 | 2,549 |
| **CapEx** | 2,165 | 1,422 | 1,250 | 986 | 1,628 |
| **Cash flow (pre-financing)** | (2,317) | (783) | 240 | 1,250 | 921 |
| **Cash flow (cumulative)** | (2,317) | (3,100) | (2,860) | (1,610) | (689) |

- **EBITDA turns positive in Year 2.**
- **Peak funding need ≈ $3.1M** (end of Year 2); **cumulative cash turns positive in
  ~Year 6** (still −$0.7M at end of Y5; Year-6 EBITDA ~$2.5M clears it) — before grants.
- **5-year CapEx ≈ $7.5M** ($4.4M network infrastructure incl. the $1.37M spine + $3.1M
  subscriber connections). CapEx per year in
  [`../data/financial/capex_detail.csv`](../data/financial/capex_detail.csv).

## 4. What grants/subsidy do to the picture

Because CapEx is ~$7.5M (not ~$24M), grants make the raise very manageable:
- **~40% grant of eligible CapEx (~$3.0M)** cuts the peak funding need toward ~$1.5–2M
  of equity/debt — within owner + a small telecom loan.
- Grants are best aimed at the **RF-shadow set (~2,417 premises)** and the long-tail
  Phase-4 zones, where per-passing cost is highest (relays/fiber). Model grant coverage
  per zone using the GIS cost outputs; doc 13 is the strategy.

### Scenarios (LOS is the key swing)

| Scenario | Wireless LOS | 5-yr CapEx | Peak need | Cash-positive |
|----------|--------------|-----------|-----------|---------------|
| **Base (foliage, NLCD DSM)** | **75%** | **~$7.5M** | **~$3.1M** | **~Y6** |
| Optimistic (bare-earth DEM) | 87% | ~$6.6M | ~$3.0M | ~Y5 |
| With nLOS radios (Tarana) | 75%→~82%* | between the two | ~$3.0M | ~Y5–6 |

\* nLOS radios penetrate light-to-moderate foliage, recovering part of the shadow set;
the true figure sits between the DSM and bare-earth bounds. Refine further with true
LiDAR first-return DSM (vs the NLCD-canopy model used here) for per-parcel precision.

## 5. Sensitivity levers (in order of impact)

1. **Grant coverage %** — biggest single lever on the raise and payback.
2. **Take rate** — pre-sales gating and host-node program protect this.
3. **Cost per passing** — wireless-vs-fiber mix, micro-trench, host-node sites.
4. **ARPU** — business/marina mix and add-ons.
5. **Transit cost** — your two on-ramp negotiations; big drop at 10G→100G tiers.

## 6. Funding stack (blended — "all of the above")

| Source | Role | Notes (see doc 13) |
|--------|------|--------------------|
| Owner/private equity | First-in risk capital, matching funds | Also PropCo for lakeside parcels |
| Grants — BEAD / USDA ReConnect / AR state | Cover high-cost passings | Non-dilutive; compliance-heavy |
| Low-interest telecom debt — USDA RUS, CoBank, RTFC/CFC | Bulk of CapEx | 20–30 yr, low rate, telecom-specialized |
| Equipment financing | Radios/OLT/fleet | Preserves cash |
| Member/host-node contributions | Site access, deposits | Co-op option; reduces passing cost |

Target blended cost of capital ~5% via the low-interest telecom lenders + grants.

## 7. Chart of accounts (starter, telecom-flavored)

- **Revenue:** residential, business, marina/resort managed, install fees, add-ons.
- **COGS/Direct:** transit/backhaul, upstream transport, field direct materials
  (expensed), warranty.
- **OpEx:** operating payroll, site leases/pole attachments, software/SaaS, insurance,
  fuel/marine, vehicles/boats operating, professional fees, marketing.
- **CapEx (fixed assets):** network plant (spine, nodes, fiber, radios), CPE, fleet,
  buildings/land (PropCo), tools/test gear, capitalized labor.
- **Contra/Other:** host-node credits, grant proceeds (offset asset or deferred),
  depreciation, interest.
- **Grant compliance:** segregated tracking per program (BEAD/USDA require it).

## 8. Controls & compliance

- Grant funds require **segregated accounting, documented match, and audit trails** —
  set this up before drawing any grant dollar.
- **Depreciation schedules** per asset class (fiber ~20–30 yr, radios ~7–10 yr, fleet
  ~7 yr).
- **FCC fees** (Form 499, USF contributions once applicable), state/county taxes,
  sales/use tax on equipment.
- **CPA + telecom-experienced bookkeeper** from day one (doc 08).
- DockOS ties BOM consumption → POs → asset records so CapEx is captured accurately by
  work order (doc 11/14).

## 9. Files

- [`../data/financial/pro_forma.csv`](../data/financial/pro_forma.csv) — the table above.
- [`../data/financial/capex_detail.csv`](../data/financial/capex_detail.csv) — CapEx
  build-up by category and year.
- Re-run: edit assumptions → regenerate. (A spreadsheet/`.xlsx` version can be
  generated on request.)
