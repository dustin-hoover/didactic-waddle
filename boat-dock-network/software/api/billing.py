#!/usr/bin/env python3
"""Boat Dock Network — billing + subscriber lifecycle API (FastAPI + PostGIS). Doc 22.

DockOS step 6: turn on paying members. Billing owns the subscriber state machine; the
network follows it:

  subscribe ─▶ pending ──(engine: OLT/CPE config)──▶ provisioned ──(tech confirms)──▶ active
                                                                        │   ▲
                              dunning (21 d past due) / seasonal hold ──┘   │ payment / resume
                                                                     suspended (walled garden)
                                   cancel / dunning (60 d) ──▶ terminated (RADIUS reject,
                                                                 member WAKE forfeited)

RADIUS never needs a sync: its authorize tables are views over service_instances
(billing_schema.sql), so a state change here IS the network policy on the next auth.
Live sessions are nudged by provisioning jobs (CoA/Disconnect, software/provisioning).

Policies (co-op defaults — change the constants, not the code):
  * Calendar-month billing in advance; first bill prorated from activation and carries
    one-time charges; the doc 18 $100 reservation deposit is credited on it.
  * Due net 15. Dunning: notice at 10 days past due, walled-garden suspend at 21,
    terminate at 60 (termination forfeits WAKE to the Commons Pool, doc 16).
  * Seasonal hold (lake homes): walled garden at $10/mo, membership and WAKE accrual
    continue — seasonal residents shouldn't lose their co-op voice every winter.
  * Upgrades/downgrades apply to the network immediately; price changes next period.
  * Member cancellation takes effect at the end of the billed month (no partial refunds).
  * Internet access is not taxed (Permanent Internet Tax Freedom Act); equipment sales
    are taxed at EQUIPMENT_TAX_RATE — confirm rates with the CPA.

Run (dev):
  pip install fastapi uvicorn asyncpg "pydantic[email]" stripe
  DATABASE_URL=postgresql://dockos:dockos@localhost:5432/dockos \
    uvicorn billing:app --reload        # from software/api (imports governance.py)
"""
from __future__ import annotations
import os, re, secrets, ipaddress, datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, EmailStr
import asyncpg

from governance import forfeit_member   # doc 16: leaving the co-op returns WAKE to the pool

try:
    import stripe
except ImportError:   # importable for tests without the SDK
    stripe = None

app = FastAPI(title="Boat Dock Network — Billing & Lifecycle API")
DB = os.environ.get("DATABASE_URL", "postgresql://dockos:dockos@localhost:5432/dockos")
# ARIN /36 (doc 17). Dev default is RFC 3849 documentation space.
IPV6_POOL = ipaddress.IPv6Network(os.environ.get("IPV6_POOL", "2001:db8::/36"))
NET_DUE_DAYS           = int(os.environ.get("NET_DUE_DAYS", 15))
DUNNING_NOTICE_DAYS    = int(os.environ.get("DUNNING_NOTICE_DAYS", 10))
DUNNING_SUSPEND_DAYS   = int(os.environ.get("DUNNING_SUSPEND_DAYS", 21))
DUNNING_TERMINATE_DAYS = int(os.environ.get("DUNNING_TERMINATE_DAYS", 60))
SEASONAL_HOLD_USD      = Decimal(os.environ.get("SEASONAL_HOLD_USD", "10.00"))
EQUIPMENT_TAX_RATE     = Decimal(os.environ.get("EQUIPMENT_TAX_RATE", "0.095"))  # AR 6.5% + local; confirm
PD_QUARANTINE_DAYS     = 90
STRIPE_SECRET_KEY      = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL        = os.environ.get("PUBLIC_BASE_URL", "https://my.boatdock.network")
if stripe and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

_pool: Optional[asyncpg.Pool] = None
async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB, min_size=1, max_size=8)
    return _pool

# ---------------------------------------------------------------- helpers
CENT = Decimal("0.01")
def money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)

def month_bounds(d: dt.date) -> tuple[dt.date, dt.date]:
    """[first day of d's month, first day of the next month)."""
    start = d.replace(day=1)
    return start, (start + dt.timedelta(days=32)).replace(day=1)

def prorate(monthly, start: dt.date, end_excl: dt.date) -> Decimal:
    ms, mn = month_bounds(start)
    return money(Decimal(str(monthly)) * (end_excl - start).days / (mn - ms).days)

def norm_mac(s: str) -> str:
    h = re.sub(r"[^0-9a-fA-F]", "", s or "").lower()
    if len(h) != 12:
        raise HTTPException(400, f"invalid MAC address: {s!r}")
    return "-".join(h[i:i + 2] for i in range(0, 12, 2))

