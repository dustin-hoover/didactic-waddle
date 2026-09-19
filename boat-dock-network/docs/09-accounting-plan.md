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

## 2. Unit economics (steady state, planning)

| Metric | Without grants | With ~40% CapEx grant |
|--------|----------------|-----------------------|
| Cost per premises passed | $1,800 | ~$1,080 |
| Cost per connection (drop+CPE) | $900 | ~$540 |
| Passing cost allocated per sub (42% take) | ~$4,286 | ~$2,571 |
| All-in cost per subscriber | ~$5,186 | ~$3,111 |
| ARPU (blended res+biz) | $100/mo ($1,200/yr) | same |
| Annual contribution/sub (~70% margin) | ~$840 | ~$840 |
| Simple payback per sub | ~6.2 yrs | ~3.7 yrs |

Host-node hosting further lowers passing cost (free/cheap sites + power + easement),
and lifts take-rate — both improve the table above. Grants are the single biggest lever
on payback; hence the funding strategy in doc 13.

## 3. 5-year pro forma (planning, $000s)

Whole-lake, phased build. See CSV for the machine-readable version.

| Line | Y1 | Y2 | Y3 | Y4 | Y5 |
|------|----|----|----|----|----|
| Premises passed (cum) | 500 | 2,000 | 4,500 | 7,000 | 9,000 |
| Subscribers (cum) | 140 | 660 | 1,710 | 2,800 | 3,780 |
| Take rate | 28% | 33% | 38% | 40% | 42% |
| **Revenue** | 88 | 504 | 1,493 | 2,841 | 4,145 |
| Transit/backhaul | 120 | 200 | 320 | 450 | 600 |
| Operating payroll | 380 | 620 | 950 | 1,250 | 1,550 |
| Site leases/pole attach | 40 | 90 | 160 | 220 | 280 |
| SG&A/software/insurance/fuel | 220 | 350 | 550 | 750 | 900 |
| **Total OpEx** | 760 | 1,260 | 1,980 | 2,670 | 3,330 |
| **EBITDA** | (672) | (756) | (487) | 171 | 815 |
| **CapEx** | 2,576 | 4,118 | 6,595 | 5,981 | 4,882 |
| **Cash flow (pre-financing)** | (3,248) | (4,874) | (7,082) | (5,810) | (4,067) |

- **EBITDA turns positive in Year 4** as subscribers mature against a fixed operating
  base.
- **Cumulative pre-financing cash need ≈ $25M** over 5 years for the whole-lake build —
  this is the raise, *before* grants.
- 5-year CapEx ≈ **$24M** (hybrid; all-fiber would be far higher — the wireless spine
  and nLOS access are what make whole-lake financeable).

## 4. What grants/subsidy do to the picture

If grants (BEAD/USDA/state) cover ~40% of eligible CapEx (~$24M eligible → ~$9.6M):
- Net equity + debt need drops to roughly **$15M + working capital**.
- Per-sub payback drops from ~6.2 to ~3.7 years.
- With deeper coverage in high-cost/low-density zones (grants target exactly those),
  the long-tail zones flip from uneconomic to fundable.

Grant coverage is location-specific — model it per zone, not lake-wide, using the GIS
cost-per-passing output (doc 05). Doc 13 is the strategy to win it.

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
