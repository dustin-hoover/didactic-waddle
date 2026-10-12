#!/usr/bin/env python3
"""End-to-end: alarms -> root cause -> outage -> boat/truck dispatch -> notices -> recovery -> credits (doc 24).

Real pieces: the NOC and dispatch APIs (in-process), PostGIS, the real designed topology
(2 head-ends, 30 spine nodes, 41 spine links from the GIS outputs), real lake + road routing
for the crew insertion, billing's account_credits. Services are synthetic (fictional members).
Alerts are posted exactly as Alertmanager's webhook (v4) sends them; `now` drives the clock.

  0. SPOF report on the design: the "ring" has bridges (doc 24 §2)
  1. hold-down: a 20 s blip opens nothing
  2. alarm storm: a backbone cut + 5 of 13 downstream nodes alarm -> ONE outage, root = the link,
     all 13 nodes dark (8 predicted before they alarm), seasonal holds excluded, P1 inserted as
     the next stop, ETA, member notices once, repeat webhooks idempotent, public status (no PII)
  3. crew fixes it; the outage waits for telemetry; recovery + clear-hold -> resolved at the
     recovery time; business SLA credit (2x, > 4 h), residential none (< 24 h)
  4. ring open -> degraded (P2, no notice); second cut isolates a segment -> outage; first repair
     -> outage resolved, un-started P1 cancelled and taken off the run sheet, ring-open again
  5. access sector (node up, 3 of 4 radios down) -> outage for those members only
  6. single member radio: pending < 30 min, P3 ticket after, self-clears; seasonal hold ignored
  7. flapping link held as one degraded incident until 15 min stable
  8. solar site forecast to die overnight -> proactive P2; the site dies -> outage adopts it (P1),
     cause = power; a recovering site's forecast clears and its visit is cancelled
  9. 26 h outage -> residential 2-day credit, business 2x hours (capped), onto account_credits
 10. head-end loss -> degraded (other head-end carries it); webhook auth; targets; board; sender
Run: TEST_DB=dockos_noc python3 software/tests/test_noc_e2e.py
"""
import os, sys, json, math, asyncio, datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

DB_NAME = os.environ.get("TEST_DB", "dockos_noc")
DSN = os.environ.setdefault("DATABASE_URL", f"postgresql://dockos:dockos@127.0.0.1:5432/{DB_NAME}")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [os.path.join(REPO, "software", "api"), os.path.join(REPO, "software", "noc"),
                os.path.join(REPO, "software", "dispatch")]

import asyncpg
from fastapi.testclient import TestClient
import topology as T, load_topology, waterroute
import noc, dispatch as D

TZ = ZoneInfo("America/Chicago")
D1 = dt.date(2026, 10, 6)
PASS = 0

def q(sql, *a, fetch="all"):
    async def go():
        c = await asyncpg.connect(DSN)
        try:
            return await getattr(c, {"all": "fetch", "row": "fetchrow", "val": "fetchval", "exec": "execute"}[fetch])(sql, *a)
        finally:
            await c.close()
    return asyncio.run(go())

def check(cond, msg):
    global PASS
    if not cond:
        raise AssertionError(msg)
    PASS += 1
    print(f"  ✓ {msg}")

def ok(r):
    assert r.status_code == 200, f"{r.status_code}: {r.text[:600]}"
    return r.json()

def at(h, m=0, s=0, day=D1):
    return dt.datetime(day.year, day.month, day.day, h, m, s, tzinfo=TZ)

def iso(t):
    return t.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def alert(name, labels, start, end=None):
    return {"status": "resolved" if end else "firing",
            "labels": {"alertname": name, "severity": "critical", **labels},
            "annotations": {"summary": f"{name} {' '.join(labels.values())}"},
            "startsAt": iso(start), "endsAt": iso(end) if end else "0001-01-01T00:00:00Z"}

def am(*alerts):
    return {"version": "4", "status": "firing", "receiver": "dockos-noc", "alerts": list(alerts)}

