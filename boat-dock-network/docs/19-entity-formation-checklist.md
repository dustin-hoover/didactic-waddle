# 19 — Entity Formation & Legal Setup Checklist

> The unlock for everything downstream: the ARIN Org (doc 17 needs a legal entity + EIN),
> the transit contracts, the member-capital campaign (doc 18 needs a co-op to hold member
> equity), and grant/loan eligibility. This is the ordered path from "an idea" to "a
> chartered Arkansas cooperative that can sign, hire, and take money."
>
> **Not legal or tax advice.** Every item below should be run past **cooperative +
> securities + telecom-regulatory counsel** and a **co-op-savvy CPA** before filing. Fees
> and forms verified against the Arkansas SoS and FCC, Sept 2026 (sources at bottom).

## 0. Recommended structure (decide first, with counsel)
- **Vehicle:** an **Arkansas Telecommunications Cooperative** under the **Rural Telephone
  Cooperative Act (Act 51 of 1951)** is the closest-fit chartered co-op form — the SoS
  issues "Articles of Incorporation of Telephone Cooperative," and the name must contain
  **"Telephone Cooperative," "Telecommunications Cooperative,"** or the like. This is the
  vehicle Arkansas electric/telephone co-ops use for broadband subsidiaries.
  - *Alternative:* a **general cooperative** (Cooperative Marketing Association form) if
    counsel prefers to avoid the telephone-act framing for a broadband-only ISP. Trade-off:
    the telecom-co-op form aligns with future voice service and co-op-to-co-op transit
    (DSN/OzarksGo, doc 17); the general form is simpler but less telecom-native.
  - **Decision to make:** telecom-co-op vs general-co-op. Lead recommendation:
    **Telecommunications Cooperative.**
- **Tax treatment:** operate under **Subchapter T** (patronage dividends — doc 09/18).
  Confirm with the CPA; this is what keeps member capital non-securitized and the WAKE
  governance token non-economic (doc 16/18).
- **Governance:** tenure-earned **WAKE** voting units + capped voting (doc 16); **capital
  never buys votes** (doc 18). Bake both into the bylaws.

## 1. Pre-formation
- [ ] **Engage counsel** (cooperative + securities + telecom) and a **co-op CPA**.
- [ ] **Pick + clear the name** — must carry "Telecommunications Cooperative" (or per the
      chosen vehicle). Search the SoS business database; reserve if needed. Grab the
      matching domain (boatdock.network is in use in the prototype) + role emails.
- [ ] **Incorporators** — line up the minimum number of incorporators the act requires
      (confirm count with counsel).
- [ ] **Registered agent + registered office** in Arkansas (required for all entities;
      can be a person or a commercial agent).
- [ ] **Principal office** address (a lakeside parcel decision ties to doc 04 / head-end).

## 2. State formation (Arkansas Secretary of State — BCS)
- [ ] **File Articles of Incorporation** — "Articles of Incorporation of Telephone
      Cooperative," **$10 filing fee** (general-co-op form is $5). File online (ark.org)
      or mail BCS, State Capitol, Little Rock AR 72201. (888-233-0325 / 501-682-3409.)
- [ ] Articles content (with counsel): name, purpose (broadband + telecom + related
      services), registered agent/office, member/stock structure, incorporators, duration.
- [ ] **Adopt bylaws** (membership, WAKE governance + capped voting, board, patronage/
      Subchapter T, capital instruments per doc 18, exit/redemption of shares & WAKE).
- [ ] **Organizational meeting** — seat the initial board, appoint officers, adopt bylaws,
      authorize bank accounts + the ARIN Org, approve the member/subscriber agreement.
- [ ] **Confirm annual obligations** — Arkansas requires an **annual report/annual
      franchise filing**; confirm the cooperative's exact annual report form + any
      **franchise tax** (now administered by AR DFA) applicability/exemption for co-ops.

## 3. Federal tax & identity
- [ ] **EIN** from the IRS (free, online) — **needed for the ARIN Org, bank, and payroll.**
- [ ] Confirm **Subchapter T** cooperative tax posture with the CPA; set up patronage
      capital / allocation accounting to match doc 09.
- [ ] Set up **role email + accounting** so member capital (doc 18) is booked to segregated
      escrow, never OpEx.

## 4. Arkansas state tax & registration (DFA)
- [ ] Register with **Arkansas DFA** (Dept. of Finance & Administration) for state tax
      accounts.
- [ ] **Sales/use tax permit** — for CPE sales, installation, and taxable services; confirm
      taxability of broadband vs equipment with the CPA.
- [ ] Employer accounts — **AR withholding + unemployment (DWS)** once staff are hired
      (ties to the staffing plan, doc 08).

## 5. FCC / telecom regulatory (facilities-based provider)
- [ ] **FRN via CORES** — get the FCC Registration Number first; it gates every other FCC
      system.
