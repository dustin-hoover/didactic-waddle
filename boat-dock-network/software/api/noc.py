#!/usr/bin/env python3
"""DockOS NOC — monitoring, correlation and outage management (DockOS step 7, doc 24).

Collectors (Prometheus + snmp/blackbox exporters, doc 21 §10) decide what is DOWN. This
service decides what BROKE, who is dark, and what happens next:

  Alertmanager webhook ──▶ alerts ──▶ element state (hold-down 60 s, clear-hold 120 s,
      flap damping: ≥3 episodes/30 min holds the element down until 15 min stable)
  ──▶ topology correlation (software/noc/topology.py): reachability from the head-ends,
      root cause vs suppressed vs silent, one event per dark component
  ──▶ incident:
        outage   (members dark: isolation / dead node / dead access sector)
                 → outage_services (ACTIVE services only — seasonal holds and suspended
                   services are not "down") → P1 repair inserted as the next stop of the
                   crew that gets there first (dispatch.dispatch_outage, doc 23)
                 → member notices with ETA → public status page
        degraded (redundancy lost, nobody dark: ring open, lost head-end) → P2 repair, no notice
        power    (solar/battery site forecast to hit low-voltage cutoff before the sun is
                 back) → proactive repair BEFORE members go dark; adopted by the outage if
                 the site dies anyway
        CPE      one member radio down ≥ 30 min → P3 ticket; cancelled if it self-clears
  ──▶ recovery (telemetry, not the crew's word) → resolve → un-started work cancelled
      → automatic credits (doc 22 account_credits) → "restored" notices.

Credits (member SLA, doc 24 §6): business — any outage over the 4 h P1 restore target
credits 2× the prorated time, rounded up to the hour; residential — outages of 24 h or more
credit whole days. Both capped at one month and applied to the next bill without asking.

Run: uvicorn noc:app (from software/api). Evaluate is also exposed for a 30 s cron tick.
"""
from __future__ import annotations
import os, sys, json, math, hashlib, html, datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import asyncpg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, os.path.join(REPO, "software", "noc"), os.path.join(REPO, "software", "dispatch")]
import topology as T                                   # noqa: E402
import dispatch as D                                   # noqa: E402  (doc 23: work orders + dispatch)

app = FastAPI(title="Boat Dock Network — NOC")
DB = os.environ.get("DATABASE_URL", "postgresql://dockos:dockos@localhost:5432/dockos")
TZ = ZoneInfo("America/Chicago")
UTC = dt.timezone.utc
WEBHOOK_TOKEN = os.environ.get("NOC_WEBHOOK_TOKEN")      # Alertmanager http_config.authorization
STATUS_URL = os.environ.get("STATUS_URL", "https://status.boatdock.network")
MGMT_DOMAIN = os.environ.get("MGMT_DOMAIN", "mgmt.boatdock.network")

HOLD_DOWN_S = 60            # an element must be down this long before anything opens
CLEAR_HOLD_S = 120          # ... and back this long before anything closes
FLAP_WINDOW_MIN, FLAP_EPISODES, FLAP_STABLE_MIN = 30, 3, 15
CPE_TICKET_AFTER_MIN = 30   # single member radio: could be a tripped breaker at the house
SECTOR_MIN_CPES, SECTOR_FRACTION = 3, 0.30
BIZ_SLA_H, BIZ_CREDIT_MULT, RES_CREDIT_AFTER_H = 4, 2, 24
SOC_CUTOFF_PCT, POWER_LEAD_H, POWER_URGENT_H, SOLAR_RECOVERY_HOUR = 20.0, 12.0, 6.0, 9
DOWN_ALERTS = {"NodeDown": "node", "LinkDown": "link", "CPEDown": "service"}
POWER_ALERTS = {"MainsFail", "OnBattery", "BatteryLow"}
REPAIR_H = D.WO_TYPES["repair"][1]
LINK_WORDS = {"water_long": "licensed microwave lake crossing", "water_short": "short lake hop",
              "land": "land hop", "headend_fiber": "head-end fiber"}

_pool: Optional[asyncpg.Pool] = None
async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB, min_size=1, max_size=8)
    return _pool

def money(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def ts(s: Optional[str]) -> Optional[dt.datetime]:
    if not s or s.startswith("0001-"):
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))

def _now(now: Optional[dt.datetime]) -> dt.datetime:
    return (now or dt.datetime.now(UTC)).astimezone(UTC)

def local(t: Optional[dt.datetime]) -> str:
    return t.astimezone(TZ).strftime("%a %-I:%M %p") if t else "—"

def dur(a: dt.datetime, b: dt.datetime) -> str:
    m = max(0, round((b - a).total_seconds() / 60))
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"

# ---------------------------------------------------------------- topology from the DB
async def db_topology(c, design: bool = False) -> T.Topology:
    """Operational graph = built/live sites and built links. design=True uses every planned
    site (for SPOF analysis before anything is lit)."""
    st = "status <> 'retired'" if design else "status IN ('built','live')"
    nodes = {r["node_id"]: {"lon": r["lon"], "lat": r["lat"], "tier": r["tier"], "zone": r["zone_id"],
                            "power": r["power"]}
             for r in await c.fetch(f"""SELECT node_id, zone_id, tier::text, power::text,
                 ST_X(geom) AS lon, ST_Y(geom) AS lat FROM nodes WHERE {st}""")}
    links = {r["link_id"]: T.Link(r["link_id"], r["a_node"], r["b_node"], r["kind"] or "land",
                                  float(r["km"] or 0), float(r["cost_usd"] or 0))
             for r in await c.fetch("SELECT * FROM links WHERE NOT COALESCE(planned, false)")
             if r["a_node"] in nodes and r["b_node"] in nodes}
    return T.Topology(nodes, links, sorted(n for n, x in nodes.items() if x["tier"] == "T0"))