# ---------------------------------------------------------------- seed
PLANS_RES = ["cove", "shoreline", "deepwater"]

def seed(topo):
    q("""TRUNCATE notifications, outage_services, site_power, alerts, devices, wo_events, dispatch_plans, weather_calls,
         crew_days, crews, vehicles, yards, work_order_items, work_orders, outages, account_credits, billing_events,
         provisioning_jobs, service_instances, subscriptions, cpe, members, customers, service_addresses, links, nodes, zones
         RESTART IDENTITY CASCADE""", fetch="exec")
    async def go():
        c = await asyncpg.connect(DSN)
        try:
            print("  topology:", await load_topology.load(c, topo, status="live"))
        finally:
            await c.close()
    asyncio.run(go())
    k = 0
    rows = []
    for i, n in enumerate(sorted(x for x in topo.nodes if x not in topo.heads)):
        x = topo.nodes[n]
        kinds = [("res", p) for p in PLANS_RES] + ([("biz", "business")] if x["tier"] == "T2" else []) \
            + ([("hold", "shoreline")] if i % 5 == 0 else [])
        for j, (kind, plan) in enumerate(kinds):
            k += 1
            lon, lat = x["lon"] + 0.002 * (j + 1), x["lat"] + 0.001 * (j - 1)
            rows.append((k, n, kind, plan, lon, lat, x["zone"]))
    async def ins():
        c = await asyncpg.connect(DSN)
        try:
            for k, n, kind, plan, lon, lat, z in rows:
                aid = await c.fetchval("""INSERT INTO service_addresses (address, zone_id, building_type, geom)
                    VALUES ($1,$2,$3,ST_SetSRID(ST_Point($4,$5),4326)) RETURNING address_id""",
                    f"{100 + k} Lakeview Ln (example)", z, "marina" if kind == "biz" else "home", lon, lat)
                cid = await c.fetchval("""INSERT INTO customers (name, email, phone, address_id)
                    VALUES ($1,$2,$3,$4) RETURNING customer_id""", f"Member {k:03d}", f"member{k:03d}@example.com",
                    f"+1-555-01{k % 100:02d}" if kind != "hold" else None, aid)
                sub = await c.fetchval("""INSERT INTO subscriptions (customer_id, plan_id, status, start_date)
                    VALUES ($1,$2,$3,'2026-06-01') RETURNING sub_id""", cid, plan, "hold" if kind == "hold" else "active")
                await c.execute("""INSERT INTO service_instances (sub_id, customer_id, address_id, medium, node_id, access,
                        radius_username, radius_password, state, suspend_reason, activated_at)
                    VALUES ($1,$2,$3,'wireless_nlos',$4,'ipoe_mac',$5,$5,$6::service_state,$7,'2026-06-01')""",
                    sub, cid, aid, n, f"aa-bb-cc-00-{k // 256:02x}-{k % 256:02x}",
                    "suspended" if kind == "hold" else "active", "seasonal_hold" if kind == "hold" else None)
        finally:
            await c.close()
    asyncio.run(ins())
    g = waterroute.grid()
    ynw, ye = g.water_point(-94.06, 36.35), g.water_point(-93.84, 36.40)
    q("INSERT INTO yards VALUES ('YARD-NW','NW yard',ST_SetSRID(ST_Point($1,$2),4326)),('YARD-E','East yard',ST_SetSRID(ST_Point($3,$4),4326))",
      ynw[0], ynw[1], ye[0], ye[1], fetch="exec")
    q("""INSERT INTO vehicles VALUES ('BOAT-1','Center console 1','boat','center_console','YARD-NW','available'),
         ('TRUCK-1','Service truck 1','truck',NULL,'YARD-NW','available'),
         ('BOAT-2','Center console 2','boat','center_console','YARD-E','available')""", fetch="exec")
    q("""INSERT INTO crews (crew_id,name,skills,yard_id,shift_hours) VALUES
         ('CREW-1','Crew 1 — Lake NW',ARRAY['repair','install_wireless'],'YARD-NW',10),
         ('CREW-2','Crew 2 — Road',ARRAY['repair','install_wireless','splice'],'YARD-NW',10),
         ('CREW-3','Crew 3 — Lake E',ARRAY['repair','install_wireless'],'YARD-E',10)""", fetch="exec")
    return len(rows)

