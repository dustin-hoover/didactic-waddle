# 12 — Regulatory & Permitting

> **Not legal advice.** This is a planning map of the approvals a shoreline ISP on a
> federal reservoir in Arkansas typically needs. Confirm every item with qualified
> telecom/land-use counsel and the agencies themselves before relying on it. Rules
> change; verify current versions.

Permitting is the #1 schedule risk (doc 06). The mitigation is to **start early, run it
as a dedicated function** (doc 08 Regulatory & Permitting Lead), and let the wireless
spine reduce shoreline construction that needs federal sign-off.

## 1. The big one: USACE (Beaver Lake is a federal reservoir)

Beaver Lake is operated by the **U.S. Army Corps of Engineers, Little Rock District**.
The shoreline and lakebed are federal land/water governed by the lake's **Shoreline
Management Plan (SMP)**.

- **Any structure, cable landing, dock modification, or crossing** on USACE-managed
  shoreline or lakebed needs USACE authorization — a **shoreline use permit** and/or a
  **real-estate outgrant/easement**, and for work in/over the water a
  **Section 10 (Rivers and Harbors Act) / Section 404 (Clean Water Act)** permit.
- **Subaqueous fiber** across a cove is the heaviest case (Section 10/404 + easement) —
  budget long timelines (see `wo-subaqueous-fiber.csv`). Prefer the **wireless spine**
  for crossings to minimize this.
- **Node siting:** put nodes on **private host-node property above the USACE take line**
  wherever possible so the site itself isn't on federal land; only the antenna's
  over-water *signal* crosses the lake (no permit needed for RF propagation).
- **Water-quality sensitivity:** Beaver Lake is the **drinking-water source** for much
  of NW Arkansas (Beaver Water District). Expect scrutiny on anything that could affect
  the reservoir; adopt zero-spill, sealed-battery, no-fueling-over-water discipline
  (doc 07). This is also a strong community-goodwill story.

**Action:** open a dialogue with the USACE Little Rock District early; map which
planned works touch federal shoreline/lakebed and pre-file those. Design to avoid
federal touchpoints where the wireless spine can carry the crossing.

## 2. FCC / spectrum

- **Unlicensed (Part 15):** 5/6/60 GHz radios (Ubiquiti/Cambium/Tarana 6 GHz) — no
  license, but follow power/AFC rules (6 GHz standard-power needs **AFC** coordination).
- **CBRS (3.5 GHz):** lightly licensed via a **SAS**; register CBSDs — great foliage
  band for Tarana access.
- **Licensed microwave (Part 101):** the spine lake-crossings — requires **frequency
  coordination + FCC license** per path (in `wo-lake-crossing-mw.csv`).
- **Antenna structures:** tall masts/towers may need **FAA** notice (Form 7460) and
  **FCC ASR** registration depending on height/location; most of ours will be short
  enough to avoid this, but check each site.
- **As an ISP:** register for **FCC Form 499** and **Broadband Data Collection (BDC)**
  filings; USF contribution obligations may apply once operating at scale.

## 3. Pole attachments (for aerial fiber)

- Poles are owned by **Ozarks Electric Cooperative**, **Carroll Electric Cooperative**,
  and **SWEPCO (AEP)** depending on area.
- **Important distinction:** **electric cooperatives are exempt from FCC pole-attachment
  rate regulation** — you negotiate agreements directly with Ozarks/Carroll. **SWEPCO
  (investor-owned)** falls under **FCC Part 1.1400** pole-attachment rules (unless a
  state regime applies). Plan for **make-ready** engineering and costs (a big line in
  `wo-fiber-aerial-mile.csv`) and long lead times.
- Get **master attachment agreements** in place early per pole owner.

## 4. State of Arkansas

- **Entity:** register the LLC/co-op with the **AR Secretary of State**; get EIN;
  business licenses.
- **Arkansas 811 (One Call):** mandatory locate requests before any excavation
  (Underground Facilities Damage Prevention Act) — in every underground BOM kit.
- **ARDOT:** utility permits for any work in **state highway right-of-way** (road
  crossings/parallels).
- **ADEQ:** environmental/stormwater (e.g., construction stormwater permit for larger
  disturbance) and any water-quality concerns near the reservoir.
- **Broadband office:** the **Arkansas State Broadband Office (Arkansas Department of
  Commerce)** administers BEAD/state grants (doc 13) and provider registration.
- **Municipal broadband law:** Arkansas historically restricted *government-owned*
  broadband (Act 1050 of 2011; loosened by Act 198 of 2019 and later acts). This only
  matters if you partner with a **public entity**; as a private company you're
  unaffected — but verify current law with counsel if a public-private structure is
  considered.

## 5. County & local (Benton, Washington, Carroll)

- **County road departments:** permits for cuts/bores in **county road ROW**.
- **Planning/zoning:** any towers, ground structures, or the shoreline yard/warehouse
  may need county land-use approval (some lake areas have overlay/scenic rules).
- **Building/electrical permits** for POP buildings and powered sites.
- **Property access/easements:** recorded easements for private-property node sites and
  drop routes (the host-node agreement includes access + power + easement terms).

## 6. Insurance & liability

- General liability, commercial marine (hull + protection & indemnity for the fleet),
  inland marine (equipment), workers' comp, professional/cyber, and auto.
- Contractor bonding where required for ROW/utility work.

## 7. The compliance "brain" (software, doc 14)

Because these rules are numerous and site-specific, DockOS includes an **Arkansas /
Benton / Washington compliance module**: a rules base (encoded from this document) plus
a **Claude-API advisor** that, for each work order, auto-generates the **permit
checklist** it needs (USACE? 811? ARDOT? pole make-ready? FAA/ASR? county ROW?), flags
BABA/grant conditions, and blocks release until required permits are logged. This turns
tribal knowledge into an enforced workflow and is a real cost-saver.

## 8. Permitting sequence (do this early)

1. Entity + insurance + AR registrations.
2. USACE Little Rock District intro + SMP review; identify federal touchpoints.
3. Master pole-attachment agreements (Ozarks/Carroll/SWEPCO).
4. FCC: ASN/499 setup; licensed-µW coordination for planned crossings; CBRS/AFC setup.
5. County ROW + zoning for pilot zone + shoreline yard.
6. Per-work-order checklists auto-enforced thereafter by DockOS.