- [ ] **Broadband Data Collection (BDC)** — as a **facilities-based fixed broadband
      provider**, file availability data (the successor to Form 477 block data);
      **semiannual**. Our GIS (docs 05/GIS outputs) already produces the coverage polygons
      this needs.
- [ ] **Form 499 / USF** — required if we earn **telecommunications/interconnected-VoIP**
      revenue (USF contributor). **Pure Title I broadband is generally exempt** — but the
      moment we add voice, this triggers (plus CPNI, 911/E-911, Form 499-A/Q). Decide the
      voice question early with counsel.
- [ ] **214 authorization** — only if we offer **interconnected voice / international**;
      not needed for broadband-only.
- [ ] **Arkansas PSC** — **pure broadband is not rate-regulated**; if we offer regulated
      telecom/voice, file for a **Certificate of Public Convenience & Necessity (CPCN)**
      with the AR Public Service Commission. Confirm scope with counsel.

## 6. Rights-of-way, poles & the lake (Beaver Lake specifics)
- [ ] **USACE (U.S. Army Corps of Engineers, Little Rock District)** — Beaver Lake is a
      **federal Corps reservoir**; shoreline structures, cable/lake crossings, and
      shoreline use need **USACE Shoreline Management permits/easements**. This is central
      to a **boat-served, dock-delivered** network — start early; it's a long lead.
- [ ] **Pole attachment agreements** — with the electric co-op(s)/utilities whose poles we
      use (Ozarks Electric et al.); governed by FCC pole-attachment rules or AR equivalent.
- [ ] **AR DOT + county/city ROW** permits for road crossings and buried/aerial runs
      (Benton, Washington, Carroll counties).
- [ ] **Arkansas One Call (811)** membership — required before any digging (locate tickets).
- [ ] **FAA** — check tower heights (30–45 m nodes, doc 07/LiDAR) against FAA notice/marking
      thresholds; most short towers are exempt but confirm per site.

## 7. Money, securities & risk
- [ ] **Business bank + segregated escrow** account (doc 18 money flow) — set up under the
      EIN after formation.
- [ ] **Securities review (doc 18)** — confirm the **membership share / reservation deposit
      / founding capital** instruments qualify under **cooperative securities exemptions**
      (federal + **Arkansas Securities Department**); prepare member disclosures + risk
      statement. Keep **capital ≠ governance** explicit in the bylaws.
- [ ] **Insurance** — general liability, commercial auto **+ watercraft/marine** (the boat
      fleet, doc 07/08), property, cyber, D&O for the board, workers' comp.
- [ ] **Lender readiness** — cooperative debt (CoBank / RTFC / Rural Utilities Service):
      they lend to chartered co-ops; formation + audited-ready books unlock this (doc 13).

## 8. Local (counties & cities)
- [ ] County business registration where required — **Benton, Washington, Carroll**.
- [ ] **Municipal ROW / franchise agreements** for any incorporated-city plant
      (Rogers, Bentonville, Eureka Springs, etc.).
- [ ] Local business licenses per jurisdiction.

## 9. Critical path (do these in order)
1. Counsel + CPA engaged → structure decided (§0).
2. Name cleared, registered agent set (§1).
3. **Articles filed** with SoS (§2) → **entity exists**.
4. **EIN** (§3) → then **ARIN Org + ASN/IP** (doc 17) and **bank + escrow** (§7).
5. Bylaws + org meeting (§2) → can **sign transit contracts** (doc 17) and **take member
   capital** (doc 18).
6. FCC FRN + BDC registration (§5); USACE + pole + ROW applications started (§6) — long
   leads, run in parallel from step 3.

## Sources (verified Sept 2026)
- Arkansas SoS — Cooperative forms & fees (Telephone Cooperative Articles $10; Cooperative
  Marketing Association $5): https://www.sos.arkansas.gov/business-commercial-services-bcs/forms-fees/cooperative
- Arkansas SoS — Corporations FAQs (filing process, annual reports):
  https://www.sos.arkansas.gov/business-commercial-services-bcs/frequently-asked-questions-faqs/corporations-faqs
- Rural Telephone Cooperative Act framing (Act 51 of 1951) — Telecommunication Cooperative
  Articles: https://forms.justia.com/arkansas/secretary-of-state/cooperative/articles-of-incorporation-of-telecommunication-33184.html
- FCC — Who Must File Form 477 / facilities-based providers:
  https://transition.fcc.gov/form477/WhoMustFileForm477.pdf
- FCC — Broadband Data Collection (BDC) FAQs:
  https://help.bdc.fcc.gov/hc/en-us/articles/7682769466395-Broadband-Data-Collection-BDC-FAQs

---
_Generated by [Claude Code](https://claude.ai/code)_
