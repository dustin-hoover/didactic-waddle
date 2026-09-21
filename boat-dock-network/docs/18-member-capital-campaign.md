# 18 — Member-Capital Campaign

> The grant-free funding engine (doc 13), made operational. How the cooperative raises
> capital **from the community it serves** — and gates each zone's build on real demand
> + committed capital. **Not legal/financial advice:** every instrument below can
> implicate securities law; structure with cooperative + securities counsel before
> taking a dollar. Co-op exemptions often apply, but confirm.

## 1. The three instruments

| Instrument | Amount (planning) | Refundable? | What it does |
|-----------|-------------------|-------------|--------------|
| **Membership share** | $200 one-time | Yes, on exit (co-op equity) | Makes you a member-owner; starts **WAKE** accrual (doc 16); one per member |
| **Reservation deposit** | $100 | Yes; credited to 1st bill at activation | Reserves your spot **and** funds your zone's working capital; proves demand |
| **Founding-member capital** | tiers $500 / $1,500 / $5,000 | Per terms (member capital certificate / member loan; revolving) | Early risk capital from lakeshore residents, marinas, resorts; founding recognition |

All three are **cooperative / member-capital** instruments — capital from members, not a
public securities offering. Kept separate from WAKE: **capital never buys votes.**
Founding members get *recognition* + a patronage preference (design with counsel) and an
optional **one-time capped WAKE grant** (e.g., +12, ≤ the 120 cap) — governance stays
tenure-earned so the decentralization design (doc 16) holds.

## 2. What it raises (ties to the pro forma)

Peak external need is **~$3.3M** (doc 09). Member capital + deposits target a large
slice of that:

- **Membership shares:** ~4,000 members × $200 ≈ **$0.8M** of patient equity (over the ramp).
- **Reservation deposits:** rolling working capital per zone (credited back at activation).
- **Founding capital:** a campaign target of **$0.5–1.0M** from early supporters.

Together with owner equity + cooperative/commercial debt, this covers the raise without
government money (doc 13). Deposits + founding capital front-load the early zones; later
zones self-fund from Year-2+ cash.

## 3. Per-zone build-gate (demand + capital)

A zone releases to construction when **both** clear (configurable):
```
reservations ≥ 25% of zone premises        (demand proof)
AND  capital_committed ≥ zone_gate_target   (skin in the game)
zone_gate_target = premises × $75   (default dial)
```
This is the discipline that replaces speculative building (doc 06/13): members vote with
deposits, and we build where the lake asks us to. `zone_demand` / `campaign_progress`
(schema below) surface it live.

## 4. Money flow (production)

```
Member picks options in the portal ─▶ create pledge (intent, amount)
   ─▶ Stripe Checkout / PaymentIntent ─▶ funds to a segregated escrow/co-op account
   ─▶ webhook: mark pledge collected ─▶ enroll member, start WAKE, credit deposit
   ─▶ campaign_progress + zone build-gate update
```
- **Escrow/segregation:** reservation deposits and founding capital held in a segregated
  account until the zone build-gate clears; refundable if a zone is cancelled (doc 09
  controls). Never commingled with OpEx.
- **Payments:** Stripe (Checkout for one-time; can support ACH for larger founding
  amounts to cut fees). Store only Stripe references, never card data.
- **Records:** `pledges` + `member_shares` + `capital_campaigns` (schema below); every
  dollar reconciled to a member and a zone for co-op accounting + audit.

## 5. Software

- **Prototype (live):** the signup portal now captures **pledge amounts** (deposit /
  share / founding) and writes a `pledges` record to the artifact db, and the owner sees
  a **Campaign cockpit** — per-zone capital vs build-gate target, totals vs the $3.3M
  peak, and funding mix. (`software/portal/make_portal.py`.)
- **Production:** `software/api/capital.py` (Stripe-backed pledge → checkout → webhook →
  collected → enroll) + `software/db/signup_schema.sql` (`capital_campaigns`,
  `member_shares`, Stripe fields on `pledges`, `campaign_progress` view).

## 6. Compliance checklist (for counsel)
- Confirm the member-share / deposit / founding-capital instruments qualify under
  **cooperative securities exemptions** (federal + Arkansas); prepare member disclosures.
- **Segregated escrow** + clear refund terms for deposits and founding capital.
- Subchapter T patronage accounting (doc 09); founding-capital preference terms.
- KYC/AML as required for larger contributions; clear member agreement + risk statement.
- Keep **capital ≠ governance** explicit in bylaws (protects the non-security WAKE design).
