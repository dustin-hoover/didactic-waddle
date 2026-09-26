# 02 — Comparable Networks & Precedents

You are not doing something unprecedented — you're combining proven models in a
specific geography. Here's who has done the pieces, what worked, and what to steal.

> Note: descriptions below are drawn from general industry knowledge as of early 2026.
> Verify current specifics (ownership, funding, footprint) before citing in a grant
> application or investor deck.

## 1. Rural WISPs (Wireless ISPs) — the operational template

Thousands of small WISPs profitably serve rural America with fixed wireless from
towers/silos/water tanks to homes. Takeaways:
- **PtMP economics work** when you concentrate subscribers per sector and reuse tall
  assets. Our "tall assets" are ridges, existing towers, and dock/mast nodes.
- **nLOS radios changed the game.** WISPs adopting Tarana-class gear now serve
  customers they previously had to turn away for tree cover — exactly our problem.
- **The hybrid trend:** successful WISPs are becoming "WISP + fiber," overbuilding
  their densest areas with FTTH while keeping wireless for the long tail. That's our
  model from day one.

## 2. Electric & telephone cooperatives building fiber — the funding template

Since ~2016, electric co-ops across Arkansas and the region (e.g., OzarksGo from
Ozarks Electric; Carroll Electric's fiber effort) have built FTTH to members, often
funded by **RDOF, USDA ReConnect, and state grants**. Takeaways:
- **Poles + right-of-way are the moat.** Co-ops win because they already own poles and
  easements. We don't — so **pole-attachment agreements** (with Ozarks Electric,
  Carroll Electric, SWEPCO) and the **lake itself as our right-of-way** are our
  equivalents. The lake ROW is genuinely differentiating: nobody else routes by water.
- **Grant stacking is normal and expected.** These builds routinely blend federal +
  state + low-interest RUS/CoBank debt. See doc 13.
- **The host/member incentive** (members get service + governance) maps directly to
  our **host-node discount** program.

## 3. Community / municipal broadband — the take-rate lesson

Networks like Chattanooga's EPB, RS Fiber (Minnesota co-op), and many others show:
- **Take rates of 40–60%+** are achievable when the incumbent is weak and the
  community is engaged. Beaver Lake's shoreline is under-served → our 42% assumption is
  conservative-to-reasonable.
- **Local presence and trust** drive adoption more than marketing spend. "The company
  whose techs arrive by boat and live on the lake" is a powerful local brand.
- Arkansas historically restricted *government-owned* broadband (Act 1050 of 2011),
  later loosened (Act 198 of 2019 and subsequent). **This matters only if a
  municipality partners;** as a private company you're unaffected — but a public-private
  structure could unlock public assets. (Verify current AR municipal-broadband law with
  counsel; see doc 12.)

## 4. Over-water and island networks — the RF precedent

Fixed wireless across water is well-established:
- **Island and lake communities** worldwide are served by PtP/PtMP links shot across
  water (e.g., Scottish islands via community networks, Great Lakes island links, many
  marina networks).
- **Utilities and ISPs** routinely run licensed microwave across bays, rivers, and
  reservoirs using **space diversity** to defeat over-water multipath.
- **Marina Wi-Fi / dock networks** are a mature niche — we absorb this as a product
  line (managed Wi-Fi for marinas, resorts, and multi-slip docks).

Lesson: crossing Beaver Lake wirelessly is normal engineering, not a moonshot. The
novelty is doing it *systematically around an entire reservoir* as an ISP spine, and
servicing it by boat.

## 5. Fixed-wireless + FTTH hybrids at scale — the architecture precedent

Regional operators increasingly run one OSS/BSS across both fiber and wireless
subscribers, choosing the medium per address. That's precisely DockOS's serviceability
engine (doc 14). We're adopting a proven architecture, not inventing one.

## 6. What's genuinely novel here (your moat)

1. **The lake as primary right-of-way and logistics network.** Boat-native build and
   service is a real cost and speed advantage on a 449-mile, cove-riddled shoreline
   where road access is slow and indirect.
2. **A single reservoir treated as one engineered system** — ring spine + zoned dock
   nodes + per-address medium selection.
3. **Host-node flywheel:** every property that hosts a node both extends coverage and
   becomes a discounted, loyal, referral-generating customer.
4. **Software-run operation** purpose-built for boat dispatch and Ozark permitting.

## 7. Risks these precedents also teach

- **Make-ready and permitting delays** are the #1 schedule killer for co-op/WISP
  builds. Our USACE shoreline exposure (doc 12) is the analog — start permitting early.
- **Over-building where take-rate is thin** burns capital. Phase by density and
  pre-sales (doc 15), don't build speculatively.
- **Under-capitalizing the NOC/support function** erodes the local-trust advantage.
  Fund operations, not just construction.
