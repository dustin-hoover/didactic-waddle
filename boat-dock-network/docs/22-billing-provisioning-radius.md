# 22 — Billing, Provisioning & RADIUS (DockOS step 6)

> Turning on paying members. This is the build behind doc 14 §5's rule — *"activating
> service creates subscription + RADIUS entry + rate limit; suspension for non-pay flips
> network state. One truth."* — plus the co-op-specific policies that make it ours
> (deposit credits from doc 18, WAKE rules from doc 16, seasonal holds for lake homes).
> Tested end-to-end against a live FreeRADIUS 3.2.5 (46 checks, §7).

## 1. The core design: billing state *is* network policy
FreeRADIUS's authorize tables — `radcheck`, `radreply`, `radusergroup`, `radgroupcheck`,
`radgroupreply` — are **SQL views over the billing tables** (`software/db/billing_schema.sql`).
Stock FreeRADIUS `rlm_sql` queries run unmodified against them.

```
 billing API ──writes──▶ service_instances.state / subscriptions.plan_id
                               │                          (views, no copy)
                               ▼
     radcheck ─ who may auth   radusergroup ─ plan group or 'suspended'
     radreply ─ IPv6 /56, static v4          radgroupreply ─ QoS derived from `plans`
                               │
          FreeRADIUS ◀─────────┘  next Access-Request gets the new policy
 provisioning job ──▶ CoA/Disconnect (RFC 5176) so a LIVE session re-auths now
```

So there is **no sync job that can drift**: suspend in billing and the next auth is in the
walled garden; add a plan to the catalog and its RADIUS profile exists automatically.

| Service state | RADIUS result | Why |
|---------------|---------------|-----|
| `pending` | Reject | not installed yet |
| `provisioned` | Accept, plan profile | tech's on-site turn-up + speed test; **billing not started** |
| `active` | Accept, plan profile + /56 (+ static v4 for business) | billing running |
| `suspended` | Accept, **walled garden** (`Filter-Id=walled-garden`, 1M/1M) | nonpay or seasonal hold — can still reach the pay page |
| `terminated` | Reject | left the co-op |

**Reply attributes.** `Filter-Id` (RFC 2865) names the BNG QoS policy — vendor-neutral, map
it to a shaper on Juniper/Cisco/Nokia BNGs. `Mikrotik-Rate-Limit` drives MikroTik BNGs
directly. `Delegated-IPv6-Prefix` hands out the member's /56. WISPr bandwidth attributes are
deliberately **not** used: they're 32-bit bps and overflow above ~4.29 Gbps (our 5G plan).

## 2. Subscriber lifecycle (`software/api/billing.py`)
```
subscribe ─▶ pending ─(engine: OLT/CPE)─▶ provisioned ─(tech confirms)─▶ active
                                                               │   ▲
                         21 d past due / seasonal hold ────────┘   │ pay / resume
                                                           suspended
                        cancel (end of month) / 60 d past due ─▶ terminated
```
| Endpoint | What it does |
|----------|--------------|
| `POST /subscriptions` | customer + subscription + service (pending) + IPv6 /56 + activate job; collected doc 18 deposits → account credit |
| `POST /services/{id}/activate` | install confirmed → billing starts, **prorated first bill** |
| `POST /billing/run` | monthly, bill-in-advance; idempotent per (subscription, month) |
| `POST /payments`, `/webhook/stripe`, `/invoices/{id}/pay` | settle (card/ACH via Stripe Checkout); idempotent on payment intent; lifts nonpay suspension |
| `POST /billing/dunning` | daily: notice 10 d, walled garden 21 d, terminate 60 d |
| `POST /subscriptions/{id}/hold` · `/resume` | seasonal hold |
| `POST /subscriptions/{id}/change-plan` | speed now, price next period |
| `POST /subscriptions/{id}/cancel` | end of billed month; warns about WAKE at risk |
| `GET /customers/{id}/account` | services, invoices, balance, credits, membership |

## 3. Co-op policies (constants, not code)
- **First bill** is prorated from activation and carries one-time charges (install, router)
  and the **$100 reservation deposit credit** (doc 18) — matched to the member's collected
  pledge by email, credited exactly once.
- **Host-node credit** from `host_node_agreements` applied monthly (prorated), capped so it
  never exceeds the service charge.
- **Seasonal hold** — a lake-specific feature. Seasonal homeowners pause at **$10/mo** in the
  walled garden **and keep their membership and WAKE accrual.** Without this, the rule "leave
  the co-op → units return to the pool" (doc 16) would strip seasonal residents of their
  vote every winter.
- **Nonpay suspension pauses WAKE accrual** (member status `suspended`) but does **not**
  forfeit; paying restores both. **Termination forfeits** WAKE to the Commons Pool via the
  shared `governance.forfeit_member` — the same code path as a voluntary exit.