async def _event(c, kind: str, customer_id=None, sub_id=None, service_id=None, **detail):
    import json
    await c.execute("""INSERT INTO billing_events (customer_id, sub_id, service_id, kind, detail)
        VALUES ($1,$2,$3,$4,$5::jsonb)""", customer_id, sub_id, service_id, kind,
        json.dumps(detail, default=str))

async def _enqueue(c, service_id: int, action: str, **payload):
    import json
    await c.execute("INSERT INTO provisioning_jobs (service_id, action, payload) VALUES ($1,$2,$3::jsonb)",
                    service_id, action, json.dumps(payload, default=str))

async def _alloc_pd(c, zone_id: Optional[str]) -> ipaddress.IPv6Network:
    """Allocate the next free /56 from the zone's /44 (doc 21 §3 hierarchy):
    /36 pool -> /40 region (region 0 reserved: infra/services) -> /44 per zone
    (4,096 x /56 each) -> /56 per member. Released prefixes are quarantined 90 days."""
    zones = [r["zone_id"] for r in await c.fetch("SELECT zone_id FROM zones ORDER BY zone_id")]
    k = zones.index(zone_id) if zone_id in zones else 239          # 'unzoned' bucket
    zone_net = list(IPV6_POOL.subnets(new_prefix=44))[16 + k]
    used = {r["ipv6_pd"] for r in await c.fetch(f"""
        SELECT ipv6_pd FROM service_instances
        WHERE ipv6_pd <<= $1::cidr AND (state <> 'terminated'
              OR terminated_at > now() - interval '{PD_QUARANTINE_DAYS} days')""", zone_net)}
    for sn in zone_net.subnets(new_prefix=56):
        if sn not in used:
            return sn
    raise HTTPException(409, f"IPv6 space exhausted for zone {zone_id}")

async def _service_for_sub(c, sub_id: int, lock=False):
    return await c.fetchrow(
        "SELECT * FROM service_instances WHERE sub_id=$1 ORDER BY service_id DESC LIMIT 1"
        + (" FOR UPDATE" if lock else ""), sub_id)

async def _member_id(c, customer_id: int) -> Optional[int]:
    r = await c.fetchrow("SELECT member_id FROM members WHERE customer_id=$1", customer_id)
    return r["member_id"] if r else None

# ---------------------------------------------------------------- state transitions
async def _suspend(c, si, reason: str, today: dt.date):
    await c.execute("""UPDATE service_instances SET state='suspended', suspend_reason=$2,
        suspended_at=$3, updated_at=now() WHERE service_id=$1""", si["service_id"], reason,
        dt.datetime.combine(today, dt.time()))
    await c.execute("UPDATE subscriptions SET status=$2 WHERE sub_id=$1", si["sub_id"],
                    "hold" if reason == "seasonal_hold" else "suspended")
    if reason == "nonpay":   # pause WAKE accrual (governance accrues status='active' only)
        await c.execute("UPDATE members SET status='suspended' WHERE customer_id=$1 AND status='active'",
                        si["customer_id"])
    await _enqueue(c, si["service_id"], "suspend", reason=reason)
    await _event(c, "suspended", si["customer_id"], si["sub_id"], si["service_id"], reason=reason)

async def _resume(c, si, today: dt.date):
    await c.execute("""UPDATE service_instances SET state='active', suspend_reason=NULL,
        suspended_at=NULL, updated_at=now() WHERE service_id=$1""", si["service_id"])
    await c.execute("UPDATE subscriptions SET status='active' WHERE sub_id=$1", si["sub_id"])
    await c.execute("UPDATE members SET status='active' WHERE customer_id=$1 AND status='suspended'",
                    si["customer_id"])
    await _enqueue(c, si["service_id"], "resume")
    await _event(c, "resumed", si["customer_id"], si["sub_id"], si["service_id"], on=today)

async def _terminate(c, si, reason: str, today: dt.date) -> float:
    await c.execute("""UPDATE service_instances SET state='terminated', terminated_at=$2,
        updated_at=now() WHERE service_id=$1""", si["service_id"], dt.datetime.combine(today, dt.time()))
    await c.execute("""UPDATE subscriptions SET status='cancelled',
        end_date=COALESCE(end_date, $2) WHERE sub_id=$1""", si["sub_id"], today)
    forfeited = 0.0
    other_live = await c.fetchval("""SELECT count(*) FROM service_instances
        WHERE customer_id=$1 AND state <> 'terminated'""", si["customer_id"])
    mid = await _member_id(c, si["customer_id"])
    if mid and not other_live:   # no longer a customer -> leaves the co-op (doc 16)
        forfeited = await forfeit_member(c, mid, note=f"service terminated ({reason})")
    await _enqueue(c, si["service_id"], "terminate", reason=reason)
    await _event(c, "terminated", si["customer_id"], si["sub_id"], si["service_id"],
                 reason=reason, wake_forfeited=forfeited)
    return forfeited

