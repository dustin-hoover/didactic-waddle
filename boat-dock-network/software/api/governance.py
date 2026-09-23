#!/usr/bin/env python3
"""Boat Dock Network — cooperative governance API (FastAPI + PostGIS).

Makes doc 16 real: the WAKE unit ledger, monthly accrual, forfeiture to the Commons
Pool, annual redistribution, and Snapshot-style capped/anti-whale voting on proposals.
Backed by software/db/governance_schema.sql. Reference implementation / contract; deploy
behind the DockOS stack (doc 14) alongside serviceability.py + capital.py.

Governance rules (doc 16 / tokenomics_sim.py):
  * +1 WAKE per full month of active membership; hosts accrue at 1.5x.
  * On churn, the member's units are forfeited to the Commons Pool.
  * Annually, 50% of the Commons Pool is redistributed equally to active members.
  * Voting weight = BASE(1) + min(units, 120), then clipped to <=2% of total active
    weight at tally time (anti-capture). Non-transferable; capital never buys votes.

Run (dev):
  pip install fastapi uvicorn asyncpg pydantic
  DATABASE_URL=postgresql://dockos:dockos@localhost:5432/dockos \
    uvicorn governance:app --reload
"""
from __future__ import annotations
import os, datetime as dt
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncpg

app = FastAPI(title="Boat Dock Network — Governance API")
DB = os.environ.get("DATABASE_URL", "postgresql://dockos:dockos@localhost:5432/dockos")

# --- governance constants (doc 16) ---
BASE_VOTE   = 1
VOTE_CAP    = 120       # units cap for voting weight (10 yrs @ 1/mo)
HOST_MULT   = 1.5       # host-node accrual multiplier
WHALE_CAP   = 0.02      # no member exceeds 2% of total active weight at tally
REDIST_FRAC = 0.50      # fraction of Commons Pool redistributed per run

_pool: Optional[asyncpg.Pool] = None
async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB, min_size=1, max_size=8)
    return _pool

# ---------- WAKE ledger mechanics ----------
async def _rebuild_balances(c: asyncpg.Connection, member_ids: Optional[list[int]] = None):
    """Recompute wake_balances from the append-only ledger (source of truth)."""
    if member_ids:
        await c.execute("""
            INSERT INTO wake_balances (member_id, units, updated_at)
            SELECT m.member_id, COALESCE(SUM(l.amount),0), now()
            FROM members m LEFT JOIN wake_ledger l ON l.member_id=m.member_id
            WHERE m.member_id = ANY($1::bigint[])
            GROUP BY m.member_id
            ON CONFLICT (member_id) DO UPDATE SET units=EXCLUDED.units, updated_at=now()
        """, member_ids)
    else:
        await c.execute("""
            INSERT INTO wake_balances (member_id, units, updated_at)
            SELECT m.member_id, COALESCE(SUM(l.amount),0), now()
            FROM members m LEFT JOIN wake_ledger l ON l.member_id=m.member_id
            GROUP BY m.member_id
            ON CONFLICT (member_id) DO UPDATE SET units=EXCLUDED.units, updated_at=now()
        """)

class AccrueIn(BaseModel):
    period: Optional[dt.date] = None   # accrual month (defaults to first of this month)

@app.post("/wake/accrue-month")
async def accrue_month(a: AccrueIn):
    """Grant +1 (x1.5 for hosts) to every active member for `period`. Idempotent:
    a member who already has an accrual row for that period is skipped."""
    period = (a.period or dt.date.today().replace(day=1))
    async with (await pool()).acquire() as c:
        async with c.transaction():
            rows = await c.fetch("""
                SELECT m.member_id, m.is_host FROM members m
                WHERE m.status='active'
                  AND NOT EXISTS (SELECT 1 FROM wake_ledger l
                     WHERE l.member_id=m.member_id AND l.event='accrual' AND l.period=$1)
            """, period)
            ids = []
            for r in rows:
                amt = HOST_MULT if r["is_host"] else 1
                ev  = 'host_bonus' if r["is_host"] else 'accrual'
                # record the base accrual as 'accrual' so idempotency check holds
                await c.execute("""INSERT INTO wake_ledger (member_id,event,amount,period,note)
                    VALUES ($1,'accrual',$2,$3,$4)""",
                    r["member_id"], amt, period,
                    'monthly accrual' + (' (host 1.5x)' if r["is_host"] else ''))
                ids.append(r["member_id"])
            await _rebuild_balances(c, ids)
    return {"ok": True, "period": str(period), "accrued_members": len(ids)}

class MemberOp(BaseModel):
    member_id: int

