# 01 — Technology Review

Goal: pick the best *available* technology to deliver gigabit around a heavily wooded,
hilly, water-broken Ozark reservoir — cost-effectively and adaptably. This review is
organized by network layer and ends with a concrete recommended stack.

The defining physical constraints at Beaver Lake:

- **Trees.** Dense hardwood/pine cover kills clean line-of-sight (LOS) for most
  premises. This single fact drives us toward **non-line-of-sight (nLOS/NLOS)** radios
  and toward fiber wherever density justifies it.
- **Terrain.** Ridges and deep coves create RF shadows but also give us high points
  for aggregation and relay sites.
- **Water.** The lake is both our highway and our biggest asset: we can shoot long,
  clean links *across* the water — but over-water RF has its own physics (multipath).
- **Federal shoreline.** USACE controls the shoreline (see doc 12); node siting must
  respect that.

---

## 1. Internet on-ramps (transit / middle-mile)

Two diverse dedicated-internet handoffs form a **protected core** (one fails, the
other carries the lake). Candidates in NW Arkansas include regional fiber providers
and cooperatives (e.g., OzarksGo / Ozarks Electric, Carroll Electric fiber, and
national carriers reaching Rogers/Bentonville). Requirements:

- **Diversity:** physically separate paths and, ideally, separate providers, so no
  single fiber cut or provider outage darkens the whole lake.
- **Scalable ports:** start 2 × 10 GbE, with a clear upgrade to 100 GbE.
- **BGP + our own IP space:** get an ARIN ASN and a portable IPv4 block + IPv6 /32 so
  we're carrier-independent and can multi-home. This is a low-cost, high-leverage move.

> Action: request quotes from both of your identified locations at 10G and 100G, with
> and without transport to our two head-end POPs.

---

## 2. Core & transport (the spine around/across the lake)

The spine is a **ring** so any single break heals. It mixes media:

### 2a. Fiber transport
- **Single-mode (OS2)**, 288–864 count on primary routes; ADSS (all-dielectric
  self-supporting) for aerial spans on poles (no bonding/grounding, good long spans),
  armored direct-bury or duct where underground.
- Use fiber for the spine wherever we already need to run it for FTTH anyway, or where
  a road/pole route is cheap.

### 2b. Licensed microwave (the lake crossings) — **recommended for the spine**
- **Why licensed:** coordinated frequencies mean no interference and FCC-protected
  reliability — essential for backbone hops you can't easily reach to fix.
- **Bands:** 6, 11, 18, 23 GHz depending on hop length and rain considerations.
- **Vendors:** Aviat, Ceragon, RADWIN, SIAE. Capacities from 1 Gbps to 10 Gbps per
  hop with adaptive modulation.
- **Over-water engineering:** water is a near-perfect RF mirror, so the reflected ray
  can arrive out of phase and fade the link. Mitigate with **space diversity** (two
  vertically separated antennas), higher antenna heights, ATPC (automatic transmit
  power control), and adaptive modulation. Account for **lake-level variation** when
  computing clearances (Beaver Lake pool moves seasonally). This is standard practice
  for over-water links and is very achievable across coves and open water.

### 2c. Unlicensed high-capacity PtP (short spine hops & backhaul to dock nodes)
- **Ubiquiti airFiber:** AF60-LR / GBE (60 GHz with 5 GHz failover) for multi-gig at
  short range; AF11FX (licensed 11 GHz) and 5 GHz XHD for longer gigabit hops. Cheap,
  huge ecosystem.
- **Cambium cnWave 60 GHz (V5000/V3000):** gigabit PtP and mesh.
- **Siklu EtherHaul (60/70–80 GHz):** carrier-grade mmWave gigabit for dense/short.