# ---------------------------------------------------------------- invoicing
async def _build_invoice(c, sub_id: int, start: dt.date, end_excl: dt.date,
                         today: dt.date, hold: bool = False) -> Optional[dict]:
    """Create the invoice for [start, end_excl) — idempotent per (sub, period). Applies
    host-node credit (prorated), one-time charges, equipment tax, then account credits
    FIFO (e.g. the reservation deposit)."""
    ps, pn = month_bounds(start)
    period_lo, period_hi = ps, pn                  # invoice key = the calendar month
    if await c.fetchval("SELECT 1 FROM invoices WHERE sub_id=$1 AND period=daterange($2,$3)",
                        sub_id, period_lo, period_hi):
        return None
    sub = await c.fetchrow("""SELECT s.*, p.name AS plan_name, p.monthly_usd, p.down_mbps, p.up_mbps
        FROM subscriptions s JOIN plans p ON p.plan_id=s.plan_id WHERE s.sub_id=$1""", sub_id)
    cust = sub["customer_id"]
    lines = []   # (kind, description, amount, taxable, tax)
    if hold:
        lines.append(("service", f"Seasonal hold {ps:%b %Y}", money(SEASONAL_HOLD_USD), False, money(0)))
        service_amt = money(SEASONAL_HOLD_USD)
    else:
        full = (start == ps and end_excl == pn)
        service_amt = money(sub["monthly_usd"]) if full else prorate(sub["monthly_usd"], start, end_excl)
        span = f"{ps:%b %Y}" if full else f"{start:%b %d}–{(end_excl - dt.timedelta(days=1)):%b %d, %Y} (prorated)"
        lines.append(("service", f"{sub['plan_name']} {sub['down_mbps']}/{sub['up_mbps']} Mbps — {span}",
                      service_amt, False, money(0)))
        host = await c.fetchval("""SELECT COALESCE(sum(monthly_credit_usd),0) FROM host_node_agreements
            WHERE customer_id=$1 AND (start_date IS NULL OR start_date < $3)
              AND (end_date IS NULL OR end_date >= $2)""", cust, start, end_excl)
        if host and host > 0:
            hc = money(host) if full else prorate(host, start, end_excl)
            hc = min(hc, service_amt)               # a host credit never pays us to serve them
            lines.append(("credit_host", "Host-node credit (thank you for hosting)", -hc, False, money(0)))
    otc = await c.fetch("""SELECT * FROM one_time_charges WHERE sub_id=$1 AND invoice_id IS NULL
        ORDER BY charge_id""", sub_id)
    for ch in otc:
        amt = money(ch["amount_usd"])
        tax = money(amt * EQUIPMENT_TAX_RATE) if ch["taxable"] else money(0)
        lines.append((ch["kind"], ch["description"] or ch["kind"], amt, ch["taxable"], tax))
    subtotal = money(sum(l[2] for l in lines))
    tax_total = money(sum(l[4] for l in lines))
    due_before_credits = subtotal + tax_total
    # account credits FIFO
    applied = money(0)
    credits = await c.fetch("""SELECT * FROM account_credits WHERE customer_id=$1 AND remaining_usd > 0
        ORDER BY created_at, credit_id FOR UPDATE""", cust)
    credit_updates = []
    for cr in credits:
        room = due_before_credits - applied
        if room <= 0:
            break
        use = min(money(cr["remaining_usd"]), room)
        applied += use
        credit_updates.append((cr["credit_id"], use))
        label = {"reservation_deposit": "Reservation deposit credit (doc 18)"}.get(cr["kind"], f"Credit: {cr['kind']}")
        lines.append((f"credit_{cr['kind']}" if cr["kind"] != "reservation_deposit" else "credit_deposit",
                      label, -use, False, money(0)))
    total = money(due_before_credits - applied)
    status = "paid" if total <= 0 else "open"
    inv = await c.fetchrow("""INSERT INTO invoices (customer_id, sub_id, period, amount_usd, subtotal_usd,
            credits_usd, tax_usd, total_usd, due_date, status, issued_at, paid_at)
        VALUES ($1,$2,daterange($3,$4),$5,$6,$7,$8,$5,$9,$10,$11,$12) RETURNING invoice_id""",
        cust, sub_id, period_lo, period_hi, total, subtotal, applied, tax_total,
        today + dt.timedelta(days=NET_DUE_DAYS), status, dt.datetime.combine(today, dt.time()),
        dt.datetime.combine(today, dt.time()) if status == "paid" else None)
    iid = inv["invoice_id"]
    for kind, desc, amt, taxable, tax in lines:
        await c.execute("""INSERT INTO invoice_lines (invoice_id, kind, description, unit_usd, amount_usd, taxable, tax_usd)
            VALUES ($1,$2,$3,$4,$4,$5,$6)""", iid, kind, desc, amt, taxable, tax)
    for cid, use in credit_updates:
        await c.execute("UPDATE account_credits SET remaining_usd = remaining_usd - $2 WHERE credit_id=$1", cid, use)
    if otc:
        await c.execute("UPDATE one_time_charges SET invoice_id=$1 WHERE charge_id = ANY($2::bigint[])",
                        iid, [ch["charge_id"] for ch in otc])
    await _event(c, "invoiced", cust, sub_id, None, invoice_id=iid, total=str(total), credits=str(applied))
    return {"invoice_id": iid, "subtotal": str(subtotal), "tax": str(tax_total),
            "credits": str(applied), "total": str(total), "status": status,
            "lines": [{"kind": k, "description": d, "amount": str(a)} for k, d, a, _, _ in lines]}

