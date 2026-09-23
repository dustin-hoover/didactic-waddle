# 21 — Network Architecture Specifications (Engineering Design Spec)

> The buildable spec behind the concept in doc 03. Vendor-neutral (equipment **classes**,
> not brand lock — the swappable-electronics rule, doc 03 §1 / doc 10), but concrete enough
> to quote, order, and commission. Numbers are design targets; confirm against quotes,
> licensing, and the LiDAR link budgets (doc 05/07/18). Ties to: transit/ASN (doc 17),
> BOM kits (doc 10), enclosures/sites (doc 20), NMS/AAA software (doc 14).

## 1. Scope & governing standards
Covers T0–T4 (doc 03 §1): optical/RF transport, access, IP/routing, power, management,
security, and acceptance. Design to these standards:
- **PON:** ITU-T **G.9807.1 (XGS-PON)**, G.988 (OMCI).
- **Ethernet/transport:** IEEE 802.3 (incl. 802.3ca where relevant), MEF 3.0 CE for
  business EVCs; IETF SR-MPLS / **EVPN-VXLAN (RFC 7432/8365)** for the service overlay.
- **Routing:** BGP-4 (RFC 4271), **RPKI ROA/ROV (RFC 6480/6811)**, **MANRS** actions.
- **Wireless:** FCC **Part 96 (CBRS)**, **Part 15** (6 GHz/60 GHz unlicensed), **Part 101**
  (licensed microwave); 3GPP/OFDMA per radio vendor.
- **Grounding/bonding:** NEC Art. 800/810, **Motorola R56** practice; NEMA enclosure ratings.
- **Timing:** NTP (RFC 5905); PTP (1588) only if voice/mobile later.

## 2. Tier specifications (summary → detail below)
| Tier | Routing/role | Access/transport gear | Uplink | Power | Enclosure (doc 20) |
|------|--------------|------------------------|--------|-------|--------------------|
| **T0** head-end | Full BGP border + core, PE | Border router, core router, XGS-PON OLT, DWDM mux, CGNAT, AAA/DNS | 2× diverse transit (doc 17) | Grid + generator (N+1) | Shelter or pad cabinet |
| **T1** core/ring | P/PE, ring transport | Aggregation router/switch, licensed µW, OLT (optional) | Dual ring (µW + fiber) | Grid + UPS (+solar opt.) | Pad or pole cabinet |
| **T2** dock agg. | PE/CE, zone serving | nLOS PtMP sectors, OLT/splitter, backhaul radio | Ring or PtP to T1 | Grid or solar+battery | Pole/pad cabinet |
| **T3** relay | L2/L3 extension | 1 sector + PtP backhaul | PtP to T2 | Solar+LiFePO4 or PoE | Pole cabinet |
| **T4** CPE | Subscriber edge | nLOS/PtMP radio **or** XGS-PON ONT + router | Access link | Premises | CPE housing |

## 3. IP addressing & numbering plan
- **ASN:** one ARIN ASN (doc 17), multihomed to ≥2 upstreams on 2 diverse paths.
- **IPv6 (primary):** ARIN **/36** (doc 17/19). Hierarchical, nibble-aligned:
  - `/36` → **`/40` per region** (16) → **`/44` per service zone** (4,096 × /56 each) →
    **`/56` per subscriber** (256 × /64 for the customer LAN). A /36 holds ~1,048,576 /56s
    vs ~9,571 premises — ~100× headroom. *(Corrected: a /48 holds only 256 /56s, but our
    largest zone, Beaver Shores, has 1,272 premises — so zones get a /44.)* **Region 0
    (the first /40) is reserved** for **infrastructure** /48s (loopbacks, P2P links as
    /127, mgmt, one per POP/T1) and **services** (DNS/CGNAT/NOC); zone *k* gets /44
    #16+k. Implemented by the billing allocator (`software/api/billing.py`, doc 22).
- **IPv4 (bridged):** public **/24–/23** (waitlist + lease, doc 17) for the CGNAT public
  pool, infra loopbacks, BGP, DNS/mail, and **static-IP business/marina** accounts.
  Residential behind **CGNAT** using **RFC 6598 100.64.0.0/10** internally.
- **Loopbacks:** IPv6 /128 + IPv4 /32 per device from a reserved block; router-id = v4 loopback.
- **P2P links:** IPv6 /127; IPv4 /31 where v4 is needed.
- **DNS:** dual-stack recursive at each head-end (anycast the resolver IP); authoritative
  for boatdock.network; PTR delegation for our blocks.

## 4. Routing & switching design
- **Edge (T0):** eBGP to each upstream; accept default + full table (or default-only at
  pilot). **Outbound:** advertise only our aggregates. **Inbound policy:** localpref/AS-path
  prepending to balance the two paths; each path sized to carry 100% (1+1, doc 17).
- **Core/IGP:** **IS-IS** (or OSPFv3) for loopback/infra reachability, single area at this
  scale; BFD on all core adjacencies for sub-second failover.