async def services(c) -> list[dict]:
    return [dict(r) for r in await c.fetch("""
        SELECT si.service_id, si.customer_id, si.node_id, si.address_id, si.state::text AS state,
               si.suspend_reason, p.monthly_usd, p.is_business
        FROM service_instances si JOIN subscriptions s ON s.sub_id = si.sub_id
        JOIN plans p ON p.plan_id = s.plan_id WHERE si.state <> 'terminated'""")]

# ---------------------------------------------------------------- ingest
class AMAlert(BaseModel):
    status: str
    labels: dict
    annotations: dict = {}
    startsAt: str
    endsAt: Optional[str] = None
    fingerprint: Optional[str] = None

class AMWebhook(BaseModel):          # Alertmanager webhook payload, version 4
    version: str = "4"
    status: Optional[str] = None
    receiver: Optional[str] = None
    alerts: list[AMAlert]

async def _element(c, labels: dict) -> tuple[Optional[str], Optional[str]]:
    for k, kind in (("node", "node"), ("link", "link"), ("service_id", "service")):
        if labels.get(k):
            return kind, str(labels[k])
    inst = (labels.get("instance") or labels.get("device") or "").split(":")[0]
    d = await c.fetchrow("SELECT role, node_id, link_id, service_id FROM devices WHERE name=$1 OR name=split_part($1,'.',1)", inst) if inst else None
    if d:
        if d["service_id"]:
            return "service", str(d["service_id"])
        if d["link_id"] and d["role"] in ("radio", "optic"):
            return "link", d["link_id"]
        if d["node_id"]:
            return "node", d["node_id"]
    return None, None

@app.post("/ingest/alertmanager")
async def ingest(w: AMWebhook, now: Optional[dt.datetime] = None, authorization: Optional[str] = Header(None)):
    if WEBHOOK_TOKEN and authorization != f"Bearer {WEBHOOK_TOKEN}":
        raise HTTPException(401, "bad webhook token")
    now = _now(now)
    n = 0
    async with (await pool()).acquire() as c:
        async with c.transaction():
            for a in w.alerts:
                kind, el = await _element(c, a.labels)
                name = a.labels.get("alertname", "unknown")
                fp = a.fingerprint or hashlib.sha1(json.dumps(a.labels, sort_keys=True).encode()).hexdigest()[:16]
                start, end = ts(a.startsAt), ts(a.endsAt)
                resolved = a.status == "resolved"
                await c.execute("""INSERT INTO alerts (fingerprint, alertname, element_kind, element, labels, annotations,
                        status, starts_at, ends_at, severity, message, opened_at, closed_at, last_seen)
                    VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7,$8,$9,$10,$11,$8,$12,$13)
                    ON CONFLICT (fingerprint, starts_at) DO UPDATE SET status=EXCLUDED.status,
                        ends_at=EXCLUDED.ends_at, closed_at=EXCLUDED.closed_at, last_seen=EXCLUDED.last_seen,
                        annotations=EXCLUDED.annotations""",
                    fp, name, kind, el, json.dumps(a.labels), json.dumps(a.annotations),
                    "resolved" if resolved else "firing", start, end if resolved else None,
                    a.labels.get("severity"), a.annotations.get("summary"), end if resolved else None, now)
                n += 1
            result = await evaluate(c, now)
    return {"ok": True, "ingested": n, **result}

@app.post("/noc/evaluate")
async def post_evaluate(now: Optional[dt.datetime] = None):
    """Periodic tick (every 30 s): hold-downs expire and forecasts move without new alerts."""
    async with (await pool()).acquire() as c:
        async with c.transaction():
            return await evaluate(c, _now(now))

# ---------------------------------------------------------------- element state
async def element_states(c, now: dt.datetime) -> dict:
    rows = await c.fetch("""SELECT element_kind, element, status, starts_at, ends_at FROM alerts
        WHERE alertname = ANY($1::text[]) AND element IS NOT NULL AND starts_at <= $2
          AND (status = 'firing' OR ends_at > $2::timestamptz - make_interval(mins => $3))
        ORDER BY starts_at""", list(DOWN_ALERTS), now, max(FLAP_WINDOW_MIN, FLAP_STABLE_MIN))
    by = {}
    for r in rows:
        by.setdefault((r["element_kind"], r["element"]), []).append(r)
    out = {}
    for key, inst in by.items():
        def end(a):
            return None if a["status"] == "firing" or (a["ends_at"] and a["ends_at"] > now) else a["ends_at"]
        firing = [a for a in inst if end(a) is None]
        recent = [a for a in inst if a["starts_at"] >= now - dt.timedelta(minutes=FLAP_WINDOW_MIN)]
        flapping = len(recent) >= FLAP_EPISODES
        if flapping:       # damped: held down until stable for FLAP_STABLE_MIN
            down = bool(firing) or any(end(a) > now - dt.timedelta(minutes=FLAP_STABLE_MIN) for a in inst if end(a))
        else:
            hold, clear = dt.timedelta(seconds=HOLD_DOWN_S), dt.timedelta(seconds=CLEAR_HOLD_S)
            down = any(now - a["starts_at"] >= hold for a in firing) or any(
                end(a) - a["starts_at"] >= hold and end(a) > now - clear for a in inst if end(a))
        ended = [end(a) for a in inst if end(a)]
        out[key] = {"down": down, "pending": bool(firing) and not down, "flapping": flapping,
                    "since": min(a["starts_at"] for a in (recent if flapping else inst)),
                    "recovered_at": None if firing else (max(ended) if ended else None)}
    return out

