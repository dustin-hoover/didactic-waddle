#!/usr/bin/env python3
"""Boat Dock Network — member-capital campaign API (FastAPI + PostGIS + Stripe).

The production money-flow behind the signup portal's pledge step (doc 18 §4/§5):

    pledge (intent) -> Stripe Checkout -> funds to segregated escrow
        -> webhook (checkout.session.completed) -> mark pledge collected
        -> enroll member / start WAKE / credit deposit -> campaign_progress updates

This is the reference implementation / contract; deploy behind the DockOS stack
(docs/14) alongside serviceability.py. Capital is kept strictly separate from
governance: paying in never buys votes (doc 16 / doc 18 §1).

Run (dev):
  pip install fastapi uvicorn asyncpg pydantic stripe
  DATABASE_URL=postgresql://dockos:dockos@localhost:5432/dockos \
  STRIPE_SECRET_KEY=sk_test_... STRIPE_WEBHOOK_SECRET=whsec_... \
  PUBLIC_BASE_URL=https://join.boatdock.network \
    uvicorn capital:app --reload

Endpoints:
  POST /pledge                    -> create pledge intent + Stripe Checkout session
  POST /webhook/stripe           -> Stripe webhook: mark collected, enroll, credit
  GET  /campaigns/progress       -> per-zone capital vs build-gate (cockpit feed)
  GET  /campaigns/{zone_id}      -> one zone's progress
  POST /pledge/{id}/refund       -> refund a refundable pledge (zone cancelled, exit)

Instruments & planning amounts (doc 18 §1) — server validates against these:
  reservation_deposit  $100  refundable, credited to first bill at activation
  membership_share     $200  refundable co-op equity; starts WAKE accrual
  founding_capital     $500 / $1,500 / $5,000  member-capital certificate
"""
from __future__ import annotations
import os
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
import asyncpg

try:
    import stripe
except ImportError:      # allow import for tests without the SDK installed
    stripe = None

app = FastAPI(title="Boat Dock Network — Capital API")
DB = os.environ.get("DATABASE_URL", "postgresql://dockos:dockos@localhost:5432/dockos")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://join.boatdock.network")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
if stripe and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

_pool: Optional[asyncpg.Pool] = None

async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB, min_size=1, max_size=8)
    return _pool

# --- instrument rules (doc 18 §1): amount is server-authoritative, never client ---
Kind = Literal["reservation_deposit", "membership_share", "founding_capital"]
AMOUNTS: dict[str, list[int]] = {
    "reservation_deposit": [100],
    "membership_share": [200],
    "founding_capital": [500, 1500, 5000],
}
REFUNDABLE = {"reservation_deposit": True, "membership_share": True, "founding_capital": True}
LABEL = {
    "reservation_deposit": "Reservation deposit (credited to your first bill)",
    "membership_share": "Cooperative membership share",
    "founding_capital": "Founding-member capital",
}

class PledgeIn(BaseModel):
    zone_id: str
    kind: Kind
    amount_usd: int
    signup_id: Optional[int] = None
    name: str
    email: EmailStr
    consent: bool = False

    @field_validator("amount_usd")
    @classmethod
    def _amt(cls, v, info):
        kind = info.data.get("kind")
        if kind and v not in AMOUNTS.get(kind, []):
            raise ValueError(f"amount ${v} not allowed for {kind}; allowed: {AMOUNTS[kind]}")
        return v

@app.post("/pledge")
async def create_pledge(p: PledgeIn):
    """Record a pledge intent and open a Stripe Checkout session for it.
    Funds settle to the segregated escrow/co-op account (doc 18 §4); we store
    only Stripe references, never card data."""
    if not p.consent:
        raise HTTPException(400, "consent required to store contact information")
    async with (await pool()).acquire() as c:
        camp = await c.fetchrow(
            "SELECT campaign_id FROM capital_campaigns WHERE zone_id=$1", p.zone_id)
        if not camp:
            raise HTTPException(404, f"no capital campaign open for zone {p.zone_id}")
        row = await c.fetchrow("""
            INSERT INTO pledges (signup_id, campaign_id, kind, amount_usd, status,
                                 refundable, zone_id)
            VALUES ($1,$2,$3,$4,'interested',$5,$6)
            RETURNING pledge_id""",
            p.signup_id, camp["campaign_id"], p.kind, p.amount_usd,
            REFUNDABLE[p.kind], p.zone_id)
        pledge_id = row["pledge_id"]

    if not (stripe and STRIPE_SECRET_KEY):
        # dev/no-Stripe path: return the pledge so the flow is testable offline
        return {"ok": True, "pledge_id": pledge_id, "checkout_url": None,
                "note": "Stripe not configured; pledge recorded as intent only"}

    session = stripe.checkout.Session.create(
        mode="payment",
        customer_email=str(p.email),
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": p.amount_usd * 100,
                "product_data": {"name": f"BDN — {LABEL[p.kind]}",
                                 "description": f"Zone {p.zone_id}"},
            },
            "quantity": 1,
        }],
        payment_intent_data={
            # route to the segregated escrow account via a connected account or
            # a dedicated Stripe account; keep out of operating funds (doc 18 §4)
            "metadata": {"pledge_id": str(pledge_id), "zone_id": p.zone_id,
                         "kind": p.kind},
        },
        metadata={"pledge_id": str(pledge_id), "zone_id": p.zone_id, "kind": p.kind},
        success_url=f"{PUBLIC_BASE_URL}/pledge/thanks?pledge={pledge_id}",
        cancel_url=f"{PUBLIC_BASE_URL}/pledge/cancel?pledge={pledge_id}",
    )
    async with (await pool()).acquire() as c:
        await c.execute(
            "UPDATE pledges SET stripe_checkout_session=$1, status='committed', "
            "updated_at=now() WHERE pledge_id=$2", session.id, pledge_id)
    return {"ok": True, "pledge_id": pledge_id, "checkout_url": session.url}

