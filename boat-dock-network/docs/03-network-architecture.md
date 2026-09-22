# 03 — Network Architecture

The design in one sentence: **two diverse internet on-ramps feed a redundant ring
spine (licensed microwave over water + fiber on land) that feeds zoned dock/aggregation
nodes, which serve premises by fiber or non-LOS wireless — chosen per address — all
sited to be built and repaired by boat.**

```
        INTERNET (multiple upstreams, BGP)
             │                    │
     ┌───────┴───────┐    ┌───────┴───────┐
     │  On-Ramp POP A │    │ On-Ramp POP B │   ← two dedicated-internet handoffs
     │  (Head-End)    │    │ (Head-End)    │     you've identified; diverse paths
     └───────┬───────┘    └───────┬───────┘
             │   PROTECTED CORE   │
             └─────────┬──────────┘
                       │
        ══════════ RING SPINE ══════════   ← licensed µW over water + fiber on land,
       ║                               ║      built as a ring so any one break heals
   [Core Node]                    [Core Node]
       ║                               ║
  [Dock Node]—[Relay]           [Dock Node]—[Relay]   ← zoned aggregation around lake
     │    │                          │    │
   FTTH  Fixed-Wireless           FTTH  Fixed-Wireless
     │    │                          │    │
  Premises (homes, docks, marinas, resorts, businesses, host-node sites)
```

---

## 1. Node taxonomy (drives GIS, BOM, and dispatch)

Every physical site is exactly one of these tiers. This taxonomy is the backbone of
the GIS model (doc 05), the BOM kits (doc 10), and the work-order system (doc 14).

| Tier | Name | Role | Typical contents | Power |
|------|------|------|------------------|-------|
| **T0** | On-Ramp / Head-End POP | Internet entry, core routing | Border routers, ASN/BGP, transport, DWDM/OLT, UPS+gen | Grid + generator |
| **T1** | Core / Ring Node | Spine transport & aggregation on high ground | Licensed µW + fiber, aggregation switch/router, OLT | Grid + UPS (+ solar option) |
| **T2** | Dock Aggregation Node | Neighborhood/zone serving point at/near shoreline | PtMP sector radios (Tarana/Cambium), PON OLT/splitter, backhaul radio | Grid or solar+battery |
| **T3** | Relay / Repeater | Reach shadowed coves & fingers | Small PtP backhaul + 1 sector or repeater | Solar+battery or PoE |
| **T4** | Customer Premise (CPE) | The subscriber | Fixed-wireless radio + router, or fiber ONT + router | Premises power |

**Adaptability rule:** T1–T3 enclosures, mounts, power, and backhaul are specced
technology-agnostic. The radio/PON electronics are swappable modules. Upgrading a
zone from PtMP to fiber, or from one radio generation to the next, is a module swap —
not a rebuild. This is how the outside plant stays adaptable for decades.

---

## 2. The protected core (your two on-ramps)

- Both on-ramps run **BGP** advertising our own ARIN IP space (get an **ASN + IPv4
  block + IPv6 /36** — /36 per doc 17/19 for the ARIN fee waiver). If either provider or
  path fails, traffic reroutes automatically.
- Each head-end POP has border router, core router, transport gear, UPS + generator
  hookup, and is the "root" of the ring in its half of the lake.
- Head-ends are also the natural home for shared services: DNS, CGNAT (if needed
  before full IPv6), RADIUS/AAA, NOC collectors, and the OLT for nearby FTTH.

## 3. The ring spine (crossing the lake)

- Built as a **logical ring** around and across the lake so a single fiber cut or
  faded microwave hop never isolates a zone — traffic flows the other way around.
- **Over water:** licensed microwave hops with **space diversity** (two vertically
  separated dishes), high masts, ATPC, adaptive modulation. Clearances computed against
  seasonal lake-level swing and Fresnel-zone + earth-curvature math (the GIS LOS tool,
  doc 05, automates this).
- **On land / around fingers:** fiber where a road/pole route is cheap; short
  unlicensed 60/5 GHz PtP where fiber isn't justified.
- **Capacity:** design each spine segment for peak zone demand × growth headroom,
  starting 1–10 Gbps/hop, upgradable by radio swap or added channels.

## 4. Zone & dock-node design

- The lake is divided into **service zones** (doc 04), each anchored by one or more
  **T2 dock aggregation nodes** on high, boat-reachable shoreline points — ideally on
  **host-node properties** (owner gets a discount).
- Each dock node covers its zone with **PtMP sectors** (Tarana for tree-shadowed
  spread; Cambium/Ubiquiti for clean-LOS clusters) and, where density warrants, a
  **PON OLT** feeding FTTH drops.
- **T3 relays** fill cove shadows and fingers the dock node can't see.

## 5. Per-address medium selection (the serviceability rule)

DockOS decides, for each service address, whether to serve by **fiber** or **wireless**
using this precedence (implemented as code in doc 14):

1. **Fiber** if the address is within economic drop distance of existing/planned fiber
   AND (business/marina/resort OR host-node OR density above threshold).
2. **Fixed wireless (nLOS/Tarana)** if a dock node/relay has an acceptable link budget
   to the premises (LiDAR-based LOS/foliage model, doc 05).
3. **Fixed wireless (PtMP LOS)** if clean LOS exists to a sector.
4. **Candidate for new relay/fiber extension** (goes into the build backlog, ranked by
   pre-sales demand) if none of the above clear.

## 6. Redundancy & resilience summary

| Failure | Mitigation |
|---------|-----------|
| One upstream provider/path down | Second diverse on-ramp + BGP reroute |
| Spine fiber cut / faded hop | Ring reroutes the other direction |
| Dock node power loss | UPS + solar/battery autonomy (2–3 days); generator for POPs |
| Radio/PON module failure | Hot-swappable module; boat-dispatched spare kit (BOM) |
| Node unreachable in storm | Solar autonomy holds; boat dispatch when safe; Starlink last-resort backhaul for critical nodes |

## 7. IP, transport & services architecture

> **Engineering-grade specs** (equipment classes, optical/RF budgets, full IP addressing
> plan, power/grounding, NMS, security, acceptance tests) are in
> **`21-network-architecture-specs.md`**. This section is the summary.

- **Own ASN + IPv6-first** (dual-stack, /36 hierarchical plan — doc 21 §3), CGNAT only as a bridge.
- **L2/L3:** MPLS or EVPN/VXLAN overlay on the ring for clean multi-service transport
  and per-zone VLAN/VRF separation; simpler routed design acceptable at pilot scale.
- **AAA:** RADIUS for wireless CPE and PPPoE/IPoE fiber sessions, integrated with
  billing (doc 14) so provisioning ↔ billing is one source of truth.
- **QoS:** per-plan rate limiting at the CPE/OLT; business/marina SLAs prioritized.
- **Monitoring:** SNMP/streaming telemetry from every T0–T3 device into the NOC stack.

## 8. Standards & documentation discipline

- Every node gets a **GIS record + as-built** before it's marked live (doc 05).
- Every link gets a **path calculation** (LOS, Fresnel, link budget, fade margin)
  stored with the node record.
- Every cabinet has a **standard build spec** so any tech can service any node.
- Naming convention: `BDN-{zone}-{tier}-{seq}` (e.g., `BDN-RockyBranch-T2-01`).