# ---------------------------------------------------------------- scenario
def main():
    topo = T.from_gis()
    n = seed(topo)
    heads = set(topo.heads)
    bridges, cuts = topo.bridges_and_cuts()
    ring = sorted(l for l in topo.links if l not in bridges and not l.startswith("HF-"))
    with TestClient(D.app) as dh, TestClient(noc.app) as h:
        for day in (D1, D1 + dt.timedelta(days=1)):
            ok(dh.post("/weather/override", json={"day": str(day), "classes": {}, "reason": "test: calm"}))
            ok(dh.post("/dispatch/plan", json={"day": str(day)}))
        svc = {r["service_id"]: dict(r) for r in q("""SELECT si.service_id, si.node_id, si.state::text, s.plan_id, p.monthly_usd,
                   p.is_business FROM service_instances si JOIN subscriptions s USING (sub_id) JOIN plans p USING (plan_id)""")}
        active_on = lambda nodes: [s for s in svc.values() if s["node_id"] in nodes and s["state"] == "active"]
        print(f"seeded {n} services on {len(topo.nodes) - 2} nodes")

        print("0. Single points of failure in the designed 'ring'")
        sp = ok(h.get("/topology/spof", params={"planning": "true"}))
        check(sp["bridges"] == 5 and sp["cut_nodes"] == 8,
              f"design has {sp['bridges']} bridge links + {sp['cut_nodes']} cut nodes (not a ring)")
        check(sp["members_behind_a_spof"] == 2367 and sp["spofs"][0]["element"] == "SP-06-13",
              f"{sp['members_behind_a_spof']:,} of {sp['members_total']:,} Year-5 members behind a SPOF; worst = SP-06-13 "
              f"({sp['spofs'][0]['members']:,})")

        print("1. Hold-down: a blip opens nothing")
        X = "BDN-Z-15-N26" if "BDN-Z-15-N26" in topo.nodes else sorted(set(topo.nodes) - heads)[-1]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(7, 55, 30))}, json=am(alert("NodeDown", {"node": X}, at(7, 55)))))
        check(r["opened"] == [] and q("SELECT disposition FROM alerts WHERE element=$1", X, fetch="val") == "pending",
              "30 s into a node alarm: pending (hold-down 60 s), no outage")
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(7, 56, 30))},
                      json=am(alert("NodeDown", {"node": X}, at(7, 55), at(7, 55, 40)))))
        check(r["opened"] == [] and q("SELECT count(*) FROM outages", fetch="val") == 0, "40 s blip cleared: nothing opened")

        print("2. Alarm storm: backbone cut SP-06-13")
        dark = topo.correlate(down_links=["SP-06-13"])["dark"]
        dark_sorted = sorted(dark)
        first = [alert("LinkDown", {"link": "SP-06-13"}, at(8, 0))] + \
                [alert("NodeDown", {"node": d}, at(8, 0, 5)) for d in dark_sorted[:5]]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(8, 1, 30))}, json=am(*first)))
        check(len(r["opened"]) == 1 and r["root_causes"] == ["SP-06-13"], f"ONE outage, root cause = link SP-06-13 ({r['opened']})")
        oid = r["opened"][0]
        o = q("SELECT * FROM outages WHERE outage_id=$1", oid, fetch="row")
        check(len(o["dark_nodes"]) == 13 and len(r["silent_dark"]) == 8,
              "all 13 downstream nodes dark — 8 predicted before their own alarms arrive")
        exp = active_on(dark)
        held = [s for s in svc.values() if s["node_id"] in dark and s["state"] != "active"]
        check(o["impacted_services"] == len(exp) and o["impacted_business"] == sum(s["is_business"] for s in exp) and held,
              f"{o['impacted_services']} active services dark ({o['impacted_business']} business); "
              f"{len(held)} on seasonal hold not counted")
        check("Backbone link failure" == o["cause"] and "SP-06-13" in o["detail"], f"cause: {o['detail']}")
        wo = q("SELECT * FROM work_orders WHERE wo_id=$1", o["wo_id"], fetch="row")
        check(wo["priority"] == "P1" and wo["status"] == "scheduled" and wo["route_seq"] == 1,
              f"P1 repair at {wo['node_id']} inserted as {wo['assigned_crew']}'s next stop by {wo['travel_mode']}")
        check(o["eta"] is not None and o["eta"] > wo["eta"], f"member ETA {noc.local(o['eta'])} (crew on site {noc.local(wo['eta'])} + repair)")
        nn = q("SELECT count(*) FROM notifications WHERE outage_id=$1 AND template='outage_opened'", oid, fetch="val")
        custs = q("SELECT count(DISTINCT customer_id) FROM notifications WHERE outage_id=$1", oid, fetch="val")
        check(custs == len(exp) and nn == 2 * len(exp), f"{nn} notices queued (sms + email) to {custs} members")
        body = q("SELECT body FROM notifications WHERE outage_id=$1 AND channel='sms' LIMIT 1", oid, fetch="val")
        check("crew is on the way" in body and "credits are applied automatically" in body, f"notice: “{body[:110]}…”")
        rest = [alert("NodeDown", {"node": d}, at(8, 0, 5)) for d in dark_sorted[5:]]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(8, 2, 30))}, json=am(*first, *rest)))
        check(r["opened"] == [] and r["updated"] == [] and r["suppressed"] == 13,
              "late alarms + Alertmanager repeat: same outage, 13 alarms suppressed, no new notices")
        disp = {x["disposition"]: x["n"] for x in q("SELECT disposition, count(*) n FROM alerts WHERE status='firing' GROUP BY 1")}
        check(disp == {"root_cause": 1, "suppressed": 13}, f"alarm dispositions {disp}")
        check(q("SELECT count(*) FROM notifications WHERE outage_id=$1", oid, fetch="val") == nn, "no duplicate notices")
        st = ok(h.get("/status"))
        blob = json.dumps(st)
        zs = [z for z in st["zones"] if z["state"] == "outage"]
        check(st["overall"] in ("partial_outage", "major_outage") and zs and sum(z["members_affected"] for z in zs) == len(exp),
              f"status page: {len(zs)} zones in outage, {sum(z['members_affected'] for z in zs)} members")
        check("example.com" not in blob and "Member 0" not in blob and "555-01" not in blob, "status page carries no member data")
        snap_now = iso(at(8, 2, 30))
        snap = {"now": snap_now, "board": ok(h.get("/noc/board", params={"now": snap_now})), "status": st,
                "notice_sms": body, "wo": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(
                    q("SELECT wo_id, priority::text, status::text, assigned_crew, travel_mode, travel_min, eta, node_id "
                      "FROM work_orders WHERE wo_id=$1", q("SELECT wo_id FROM outages WHERE outage_id=$1", oid, fetch="val"),
                      fetch="row")).items()}}
        page = h.get("/status.html").text
        check("Some areas have an outage" in page or "Major outage" in page, "status.html renders")

        print("3. Crew fixes it; telemetry decides")
        rep = o["wo_id"]
        ok(dh.post("/field/actions", json={"actions": [
            {"client_action_id": "n-1", "wo_id": rep, "kind": "started", "at": at(9, 0).isoformat()},
            {"client_action_id": "n-2", "wo_id": rep, "kind": "capture", "data": {"resolution": "Re-aimed 11 GHz dish after storm"}},
            {"client_action_id": "n-3", "wo_id": rep, "kind": "completed", "at": at(12, 50).isoformat()}]}))
        o = q("SELECT status, field_fixed_at FROM outages WHERE outage_id=$1", oid, fetch="row")
        check(o["status"] == "open" and o["field_fixed_at"] is not None, "crew closed the WO; outage stays open until telemetry confirms")
        rec = [alert("LinkDown", {"link": "SP-06-13"}, at(8, 0), at(13, 0))] + \
              [alert("NodeDown", {"node": d}, at(8, 0, 5), at(13, 0, 20)) for d in dark_sorted]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(13, 1, 30))}, json=am(*rec)))
        check(r["resolved"] == [], "90 s after recovery: still open (clear-hold 120 s)")
        r = ok(h.post("/noc/evaluate", params={"now": iso(at(13, 3))}))
        check(len(r["resolved"]) == 1 and r["resolved"][0]["duration"] == "5 h 00 min" and not r["resolved"][0]["wo_cancelled"],
              f"resolved at recovery time: {r['resolved'][0]['duration']}")
        biz = [s for s in exp if s["is_business"]]
        want = Decimal(str(round(199 * 2 * 5 / 720, 2)))
        cr = q("SELECT amount_usd, note FROM account_credits WHERE kind='outage'")
        check(len(cr) == len(biz) and all(c["amount_usd"] == want for c in cr),
              f"business SLA: {len(biz)} credits of ${want} (2x prorated, > 4 h); residential none (< 24 h)")
        check(q("SELECT count(*) FROM notifications WHERE outage_id=$1 AND template='outage_resolved'", oid, fetch="val") == nn,
              "restored notices queued")
        br = q("SELECT body FROM notifications WHERE outage_id=$1 AND template='outage_resolved' AND customer_id=(SELECT customer_id FROM account_credits LIMIT 1) AND channel='sms'", oid, fetch="val")
        check(f"${want}" in br, f"business notice: “{br[br.index('A $'):][:48]}…”")

        print("4. Ring open, then a second cut")
        pair = next((a, b) for a in ring for b in ring if a < b and topo.correlate(down_links=[a, b])["dark"]
                    and not (topo.correlate(down_links=[a, b])["dark"] & dark))
        A, B = pair
        seg = topo.correlate(down_links=[A, B])["dark"]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(13, 11, 30))}, json=am(alert("LinkDown", {"link": A}, at(13, 10)))))
        dg = q("SELECT * FROM outages WHERE outage_id=$1", r["opened"][0], fetch="row")
        p2 = q("SELECT priority, status FROM work_orders WHERE wo_id=$1", dg["wo_id"], fetch="row")
        check(dg["kind"] == "degraded" and r["ring_open"] == [A] and p2["priority"] == "P2" and p2["status"] == "released",
              f"{A} down, nothing isolated: degraded + P2 for the planner")
        check(q("SELECT count(*) FROM notifications WHERE outage_id=$1", dg["outage_id"], fetch="val") == 0
              and ok(h.get("/status"))["overall"] == "operational", "no member notices; status stays operational")
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(13, 21, 30))},
                      json=am(alert("LinkDown", {"link": A}, at(13, 10)), alert("LinkDown", {"link": B}, at(13, 20)))))
        o2 = q("SELECT * FROM outages WHERE outage_id=$1", r["opened"][0], fetch="row")
        check(o2["kind"] == "outage" and set(o2["root_elements"]) == {A, B} and set(o2["dark_nodes"]) == seg,
              f"{B} also down: segment of {len(seg)} node(s) isolated -> outage, roots {A} + {B}")
        check(r["resolved"][0]["outage_id"] == dg["outage_id"] and r["resolved"][0]["wo_cancelled"],
              "the degraded incident folds into the outage (its P2 cancelled)")
        p1 = q("SELECT * FROM work_orders WHERE wo_id=$1", o2["wo_id"], fetch="row")
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(14, 2, 30))},
                      json=am(alert("LinkDown", {"link": A}, at(13, 10)), alert("LinkDown", {"link": B}, at(13, 20), at(14, 0)))))
        res = next(x for x in r["resolved"] if x["outage_id"] == o2["outage_id"])
        plan = json.loads(q("SELECT plan FROM dispatch_plans WHERE day=$1 AND crew_id=$2", D1, p1["assigned_crew"], fetch="val"))
        check(res["wo_cancelled"] and p1["wo_id"] not in [s["wo_id"] for s in plan["stops"]]
              and [s["seq"] for s in plan["stops"]] == list(range(1, len(plan["stops"]) + 1)),
              f"{B} restored before the crew started: P1 cancelled and off {p1['assigned_crew']}'s run sheet")
        check(len(r["opened"]) == 1 and q("SELECT kind FROM outages WHERE outage_id=$1", r["opened"][0], fetch="val") == "degraded",
              f"back to ring-open on {A}")
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(14, 12, 30))},
                      json=am(alert("LinkDown", {"link": A}, at(13, 10), at(14, 10)))))
        check(len(r["resolved"]) == 1 and r["resolved"][0]["kind"] == "degraded", f"{A} restored: ring closed")

        print("5. Access sector down, node up")
        S = next(x for x in sorted(topo.nodes) if topo.nodes[x]["tier"] == "T2" and x not in seg | dark)
        sv = [s for s in active_on({S})][:3]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(14, 31, 30))},
                      json=am(*[alert("CPEDown", {"service_id": str(s["service_id"])}, at(14, 30)) for s in sv])))
        o3 = q("SELECT * FROM outages WHERE outage_id=$1", r["opened"][0], fetch="row")
        check(o3["root_elements"] == [f"{S}:access"] and o3["impacted_services"] == 3 and o3["wo_id"],
              f"3 of {len(active_on({S}))} radios down on {S}: sector outage, P1, only those 3 members")

        print("6. One member radio; a seasonal home")
        Q = next(x for x in sorted(topo.nodes) if x not in heads | seg | dark | {S})
        one = active_on({Q})[0]
        hold = next(s for s in svc.values() if s["state"] != "active" and s["node_id"] not in dark | seg)
        cpe = [alert("CPEDown", {"service_id": str(one["service_id"])}, at(14, 30)),
               alert("CPEDown", {"service_id": str(hold["service_id"])}, at(14, 30))]
        ok(h.post("/ingest/alertmanager", params={"now": iso(at(14, 41))}, json=am(*cpe)))
        dd = dict(q("SELECT element, disposition FROM alerts WHERE element = ANY($1::text[])",
                    [str(one["service_id"]), str(hold["service_id"])]))
        check(dd[str(one["service_id"])] == "pending" and dd[str(hold["service_id"])] == "ignored_inactive",
              "11 min: member radio pending; seasonal-hold radio ignored (expected to be off)")
        sec_recovered = [alert("CPEDown", {"service_id": str(s["service_id"])}, at(14, 30), at(15, 0)) for s in sv]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(15, 2, 30))}, json=am(*cpe, *sec_recovered)))
        check(len(r["tickets"]["opened"]) == 1 and q("SELECT priority FROM work_orders WHERE wo_id=$1", r["tickets"]["opened"][0], fetch="val") == "P3",
              "32 min: P3 ticket for the one member (none for the seasonal home)")
        res = next(x for x in r["resolved"] if x["outage_id"] == o3["outage_id"])
        check(res["wo_cancelled"] and res["duration"] == "30 min", "sector back after 30 min: resolved, crew visit cancelled")
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(15, 12, 30))},
                      json=am(alert("CPEDown", {"service_id": str(one["service_id"])}, at(14, 30), at(15, 10)))))
        check(len(r["tickets"]["self_cleared"]) == 1,
              "member radio back on its own: ticket cancelled")

        print("7. Flapping link")
        C = next(l for l in ring if l not in (A, B))
        flaps = [alert("LinkDown", {"link": C}, at(15, 20 + 5 * i), at(15, 20 + 5 * i, 20)) for i in range(3)]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(15, 30, 30))}, json=am(*flaps)))
        fo = q("SELECT kind, detail FROM outages WHERE outage_id=$1", r["opened"][0], fetch="row") if r["opened"] else None
        check(fo and fo["kind"] == "degraded" and "flapping" in fo["detail"],
              "three 20 s drops in 10 min (each under hold-down): damped into one degraded incident")
        r = ok(h.post("/noc/evaluate", params={"now": iso(at(15, 40))}))
        check(r["resolved"] == [], "still held 10 min after the last drop")
        r = ok(h.post("/noc/evaluate", params={"now": iso(at(15, 46))}))
        check(len(r["resolved"]) == 1, "15 min stable: closed")

        print("8. Solar site power forecast")
        t3 = [x for x in sorted(topo.nodes) if topo.nodes[x]["power"] == "solar_battery" and x not in dark | seg | {S, Q}]
        P = max(t3, key=lambda x: len(topo.impact(failed_nodes=[x])["isolated"]) * 100 + len(active_on({x})))
        P2 = next(x for x in t3 if x != P)
        samples = [{"node_id": nd, "ts": at(12 + i).isoformat(), "soc_pct": 70 - 2.5 * i} for i in range(5) for nd in (P, P2)]
        r = ok(h.post("/telemetry/power", params={"now": iso(at(16))}, json={"samples": samples}))
        po = {x["node"]: x for x in r["power"]["opened"]}
        pw = q("SELECT * FROM outages WHERE outage_id=$1", po[P]["outage_id"], fetch="row")
        pwo = q("SELECT priority, status FROM work_orders WHERE wo_id=$1", pw["wo_id"], fetch="row")
        check(set(po) == {P, P2} and po[P]["hours_to_cutoff"] == 16.0 and pwo["priority"] == "P2" and pwo["status"] == "released",
              f"{P}: 60% falling 2.5%/h -> 20% cutoff at {noc.local(pw['eta'])}, before the sun: proactive P2 "
              f"({po[P]['members_at_risk']} members, {po[P]['nodes_at_risk']} node(s) at risk)")
        up = [{"node_id": P2, "ts": at(16, 30 + 10 * i).isoformat(), "soc_pct": 62 + 4 * i} for i in range(3)]
        r = ok(h.post("/telemetry/power", params={"now": iso(at(17))}, json={"samples": up}))
        check([x["node"] for x in r["power"]["resolved"]] == [P2] and r["power"]["resolved"][0]["wo_cancelled"],
              f"{P2}: sun came out, SOC rising -> forecast cleared, visit cancelled")
        dead = [alert("BatteryLow", {"node": P}, at(16, 55)), alert("NodeDown", {"node": P}, at(17, 0))]
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(17, 1, 30))}, json=am(*dead)))
        o4 = q("SELECT * FROM outages WHERE outage_id=$1", r["opened"][0], fetch="row")
        check(o4["cause"] == "Power loss at a network site" and "battery exhausted" in o4["detail"], f"{P} dies: {o4['detail']}")
        check(q("SELECT status FROM outages WHERE outage_id=$1", pw["outage_id"], fetch="val") == "resolved"
              and q("SELECT priority FROM work_orders WHERE wo_id=$1", o4["wo_id"], fetch="val") == "P1",
              "outage adopts the power forecast: P2 upgraded to a P1 insertion, forecast closed as superseded")

        print("9. Long outage credits")
        D2 = D1 + dt.timedelta(days=1)
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(19, 2, 30, day=D2))},
                      json=am(alert("BatteryLow", {"node": P}, at(16, 55), at(18, 30, day=D2)),
                              alert("NodeDown", {"node": P}, at(17, 0), at(19, 0, day=D2)))))
        res = next(x for x in r["resolved"] if x["outage_id"] == o4["outage_id"])
        hrs = 26.0
        exp4 = q("SELECT os.*, cu.customer_id FROM outage_services os JOIN customers cu USING (customer_id) WHERE outage_id=$1", o4["outage_id"])
        def want_credit(m, biz):
            m = Decimal(str(m))
            v = m * 2 * math.ceil(hrs) / 720 if biz else m * math.ceil(hrs / 24) / 30
            return min(v, m).quantize(Decimal("0.01"))
        got = {r_["service_id"]: r_["credit_usd"] for r_ in exp4}
        check(res["duration"] == "26 h 00 min" and all(got[s["service_id"]] == want_credit(s["monthly_usd"], s["is_business"]) for s in exp4),
              f"26 h: residential 2 days prorated{', business 2x hours' if any(s['is_business'] for s in exp4) else ''}"
              f" — ${res['credits_usd']:.2f} to {len(exp4)} members")
        check(q("SELECT sum(amount_usd) FROM account_credits WHERE note LIKE $1", f"Outage #{o4['outage_id']}%", fetch="val")
              == Decimal(str(res["credits_usd"])).quantize(Decimal("0.01")), "credits posted to account_credits (applied on the next bill)")

        print("10. Head-end, auth, targets, board, sender")
        r = ok(h.post("/ingest/alertmanager", params={"now": iso(at(9, 1, 30, day=D2 + dt.timedelta(days=1)))},
                      json=am(alert("NodeDown", {"node": "HE-NW"}, at(9, 0, day=D2 + dt.timedelta(days=1))))))
        ho = q("SELECT kind, impacted_services FROM outages WHERE outage_id=$1", r["opened"][0], fetch="row")
        check(ho["kind"] == "degraded", "HE-NW down: everything rides HE-E -> degraded, no members dark")
        t3 = {"now": iso(at(9, 2, day=D2 + dt.timedelta(days=1)))}
        noc.WEBHOOK_TOKEN = "s3cret"
        check(h.post("/ingest/alertmanager", params=t3, json=am()).status_code == 401, "webhook without the bearer token -> 401")
        check(h.post("/ingest/alertmanager", params=t3, json=am(), headers={"Authorization": "Bearer s3cret"}).status_code == 200,
              "with token -> 200")
        noc.WEBHOOK_TOKEN = None
        tg = ok(h.get("/noc/targets"))
        check(len(tg) == 87 and any(t["labels"].get("link") == "SP-06-13" for t in tg),
              f"Prometheus file_sd: {len(tg)} targets labelled node/link")
        b = ok(h.get("/noc/board", params=t3))
        check(any(i["kind"] == "degraded" for i in b["incidents"]) and len(b["nodes"]) == 32, "board: open incidents + element states")
        s = ok(h.post("/notifications/send"))
        check(s["sent"] > 0 and q("SELECT count(*) FROM notifications WHERE status='queued'", fetch="val") == 0,
              f"dry-run sender delivered {s['sent']} notices")
        k = q("SELECT * FROM outage_kpis WHERE outages > 0", fetch="row")
        check(k["outages"] == 4 and k["mttr_min"] > 0, f"KPIs: {k['outages']} outages, MTTR {k['mttr_min']} min, "
              f"{int(k['member_minutes_lost']):,} member-minutes, ${k['credits_usd']} credited")
        snap["log"] = [{k: (v.isoformat() if hasattr(v, "isoformat") else (float(v) if isinstance(v, Decimal) else v))
                        for k, v in dict(r_).items()} for r_ in q("""SELECT outage_id, kind, cause, detail, root_elements,
                        started_at, resolved_at, impacted_services, impacted_business, credits_usd, status
                        FROM outages ORDER BY outage_id""")]
        os.makedirs(os.path.join(REPO, "data", "noc"), exist_ok=True)
        json.dump(snap, open(os.path.join(REPO, "data", "noc", "demo_board.json"), "w"), indent=1, default=str)
    print(f"\nALL {PASS} CHECKS PASSED")

if __name__ == "__main__":
    main()