# ---------------------------------------------------------------- the evaluator
async def evaluate(c, now: dt.datetime) -> dict:
    await c.execute("SELECT pg_advisory_xact_lock(7240)")          # one evaluator at a time
    topo = await db_topology(c)
    st = await element_states(c, now)
    fn = {e for (k, e), s in st.items() if k == "node" and s["down"] and e in topo.nodes}
    fl = {e for (k, e), s in st.items() if k == "link" and s["down"] and e in topo.links}
    corr = topo.correlate(fn, fl)
    svcs = await services(c)
    by_node = {}
    for s in svcs:
        by_node.setdefault(s["node_id"], []).append(s)
    heads = set(topo.heads)
    power_evidence = {r["element"] for r in await c.fetch("""SELECT DISTINCT element FROM alerts
        WHERE alertname = ANY($1::text[]) AND element_kind='node' AND starts_at > $2::timestamptz - interval '24 hours'""",
        list(POWER_ALERTS), now)}
    power_evidence |= {r["node_id"] for r in await c.fetch("""SELECT DISTINCT ON (node_id) node_id, soc_pct FROM site_power
        WHERE ts <= $1 AND ts > $1::timestamptz - interval '6 hours' ORDER BY node_id, ts DESC""", now)
        if r["soc_pct"] is not None and float(r["soc_pct"]) <= SOC_CUTOFF_PCT + 5}

    want = []                                   # desired open incidents this tick
    for comp in corr["components"]:
        roots = comp["roots"]
        since = min([st[("node", r)]["since"] for r in roots if ("node", r) in st] +
                    [st[("link", r)]["since"] for r in roots if ("link", r) in st] or [now])
        flapping = any(st.get(("node", r), st.get(("link", r), {})).get("flapping") for r in roots)
        served = comp["dark"] - heads
        detail, public = _cause(topo, corr, roots, power_evidence)
        if flapping:
            detail += " (flapping — held until stable 15 min)"
        repair = next((r for r in roots if r in topo.nodes), None) or \
            (topo.far_end(roots[0], corr["reachable"]) if roots else sorted(comp["dark"])[0])
        if not served:          # only head-ends dark: traffic rides the other head-end
            want.append({"kind": "degraded", "roots": roots, "dark": set(), "since": since, "repair": repair,
                         "detail": detail + " — traffic on the other head-end, no members affected",
                         "cause": "Reduced redundancy", "svcs": []})
            continue
        impacted = [s for n in served for s in by_node.get(n, []) if s["state"] == "active"]
        want.append({"kind": "outage", "roots": roots, "dark": served, "since": since, "repair": repair,
                     "detail": detail, "cause": public, "svcs": impacted, "silent": comp["silent"]})
    for lid in sorted(corr["ring_open"]):
        s = st[("link", lid)]
        want.append({"kind": "degraded", "roots": [lid], "dark": set(), "since": s["since"],
                     "repair": topo.links[lid].a if topo.links[lid].a not in heads else topo.links[lid].b,
                     "detail": f"Ring open: {lid} ({LINK_WORDS.get(topo.links[lid].kind, '')}) down — traffic "
                               f"rerouted, no members affected{' (flapping)' if s['flapping'] else ''}",
                     "cause": "Reduced redundancy", "svcs": []})

    # member radios: suppressed by a dark node, a sector event, a ticket, or ignored (not active)
    down_svc = {int(e): s for (k, e), s in st.items() if k == "service" and s["down"]}
    svc_by_id = {s["service_id"]: s for s in svcs}
    disp = {}
    sector_svcs, tickets = set(), []
    for n, lst in by_node.items():
        if n in corr["dark"] or n not in topo.nodes:
            continue
        active = [s for s in lst if s["state"] == "active"]
        dn = [s for s in active if s["service_id"] in down_svc]
        if len(dn) >= SECTOR_MIN_CPES and len(dn) >= SECTOR_FRACTION * len(active):
            since = min(down_svc[s["service_id"]]["since"] for s in dn)
            want.append({"kind": "outage", "roots": [f"{n}:access"], "dark": set(), "since": since, "repair": n,
                         "detail": f"Access radio at {n}: {len(dn)} of {len(active)} member radios down, node reachable",
                         "cause": "Access-radio failure at a local network site", "svcs": dn})
            sector_svcs |= {s["service_id"] for s in dn}
    for sid, s in down_svc.items():
        si = svc_by_id.get(sid)
        if not si:
            continue
        if si["node_id"] in corr["dark"]:
            disp[("service", str(sid))] = "suppressed"
        elif si["state"] != "active":
            disp[("service", str(sid))] = "ignored_inactive"      # seasonal hold / suspended: expected
        elif sid in sector_svcs:
            disp[("service", str(sid))] = "root_cause"
        elif s["since"] <= now - dt.timedelta(minutes=CPE_TICKET_AFTER_MIN):
            tickets.append(si); disp[("service", str(sid))] = "ticket"
        else:
            disp[("service", str(sid))] = "pending"

    changes = await reconcile(c, topo, corr, want, now)
    changes["tickets"] = await cpe_tickets(c, tickets, set(down_svc), now)
    changes["power"] = await evaluate_power(c, topo, by_node, corr, now)

    # alert dispositions (what the NOC board shows next to every alarm)
    el_outage = changes.pop("_element_outage")
    for n in fn:
        disp[("node", n)] = "root_cause" if n in corr["root_nodes"] else "suppressed"
    for l in fl:
        disp[("link", l)] = ("root_cause" if l in corr["root_links"] else
                             "ring_open" if l in corr["ring_open"] else "suppressed")
    for key, s in st.items():
        if s["pending"] and key not in disp:
            disp[key] = "pending"
    for (k, e), d in disp.items():
        oid = el_outage.get(e) or (el_outage.get(f"{svc_by_id[int(e)]['node_id']}:access")
                                   if k == "service" and int(e) in svc_by_id else None)
        if k == "service" and d == "suppressed":
            oid = el_outage.get(svc_by_id[int(e)]["node_id"])
        await c.execute("""UPDATE alerts SET disposition=$3, outage_id=COALESCE($4, outage_id)
            WHERE element_kind=$1 AND element=$2 AND status='firing'""", k, e, d, oid)
    await c.execute("""UPDATE alerts SET disposition='info' WHERE status='firing' AND disposition IS NULL
        AND alertname <> ALL($1::text[])""", list(DOWN_ALERTS))
    return {"now": now.isoformat(), "down_nodes": sorted(fn), "down_links": sorted(fl),
            "root_causes": sorted(corr["root_nodes"] | corr["root_links"]),
            "suppressed": len(corr["suppressed_nodes"]) + len(corr["suppressed_links"]),
            "silent_dark": sorted(set().union(*[c_["silent"] for c_ in corr["components"]]) - heads)
            if corr["components"] else [],
            "ring_open": sorted(corr["ring_open"]), **changes}