- **Cancellation** takes effect at the end of the billed month (no partial refunds, simple
  accounting); the response states the WAKE at risk and suggests a hold instead.
- **Plan changes** hit the network immediately (the view changes; CoA re-applies it); the new
  price starts next period — upgrades are never a billing penalty mid-month.
- **Taxes:** internet access is not taxable (Permanent Internet Tax Freedom Act); equipment
  sales are taxed at `EQUIPMENT_TAX_RATE` (default 9.5% ≈ AR 6.5% + local) — **confirm with
  the CPA**. Termination doesn't erase a receivable: unpaid final invoices stay collectible.

## 4. Provisioning engine (`software/provisioning/engine.py`)
Billing never touches devices; it enqueues `provisioning_jobs`. Workers claim with
`FOR UPDATE SKIP LOCKED` (safe to run several), retry up to 5×, then park as `failed`.
- `activate` → access adapter configures the **ONT** (XGS-PON OLT) or **CPE** (Tarana/Cambium),
  then `pending → provisioned`.
- `suspend` / `resume` / `change_plan` → **RFC 5176 Disconnect-Request** to the NAS for each
  open session (from `radacct`, secret from the `nas` registry) so it re-auths into its new group.
- `terminate` → disconnect + deprovision the device.

Vendor adapters (`OltAdapter`, `WirelessCpeAdapter`) are interfaces to implement once the
gear is chosen by quote (doc 10/21); `DryRun` adapters run the whole pipeline in dev/CI.

## 5. Addressing (doc 21 §3, implemented)
The allocator hands each member the next free **/56** from their zone's **/44**
(`/36 → /40 region → /44 zone → /56`; region 0 reserved for infrastructure). Released
prefixes are quarantined 90 days before reuse; a partial unique index stops double
allocation. Static IPv4 is a business/marina-only feature. *(Building this corrected doc 21:
a /48 per zone holds only 256 /56s — too small for Beaver Shores' 1,272 premises.)*

## 6. RADIUS deployment (`software/radius/`)
`setup_freeradius.sh` installs the `sql` module (`sql.conf.tmpl`), enables it, validates the
config, and creates a **least-privilege `radius` DB role**: SELECT on the authorize views +
`nas`, write on `radacct`/`radpostauth` only. Views execute with their owner's rights, so the
RADIUS server can't read `service_instances`, invoices, or member data (verified in §7).
NAS/BNG clients come from the `nas` table (`read_clients = yes`) — the same registry the
engine uses for CoA secrets. Accounting uses FreeRADIUS's own `radacct` DDL (64-bit octets
via Gigawords), feeding `usage_monthly` for NOC capacity planning.

## 7. Verified end-to-end (`software/tests/test_billing_e2e.py`)
Runs the billing + governance APIs on a real Postgres, the provisioning engine, and **real
RADIUS packets** (`radtest` / `radclient`) against a running FreeRADIUS 3.2.5 — **46 checks**:
- Reject while pending → Accept at turn-up with plan QoS + `Delegated-IPv6-Prefix`.
- First bill exact to the cent: $89 × 22/31 = 63.16, host credit −10.65, router 120.00 +
  11.40 tax, deposit −100.00 → **$83.91**. November: 89 − 15 = **$74.00**; re-runs issue nothing.
- Accounting Start/Interim with Gigawords → 9 GB down / 2 GB up in `usage_monthly`.
- Dunning: notice once at 11 days; walled garden at 22 days; Disconnect-Request built for the
  live session; WAKE accrual paused; payment restores service + membership; webhook retries
  are idempotent.
- Upgrade reflected on the very next auth; seasonal hold bills $10 and **still accrues WAKE**.
- Cancel → terminated at the next run → Reject; **10.5 WAKE forfeited to the Commons Pool**.
- Business PPPoE with static `Framed-IP-Address`; wrong password rejected; residential static
  IPv4 refused.
- The `radius` role can read `radcheck` but is **denied** `service_instances` and `invoices`.

To reproduce: load the four schemas into a test DB, run `setup_freeradius.sh`, start
FreeRADIUS, then `TEST_DB=<db> python3 software/tests/test_billing_e2e.py`. (In this build
container the test FreeRADIUS ran without its IPv6 listeners because the container has no
IPv6 sockets; production is dual-stack and uses the stock listeners.)

## 8. Not yet built (next steps)
- Real OLT / Tarana / Cambium adapters (after gear selection) and a live CoA test against the
  chosen BNG.
- Member-facing billing page (pay, hold, upgrade) — can extend the signup portal.
- Notification delivery for `dunning_notice` events (email/SMS), and Stripe customer/ACH mandate
  setup for autopay.
- Patronage-dividend allocation from annual margins (doc 09) — the annual close, not monthly billing.