@app.post("/members/leave")
async def member_leave(m: MemberOp):
    """Member churns: forfeit their current units to the Commons Pool (doc 16)."""
    async with (await pool()).acquire() as c:
        async with c.transaction():
            bal = await c.fetchrow("SELECT units FROM wake_balances WHERE member_id=$1", m.member_id)
            units = float(bal["units"]) if bal else 0.0
            if units > 0:
                await c.execute("""INSERT INTO wake_ledger (member_id,event,amount,note)
                    VALUES ($1,'forfeit',$2,'forfeit on exit')""", m.member_id, -units)
                await c.execute("""INSERT INTO commons_pool (id,units,updated_at)
                    VALUES (1,$1,now()) ON CONFLICT (id)
                    DO UPDATE SET units=commons_pool.units+$1, updated_at=now()""", units)
            await c.execute("UPDATE members SET status='lapsed', lapsed_at=current_date "
                            "WHERE member_id=$1", m.member_id)
            await _rebuild_balances(c, [m.member_id])
    return {"ok": True, "member_id": m.member_id, "forfeited": units}

@app.post("/wake/redistribute")
async def redistribute():
    """Annual: redistribute 50% of the Commons Pool equally to active members (doc 16)."""
    async with (await pool()).acquire() as c:
        async with c.transaction():
            p = await c.fetchrow("SELECT units FROM commons_pool WHERE id=1")
            pool_units = float(p["units"]) if p else 0.0
            actives = [r["member_id"] for r in await c.fetch(
                "SELECT member_id FROM members WHERE status='active'")]
            if pool_units <= 0 or not actives:
                return {"ok": True, "redistributed": 0, "per_member": 0, "recipients": len(actives)}
            give = pool_units * REDIST_FRAC
            per = give / len(actives)
            for mid in actives:
                await c.execute("""INSERT INTO wake_ledger (member_id,event,amount,note)
                    VALUES ($1,'redistribute',$2,'annual commons redistribution')""", mid, per)
            await c.execute("UPDATE commons_pool SET units=units-$1, updated_at=now() WHERE id=1", give)
            await _rebuild_balances(c, actives)
    return {"ok": True, "redistributed": round(give, 3), "per_member": round(per, 4),
            "recipients": len(actives)}

# ---------- voting weight ----------
def _raw_weight(units: float) -> float:
    return BASE_VOTE + min(float(units), VOTE_CAP)

def _clip_whale(weights: dict[int, float]) -> dict[int, float]:
    """Anti-capture cap (doc 16): no member controls more than the GREATER of 2% or one
    equal share of the total active weight. The `1/N` floor keeps the rule coherent at
    small membership (a flat 2% would clip everyone when there are <50 members, since
    2% < an equal share); at scale it converges to the 2% anti-whale cap. Single pass vs
    the pre-clip total, 'of the total active weight at tally time'."""
    n = len(weights)
    total = sum(weights.values())
    if n == 0 or total <= 0:
        return weights
    cap = max(WHALE_CAP, 1.0 / n) * total
    return {mid: min(w, cap) for mid, w in weights.items()}

async def _active_weights(c: asyncpg.Connection) -> dict[int, float]:
    rows = await c.fetch("""
        SELECT b.member_id, b.units FROM wake_balances b
        JOIN members m ON m.member_id=b.member_id WHERE m.status='active'""")
    return {r["member_id"]: _raw_weight(r["units"]) for r in rows}

@app.get("/governance/weights")
async def governance_weights():
    """Current voting weights: raw and whale-clipped, plus totals (for the cockpit)."""
    async with (await pool()).acquire() as c:
        raw = await _active_weights(c)
        p = await c.fetchrow("SELECT units FROM commons_pool WHERE id=1")
    clipped = _clip_whale(raw)
    return {"members": len(raw), "total_raw_weight": round(sum(raw.values()), 3),
            "total_clipped_weight": round(sum(clipped.values()), 3),
            "commons_pool_units": float(p["units"]) if p else 0.0,
            "whale_cap_pct": WHALE_CAP * 100, "vote_cap_units": VOTE_CAP}

# ---------- proposals & votes ----------
class ProposalIn(BaseModel):
    title: str
    body: Optional[str] = None
    category: Optional[str] = None
    quorum_pct: float = 15
    pass_pct: float = 50          # 66.7 for bylaws
    created_by: Optional[int] = None
    days_open: int = 7

@app.post("/proposals")
async def create_proposal(p: ProposalIn):
    async with (await pool()).acquire() as c:
        row = await c.fetchrow("""
            INSERT INTO proposals (title,body,category,status,quorum_pct,pass_pct,created_by)
            VALUES ($1,$2,$3,'draft',$4,$5,$6) RETURNING proposal_id""",
            p.title, p.body, p.category, p.quorum_pct, p.pass_pct, p.created_by)
    return {"ok": True, "proposal_id": row["proposal_id"], "days_open": p.days_open}