def _cause(topo, corr, roots, power_evidence) -> tuple[str, str]:
    det, pub = [], set()
    for r in roots:
        if r in topo.heads:
            det.append(f"Head-end {r} down"); pub.add("Head-end failure")
        elif r in topo.nodes:
            p = topo.nodes[r]["power"]
            if r in power_evidence:
                why = "battery exhausted" if p == "solar_battery" else "utility power loss outlasted the UPS"
                det.append(f"Power loss at {r} ({why})"); pub.add("Power loss at a network site")
            else:
                det.append(f"Node {r} not responding"); pub.add("Equipment failure at a network site")
        else:
            l = topo.links[r]
            det.append(f"Backbone link {r} down ({LINK_WORDS.get(l.kind, l.kind)}) — "
                       f"{topo.far_end(r, corr['reachable'])} side cut off")
            pub.add("Backbone link failure")
    return "; ".join(det) or "Unreachable (no path in the design)", "; ".join(sorted(pub)) or "Network failure"

# ---------------------------------------------------------------- incidents
async def reconcile(c, topo, corr, want: list[dict], now: dt.datetime) -> dict:
    open_ = [dict(r) for r in await c.fetch("""SELECT * FROM outages WHERE status='open' AND noc_managed
        AND kind IN ('outage','degraded') FOR UPDATE""")]
    used, opened, updated, resolved, el_outage = set(), [], [], [], {}
    for w in want:
        match = next((o for o in open_ if o["outage_id"] not in used and o["kind"] == w["kind"] and (
            set(o["root_elements"] or []) & set(w["roots"]) or set(o["dark_nodes"] or []) & w["dark"])), None)
        if match:
            used.add(match["outage_id"])
            oid = match["outage_id"]
            if await _update(c, match, w, now):
                updated.append(oid)
        else:
            oid = await _open(c, topo, w, now)
            opened.append(oid)
        for e in list(w["roots"]) + sorted(w["dark"]):
            el_outage[e] = oid
    for o in open_:
        if o["outage_id"] not in used:
            resolved.append(await resolve(c, o, now))
    return {"opened": opened, "updated": updated, "resolved": resolved, "_element_outage": el_outage}

async def _geo(c, nodes: list[str]):
    return await c.fetchval("""SELECT ST_Multi(ST_ConvexHull(ST_Collect(ST_Buffer(geom::geography, 2000)::geometry)))
        FROM nodes WHERE node_id = ANY($1::text[])""", nodes)

async def _add_services(c, oid: int, svcs: list[dict]) -> list[int]:
    new = []
    for s in svcs:
        r = await c.fetchval("""INSERT INTO outage_services (outage_id, service_id, customer_id, node_id, is_business, monthly_usd)
            VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING RETURNING customer_id""",
            oid, s["service_id"], s["customer_id"], s["node_id"], bool(s["is_business"]), s["monthly_usd"])
        if r:
            new.append(r)
    await c.execute("""UPDATE outages SET impacted_services=(SELECT count(*) FROM outage_services WHERE outage_id=$1),
        impacted_business=(SELECT count(*) FROM outage_services WHERE outage_id=$1 AND is_business),
        impacted_customers=(SELECT count(DISTINCT customer_id) FROM outage_services WHERE outage_id=$1)
        WHERE outage_id=$1""", oid)
    return new

async def _zones(c, nodes) -> list[str]:
    return [r["zone_id"] for r in await c.fetch(
        "SELECT DISTINCT zone_id FROM nodes WHERE node_id = ANY($1::text[]) AND zone_id IS NOT NULL ORDER BY 1", list(nodes))]

async def _open(c, topo, w: dict, now: dt.datetime) -> int:
    area = sorted(w["dark"]) or [w["repair"]]
    oid = await c.fetchval("""INSERT INTO outages (kind, status, noc_managed, cause, detail, root_node, root_elements,
            dark_nodes, zones, started_at, detected_at, impact_polygon, updated_at)
        VALUES ($1,'open',true,$2,$3,$4,$5,$6,$7,$8,$9,$10,$9) RETURNING outage_id""",
        w["kind"], w["cause"], w["detail"], w["repair"], w["roots"], sorted(w["dark"]),
        await _zones(c, area), w["since"], now, await _geo(c, area))
    if w["kind"] == "degraded":
        wo = await D.create_wo(c, D.WOIn(wo_type="repair", node_id=w["repair"], priority="P2", outage_id=oid,
                                         note=f"NOC #{oid}: {w['detail']}"))
        await D.release_wo(c, wo)
        await c.execute("UPDATE outages SET wo_id=$2 WHERE outage_id=$1", oid, wo)
        return oid
    custs = await _add_services(c, oid, w["svcs"])
    # a crew already heading to this site for a power forecast keeps its place in the run
    pw = await c.fetchrow("""SELECT outage_id, wo_id FROM outages WHERE status='open' AND kind='power'
        AND root_node=$1 AND wo_id IS NOT NULL""", w["repair"])
    if pw:
        await c.execute("UPDATE outages SET wo_id=$2 WHERE outage_id=$1", oid, pw["wo_id"])
        await c.execute("UPDATE work_orders SET outage_id=$2, priority='P1', note=note || $3 WHERE wo_id=$1",
                        pw["wo_id"], oid, f"\nNow outage #{oid}: {w['detail']}")
        await c.execute("""UPDATE outages SET status='resolved', resolved_at=$2, wo_id=NULL,
            detail=detail || $3 WHERE outage_id=$1""", pw["outage_id"], now, f" — superseded by outage #{oid}")
        wo = await c.fetchrow("SELECT eta, status FROM work_orders WHERE wo_id=$1", pw["wo_id"])
        if wo["status"] == "released":      # was a P2 for the planner: insert it now
            await c.execute("UPDATE outages SET wo_id=NULL WHERE outage_id=$1", oid)
            await c.execute("UPDATE work_orders SET status='cancelled', note=note || $2 WHERE wo_id=$1",
                            pw["wo_id"], f"\nreplaced by P1 for outage #{oid}")
            await _dispatch(c, oid, now)
        else:
            eta = wo["eta"] + dt.timedelta(hours=REPAIR_H) if wo["eta"] else None
            await c.execute("UPDATE outages SET eta=$2 WHERE outage_id=$1", oid, eta)
    else:
        await _dispatch(c, oid, now)
    await notify(c, oid, custs, "outage_opened")
    return oid

