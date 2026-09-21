# 17 — Middle-Mile & Internet Transit (to firm up)

> Captured for the circle-back. Goal: buy the actual internet capacity that feeds the
> two head-end POPs (doc 03) — diverse, scalable, and priced right. Verify all provider
> specifics and pricing with quotes; this is a planning map, not a quote.

## What we're buying

Two things, often from different vendors:
1. **IP transit** — the actual route to the internet (a blend of upstreams, or a
   transit provider), delivered as Gbps at a handoff. Start **2 × 10 GbE**, scale to
   **N × 100 GbE**. Bring our **own ASN + IPv4/IPv6** (ARIN) and run **BGP** so we're
   carrier-independent and can multi-home (doc 03 §2).
2. **Transport / wavelengths (DWDM)** — getting that capacity from a carrier POP to our
   two head-ends on **diverse physical paths**. This is where OzarksGo's DWDM fits: a
   lit wavelength (10G/100G) or dark fiber between their POP and ours.

Diversity is the whole point: two providers *and* two physical paths so no single cut
or vendor outage darkens the lake.

## Candidate providers (NW Arkansas — verify current offerings)

| Provider | Role | Notes |
|----------|------|-------|
| **OzarksGo / Ozarks Electric** | Transport (DWDM), possibly transit | Fiber-rich in NWA; you noted they have DWDM. Likely wavelength or dark-fiber handoff near the lake. Co-op-to-co-op relationship is a plus. |
| **Carroll Electric / fiber** | Transport (east/Carroll side) | Serves the Eureka/Carroll shoreline; possible second-path handoff. |
| **Uniti Fiber** | Dark fiber / wavelengths / transit | Large regional wholesale fiber; Little Rock–NWA routes. |
| **Aristotle** | Transit / transport | Arkansas ISP/wholesale. |
| **Cox Business / Cox Wholesale** | Transit + transport | Metro fiber in Rogers/Bentonville/Fayetteville. |
| **AT&T Wholesale / Lumen (CenturyLink)** | Transit + long-haul transport | National backbones through the region. |
| **Ritter Communications / others** | Regional wholesale | Check footprint near the lake. |

> ARE-ON (Arkansas Research & Education Optical Network) is education/research only —
> not available to a commercial ISP; note but don't plan on it.

## The decision (why we may not use OzarksGo alone)

- **Path/vendor diversity:** if both head-ends buy from OzarksGo on the same route,
  we're single-vendor / single-path. Pair OzarksGo (one head-end/path) with a **second
  provider on a physically diverse route** (e.g., Uniti / Cox / Lumen) for the other.
- **Transit vs transport split:** OzarksGo DWDM may be great **transport** but not the
  cheapest **IP transit**; we can buy a wavelength from them and blended IP transit from
  a transit specialist, terminating both at our head-ends.
- **Scalability:** confirm a clean 10G→100G upgrade path and pricing tiers (cost/Mbps
  drops sharply at 10G+ and again at 100G — model per the ASSUMPTIONS transit dial).

## Action list (for the circle-back)
1. Get quotes from **≥3**: OzarksGo (DWDM wavelength + transit if offered), one national
   (Lumen/Cox/AT&T), one regional wholesale (Uniti/Aristotle). Ask for 10G and 100G,
   with and without transport to each of our two head-end sites.
2. Confirm **physical path maps** to prove diversity between the two head-ends.
3. Get **ARIN ASN + IPv4 block + IPv6 /32** in parallel (long lead; do early).
4. Nail down **handoff locations** — this may drive the "buy a small lakeside parcel
   near a fiber-rich POP" decision (doc 04 §3).
5. Feed real $/Mbps into `docs/ASSUMPTIONS.md` (transit dial) and re-run the pro forma.

## Model hook
The pro forma's `opex_transit_backhaul` line (doc 09) is the placeholder for this. Once
we have quotes, replace the planning estimate ($0.30–1.50/Mbps tiered) with real
committed-rate + overage terms and per-head-end transport lease costs.