**Recommendation:** licensed microwave for the *critical* over-water/long spine hops
(reliability you can't boat out to babysit), unlicensed 60/5 GHz for shorter, cheaper,
easily-reachable hops and dock-node backhaul. Design the spine as a ring so a faded
hop is never a single point of failure.

---

## 3. Access layer (getting to the premises)

Two access technologies, chosen per-premise by a serviceability rule (see doc 03):

### 3a. Fiber to the home/business (FTTH) — where density/terrain justify it
- **XGS-PON** (10 Gbps symmetric) is the right PON choice today — future-proof over
  GPON. OLT at dock/POP nodes; 1:32 or 1:64 splits; ONT at premises.
- Active Ethernet for demanding business/marina customers.
- **Drops:** aerial flat/self-support drop, or underground armored drop / microduct +
  blown fiber. **HDD (directional boring)** for driveway and road crossings.
- **Micro-trenching** along road edges dramatically cuts underground cost where rock
  allows.
- **Subaqueous fiber** (double-armored submarine-rated cable) can cross a cove
  directly instead of routing all the way around — but requires USACE permitting and
  careful anchoring; treat as a selective tool, not the default (the wireless spine is
  usually cheaper and permit-lighter for crossings).

### 3b. Fixed wireless — where fiber is uneconomic or blocked
- **Tarana G1 — the foliage/nLOS game-changer.** Purpose-built for non-line-of-sight;
  works through trees and around obstructions where traditional radios fail, on CBRS
  (3.5 GHz) and 5/6 GHz. Higher per-unit cost, but it *serves premises other radios
  can't*, which in the Ozarks is the whole ballgame. This is likely our workhorse
  access radio for tree-shadowed shorelines.
- **Cambium PMP 450m / 450v (PtMP)** and **ePMP 4600 (6 GHz)**: proven, cost-effective
  sectored access for cleaner-LOS clusters.
- **Ubiquiti airMAX / LTU:** lowest cost, good for LOS clusters and marinas.
- **CBRS (3.5 GHz):** better foliage penetration and a lightly-licensed framework
  (SAS-coordinated) that reduces interference — strong fit for lakeshore trees.

**Recommendation:** Tarana G1 (CBRS/6 GHz) as the primary access workhorse for
tree-heavy shoreline; Cambium/Ubiquiti PtMP for clean-LOS clusters and marinas; FTTH
for dense pockets, businesses, resorts, and any host-node property.

---

## 4. Node power & resilience

- **PoE + local UPS** at small nodes; rack UPS + generator hookup at POPs.
- **Solar + battery** for remote relay/dock nodes without easy grid power — sized for
  Ozark winter sun with 2–3 days autonomy. This also decouples us from a host's power
  bill.
- **Environmental:** NEMA-4X / marine-rated enclosures; surface-water-protection
  discipline (no leaking batteries near a drinking-water reservoir — Beaver Lake is
  NWA's drinking source; see doc 12).

---

## 5. Complementary / competitive tech to respect

- **Starlink (LEO satellite):** the incumbent "good enough" option for isolated docks.
  We beat it on latency, price stability, consistency, and local support — and we can
  *use* it as an emergency backhaul of last resort for a stranded node.
- **Terragraph / 60 GHz mesh:** interesting for dense marina/village clusters.
- **Incumbents:** Cox, Sparklight (Cable One), AT&T, plus cooperative fiber
  (OzarksGo, Carroll) — strong in town, thin on the actual shoreline coves. Our wedge
  is the shoreline they don't reach.

---

## 6. Recommended stack (the short version)

| Layer | Choice | Why |
|-------|--------|-----|
| On-ramps | 2 diverse transit handoffs, BGP + own ASN/IP | Redundancy + carrier independence |
| Core | Ring: licensed microwave over water + fiber on land | Reliability where we can't easily reach |
| Short backhaul | Ubiquiti airFiber / Cambium cnWave 60 GHz | Cheap multi-gig |
| Access (trees) | **Tarana G1 (CBRS/6 GHz)** | Serves nLOS premises others can't |
| Access (clean LOS) | Cambium PMP / Ubiquiti LTU | Cost-effective sectors |
| Access (dense/biz) | **XGS-PON FTTH** | Future-proof symmetric gig+ |
| Power | PoE/UPS + solar-battery for remote | Reachability, resilience |
| Enclosures | NEMA-4X / marine-rated | Lake + water-source rules |

**Design principle: technology-agnostic sites.** Every node cabinet is specced so the
radio/PON module inside can be swapped as tech improves. The *outside plant* (mounts,
power, backhaul, enclosure) is the durable, adaptable investment; the electronics are
the cheap, replaceable part. This is what makes the physical design "adaptable" per
your requirement.