async def _dispatch(c, oid: int, now: dt.datetime) -> dict:
    r = await D.dispatch_outage(c, oid, now)
    eta = dt.datetime.fromisoformat(r["eta"]) + dt.timedelta(hours=REPAIR_H) if r.get("assigned") else None
    await c.execute("UPDATE outages SET eta=$2 WHERE outage_id=$1", oid, eta)
    return r

async def _update(c, o: dict, w: dict, now: dt.datetime) -> bool:
    changed = set(o["dark_nodes"] or []) != w["dark"] or set(o["root_elements"] or []) != set(w["roots"]) \
        or o["detail"] != w["detail"]
    if not changed:
        return False
    area = sorted(w["dark"]) or [w["repair"]]
    await c.execute("""UPDATE outages SET root_elements=$2, dark_nodes=$3, detail=$4, cause=$5, zones=$6,
        impact_polygon=$7, updated_at=$8 WHERE outage_id=$1""",
        o["outage_id"], w["roots"], sorted(set(o["dark_nodes"] or []) | w["dark"]), w["detail"], w["cause"],
        sorted(set(o["zones"] or []) | set(await _zones(c, area))), await _geo(c, area), now)
    if o["kind"] == "outage":
        custs = await _add_services(c, o["outage_id"], w["svcs"])
        await notify(c, o["outage_id"], custs, "outage_opened")      # newly dark members only
    return True

async def _recovered_at(c, o: dict, now: dt.datetime) -> dt.datetime:
    els = list(o["root_elements"] or []) + list(o["dark_nodes"] or [])
    svc = [str(r["service_id"]) for r in await c.fetch("SELECT service_id FROM outage_services WHERE outage_id=$1", o["outage_id"])]
    t = await c.fetchval("""SELECT max(ends_at) FROM alerts WHERE status='resolved' AND ends_at <= $1 AND ends_at >= $2
        AND alertname = ANY($3::text[]) AND (element = ANY($4::text[]) OR (element_kind='service' AND element = ANY($5::text[])))""",
        now, o["started_at"], list(DOWN_ALERTS), els, svc)
    return t or now

async def cancel_unstarted(c, wo_id: Optional[int], reason: str) -> bool:
    if not wo_id:
        return False
    w = await c.fetchrow("SELECT status::text, scheduled_for, assigned_crew FROM work_orders WHERE wo_id=$1 FOR UPDATE", wo_id)
    if not w or w["status"] not in ("draft", "permitting", "released", "scheduled"):
        return False
    await c.execute("""UPDATE work_orders SET status='cancelled', route_seq=NULL,
        note=COALESCE(note || E'\\n','') || $2 WHERE wo_id=$1""", wo_id, reason)
    if w["status"] == "scheduled":        # take the stop off the crew's run sheet
        p = await c.fetchrow("SELECT plan FROM dispatch_plans WHERE day=$1 AND crew_id=$2 FOR UPDATE",
                             w["scheduled_for"], w["assigned_crew"])
        if p:
            plan = json.loads(p["plan"]) if isinstance(p["plan"], str) else p["plan"]
            plan["stops"] = [dict(s, seq=i) for i, s in enumerate((s for s in plan["stops"] if s["wo_id"] != wo_id), 1)]
            for s in plan["stops"]:
                await c.execute("UPDATE work_orders SET route_seq=$2 WHERE wo_id=$1", s["wo_id"], s["seq"])
            await c.execute("UPDATE dispatch_plans SET plan=$3::jsonb WHERE day=$1 AND crew_id=$2",
                            w["scheduled_for"], w["assigned_crew"], json.dumps(plan, default=str))
    await D._event(c, wo_id, "cancelled", actor="noc", detail={"reason": reason})
    return True

async def resolve(c, o: dict, now: dt.datetime) -> dict:
    at = await _recovered_at(c, o, now)
    await c.execute("UPDATE outages SET status='resolved', resolved_at=$2, updated_at=$3 WHERE outage_id=$1",
                    o["outage_id"], at, now)
    cancelled = await cancel_unstarted(c, o["wo_id"], f"auto-resolved: telemetry recovered {local(at)} before the crew started")
    out = {"outage_id": o["outage_id"], "kind": o["kind"], "resolved_at": at.isoformat(),
           "duration": dur(o["started_at"], at), "wo_cancelled": cancelled}
    if o["kind"] == "outage":
        out["credits_usd"] = float(await credit(c, o["outage_id"], o["started_at"], at))
        await notify(c, o["outage_id"], None, "outage_resolved")
    return out