- **Service overlay:** **SR-MPLS or EVPN-VXLAN** on the ring for per-zone L2/L3 separation
  (VRF/EVI per zone or per service class); simple routed L3 acceptable at pilot, migrate to
  overlay as zones grow (doc 03 §7).
- **Ring protection:** logical ring; IGP + FRR (TI-LFA / SR) reroutes the other way on any
  single break — target **< 50 ms** reconvergence for protected segments.
- **Subscriber sessions:** **IPoE + DHCPv6-PD/SLAAC** (preferred) or PPPoE for fiber;
  wireless CPE via RADIUS-authed IPoE. Prefix-delegate a /56 per sub.
- **Security of routing:** publish **ROAs** for all prefixes; **ROV** on eBGP; prefix + AS
  filters both directions; max-prefix limits; **BCP38** anti-spoofing at the edge.

## 5. Transport specifications
### 5.1 Fiber / optical (OSP)
- **Cable:** OS2 single-mode (G.652.D). ADSS for aerial, armored for buried, **armored
  submarine** for subaqueous cove crossings (doc 10).
- **XGS-PON (FTTH):** 10 Gbit/s symmetric; DS **1577 nm** / US **1270 nm**; **split 1:32**
  design (up to 1:64 where loss budget allows); power-budget class **N2/E1 (31–33 dB)**;
  design reach ≤ 20 km (we're well inside that). ONU per premises; OMCI-managed.
- **Loss budget:** compute per drop (connectors 0.3 dB, splices 0.1 dB, splitter 1:32 ≈
  17.5 dB, fiber 0.35 dB/km @1310 / 0.25 @1550); require ≥ 3 dB margin over class budget.
- **Metro/DWDM:** between head-ends and to transit — colored optics or muxponder; start
  10G waves, groom to 100G (doc 17 ramp).
### 5.2 Licensed microwave (lake crossings) — Part 101
- **Bands:** long over-water hops in **6 or 11 GHz** (rain-robust); shorter in 18/23 GHz.
- **Diversity:** **space diversity** (two vertically separated dishes) mandatory over water
  (multipath/ducting); ATPC + adaptive modulation.
- **Availability target:** **99.999%** per hop; compute fade margin with Vigants-Barnett
  over water, **including seasonal lake-level swing** and Fresnel + earth-curvature
  (the GIS LOS tool, doc 05). Licensed + frequency-coordinated (doc 12/19).
- **Capacity:** 1–10 Gbit/s/hop, upgradable by channel/XPIC or radio swap.
### 5.3 Unlicensed PtP (short backhaul)
- **60 GHz (V-band)** for short, high-capacity hops (rain-limited, ≤ ~1–1.5 km);
  **5 GHz** for longer, lower-capacity. Not for critical over-water spans.

## 6. Access specifications
### 6.1 Fixed wireless
- **nLOS PtMP (primary, tree-shadowed lake):** CBRS **3.55–3.70 GHz** (Part 96) and/or
  **6 GHz**; OFDMA, adaptive MCS. **CBRS requires a SAS account + CPI-certified installs**
  for CBSD registration (GAA spectrum; consider PAL later). This is the answer to the
  ~half-of-LOS-blocked finding (doc 18).
- **PtMP LOS (clean clusters):** 5/6 GHz sectored.
- **Tower heights:** **30–45 m** per the LiDAR viewshed (doc 07/18) to clear canopy;
  FAA check per site (doc 19 §6).
- **RF design targets:** link budget with ≥ **10 dB fade margin**; plan to modulation that
  holds the sold rate at cell edge; sector azimuth/downtilt from the viewshed model.
- **Spectrum reuse:** channel plan per zone to avoid adjacent-sector interference.
### 6.2 FTTH
- XGS-PON per §5.1 where density/business/host-node warrants (medium-selection rule,
  doc 03 §5). ONT hands off dual-stack; managed via OMCI + TR-069/USP where applicable.
### 6.3 Service profiles (map to plans, doc 06 / portal)
| Plan | Rate (sym) | Medium | Oversub target | Notes |
|------|-----------|--------|----------------|-------|
| Cove | 300 Mbps | FW/FTTH | ≤ 25:1 | residential |
| Shoreline | 1 Gbps | FW/FTTH | ≤ 20:1 | residential |
| Deep Water | 2–5 Gbps | FTTH | ≤ 10:1 | premium |
| Business/Marina | 1 Gbps–multi-gig | FTTH | **1:1 CIR option** | SLA-backed |

## 7. Site, power & environmental specs (per doc 20 enclosure)
- **Enclosure:** **NEMA-4X** (marine/lakeside) outdoor cabinets; shelter only where
  justified (doc 20 §1.5). Mounting above floodplain on pad or platform.
- **Thermal:** thermostatic filtered fans; **A/C or heat-exchanger** for OLT/router
  cabinets in sun; derate gear to 50 °C ambient.
- **Power:**
  - **T0:** commercial power + **standby generator (N+1)**; rack UPS for ride-through;
    dual PSUs on core gear; ATS.
  - **T1:** grid + **UPS (4–8 h)**; solar option; dual PSU on aggregation gear.
  - **T2/T3 remote:** **solar + LiFePO4** sized for **2–3 days autonomy** (doc 03 §6),
    MPPT charge controller, low-temp cutoff; PoE++ where a drop suffices.
  - DC plant (−48 V) at large sites; PoE injection at edge.
- **Grounding/bonding:** single-point ground, ground ring/rods, **lightning arrestors on
  every coax/antenna and copper line** (R56) — non-negotiable on exposed shoreline masts.
- **Physical security:** keyed-alike locks, **door/intrusion + temp + power alarms** to the
  NOC; camera at head-ends.
- **Cabling/labeling:** every port/fiber/circuit labeled to the naming convention (§10).

## 8. Capacity, performance & availability targets
- **Backhaul sizing:** each spine segment ≥ peak zone busy-hour demand × growth headroom;
  ring so either direction carries a segment's load on a break. Transit sized per
  `transit_sizing.py` (doc 17): 2×10G → 2×25G → 2×100G.
- **Latency:** intra-network one-way **< 10 ms** edge-to-head-end; to transit handoff per
  provider SLA; jitter < 5 ms for voice-ready service.
- **Availability:** head-end/core **99.99%**; licensed µW hops **99.999%**; access target
  **99.9%** (weather/solar caveats at remote T3). Track MTTR against the boat-dispatch model
  (doc 07).
- **Oversubscription:** per §6.3; monitor and split sectors/add waves before hitting 70%
  sustained busy-hour utilization.

## 9. QoS & traffic policy
- **Marking:** DSCP at edge; trust boundary at CPE/OLT. Classes: network-control, business
  CIR/real-time, standard, scavenger.
- **Shaping/policing:** per-plan rate at CPE/ONT/OLT; **business SLAs prioritized** with
  committed rate; fair-queue standard residential.
- **Congestion:** WRED on core; protect control-plane and business classes on any ring
  break (single-direction load).

## 10. Management, AAA & provisioning (feeds DockOS, doc 14)
- **AAA:** **RADIUS** (auth/acct) for wireless CPE and fiber IPoE/PPPoE; one source of
  truth with billing/provisioning (doc 14) — activate/suspend flows from billing state.
- **Provisioning:** **TR-069/USP** for routers/ONTs, **OMCI** for PON; zero-touch where
  possible; config templates per tier.
- **Telemetry:** **SNMPv3 + streaming (gNMI/gRPC)** and **NetFlow/IPFIX** from every T0–T3
  device into the NOC stack; syslog to a central collector; **NTP** everywhere.
- **OOB management:** out-of-band path to head-ends/core (cellular or Starlink at critical
  sites, doc 03 §6); management VRF isolated from customer traffic.
- **IPAM/DCIM:** authoritative IP + device + circuit inventory (in DockOS); every node has a
  GIS record + as-built before "live" (doc 03 §8).

## 11. Security & resilience
- **Routing:** RPKI ROA for all prefixes, ROV + prefix/AS filters + max-prefix on eBGP,
  BCP38/uRPF at edge, **MANRS**-compliant.
- **Control/management plane:** iACL + **CoPP**; SSH/HTTPS only, keys not passwords; RBAC;
  mgmt reachable only via OOB/VRF + jump host; MFA for admins.
- **DDoS:** upstream scrubbing/blackhole community support in the transit RFQ (doc 17);
  flow-based detection from NetFlow.
- **Subscriber isolation:** per-zone VRF/EVI; no L2 bridging between customers; DHCP
  snooping / RA-guard on access.
- **Backups:** nightly config export (git-backed), tested restore; documented DR for a
  head-end loss (the other head-end + ring carry the lake).
- **CPNI/voice:** if voice is added, layer CPNI, 911/E-911, lawful-intercept readiness
  (decision in doc 19 §5).

## 12. Naming, numbering & acceptance
- **Naming (doc 03 §8):** `BDN-{zone}-{tier}-{seq}`, e.g. `BDN-RockyBranch-T2-01`; loopbacks,
  links, and circuits derive from it.
- **Commissioning tests before "live":**
  - Fiber: **OTDR trace + optical power** within loss budget (§5.1), stored on the node record.
  - Wireless: measured RSSI/SNR/MCS + throughput at sold rate with fade margin (§6.1).
  - µW hop: received signal level vs predicted, fade-margin verification, diversity test.
  - IP: BGP session + ROA validity, failover drill (pull each path/ring direction),
    latency/throughput baseline, telemetry landing in NOC.
  - Power: UPS/solar autonomy check; alarm test to NOC; grounding continuity.
- **As-built** + GIS record + path calc filed = node marked live (doc 03 §8 / doc 05).

## 13. Related files
- Concept: `03-network-architecture.md` · BOM kits: `10-materials-and-bom.md` ·
  transit/ASN/IP: `17-middle-mile-transit.md` + `../procurement/arin_resource_request.md` ·
  enclosures/sites: `20-site-acquisition-and-real-estate.md` · regulatory/licensing:
  `12-regulatory-permitting.md` + `19-entity-formation-checklist.md` · software/NMS/AAA:
  `14-software-architecture.md`.

---
_Generated by [Claude Code](https://claude.ai/code)_