async def _credit_reservation_deposits(c, customer_id: int, email: Optional[str]) -> list[int]:
    """Turn collected doc 18 reservation deposits into account credits (once each)."""
    rows = await c.fetch("""
        SELECT p.pledge_id, p.amount_usd FROM pledges p
        LEFT JOIN signups s ON s.signup_id = p.signup_id
        WHERE p.kind='reservation_deposit' AND p.status='collected'
          AND (p.customer_id=$1 OR ($2::text IS NOT NULL AND lower(s.email)=lower($2)))
          AND NOT EXISTS (SELECT 1 FROM account_credits a WHERE a.source_pledge_id=p.pledge_id)""",
        customer_id, email)
    for r in rows:
        await c.execute("""INSERT INTO account_credits (customer_id, kind, amount_usd, remaining_usd,
                source_pledge_id, note) VALUES ($1,'reservation_deposit',$2,$2,$3,'doc 18 deposit')
            ON CONFLICT (source_pledge_id) DO NOTHING""", customer_id, money(r["amount_usd"]), r["pledge_id"])
        await c.execute("UPDATE pledges SET customer_id=$1, updated_at=now() WHERE pledge_id=$2",
                        customer_id, r["pledge_id"])
    return [r["pledge_id"] for r in rows]

# ---------------------------------------------------------------- endpoints
class SubscribeIn(BaseModel):
    customer_id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address_id: Optional[int] = None
    zone_id: Optional[str] = None
    plan_id: str
    medium: Literal["fiber", "wireless_nlos", "wireless_ptmp"] = "wireless_nlos"
    access: Literal["ipoe_mac", "pppoe", "ont_serial"]
    device_id: Optional[str] = None        # CPE MAC (ipoe_mac) or ONT serial (ont_serial)
    node_id: Optional[str] = None
    s_vlan: Optional[int] = None
    c_vlan: Optional[int] = None
    ipv4_static: Optional[str] = None      # business/marina only
    install_usd: Decimal = Decimal("0")
    equipment_usd: Decimal = Decimal("0")  # router/CPE sale (taxable)

