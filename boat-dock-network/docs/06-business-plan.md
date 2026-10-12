# 06 — Business Plan

## 1. Executive summary

**Boat Dock Network (BDN)** is a hybrid fiber + fixed-wireless internet service
provider delivering symmetric gigabit-class internet to homes, businesses, marinas, and
resorts around the entire perimeter of Beaver Lake, Arkansas. BDN uses the lake itself
as its right-of-way and logistics network: nodes are sited on shoreline high points and
boat docks, links cross the water on a redundant licensed-microwave spine, and every
install and repair is performed by specialized **boat-based** field technicians.
Property owners who host a network node receive a service discount, creating a
coverage-expanding flywheel. The whole operation runs on **DockOS**, an open-source-
first software platform for GIS/OSP, signup, billing, monitoring, outage management,
boat dispatch, and procurement.

The opportunity: thousands of lakeshore premises are poorly served by incumbents who
built for towns, not coves. BDN is purpose-built for the shoreline.

## 2. Market

- **Geography:** ~449 miles of shoreline, ~28,000 acres, three counties (Benton,
  Washington, Carroll) in fast-growing NW Arkansas.
- **Demand drivers:** remote work, second-home/vacation-rental growth, marinas and
  resorts needing reliable connectivity, and weak shoreline broadband today.
- **Addressable premises (planning):** ~9,000 *(estimate; firm with GIS)* — mix of
  year-round homes, seasonal/vacation homes, and ~120 commercial sites.
- **Competition:** Cox, Sparklight (Cable One), AT&T, cooperative fiber (OzarksGo,
  Carroll), and Starlink. Strong in town, thin on the actual coves — our wedge.
- **Willingness to pay:** lakeshore property owners skew higher-income; reliability and
  local service beat price as the deciding factors.

## 3. Product & pricing

### Residential (symmetric, no data caps)
| Tier | Speed | Price/mo *(planning)* |
|------|-------|-----------------------|
| Cove | 300 Mbps | $69 |
| Shoreline | 1 Gbps | $89 |
| Deep Water | 2–5 Gbps (fiber where available) | $129–$199 |

### Business / marina / resort
| Tier | Speed | Price/mo *(planning)* |
|------|-------|-----------------------|
| Dock Business | 1 Gbps + static IP | $199 |
| Marina Managed | multi-gig + managed Wi-Fi for slips | $399–$1,200 |
| Resort/Enterprise | custom + SLA | custom |

### Add-ons
Managed Wi-Fi, static IPs, VoIP, marina guest Wi-Fi, seasonal "snowbird" pause plans,
priority business SLA, RV/marina transient access.

### Host-node program (the flywheel)
Property owners hosting a node get a tiered benefit:
| Node tier hosted | Benefit *(planning)* |
|------------------|----------------------|
| T3 relay | $25/mo credit |
| T2 dock node | $75/mo credit or free Shoreline tier |
| T1 core / land lease | free service + lease payment / equity option |

Benefits are contract-termed, tied to site access + power + easement, and modeled as
a customer-acquisition + real-estate cost (doc 09).

## 4. Revenue model

Recurring subscription ARPU (residential blended ~$89, business blended ~$260) plus
one-time install fees (often promoted to $0), plus managed-service add-ons. Revenue
scales with **passings × take-rate**; the host-node program lifts both coverage and
take-rate.

## 5. Go-to-market

1. **Zone-by-zone pre-sales.** Before building a zone, collect refundable deposits /
   sign-ups via the signup portal (doc 14). Build where demand clears the threshold.
2. **Host-node recruiting** in each zone (best high points + docks) — doubles as
   coverage engineering and anchor-customer acquisition.
3. **Local presence:** boat-branded techs, marina partnerships, lake associations, HOA
   meetings, county fairs. "The lake's own internet company."
4. **Referral flywheel:** neighbors refer neighbors; host nodes advertise coverage.
5. **Marina/resort B2B** as lighthouse accounts with visible, high-traffic Wi-Fi.

## 6. Competitive advantages

- Lake-as-ROW + boat-native ops (cost + speed on the shoreline).
- nLOS wireless + fiber hybrid reaches premises incumbents skip.
- Host-node flywheel (coverage + loyalty + referrals).
- Software-run efficiency (low OpEx per subscriber).
- Local trust and responsiveness.

## 7. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| USACE/permitting delays | Start permitting early; wireless spine reduces shoreline construction; dedicated permitting role (doc 08/12) |
| Over-water RF reliability | Licensed µW + space diversity + ring redundancy |
| Thin take-rate in sparse zones | Pre-sales gating; demand-driven long tail |
| CapEx overrun (rock/make-ready) | Micro-trench/aerial/wireless mix; phase-gated spend |
| Incumbent price response | Compete on reliability/service/symmetry, not just price |
| Key-person/skill scarcity | Strong JDs, cross-training, documented standards, DockOS |
| Weather/seasonality of boat ops | Safety SOP, seasonal scheduling, solar autonomy on nodes |
| Financing/grant timing | Blended stack; phase spend to funding (doc 13) |

## 8. Legal/entity & structure (see doc 12 for detail)

- Form an **Arkansas LLC** (or co-op if pursuing the member model); register with AR
  Secretary of State; obtain EIN.
- File as a broadband/telecom provider as required; register for **FCC Form 499** and
  **BDC (Broadband Data Collection)** obligations once operating.
- Consider a **holding structure**: OpCo (ISP) + PropCo (owns strategic lakeside
  parcels/towers) for tax and financing flexibility — discuss with counsel/CPA.
- **Cooperative + DAO ownership (see doc 16).** BDN is designed as a **member
  cooperative**: members earn a non-transferable, tenure-weighted governance unit
  (**WAKE**, 1/month, capped) and share surplus via **patronage dividends**. This
  separates governance (token, non-security) from economics (dividends) so the co-op
  gets a genuine community-ownership story without triggering securities law or
  scaring lenders/grantors. Host-node members accrue WAKE at 1.5×.

## 9. Milestones (ties to doc 15)

1. Entity + ASN/IP + two transit LOIs.
2. GIS-verified passings + pilot-zone design + permits filed.
3. Pilot zone live (incl. one lake crossing) with paying customers.
4. Central region built; grant/loan financing closed.
5. Ring closed; long-tail demand-driven expansion.