async def _mark_collected(c: asyncpg.Connection, pledge_id: int,
                          payment_intent: str, charge_id: Optional[str],
                          stripe_customer: Optional[str], email: Optional[str],
                          name: Optional[str]) -> None:
    """Idempotent: mark the pledge collected, then enroll/credit per instrument."""
    pl = await c.fetchrow(
        "SELECT pledge_id, kind, amount_usd, status, customer_id "
        "FROM pledges WHERE pledge_id=$1 FOR UPDATE", pledge_id)
    if not pl or pl["status"] == "collected":
        return  # unknown or already processed (webhooks retry)
    await c.execute("""
        UPDATE pledges SET status='collected', collected_at=now(),
            stripe_payment_intent=$2, stripe_charge_id=$3, stripe_customer_id=$4,
            updated_at=now() WHERE pledge_id=$1""",
        pledge_id, payment_intent, charge_id, stripe_customer)

    # membership_share -> enroll member (starts WAKE accrual, doc 16) + record share.
    # members link to customers (contact info lives there), so resolve/create both.
    if pl["kind"] == "membership_share" and email:
        cust = await c.fetchrow("SELECT customer_id FROM customers WHERE email=$1", email)
        if not cust:
            cust = await c.fetchrow(
                "INSERT INTO customers (name,email) VALUES ($1,$2) RETURNING customer_id",
                name or email, email)
        m = await c.fetchrow(
            "SELECT member_id FROM members WHERE customer_id=$1", cust["customer_id"])
        if not m:
            m = await c.fetchrow(
                "INSERT INTO members (customer_id,joined_at) VALUES ($1, current_date) "
                "RETURNING member_id", cust["customer_id"])
        # link the pledge to the customer for co-op accounting, then record the share
        await c.execute("UPDATE pledges SET customer_id=$2 WHERE pledge_id=$1",
                        pledge_id, cust["customer_id"])
        await c.execute(
            "INSERT INTO member_shares (member_id, pledge_id, amount_usd) "
            "VALUES ($1,$2,$3)", m["member_id"], pledge_id, pl["amount_usd"])
    # reservation_deposit / founding_capital: funds sit in escrow until the zone
    # build-gate clears; campaign_progress picks them up automatically.

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook. Verifies the signature, then on a completed checkout marks
    the pledge collected and runs enrollment (doc 18 §4)."""
    if not (stripe and STRIPE_WEBHOOK_SECRET):
        raise HTTPException(503, "Stripe webhook not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:  # signature/parse failure
        raise HTTPException(400, f"invalid webhook: {e}")

    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        pledge_id = int((s.get("metadata") or {}).get("pledge_id", 0) or 0)
        if pledge_id:
            details = (s.get("customer_details") or {})
            async with (await pool()).acquire() as c:
                async with c.transaction():
                    await _mark_collected(
                        c, pledge_id,
                        payment_intent=s.get("payment_intent"),
                        charge_id=None,
                        stripe_customer=s.get("customer"),
                        email=details.get("email") or s.get("customer_email"),
                        name=details.get("name"))
    elif event["type"] == "charge.refunded":
        s = event["data"]["object"]
        pledge_id = int((s.get("metadata") or {}).get("pledge_id", 0) or 0)
        if pledge_id:
            async with (await pool()).acquire() as c:
                await c.execute(
                    "UPDATE pledges SET status='refunded', refunded_at=now(), "
                    "updated_at=now() WHERE pledge_id=$1", pledge_id)
    elif event["type"] == "checkout.session.expired":
        s = event["data"]["object"]
        pledge_id = int((s.get("metadata") or {}).get("pledge_id", 0) or 0)
        if pledge_id:  # abandoned checkout — cancel only if not already paid
            async with (await pool()).acquire() as c:
                await c.execute(
                    "UPDATE pledges SET status='cancelled', updated_at=now() "
                    "WHERE pledge_id=$1 AND status<>'collected'", pledge_id)
    return {"received": True}

@app.get("/campaigns/progress")
async def campaigns_progress():
    """Cockpit feed: every zone's capital vs its build-gate (doc 18 §5)."""
    async with (await pool()).acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM campaign_progress ORDER BY build_gate_met DESC, "
            "capital_committed_usd DESC")
    return [dict(r) for r in rows]

@app.get("/campaigns/{zone_id}")
async def campaign_one(zone_id: str):
    async with (await pool()).acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM campaign_progress WHERE zone_id=$1", zone_id)
    if not row:
        raise HTTPException(404, f"no campaign for zone {zone_id}")
    return dict(row)

@app.post("/pledge/{pledge_id}/refund")
async def refund_pledge(pledge_id: int):
    """Refund a refundable pledge (zone cancelled, or member exit — doc 18 §4/§6)."""
    async with (await pool()).acquire() as c:
        pl = await c.fetchrow(
            "SELECT stripe_payment_intent, refundable, status FROM pledges "
            "WHERE pledge_id=$1", pledge_id)
    if not pl:
        raise HTTPException(404, "pledge not found")
    if not pl["refundable"]:
        raise HTTPException(400, "pledge is not refundable")
    if stripe and STRIPE_SECRET_KEY and pl["stripe_payment_intent"]:
        stripe.Refund.create(payment_intent=pl["stripe_payment_intent"])
        # the charge.refunded webhook will flip status; return optimistically
    else:
        async with (await pool()).acquire() as c:
            await c.execute(
                "UPDATE pledges SET status='refunded', refunded_at=now(), "
                "updated_at=now() WHERE pledge_id=$1", pledge_id)
    return {"ok": True, "pledge_id": pledge_id, "status": "refunding"}