@app.post("/subscriptions")
async def subscribe(s: SubscribeIn):
    """Sign a member up for service: customer + subscription + service instance
    (pending) + IPv6 /56 + provisioning job. Collected reservation deposits become
    account credits for the first bill."""
    async with (await pool()).acquire() as c:
        async with c.transaction():
            plan = await c.fetchrow("SELECT * FROM plans WHERE plan_id=$1 AND active", s.plan_id)
            if not plan:
                raise HTTPException(400, f"unknown plan {s.plan_id}")
            if s.ipv4_static and not plan["is_business"]:
                raise HTTPException(400, "static IPv4 is a business/marina feature")
            if s.customer_id:
                cust = await c.fetchrow("SELECT * FROM customers WHERE customer_id=$1", s.customer_id)
                if not cust:
                    raise HTTPException(404, "customer not found")
            else:
                if not s.name:
                    raise HTTPException(400, "name (or customer_id) required")
                cust = await c.fetchrow("""INSERT INTO customers (name,email,phone,address_id)
                    VALUES ($1,$2,$3,$4) RETURNING *""", s.name, s.email, s.phone, s.address_id)
            cid = cust["customer_id"]
            zone_id = s.zone_id
            if s.address_id and not zone_id:
                zone_id = await c.fetchval("SELECT zone_id FROM service_addresses WHERE address_id=$1", s.address_id)
            sub = await c.fetchrow("""INSERT INTO subscriptions (customer_id, plan_id, status, address_id)
                VALUES ($1,$2,'pending',$3) RETURNING sub_id""", cid, s.plan_id, s.address_id)
            sub_id = sub["sub_id"]
            if s.access == "ipoe_mac":
                user = norm_mac(s.device_id); pw = user
            elif s.access == "ont_serial":
                if not s.device_id:
                    raise HTTPException(400, "ONT serial required")
                user = s.device_id.strip().upper(); pw = user
            else:
                user = f"bdn{sub_id:06d}"; pw = secrets.token_urlsafe(12)
            if await c.fetchval("""SELECT 1 FROM service_instances WHERE radius_username=$1""", user):
                raise HTTPException(409, f"device {user} is already registered")
            pd = await _alloc_pd(c, zone_id)
            si = await c.fetchrow("""INSERT INTO service_instances (sub_id, customer_id, address_id, medium,
                    node_id, access, radius_username, radius_password, s_vlan, c_vlan, ipv6_pd, ipv4_static)
                VALUES ($1,$2,$3,$4::medium_type,$5,$6::access_kind,$7,$8,$9,$10,$11,$12::inet)
                RETURNING service_id""", sub_id, cid, s.address_id, s.medium, s.node_id, s.access,
                user, pw, s.s_vlan, s.c_vlan, pd, s.ipv4_static)
            if s.install_usd > 0:
                await c.execute("""INSERT INTO one_time_charges (customer_id, sub_id, kind, description, amount_usd)
                    VALUES ($1,$2,'install','Installation (boat-delivered)',$3)""", cid, sub_id, money(s.install_usd))
            if s.equipment_usd > 0:
                await c.execute("""INSERT INTO one_time_charges (customer_id, sub_id, kind, description, amount_usd, taxable)
                    VALUES ($1,$2,'equipment','Router / CPE',$3,true)""", cid, sub_id, money(s.equipment_usd))
            credited = await _credit_reservation_deposits(c, cid, cust["email"])
            await _enqueue(c, si["service_id"], "activate")
            await _event(c, "subscribed", cid, sub_id, si["service_id"], plan=s.plan_id,
                         access=s.access, ipv6_pd=str(pd), deposits_credited=credited)
    return {"ok": True, "customer_id": cid, "sub_id": sub_id, "service_id": si["service_id"],
            "radius_username": user, "radius_password": pw if s.access == "pppoe" else None,
            "ipv6_pd": str(pd), "deposits_credited": credited}

async def activate_service(c, service_id: int, today: dt.date) -> dict:
    """Start billing for an installed service (run inside the caller's transaction).
    Shared by the endpoint below and the work-order engine (dispatch.py), which calls it
    when a crew completes the install WO in the field PWA."""
    si = await c.fetchrow("SELECT * FROM service_instances WHERE service_id=$1 FOR UPDATE", service_id)
    if not si:
        raise HTTPException(404, "service not found")
    if si["state"] == "active":
        return {"ok": True, "already_active": True}
    if si["state"] not in ("pending", "provisioned"):
        raise HTTPException(400, f"cannot activate from state {si['state']}")
    await c.execute("""UPDATE service_instances SET state='active', activated_at=$2,
        provisioned_at=COALESCE(provisioned_at,$2), updated_at=now() WHERE service_id=$1""",
        service_id, dt.datetime.combine(today, dt.time()))
    await c.execute("UPDATE subscriptions SET status='active', start_date=$2 WHERE sub_id=$1",
                    si["sub_id"], today)
    await c.execute("UPDATE members SET status='active' WHERE customer_id=$1 AND status='suspended'",
                    si["customer_id"])
    _, nxt = month_bounds(today)
    inv = await _build_invoice(c, si["sub_id"], today, nxt, today)
    await _event(c, "activated", si["customer_id"], si["sub_id"], service_id, on=today)
    return {"ok": True, "service_id": service_id, "first_invoice": inv}

@app.post("/services/{service_id}/activate")
async def activate(service_id: int, as_of: Optional[dt.date] = None):
    """Install confirmed (tech/boat crew closes the install WO): start billing, issue the
    prorated first bill (one-time charges + deposit credit), mark the member active."""
    async with (await pool()).acquire() as c:
        async with c.transaction():
            return await activate_service(c, service_id, as_of or dt.date.today())

class RunIn(BaseModel):
    period: str                    # 'YYYY-MM'
    as_of: Optional[dt.date] = None