# ---------------------------------------------------------------- credits (doc 22 account_credits)
def outage_credit(monthly, is_business: bool, hours: float) -> Decimal:
    m = Decimal(str(monthly or 0))
    if is_business:
        if hours <= BIZ_SLA_H:
            return Decimal("0.00")
        amt = m * BIZ_CREDIT_MULT * math.ceil(hours) / 720
    else:
        if hours < RES_CREDIT_AFTER_H:
            return Decimal("0.00")
        amt = m * math.ceil(hours / 24) / 30
    return money(min(amt, m))

async def credit(c, oid: int, start: dt.datetime, end: dt.datetime) -> Decimal:
    if await c.fetchval("SELECT credited_at FROM outages WHERE outage_id=$1", oid):
        return Decimal(await c.fetchval("SELECT COALESCE(credits_usd,0) FROM outages WHERE outage_id=$1", oid))
    hours = round((end - start).total_seconds() / 60) / 60     # whole minutes, as shown to the member
    total = Decimal("0.00")
    for s in await c.fetch("SELECT * FROM outage_services WHERE outage_id=$1", oid):
        amt = outage_credit(s["monthly_usd"], s["is_business"], hours)
        await c.execute("UPDATE outage_services SET credit_usd=$3 WHERE outage_id=$1 AND service_id=$2",
                        oid, s["service_id"], amt)
        if amt > 0:
            await c.execute("""INSERT INTO account_credits (customer_id, kind, amount_usd, remaining_usd, note)
                VALUES ($1,'outage',$2,$2,$3)""", s["customer_id"], amt,
                f"Outage #{oid} ({dur(start, end)}){' — business SLA 2x' if s['is_business'] else ''}")
            total += amt
    await c.execute("UPDATE outages SET credited_at=now(), credits_usd=$2 WHERE outage_id=$1", oid, total)
    return total

# ---------------------------------------------------------------- member notices
async def notify(c, oid: int, customer_ids: Optional[list[int]], template: str) -> int:
    o = await c.fetchrow("SELECT * FROM outages WHERE outage_id=$1", oid)
    zn = [r["name"] for r in await c.fetch("SELECT name FROM zones WHERE zone_id = ANY($1::text[]) ORDER BY name", o["zones"] or [])]
    where = ", ".join(zn) or "your area"
    rows = await c.fetch("""SELECT DISTINCT ON (os.customer_id) os.customer_id, os.is_business, os.credit_usd,
            cu.email, cu.phone, cu.name
        FROM outage_services os JOIN customers cu ON cu.customer_id=os.customer_id
        WHERE os.outage_id=$1 AND ($2::bigint[] IS NULL OR os.customer_id = ANY($2::bigint[]))
        ORDER BY os.customer_id, os.is_business DESC""", oid, customer_ids)
    n = 0
    for r in rows:
        if template == "outage_opened":
            eta = (f"A crew is on the way — we expect service back by {local(o['eta'])}."
                   if o["eta"] else "A crew is being assigned; we'll text an estimate as soon as we have one.")
            subj = f"Service interruption — {where}"
            body = (f"Boat Dock Network: service in {where} has been interrupted since {local(o['started_at'])} "
                    f"({o['cause'].lower()}). {eta} Live status: {STATUS_URL}. No need to call — outage "
                    f"credits are applied automatically under the member SLA.")
        else:
            cr = Decimal(r["credit_usd"] or 0)
            credit_line = (f"A ${cr:.2f} credit is on your next bill." if cr > 0 else
                           ("Business outages over 4 h are credited automatically; this one was shorter."
                            if r["is_business"] else "Outages of 24 h or more are credited automatically."))
            subj = f"Service restored — {where}"
            body = (f"Boat Dock Network: service in {where} was restored {local(o['resolved_at'])} after "
                    f"{dur(o['started_at'], o['resolved_at'])}. {credit_line} Thanks for your patience — "
                    f"what happened is on {STATUS_URL}.")
        for ch, dest in (("sms", r["phone"]), ("email", r["email"])):
            if not dest:
                continue
            n += await c.fetchval("""INSERT INTO notifications (customer_id, outage_id, template, channel, subject, body)
                VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING RETURNING 1""",
                r["customer_id"], oid, template, ch, subj if ch == "email" else None, body) or 0
    return n

@app.post("/notifications/send")
async def send_notifications(limit: int = 500):
    """Sender: dry-run by default (marks queued notices sent and returns them). Wire the SMS /
    email provider chosen in doc 13 behind NOTIFY_ADAPTER before launch."""
    adapter = os.environ.get("NOTIFY_ADAPTER", "dryrun")
    if adapter != "dryrun":
        raise HTTPException(501, f"adapter {adapter!r} not configured")
    async with (await pool()).acquire() as c:
        rows = await c.fetch("""UPDATE notifications SET status='sent', sent_at=now() WHERE notification_id IN
            (SELECT notification_id FROM notifications WHERE status='queued' ORDER BY notification_id LIMIT $1
             FOR UPDATE SKIP LOCKED) RETURNING notification_id, channel, template""", limit)
    return {"adapter": adapter, "sent": len(rows)}

# ---------------------------------------------------------------- single member radio -> P3 ticket
async def cpe_tickets(c, tickets: list[dict], down_ids: set[int], now: dt.datetime) -> dict:
    made, cleared = [], []
    for si in tickets:
        if await c.fetchval("""SELECT 1 FROM work_orders WHERE service_id=$1 AND status NOT IN ('closed','cancelled')""",
                            si["service_id"]):
            continue
        wo = await D.create_wo(c, D.WOIn(wo_type="repair", service_id=si["service_id"], address_id=si["address_id"],
                                         node_id=None if si["address_id"] else si["node_id"], priority="P3",
                                         note=f"NOC: member radio down since {local(now - dt.timedelta(minutes=CPE_TICKET_AFTER_MIN))}"
                                              " — call the member first (power at the house?)"))
        await D.release_wo(c, wo)
        made.append(wo)
    for r in await c.fetch("""SELECT wo_id, service_id FROM work_orders WHERE wo_type='repair' AND priority='P3'
            AND note LIKE 'NOC:%' AND status IN ('draft','released','scheduled')"""):
        if r["service_id"] not in down_ids and await cancel_unstarted(c, r["wo_id"], "member radio back up on its own"):
            cleared.append(r["wo_id"])
    return {"opened": made, "self_cleared": cleared}

