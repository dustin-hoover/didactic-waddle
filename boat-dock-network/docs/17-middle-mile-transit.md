# 17 — Middle-Mile & Internet Transit

> Goal: buy the internet capacity that feeds the two head-end POPs (doc 03) —
> diverse, scalable, cost-effective, and (ideally) co-op-aligned. Pricing is not public;
> the numbers here are planning-grade — send the RFQ (`../procurement/transit_rfq.md`)
> to get real quotes. Not legal/financial advice.

## 1. Key finding: a co-op wholesale middle-mile already exists

**Diamond State Networks (DSN)** is a wholesale, carrier-neutral middle-mile provider
formed by **13 Arkansas electric cooperatives — OzarksGo/Ozarks Electric among them** —
with **50,000+ route-miles** of fiber (800G-capable) covering ~64% of the state, built
specifically to sell transport to ISPs and WISPs. That is almost exactly our need, and
it's **co-op-to-co-op** — aligned with BDN's cooperative model and the grant-free,
community-owned story (doc 16). OzarksGo's DWDM you mentioned is part of this fabric.

**Implication:** lead with **DSN / OzarksGo for transport on one path**, and pair it
with a **physically diverse second carrier** (national or regional) for the other path,
so we are never single-vendor or single-route.

## 2. What we're actually buying (two things, often two vendors)

1. **Transport / wavelengths (DWDM) or dark fiber** — getting capacity from a carrier
   POP to each of our two head-ends, on **diverse physical paths**. DSN/OzarksGo fits
   here (lit 10/100G waves or dark fiber).
2. **IP transit** — the actual route to the internet (blended upstreams). Bring our
   **own ARIN ASN + IPv4 block + IPv6 /32** and run **BGP** so we multi-home and stay
   carrier-independent (doc 03 §2). Buy transit from whoever is cheapest/best per Mbps;
   it can ride the DSN transport or come from the second carrier.

Diversity is the whole point: **two vendors AND two physical paths** so no single cut or
provider outage darkens the lake.

## 3. How much to buy (capacity plan)

From `software/finance/transit_sizing.py` → `../data/financial/transit_plan.csv`
(busy-hour demand × business uplift × headroom; **each of two on-ramps sized to carry
the whole load if the other fails — 1+1 redundancy**):

| Year | Subs | Peak (Gbps) | Provision (Gbps) | Ports (each path) | Est. $/yr |
|------|------|-------------|------------------|-------------------|-----------|
| Y1 | 835 | 2.7 | 3.8 | 10G ×2 | ~$58k |
| Y2 | 1,889 | 6.9 | 9.6 | 10G ×2 | ~$92k |
| Y3 | 2,963 | 12.3 | 17.3 | 25G ×2 | ~$127k |
| Y4 | 3,828 | 17.9 | 25.1 | 25G ×2 | ~$157k |
| Y5 | 4,211 | 21.9 | 30.7 | 100G ×2 | ~$213k |

Start **2 × 10 GbE**, step to **2 × 25G** (~Y3), and **2 × 100G** (~Y5). This bottoms-up
cost is *below* the pro forma's conservative `opex_transit_backhaul` line (doc 09) — good
headroom; keep the conservative line until quotes land.

## 4. Candidate providers (NW Arkansas — verify offerings + pricing)

| Provider | Best for | Notes |
|----------|----------|-------|
| **Diamond State Networks / OzarksGo** | Transport (waves/dark fiber), maybe transit | Co-op wholesale, 800G, statewide; contact contact@diamondstatenetworks.com. **Lead candidate, path A.** |
| **Uniti Fiber** | Dark fiber / waves / transit | Regional wholesale; possible diverse path B. |
| **Lumen (CenturyLink)** | IP transit + long-haul | National backbone; strong diverse transit. |
| **Cox Business / Wholesale** | Transit + metro transport | Fiber in Rogers/Bentonville/Fayetteville. |
| **Aristotle** | Transit / transport | Arkansas provider. |
| **AT&T Wholesale** | Transit + transport | National. |

> ARE-ON (research/education network) is not available to a commercial ISP — note but
> don't plan on it.

## 5. Decision framework

Score candidates (`../procurement/provider_scorecard.csv`) on: **path/route diversity**
(vs the other on-ramp), **$/Mbps at 10/25/100G**, **transport lease $/mo to each
head-end**, **upgrade path to 100G+**, **install lead time**, **SLA/latency**,
**contract term/flexibility**, and **co-op alignment**. Target outcome: **DSN/OzarksGo
on path A + one diverse carrier on path B**, with a proven physically-separate route map
between the two head-ends.

## 6. The plan (for execution)

1. **Get the ASN + IP space now** (ARIN) — long lead; org-wide asset (see doc 03).
2. **Send the RFQ** (`../procurement/transit_rfq.md`) to DSN/OzarksGo + Uniti + Lumen/Cox
   for 10G/25G/100G, with and without transport to each of the two head-end sites.
3. **Confirm physical path maps** to prove diversity between the two head-ends; this can
   drive the "buy a small lakeside parcel near a fiber-rich POP" decision (doc 04 §3).
4. **Score + choose** two providers/paths; sign transport + transit.
5. **Feed real $/Mbps + transport lease** into `docs/ASSUMPTIONS.md` and re-run the
   pro forma (`transit_sizing.py` + `model.py`).

## 7. Model hooks
- `data/financial/transit_plan.csv` — capacity + indicative cost by year.
- `opex_transit_backhaul` (doc 09) — the pro forma line this feeds; currently
  conservative vs the bottoms-up sizing.
