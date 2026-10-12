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

> **VERIFIED MODEL — LiDAR-informed base case (supersedes the fiber-default estimate).**
> Regenerate with `python3 software/finance/model.py`. Validating against **real 3DEP
> LiDAR canopy** (Phase-1) showed clean wireless line-of-sight is only ~26% at short
> masts — real trees block more than the NLCD proxy assumed. The engineering answer is
> **30–45 m towers** (recover LOS to ~40–45%) plus **non-line-of-sight radios (Tarana)**
> and more fiber/relay. Folding that in: cost-per-passing **~$516** (still a fraction of
> the ~$1,800 a fiber overbuild assumes), whole-lake CapEx **~$8.3M**, peak funding need
> **~$3.3M**, EBITDA-positive Year 2. See `data/gis/outputs/lidar_validation.csv`.

## 2. Unit economics (verified, LiDAR-informed)

| Metric | Value | Note |
|--------|-------|------|
| Cost per premises passed | **~$516** | Wireless-first + taller towers; infra shared across a zone |
| Cost per connection (CPE + install) | **~$800** | nLOS-default + more fiber/relay (LiDAR-informed) |
| All-in cost per subscriber (5-yr) | **~$1,973** | Total CapEx ÷ Year-5 subscribers |
| ARPU (blended res + business/marina) | $105/mo ($1,260/yr) | Premium market: median home $410k, 522 >$1M |
| Annual contribution/sub (~70% margin) | ~$882 | |
| Simple payback per sub | **~2.2 yrs** | vs ~6.2 yrs in the fiber-default estimate |

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
| **CapEx** | 2,248 | 1,565 | 1,382 | 1,109 | 2,006 |
| **Cash flow (pre-financing)** | (2,400) | (926) | 108 | 1,127 | 543 |
| **Cash flow (cumulative)** | (2,400) | (3,326) | (3,218) | (2,091) | (1,548) |

- **EBITDA turns positive in Year 2.**
- **Peak funding need ≈ $3.3M** (end of Year 2); **cumulative cash turns positive in
  ~Year 6** (−$1.5M at end of Y5; Year-6 EBITDA ~$2.5M clears it) — before grants.
- **5-year CapEx ≈ $8.3M** ($4.9M network infrastructure incl. the $1.37M spine + 30–45 m
  towers + $3.4M subscriber connections). CapEx per year in
  [`../data/financial/capex_detail.csv`](../data/financial/capex_detail.csv).

## 4. Covering the raise WITHOUT government money

**Base case assumes no grants and no federal (RUS) loans.** The ~$3.1M peak funding
need is covered by a grant-free stack (doc 13): owner equity, **member capital**
(the cooperative's grant replacement — membership shares, founding-member capital,
patronage retention), **pre-sales deposits**, and **private + cooperative debt**
(CoBank, RTFC/CFC — member-owned lenders, not government) plus equipment financing.

Representative cover of the ~$3.1M peak: ~$1.0M owner equity + ~$0.8M member capital &
pre-sales + ~$1.0M cooperative/commercial debt + ~$0.3M equipment finance. Because
EBITDA is positive from Year 2, later phases (and the high-cost RF-shadow tail) can be
**demand-gated and self-funded from operating cash** rather than needing external
capital. If public programs ever return, they are pure upside that shrinks this raise.

### Line-of-sight, validated against real LiDAR (the key engineering swing)

Clean wireless LOS to Phase-1 premises (same 18 candidates, 3,341 premises;
`data/gis/outputs/lidar_validation.csv`):

| Surface / config | Clean wireless LOS |
|------------------|--------------------|
| Bare-earth DEM (optimistic) | 55% |
| NLCD-canopy proxy | 44% |
| **True 3DEP LiDAR DSM, 15 m mast** | **26%** |
| True LiDAR + **30 m (100 ft) tower** | 40% |
| True LiDAR + **45 m (150 ft) tower** | 45% |

Real canopy blocks roughly **half** of clean LOS — worse than the proxy. Two levers
recover it: **taller towers** (26%→45%) and **nLOS radios (Tarana)**, which serve many
premises with no clean LOS at all; the deep-shadow remainder takes fiber/relay. The
model is now **LiDAR-informed**: T2/T3 node costs raised for 30–45 m towers, and the
connection blend + shadow CapEx raised for an nLOS-default access layer.

| Scenario | 5-yr CapEx | Peak need | Cash-positive |
|----------|-----------|-----------|---------------|
| **LiDAR-informed base (towers + nLOS + fiber)** | **~$8.3M** | **~$3.3M** | **~Y6** |
| NLCD-proxy (prior) | ~$7.5M | ~$3.1M | ~Y6 |
| Bare-earth (optimistic) | ~$6.6M | ~$3.0M | ~Y5 |

> Note on absolute %: this LiDAR test is at 10 m with 18 sites over Phase-1, so its
> figures are lower than the 30 m whole-lake run — use the **ratios** (canopy vs bare,
> tower lift) as the signal. A whole-lake LiDAR pass (other counties' 3DEP projects)
> and a real nLOS-propagation model are the next refinements.

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