# ---------------------------------------------------------------- solar/battery sites
class PowerSample(BaseModel):
    node_id: str
    ts: dt.datetime
    soc_pct: float
    load_w: Optional[float] = None
    pv_w: Optional[float] = None

class PowerBatch(BaseModel):
    samples: list[PowerSample]

@app.post("/telemetry/power")
async def power_ingest(b: PowerBatch, now: Optional[dt.datetime] = None):
    async with (await pool()).acquire() as c:
        async with c.transaction():
            for s in b.samples:
                await c.execute("""INSERT INTO site_power (node_id, ts, soc_pct, load_w, pv_w) VALUES ($1,$2,$3,$4,$5)
                    ON CONFLICT (node_id, ts) DO UPDATE SET soc_pct=EXCLUDED.soc_pct""",
                    s.node_id, s.ts, s.soc_pct, s.load_w, s.pv_w)
            return await evaluate(c, _now(now))

def soc_forecast(rows: list[tuple[dt.datetime, float]]) -> Optional[dict]:
    """Least-squares SOC trend over the last 6 h -> when the low-voltage disconnect trips."""
    if len(rows) < 3:
        return None
    t0 = rows[0][0]
    xs = [(t - t0).total_seconds() / 3600 for t, _ in rows]
    ys = [float(v) for _, v in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    last_t, soc = rows[-1][0], ys[-1]
    out = {"soc_pct": soc, "slope_pct_h": round(slope, 2), "at": last_t}
    if slope < -0.1:
        h = max(0.0, (soc - SOC_CUTOFF_PCT) / -slope)
        out["hours_to_cutoff"] = round(h, 1)
        out["cutoff_at"] = last_t + dt.timedelta(hours=h)
    return out

async def evaluate_power(c, topo, by_node, corr, now: dt.datetime) -> dict:
    opened, resolved = [], []
    for n, x in topo.nodes.items():
        if x["power"] != "solar_battery":
            continue
        rows = [(r["ts"], r["soc_pct"]) for r in await c.fetch("""SELECT ts, soc_pct FROM site_power
            WHERE node_id=$1 AND ts <= $2 AND ts > $2::timestamptz - interval '6 hours' AND soc_pct IS NOT NULL ORDER BY ts""", n, now)]
        f = soc_forecast(rows)
        ex = await c.fetchrow("SELECT * FROM outages WHERE status='open' AND kind='power' AND root_node=$1 FOR UPDATE", n)
        risk = False
        if f and f.get("cutoff_at") and n not in corr["dark"]:
            loc = f["at"].astimezone(TZ)
            sun = loc.replace(hour=SOLAR_RECOVERY_HOUR, minute=0, second=0, microsecond=0)
            if sun <= loc:
                sun += dt.timedelta(days=1)
            risk = f["cutoff_at"] < sun or f["hours_to_cutoff"] < POWER_LEAD_H
        if risk and not ex:
            behind = topo.impact(failed_nodes=[n])["isolated"] | {n}
            at_risk = [s for m in behind for s in by_node.get(m, []) if s["state"] == "active"]
            detail = (f"Battery at {n} forecast to hit the {SOC_CUTOFF_PCT:.0f}% cutoff {local(f['cutoff_at'])} "
                      f"({f['soc_pct']:.0f}% now, {f['slope_pct_h']}%/h; before the panels recover). "
                      f"If it trips: {len(behind)} node(s), {len(at_risk)} members dark.")
            oid = await c.fetchval("""INSERT INTO outages (kind, status, noc_managed, cause, detail, root_node,
                    root_elements, dark_nodes, zones, started_at, detected_at, impacted_services, eta, updated_at)
                VALUES ('power','open',true,'Planned battery service at a network site',$1,$2,$3,$4,$5,$6,$6,$7,$8,$6)
                RETURNING outage_id""", detail, n, [f"{n}:power"], sorted(behind), await _zones(c, [n]), now,
                len(at_risk), f["cutoff_at"])
            if f["hours_to_cutoff"] <= POWER_URGENT_H:
                await D.dispatch_outage(c, oid, now)
            else:
                wo = await D.create_wo(c, D.WOIn(wo_type="repair", node_id=n, priority="P2", outage_id=oid,
                                                 note=f"NOC #{oid}: {detail} Bring battery/generator."))
                await D.release_wo(c, wo)
                await c.execute("UPDATE outages SET wo_id=$2 WHERE outage_id=$1", oid, wo)
            opened.append({"outage_id": oid, "node": n, "hours_to_cutoff": f["hours_to_cutoff"],
                           "members_at_risk": len(at_risk), "nodes_at_risk": len(behind)})
        elif ex and not risk and n not in corr["dark"] and f and (f["slope_pct_h"] >= 0 or f["soc_pct"] >= 50):
            await c.execute("UPDATE outages SET status='resolved', resolved_at=$2, updated_at=$2 WHERE outage_id=$1",
                            ex["outage_id"], now)
            resolved.append({"outage_id": ex["outage_id"], "node": n,
                             "wo_cancelled": await cancel_unstarted(c, ex["wo_id"], "battery recovering — visit not needed")})
    return {"opened": opened, "resolved": resolved}

# ---------------------------------------------------------------- read APIs
@app.get("/status")
async def status():
    """Public status (no member data: zone-level state + aggregate counts only)."""
    async with (await pool()).acquire() as c:
        zones = [dict(r) for r in await c.fetch("SELECT * FROM status_zones")]
        recent = [dict(r) for r in await c.fetch("""SELECT o.started_at, o.resolved_at, o.cause,
                (SELECT array_agg(name ORDER BY name) FROM zones WHERE zone_id = ANY(o.zones)) AS zones
            FROM outages o WHERE o.kind='outage' AND o.status='resolved' AND o.resolved_at > now() - interval '30 days'
            ORDER BY o.started_at DESC LIMIT 20""")]
    for r in recent:
        r["duration"] = dur(r["started_at"], r["resolved_at"])
    down = [z for z in zones if z["state"] != "operational"]
    return {"generated_at": dt.datetime.now(UTC).isoformat(),
            "overall": "operational" if not down else ("major_outage" if len(down) > len(zones) / 3 else "partial_outage"),
            "zones": zones, "recent": recent}

@app.get("/status.html", response_class=HTMLResponse)
async def status_html():
    s = await status()
    head = {"operational": "All systems normal", "partial_outage": "Some areas have an outage",
            "major_outage": "Major outage"}[s["overall"]]
    rows = "".join(
        f"<tr><td>{html.escape(z['name'])}</td><td class='{z['state']}'>"
        f"{'Normal' if z['state'] == 'operational' else 'Outage'}</td>"
        f"<td>{'' if z['state'] == 'operational' else html.escape((z['cause'] or '') + ' · since ' + local(z['since']) + (' · expected back ' + local(z['eta']) if z['eta'] else ''))}</td></tr>"
        for z in s["zones"])
    hist = "".join(f"<li>{local(r['started_at'])} · {html.escape(', '.join(r['zones'] or []))} · "
                   f"{html.escape(r['cause'] or '')} · {r['duration']}</li>" for r in s["recent"]) or "<li>No outages in 30 days.</li>"
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60"><title>Boat Dock Network status</title>
<style>:root{{--bg:#EDF2F1;--fg:#0C1A1F;--mut:#51656B;--ok:#1E7A4B;--bad:#C2332B;--line:#CCD9D8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0B1519;--fg:#E4EEED;--mut:#8FA6AB;--ok:#45B37B;--bad:#EF6A60;--line:#24363C}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}main{{max-width:760px;margin:0 auto;padding:24px 16px}}
h1{{font-size:28px;margin:0 0 4px}}.sub{{color:var(--mut);margin:0 0 20px}}table{{width:100%;border-collapse:collapse}}
td{{padding:10px 6px;border-bottom:1px solid var(--line);vertical-align:top}}.operational{{color:var(--ok);font-weight:600}}.outage{{color:var(--bad);font-weight:600}}
h2{{font-size:18px;margin:28px 0 8px}}li{{margin:4px 0;color:var(--mut)}}</style>
<main><h1>{head}</h1><p class="sub">Boat Dock Network · updated {local(dt.datetime.now(UTC))} · refreshes every minute</p>
<table><tbody>{rows}</tbody></table><h2>Last 30 days</h2><ul>{hist}</ul></main></html>"""

@app.get("/noc/board")
async def board(now: Optional[dt.datetime] = None):
    """Everything the NOC board renders: incidents, element states, alert dispositions."""
    now = _now(now)
    async with (await pool()).acquire() as c:
        topo = await db_topology(c)
        st = await element_states(c, now)
        corr = topo.correlate({e for (k, e), s in st.items() if k == "node" and s["down"]},
                              {e for (k, e), s in st.items() if k == "link" and s["down"]})
        incidents = [dict(r) for r in await c.fetch("SELECT * FROM noc_board")]
        alerts = [dict(r) for r in await c.fetch("""SELECT disposition, count(*) AS n FROM alerts
            WHERE status='firing' GROUP BY 1""")]
        queued = await c.fetchval("SELECT count(*) FROM notifications WHERE status='queued'")
    return {"generated_at": now.isoformat(), "incidents": incidents, "alerts_by_disposition": alerts,
            "notifications_queued": queued,
            "nodes": [{"id": n, **x, "state": ("root" if n in corr["root_nodes"] else "dark" if n in corr["dark"] else "up")}
                      for n, x in topo.nodes.items()],
            "links": [{"id": l.link_id, "a": l.a, "b": l.b, "kind": l.kind,
                       "state": ("root" if l.link_id in corr["root_links"] else "ring_open" if l.link_id in corr["ring_open"]
                                 else "down" if l.link_id in corr["suppressed_links"] else "up")} for l in topo.links.values()]}

@app.get("/topology/spof")
async def spof(design: bool = False, planning: bool = False):
    """Single points of failure with the members behind each. planning=true weights by the
    Year-5 premises x take-rate view instead of live services (use before launch)."""
    async with (await pool()).acquire() as c:
        topo = await db_topology(c, design=design or planning)
        if planning:
            mb = T.members_by_node_from_premises(topo)
        else:
            mb = {r["node_id"]: r["n"] for r in await c.fetch(
                "SELECT node_id, count(*) AS n FROM service_instances WHERE state='active' GROUP BY 1")}
    rep = topo.spof_report(mb)
    rep["members_total"] = sum(mb.values())
    return rep

@app.get("/noc/targets")
async def targets():
    """Prometheus file_sd from the device inventory: the element labels the correlator needs
    are attached at scrape time, so every alert already names its node / link / service."""
    async with (await pool()).acquire() as c:
        rows = await c.fetch("SELECT name, role, node_id, link_id, service_id FROM devices WHERE active ORDER BY name")
    out = []
    for r in rows:
        labels = {"role": r["role"]}
        if r["service_id"]:
            labels["service_id"] = str(r["service_id"])
        elif r["link_id"]:
            labels["link"] = r["link_id"]
        elif r["node_id"]:
            labels["node"] = r["node_id"]
        out.append({"targets": [f"{r['name']}.{MGMT_DOMAIN}"], "labels": labels})
    return out