@app.post("/billing/run")
async def billing_run(r: RunIn):
    """Monthly run for `period` (bill in advance). Terminates scheduled cancellations,
    then invoices every active or on-hold subscription activated before the period.
    Idempotent: re-running a period issues nothing new."""
    y, m = map(int, r.period.split("-"))
    ps, pn = dt.date(y, m, 1), month_bounds(dt.date(y, m, 1))[1]
    today = r.as_of or ps
    terminated, issued, total = [], [], Decimal(0)
    async with (await pool()).acquire() as c:
        due_cancel = await c.fetch("""SELECT si.* FROM subscriptions s
            JOIN service_instances si ON si.sub_id=s.sub_id
            WHERE s.end_date IS NOT NULL AND s.end_date < $1 AND si.state <> 'terminated'""", ps)
        for si in due_cancel:
            async with c.transaction():
                await _terminate(c, si, "member_cancel", today)
            terminated.append(si["sub_id"])
        subs = await c.fetch("""SELECT s.sub_id, s.status FROM subscriptions s
            JOIN service_instances si ON si.sub_id=s.sub_id
            WHERE s.status IN ('active','hold') AND si.activated_at::date < $1
              AND (s.end_date IS NULL OR s.end_date >= $1)""", ps)
        for s in subs:
            async with c.transaction():
                inv = await _build_invoice(c, s["sub_id"], ps, pn, today, hold=(s["status"] == "hold"))
            if inv:
                issued.append(inv["invoice_id"]); total += Decimal(inv["total"])
    return {"ok": True, "period": r.period, "invoices_issued": len(issued),
            "billed_usd": str(money(total)), "terminated_subs": terminated}

async def _apply_payment(c, invoice_id: int, amount: Decimal, method: str,
                         payment_intent: Optional[str], today: dt.date) -> dict:
    if payment_intent and await c.fetchval("SELECT 1 FROM payments WHERE stripe_payment_intent=$1", payment_intent):
        return {"ok": True, "duplicate": True}
    inv = await c.fetchrow("SELECT * FROM invoices WHERE invoice_id=$1 FOR UPDATE", invoice_id)
    if not inv:
        raise HTTPException(404, "invoice not found")
    await c.execute("""INSERT INTO payments (invoice_id, customer_id, amount_usd, method, ref,
            stripe_payment_intent, paid_at) VALUES ($1,$2,$3,$4,$5,$5,$6)""",
        invoice_id, inv["customer_id"], money(amount), method, payment_intent,
        dt.datetime.combine(today, dt.time()))
    paid = await c.fetchval("SELECT COALESCE(sum(amount_usd),0) FROM payments WHERE invoice_id=$1", invoice_id)
    settled = money(paid) >= money(inv["total_usd"] or 0)
    if settled and inv["status"] == "open":
        await c.execute("UPDATE invoices SET status='paid', paid_at=$2 WHERE invoice_id=$1",
                        invoice_id, dt.datetime.combine(today, dt.time()))
    await _event(c, "paid", inv["customer_id"], inv["sub_id"], None, invoice_id=invoice_id,
                 amount=str(money(amount)), settled=settled)
    resumed = False
    si = await _service_for_sub(c, inv["sub_id"], lock=True) if inv["sub_id"] else None
    if si and si["state"] == "suspended" and si["suspend_reason"] == "nonpay":
        still_late = await c.fetchval("""SELECT count(*) FROM invoices WHERE customer_id=$1
            AND status='open' AND due_date + $2::int <= $3""", inv["customer_id"], DUNNING_SUSPEND_DAYS, today)
        if not still_late:
            await _resume(c, si, today); resumed = True
    return {"ok": True, "invoice_id": invoice_id, "settled": settled, "service_resumed": resumed}

class PaymentIn(BaseModel):
    invoice_id: int
    amount_usd: Decimal
    method: str = "card"
    stripe_payment_intent: Optional[str] = None
    as_of: Optional[dt.date] = None

@app.post("/payments")
async def record_payment(p: PaymentIn):
    """Record a payment (manual/ACH/check, or called by the Stripe webhook). Settling
    the past-due balance lifts a nonpay suspension automatically."""
    async with (await pool()).acquire() as c:
        async with c.transaction():
            return await _apply_payment(c, p.invoice_id, p.amount_usd, p.method,
                                        p.stripe_payment_intent, p.as_of or dt.date.today())

