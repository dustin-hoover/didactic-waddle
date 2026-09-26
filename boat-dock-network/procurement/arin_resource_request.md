# ARIN Number-Resource Request — Boat Dock Network

> The long-lead, org-wide asset (doc 17 §6 step 1): our own **ASN + IPv6 + IPv4** so we
> multi-home over two diverse transit providers and never depend on one carrier's
> addresses. **Do this first** — it gates BGP turn-up and the IPv4 waitlist clock is
> >1 year, so the sooner we're in line the better. Fees/process verified against ARIN,
> Jan 2026 (sources at bottom). Not legal/financial advice.

## 0. TL;DR — what to request
| Resource | What to request | Why | Cost (2026) |
|----------|-----------------|-----|-------------|
| **ASN** | 1 ASN (16-bit if available, else 32-bit) | Run BGP, multi-home on 2 providers | in RSP |
| **IPv6** | direct **/36** allocation | Native v6 to every member; futureproof | in RSP; **fee waiver applies** |
| **IPv4** | initial **/24** via the **Waiting List** | Public pool + CGNAT; only path to free ARIN v4 | in RSP |
| **IPv4 (bridge)** | **lease a /24–/23** on the transfer market | Launch *now* — waitlist is >1 yr | ~$0.40–1.50/IP/mo |

**Registration Services Plan (RSP) fee:** holding an ASN + IPv6 /36 puts us in **2X-Small
($550/yr)**, but the **temporary IPv6 fee waiver** (expires 31 Dec 2026) bills us at
**3X-Small ($275/yr)** if our IPv4 holding is /24-or-smaller. So **apply in 2026** to lock
the lower fee. Plus one-time **Org Create $50**.

## 1. Prerequisites (create these at arin.net)
1. **ARIN Online account** (individual) → then **create an Org ID** (Org Create, $50).
2. **Legal entity:** ARIN needs the cooperative to be a registered legal entity —
   coordinate with **`docs/19-entity-formation-checklist.md`** (AR cooperative filing →
   EIN). Have the incorporation doc / EIN ready; ARIN validates org identity.
3. **Point of contact (POC)** handles: Admin, Tech, Abuse. Use role accounts
   (admin@, noc@, abuse@ boatdock.network), not a personal address.
4. **Sign the RSA** (Registration Services Agreement) — required for all resources.

## 2. ASN request
- **Justification:** we will **multi-home** (BGP to ≥2 distinct upstream ASNs on 2
  diverse paths — doc 17). That is the standard, accepted justification; have the two
  transit providers (or signed LOIs / order confirmations) named when asked.
- **16- vs 32-bit:** request 16-bit; accept a 32-bit ASN if that's what's issued (all
  modern gear + our transit peers handle 4-byte ASNs).
- Category impact: 1–3 ASNs = 3X-Small on its own.

## 3. IPv6 request — /36 direct allocation
- **Eligibility:** any ISP that (a) has (or is requesting) an ASN and (b) intends to
  multi-home or make sub-assignments qualifies for a direct IPv6 allocation. We qualify.
- **Why /36, not /32:** /36 lands us in **2X-Small** and (crucially) triggers the
  **IPv6 fee waiver** so we still pay the 3X-Small **$275** through 2026. A /36 is
  enormous for us:
  - Assign **/56 per member** (256 /64s each) → a /36 holds **1,048,576 /56s** vs our
    ~9,571 premises. ~100× headroom even at /48-per-member if we ever wanted it.
  - Reserve /48s per head-end/aggregation site out of the same /36.
- **Addressing plan (attach to the request):** /36 → nibble-aligned /40s per region →
  /48 per POP/zone → /56 per member. Documented plan strengthens the request.

## 4. IPv4 request — the reality (v4 is exhausted)
ARIN has **no free pool**; all new IPv4 comes from the **Waiting List** or the
**transfer market**.

**A) Waiting List (do this — it's cheap and it's ours long-term):**
- A new ISP with **no ARIN IPv4** automatically qualifies for an **initial /24**
  (no utilization history needed).
- Reality check (Apr 2026): ~523 unmet requests, front of line ~388 days old →
  **budget ~12–15+ months** to fulfillment. **Waitlisted space can't be transferred for
  60 months** — fine, we're keeping it.
- **Action:** get in line **now** so the clock runs while we build.

**B) Transfer-market bridge (do this to launch on time):**
- Lease a **/24 (256) or /23 (512)** for launch; typical lease ~**$0.40–1.50/IP/mo**
  (buy ~$30–40/IP if we'd rather own — a /24 ≈ $8–10k one-time).
- A leased/bought block used as our public pool covers NAT/CGNAT egress, head-end
  loopbacks/BGP, DNS, mail, and business/static-IP customers.

**C) Sizing (why a /24–/23 is enough for 9,571 premises):**
- **CGNAT** residential subs behind RFC 6598 (100.64/10) space → a handful of public
  IPs serve thousands of subs.
- Public v4 needed for: CGNAT pools, infra (routers/DNS/mail/NOC), and static-IP
  business/marina accounts. A **/23** comfortably covers Year-5 scale (~4,200 subs);
  start with a **/24** and grow.

## 5. Cost summary (Year 1)
| Item | One-time | Recurring |
|------|----------|-----------|
| Org Create | $50 | — |
| RSP (ASN + IPv6 /36, waiver) | — | **$275/yr** (2026); ~$550/yr after waiver ends |
| IPv4 waitlist | $0 | in RSP |
| IPv4 lease (bridge, /24) | — | ~$100–400/mo (or buy ~$8–10k once) |
| **Approx. Year-1** | **~$50** | **~$275 + IPv4 lease** |

Feeds the pro forma's regulatory/IP line (doc 09). Trivial vs the transport/transit MRC.

## 6. Do-now checklist
- [ ] Confirm cooperative legal entity + EIN (entity-formation checklist).
- [ ] Create ARIN Online account → Org ID (pay Org Create $50).
- [ ] Stand up role POCs: admin@, noc@, abuse@ boatdock.network.
- [ ] Sign the RSA.
- [ ] Submit **ASN** request (justification: multi-homing on 2 providers).
- [ ] Submit **IPv6 /36** request (attach the addressing plan in §3).
- [ ] Submit **IPv4 /24 Waiting List** request (get in line now).
- [ ] Start **IPv4 lease** sourcing in parallel (brokers) for launch bridge.
- [ ] Record ASN + prefixes in `docs/ASSUMPTIONS.md` and the NOC once issued.

## Sources (verified Jan 2026)
- ARIN 2026 Fee Schedule — RSP categories & amounts, transaction fees, IPv6 waiver:
  https://www.arin.net/resources/fees/fee_schedule/
- ARIN 2026 fee increase (5% RSP; IPv6 waiver to 31 Dec 2026):
  https://www.arin.net/announcements/20250512/
- ARIN Request IPv4 / Waiting List (initial /24 eligibility, waitlist mechanics):
  https://www.arin.net/resources/guide/ipv4/waiting_list/
- IPv4 Waiting List distribution status (backlog/age): https://www.arin.net/announcements/20260114/

---
_Generated by [Claude Code](https://claude.ai/code)_