@app.post("/proposals/{pid}/open")
async def open_proposal(pid: int, days_open: int = 7):
    async with (await pool()).acquire() as c:
        r = await c.fetchrow("""UPDATE proposals SET status='open', opens_at=now(),
            closes_at=now() + ($2 || ' days')::interval
            WHERE proposal_id=$1 AND status IN ('draft','open') RETURNING proposal_id""",
            pid, str(days_open))
    if not r:
        raise HTTPException(400, "proposal not found or not openable")
    return {"ok": True, "proposal_id": pid}

class VoteIn(BaseModel):
    member_id: int
    choice: Literal["for", "against", "abstain"]

@app.post("/proposals/{pid}/vote")
async def cast_vote(pid: int, v: VoteIn):
    """Cast (or change) a member's vote; stores the member's raw weight at cast time.
    The anti-whale clip is applied at tally, not here."""
    async with (await pool()).acquire() as c:
        prop = await c.fetchrow("SELECT status FROM proposals WHERE proposal_id=$1", pid)
        if not prop or prop["status"] != "open":
            raise HTTPException(400, "proposal not open for voting")
        m = await c.fetchrow("""SELECT b.units FROM wake_balances b JOIN members m
            ON m.member_id=b.member_id WHERE b.member_id=$1 AND m.status='active'""", v.member_id)
        if not m:
            raise HTTPException(400, "not an active member")
        w = _raw_weight(m["units"])
        await c.execute("""INSERT INTO votes (proposal_id,member_id,choice,weight)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (proposal_id,member_id)
            DO UPDATE SET choice=EXCLUDED.choice, weight=EXCLUDED.weight, cast_at=now()""",
            pid, v.member_id, v.choice, w)
    return {"ok": True, "proposal_id": pid, "member_id": v.member_id, "raw_weight": w}

async def _tally(c: asyncpg.Connection, pid: int) -> dict:
    """Whale-clipped tally against the total ACTIVE weight (quorum denominator)."""
    active = await _active_weights(c)                     # member_id -> raw
    clipped = _clip_whale(active)                         # member_id -> clipped
    total_active = sum(clipped.values())
    votes = await c.fetch("SELECT member_id, choice FROM votes WHERE proposal_id=$1", pid)
    agg = {"for": 0.0, "against": 0.0, "abstain": 0.0}
    participating = 0.0
    for r in votes:
        w = clipped.get(r["member_id"], 0.0)              # only active members count
        if w <= 0:
            continue
        agg[r["choice"]] += w
        participating += w
    prop = await c.fetchrow("SELECT quorum_pct, pass_pct, status FROM proposals WHERE proposal_id=$1", pid)
    quorum_pct = float(prop["quorum_pct"]); pass_pct = float(prop["pass_pct"])
    turnout = (100 * participating / total_active) if total_active else 0.0
    decisive = agg["for"] + agg["against"]
    approval = (100 * agg["for"] / decisive) if decisive else 0.0
    quorum_met = turnout >= quorum_pct
    passed = quorum_met and approval >= pass_pct
    return {"proposal_id": pid, "status": prop["status"],
            "total_active_weight": round(total_active, 3),
            "for": round(agg["for"], 3), "against": round(agg["against"], 3),
            "abstain": round(agg["abstain"], 3),
            "turnout_pct": round(turnout, 2), "quorum_pct": quorum_pct,
            "quorum_met": quorum_met, "approval_pct": round(approval, 2),
            "pass_pct": pass_pct, "would_pass": passed}

@app.get("/proposals")
async def list_proposals():
    async with (await pool()).acquire() as c:
        rows = await c.fetch("SELECT * FROM proposals ORDER BY created_at DESC")
    return [dict(r) for r in rows]

@app.get("/proposals/{pid}")
async def get_proposal(pid: int):
    async with (await pool()).acquire() as c:
        prop = await c.fetchrow("SELECT * FROM proposals WHERE proposal_id=$1", pid)
        if not prop:
            raise HTTPException(404, "proposal not found")
        tally = await _tally(c, pid)
    return {"proposal": dict(prop), "tally": tally}

@app.post("/proposals/{pid}/close")
async def close_proposal(pid: int):
    """Finalize: compute the tally and set passed/failed by quorum + pass %."""
    async with (await pool()).acquire() as c:
        async with c.transaction():
            t = await _tally(c, pid)
            new_status = "passed" if t["would_pass"] else "failed"
            await c.execute("UPDATE proposals SET status=$2 WHERE proposal_id=$1", pid, new_status)
            t["status"] = new_status
    return t