@app.post("/invoices/{invoice_id}/pay")
async def pay_link(invoice_id: int):
    """Stripe Checkout link for an invoice (card or ACH); webhook settles it."""
    async with (await pool()).acquire() as c:
        inv = await c.fetchrow("SELECT * FROM invoices WHERE invoice_id=$1", invoice_id)
    if not inv or inv["status"] != "open":
        raise HTTPException(400, "invoice not payable")
    if not (stripe and STRIPE_SECRET_KEY):
        return {"ok": True, "checkout_url": None, "note": "Stripe not configured"}
    s = stripe.checkout.Session.create(
        mode="payment", payment_method_types=["card", "us_bank_account"],
        line_items=[{"price_data": {"currency": "usd", "unit_amount": int(money(inv["total_usd"]) * 100),
                     "product_data": {"name": f"Boat Dock Network invoice #{invoice_id}"}}, "quantity": 1}],
        metadata={"invoice_id": str(invoice_id)},
        payment_intent_data={"metadata": {"invoice_id": str(invoice_id)}},
        success_url=f"{PUBLIC_BASE_URL}/billing?paid={invoice_id}",
        cancel_url=f"{PUBLIC_BASE_URL}/billing")
    return {"ok": True, "checkout_url": s.url}

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    if not (stripe and STRIPE_WEBHOOK_SECRET):
        raise HTTPException(503, "Stripe webhook not configured")
    try:
        ev = stripe.Webhook.construct_event(await request.body(),
                                            request.headers.get("stripe-signature", ""), STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(400, f"invalid webhook: {e}")
    if ev["type"] == "checkout.session.completed":
        s = ev["data"]["object"]
        iid = int((s.get("metadata") or {}).get("invoice_id", 0) or 0)
        if iid and s.get("payment_status") == "paid":
            async with (await pool()).acquire() as c:
                async with c.transaction():
                    await _apply_payment(c, iid, Decimal(s["amount_total"]) / 100, "stripe",
                                         s.get("payment_intent"), dt.date.today())
    return {"received": True}

class AsOfIn(BaseModel):
    as_of: Optional[dt.date] = None

@app.post("/billing/dunning")
async def dunning(d: AsOfIn):
    """Daily job: notice at 10 days past due, walled-garden suspend at 21, terminate at 60."""
    today = d.as_of or dt.date.today()
    out = {"notices": [], "suspended": [], "terminated": []}
    async with (await pool()).acquire() as c:
        late = await c.fetch("""SELECT sub_id, customer_id, min(due_date) AS oldest_due,
                array_agg(invoice_id) AS invoice_ids
            FROM invoices WHERE status='open' AND COALESCE(total_usd,0) > 0 AND due_date < $1
              AND sub_id IS NOT NULL
            GROUP BY sub_id, customer_id""", today)
        for row in late:
            dpd = (today - row["oldest_due"]).days
            async with c.transaction():
                si = await _service_for_sub(c, row["sub_id"], lock=True)
                if not si or si["state"] == "terminated":
                    continue
                if dpd >= DUNNING_TERMINATE_DAYS:
                    await _terminate(c, si, "nonpay", today); out["terminated"].append(row["sub_id"])
                elif dpd >= DUNNING_SUSPEND_DAYS and si["state"] in ("active", "provisioned"):
                    await _suspend(c, si, "nonpay", today); out["suspended"].append(row["sub_id"])
                elif dpd >= DUNNING_NOTICE_DAYS:
                    sent = await c.fetchval("""SELECT 1 FROM billing_events WHERE sub_id=$1
                        AND kind='dunning_notice' AND detail->>'oldest_due' = $2""", row["sub_id"], str(row["oldest_due"]))
                    if not sent:
                        await _event(c, "dunning_notice", row["customer_id"], row["sub_id"], si["service_id"],
                                     oldest_due=str(row["oldest_due"]), days_past_due=dpd)
                        out["notices"].append(row["sub_id"])
    return {"ok": True, "as_of": str(today), **out}

@app.post("/subscriptions/{sub_id}/hold")
async def seasonal_hold(sub_id: int, d: AsOfIn):
    """Seasonal hold for lake homes: walled garden at SEASONAL_HOLD_USD/mo from next
    period; membership + WAKE accrual continue (no forfeiture)."""
    today = d.as_of or dt.date.today()
    async with (await pool()).acquire() as c:
        async with c.transaction():
            si = await _service_for_sub(c, sub_id, lock=True)
            if not si or si["state"] != "active":
                raise HTTPException(400, "only an active service can be put on hold")
            await _suspend(c, si, "seasonal_hold", today)
    return {"ok": True, "sub_id": sub_id, "hold_fee_usd": str(SEASONAL_HOLD_USD)}

@app.post("/subscriptions/{sub_id}/resume")
async def resume(sub_id: int, d: AsOfIn):
    today = d.as_of or dt.date.today()
    async with (await pool()).acquire() as c:
        async with c.transaction():
            si = await _service_for_sub(c, sub_id, lock=True)
            if not si or si["state"] != "suspended":
                raise HTTPException(400, "service is not suspended")
            if si["suspend_reason"] == "nonpay":
                raise HTTPException(402, "settle the past-due balance to restore service")
            await _resume(c, si, today)
    return {"ok": True, "sub_id": sub_id}

class ChangePlanIn(BaseModel):
    plan_id: str

@app.post("/subscriptions/{sub_id}/change-plan")
async def change_plan(sub_id: int, p: ChangePlanIn):
    """Speed change now (RADIUS group follows the view; CoA re-applies it to the live
    session); new price from the next billing period."""
    async with (await pool()).acquire() as c:
        async with c.transaction():
            plan = await c.fetchrow("SELECT * FROM plans WHERE plan_id=$1 AND active", p.plan_id)
            si = await _service_for_sub(c, sub_id, lock=True)
            if not plan or not si or si["state"] == "terminated":
                raise HTTPException(400, "invalid plan or service")
            if si["ipv4_static"] is not None and not plan["is_business"]:
                raise HTTPException(400, "move off the static IPv4 before leaving a business plan")
            old = await c.fetchval("SELECT plan_id FROM subscriptions WHERE sub_id=$1", sub_id)
            await c.execute("UPDATE subscriptions SET plan_id=$2 WHERE sub_id=$1", sub_id, p.plan_id)
            await _enqueue(c, si["service_id"], "change_plan", old=old, new=p.plan_id)
            await _event(c, "plan_changed", si["customer_id"], sub_id, si["service_id"], old=old, new=p.plan_id)
    return {"ok": True, "sub_id": sub_id, "plan_id": p.plan_id, "billing_from": "next period"}

class CancelIn(BaseModel):
    immediate: bool = False
    as_of: Optional[dt.date] = None

@app.post("/subscriptions/{sub_id}/cancel")
async def cancel(sub_id: int, x: CancelIn):
    """Member cancellation: effective end of the billed month (or now). Leaving the
    co-op forfeits WAKE — the response says how much, and suggests a seasonal hold."""
    today = x.as_of or dt.date.today()
    async with (await pool()).acquire() as c:
        async with c.transaction():
            si = await _service_for_sub(c, sub_id, lock=True)
            if not si or si["state"] == "terminated":
                raise HTTPException(400, "nothing to cancel")
            mid = await _member_id(c, si["customer_id"])
            at_risk = float(await c.fetchval("SELECT COALESCE(units,0) FROM wake_balances WHERE member_id=$1", mid) or 0) if mid else 0.0
            if x.immediate:
                forfeited = await _terminate(c, si, "member_cancel", today)
                return {"ok": True, "effective": str(today), "wake_forfeited": forfeited}
            end = month_bounds(today)[1] - dt.timedelta(days=1)
            await c.execute("UPDATE subscriptions SET end_date=$2 WHERE sub_id=$1", sub_id, end)
            await _event(c, "cancel_scheduled", si["customer_id"], sub_id, si["service_id"], effective=str(end))
    return {"ok": True, "effective": str(end), "wake_units_at_risk": at_risk,
            "note": "Leaving returns your WAKE units to the Commons Pool. Away for the season? "
                    "A seasonal hold keeps your membership and vote."}

@app.get("/customers/{customer_id}/account")
async def account(customer_id: int):
    async with (await pool()).acquire() as c:
        cust = await c.fetchrow("SELECT customer_id, name, email FROM customers WHERE customer_id=$1", customer_id)
        if not cust:
            raise HTTPException(404, "customer not found")
        svcs = await c.fetch("""SELECT si.service_id, si.sub_id, s.plan_id, s.status AS sub_status, si.state,
                si.suspend_reason, si.radius_username, si.ipv6_pd::text, host(si.ipv4_static) AS ipv4_static
            FROM service_instances si JOIN subscriptions s ON s.sub_id=si.sub_id
            WHERE si.customer_id=$1 ORDER BY si.service_id""", customer_id)
        invs = await c.fetch("""SELECT i.invoice_id, lower(i.period) AS period, i.total_usd, i.status, i.due_date,
                i.total_usd - COALESCE((SELECT sum(amount_usd) FROM payments p WHERE p.invoice_id=i.invoice_id),0) AS balance
            FROM invoices i WHERE i.customer_id=$1 ORDER BY lower(i.period)""", customer_id)
        credit = await c.fetchval("SELECT COALESCE(sum(remaining_usd),0) FROM account_credits WHERE customer_id=$1", customer_id)
        wake = await c.fetchrow("""SELECT m.member_id, m.status, COALESCE(b.units,0) AS units FROM members m
            LEFT JOIN wake_balances b ON b.member_id=m.member_id WHERE m.customer_id=$1""", customer_id)
    return {"customer": dict(cust), "services": [dict(r) for r in svcs],
            "invoices": [dict(r) for r in invs],
            "balance_due": str(money(sum((r["balance"] for r in invs if r["status"] == "open"), Decimal(0)))),
            "credit_available": str(money(credit)), "membership": dict(wake) if wake else None}
