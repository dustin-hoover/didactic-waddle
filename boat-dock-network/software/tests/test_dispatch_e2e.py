#!/usr/bin/env python3
"""End-to-end: signup -> install work order -> boat/truck dispatch -> crew PWA -> first bill (doc 23).

Real pieces: billing API (doc 22), the dispatch API served by uvicorn, the crew PWA driven
in headless Chromium, the real lake grid (NHD) and real OSM road graph, PostGIS.

  * 4 member sign-ups -> install WOs with kits by medium (nLOS x3, fiber drop x1)
  * release: BOM -> warehouse reservation -> CPE shortfall -> draft PO -> parts received -> unblocked
  * dock-node build: held in 'permitting' until the permit checklist clears
  * weather: dispatcher no-go keeps every boat home (boat-only work waits; installs go by truck);
    re-plan on a go day: boat-first sites by boat, truck-first sites by truck, the build by pontoon
  * NOC outage -> P1 repair inserted as the next stop of the crew that can get there first
  * crew PWA at phone width: tie up, start, readings, complete -> RADIUS re-keyed to the CPE
    actually installed, stock consumed, asset + CPE recorded, service live, FIRST BILL issued
  * offline on the lake: action queued, replayed on reconnect; replays are idempotent
  * missing readings refuse completion; "can't complete" returns the job to dispatch
  * measured dock turnaround (>= 5 stops) replaces the planner's default
Run: TEST_DB=dockos_disp python3 software/tests/test_dispatch_e2e.py
"""
import os, sys, json, time, asyncio, subprocess, datetime as dt
import numpy as np

DB_NAME = os.environ.get("TEST_DB", "dockos_disp")
DSN = os.environ.setdefault("DATABASE_URL", f"postgresql://dockos:dockos@127.0.0.1:5432/{DB_NAME}")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
API_DIR = os.path.join(REPO, "software", "api")
sys.path[:0] = [API_DIR, os.path.join(REPO, "software", "dispatch")]

import asyncpg, httpx
from fastapi.testclient import TestClient
import billing, waterroute, roadroute

PORT = int(os.environ.get("DISPATCH_PORT", 8765))
BASE = f"http://127.0.0.1:{PORT}"
D1 = dt.date(2026, 10, 6)      # a Tuesday
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
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    return r.json()

def pick_sites():
    """Real premises: 2 where the boat clearly wins (Z-05) and 2 where the truck clearly wins (Z-01)."""
    g, rg = waterroute.grid(), roadroute.road()
    yard = g.water_point(-94.06, 36.35)
    feats = json.load(open(os.path.join(REPO, "data", "gis", "outputs", "premises.geojson")))["features"]
    out = {}
    for z, want in (("Z-05", "boat"), ("Z-01", "truck")):
        pts = np.array([f["geometry"]["coordinates"][:2] for f in feats if f["properties"]["z"] == z])
        k, leg = g.snap_many(pts)
        ny, _ = g.snap(*yard)
        boat = g._sssp("center_console", ny)[0][k] + 10 + leg / 60
        boat[leg > 300] = np.inf
        truck = rg.drive_minutes(yard, pts) + 10
        margin = (truck - boat) if want == "boat" else (boat - truck)
        margin[~np.isfinite(margin)] = -1e9          # both modes must be feasible: a real choice
        order = np.argsort(-margin)
        out[z] = [(tuple(pts[i]), float(boat[i]), float(truck[i])) for i in order[:2]]
    shore = g.to_ll(float(g.cx[g.snap(*out["Z-05"][0][0])[0]]), float(g.cy[g.snap(*out["Z-05"][0][0])[0]]))
    return yard, g.water_point(-93.84, 36.40), out, shore

def seed(yard_nw, yard_e, sites, shore):
    q("""TRUNCATE wo_events, dispatch_plans, weather_calls, crew_days, crews, vehicles, yards, po_lines, purchase_orders,
         vendors, inventory, assets, work_order_items, outages, work_orders, billing_events, provisioning_jobs, payments,
         invoice_lines, invoices, one_time_charges, account_credits, service_instances, subscriptions, cpe,
         host_node_agreements, pledges, signups, wake_ledger, wake_balances, members, customers, service_addresses,
         nodes, zones, skus RESTART IDENTITY CASCADE""", fetch="exec")
    q("INSERT INTO zones(zone_id,name,phase) VALUES ('Z-05','Lost Bridge Village',1),('Z-01','Beaver Shores',1)", fetch="exec")
    for z, lst in sites.items():
        for i, (p, _, _) in enumerate(lst):
            q("INSERT INTO service_addresses(address,zone_id,building_type,geom) VALUES ($1,$2,'home',ST_SetSRID(ST_Point($3,$4),4326))",
              f"{10 + i} {'Lost Bridge Rd' if z == 'Z-05' else 'Beaver Shores Dr'} (example)", z, p[0], p[1], fetch="exec")
    q("INSERT INTO nodes(node_id,zone_id,tier,status,geom) VALUES ('BDN-LostBridge-T2-01','Z-05','T2','permitted',ST_SetSRID(ST_Point($1,$2),4326))",
      shore[0], shore[1], fetch="exec")
    q("INSERT INTO yards VALUES ('YARD-NW','NW yard (candidate head-end parcel)',ST_SetSRID(ST_Point($1,$2),4326)),"
      "('YARD-E','East yard (dam side)',ST_SetSRID(ST_Point($3,$4),4326))", yard_nw[0], yard_nw[1], yard_e[0], yard_e[1], fetch="exec")
    q("""INSERT INTO vehicles VALUES ('BOAT-1','Center console 1','boat','center_console','YARD-NW','available'),
         ('TRUCK-1','Service truck 1','truck',NULL,'YARD-NW','available'),
         ('PONTOON-1','Work pontoon 1','boat','pontoon','YARD-E','available')""", fetch="exec")
    q("""INSERT INTO crews (crew_id,name,skills,yard_id,shift_hours) VALUES
         ('CREW-1','Crew 1 — Lake',ARRAY['install_wireless','repair','survey'],'YARD-NW',9),
         ('CREW-2','Crew 2 — Road',ARRAY['install_wireless','install_fiber','splice','repair'],'YARD-NW',10),
         ('CREW-3','Crew 3 — Build',ARRAY['tower','marine_ops'],'YARD-E',9)""", fetch="exec")
    q("INSERT INTO crew_days VALUES ('CREW-1',$1,'BOAT-1'),('CREW-2',$1,'TRUCK-1'),('CREW-3',$1,'PONTOON-1')", D1, fetch="exec")

def main():
    yard_nw, yard_e, sites, shore = pick_sites()
    print("sites:", {z: [(round(b), round(t)) for _, b, t in v] for z, v in sites.items()}, "(boat, truck min from NW yard)")
    seed(yard_nw, yard_e, sites, shore)
    env = dict(os.environ, DATABASE_URL=DSN)
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "dispatch:app", "--port", str(PORT), "--log-level", "warning"],
                           cwd=API_DIR, env=env)
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{BASE}/metrics/turnaround", timeout=2).status_code == 200:
                    break
            except Exception:
                time.sleep(0.5)
        h = httpx.Client(base_url=BASE, timeout=60)
        run(h, shore)
    finally:
        srv.terminate(); srv.wait(10)

def run(h, shore):
    bc = TestClient(billing.app)
    with bc:
        print("1. Four members sign up (billing, doc 22)")
        people = [("Ada Harper", 1, "wireless_nlos", "AA:BB:CC:00:00:01"), ("Ben Ortiz", 2, "wireless_nlos", "AA:BB:CC:00:00:02"),
                  ("Cora Blake", 3, "wireless_nlos", "AA:BB:CC:00:00:03"), ("Dev Patel", 4, "fiber", "ONT000000004")]
        svc = {}
        for name, addr, medium, dev in people:
            r = ok(bc.post("/subscriptions", json={"name": name, "email": f"{name.split()[0].lower()}@example.com",
                   "address_id": addr, "plan_id": "shoreline", "medium": medium,
                   "access": "ont_serial" if medium == "fiber" else "ipoe_mac", "device_id": dev}))
            svc[name] = r
        check(all(r["service_id"] for r in svc.values()), "4 pending services")

        print("2. Install work orders from pending services")
        ok(h.post("/catalog/load"))
        made = ok(h.post("/work-orders/sync-installs"))["created"]
        check(len(made) == 4, f"sync-installs created 4 WOs ({made})")
        check(ok(h.post("/work-orders/sync-installs"))["created"] == [], "sync is idempotent (one open install per service)")
        types = {r["service_id"]: r["wo_type"] for r in q("SELECT service_id, wo_type FROM work_orders")}
        check(types[svc["Dev Patel"]["service_id"]] == "drop-aerial-fiber" and
              types[svc["Ada Harper"]["service_id"]] == "cpe-wireless-nlos", "kit chosen by medium (nLOS / fiber drop)")
        wo = {n: q("SELECT wo_id FROM work_orders WHERE service_id=$1", svc[n]["service_id"], fetch="val") for n in svc}

        print("3. Release: BOM -> reservation -> shortfall -> PO -> receive")
        q("""INSERT INTO inventory (sku, location, qty_on_hand) SELECT sku, 'warehouse', 5000 FROM skus
             WHERE category IN ('radio','optics','fiber','enclosure','power','mount','misc')""", fetch="exec")
        cpe_sku = q("SELECT sku FROM skus WHERE description LIKE 'nLOS CPE radio%'", fetch="val")
        q("UPDATE inventory SET qty_on_hand=2 WHERE sku=$1", cpe_sku, fetch="exec")
        rel = {n: ok(h.post(f"/work-orders/{wo[n]}/release")) for n in ("Ada Harper", "Ben Ortiz", "Cora Blake", "Dev Patel")}
        check(rel["Ada Harper"]["bom_lines"] > 0 and not rel["Ada Harper"]["shortfall"], "Ada: BOM expanded, fully reserved")
        check(rel["Cora Blake"]["shortfall"] and rel["Cora Blake"]["shortfall"][0]["sku"] == cpe_sku and rel["Cora Blake"]["draft_pos"],
              "Cora: 3rd CPE short -> draft PO to the vendor")
        check(q("SELECT v.name FROM po_lines l JOIN purchase_orders p USING(po_id) JOIN vendors v USING(vendor_id) WHERE l.sku=$1",
                cpe_sku, fetch="val") == "Tarana", "PO addressed to Tarana (vendor from the BOM kit)")
        flat = q("SELECT qty FROM work_order_items WHERE wo_id=$1 AND sku LIKE 'flat-drop-fiber%'", wo["Dev Patel"], fetch="val")
        check(float(flat) == 150, "fiber drop LEN_FT defaulted to 150 ft (repaired kit parses)")
        rec = ok(h.post("/inventory/receive", json={"sku": cpe_sku, "qty": 5}))
        check(rec["unblocked"] == [wo["Cora Blake"]], "parts received -> Cora unblocked")

        dock = ok(h.post("/work-orders", json={"wo_type": "t2-docknode", "node_id": "BDN-LostBridge-T2-01",
                                               "params": {"N_SECTORS": 2}}))["wo_id"]
        check(ok(h.post(f"/work-orders/{dock}/release"))["status"] == "permitting", "dock-node build held for permits")
        q("UPDATE work_orders SET params = params || '{\"permit_approved\": true}' WHERE wo_id=$1", dock, fetch="exec")
        check(ok(h.post(f"/work-orders/{dock}/release"))["status"] == "released", "permits cleared -> released")

        print("4. Weather: dispatcher no-go keeps boats home")
        ok(h.post("/weather/override", json={"day": str(D1), "reason": "thunderstorms on radar",
                                             "classes": {k: False for k in waterroute.BOAT_CLASSES}}))
        p = ok(h.post("/dispatch/plan", json={"day": str(D1)}))
        by = {x["crew_id"]: x for x in p["plans"]}
        check(not by["CREW-1"]["stops"] and not by["CREW-3"]["stops"], "no boat stops on a no-go day")
        check(any(u["wo_id"] == dock for u in p["unassigned"]), "boat-only dock-node build waits for weather")
        modes = {r["travel_mode"] for r in q("SELECT travel_mode FROM work_orders WHERE scheduled_for=$1", D1)}
        check(len(by["CREW-2"]["stops"]) >= 2 and modes == {"truck"}, "installs still go out, all by truck")
        check(any(u["wo_id"] == wo["Dev Patel"] for u in p["unassigned"]), "a truck-only day runs out of shift: fiber drop waits")
        check(p["weather"]["source"] == "override", "dispatcher override recorded")

        print("5. Go day: boat vs truck chosen per job on real routes")
        ok(h.post("/weather/override", json={"day": str(D1), "reason": "clear, light wind", "classes": {}}))
        p = ok(h.post("/dispatch/plan", json={"day": str(D1)}))
        by = {x["crew_id"]: x for x in p["plans"]}
        mode = {r["wo_id"]: (r["assigned_crew"], r["travel_mode"]) for r in q("SELECT wo_id, assigned_crew, travel_mode FROM work_orders")}
        check(mode[wo["Ada Harper"]] == ("CREW-1", "boat") and mode[wo["Ben Ortiz"]] == ("CREW-1", "boat"),
              "Lost Bridge (boat-first) installs go by boat")
        check(mode[wo["Cora Blake"]][1] == "truck" and mode[wo["Dev Patel"]] == ("CREW-2", "truck"),
              "Beaver Shores (truck-first) installs go by truck")
        check(mode[dock] == ("CREW-3", "boat"), "dock-node build goes to the pontoon crew")
        rs = ok(h.get(f"/dispatch/runsheet/CREW-1", params={"day": str(D1)}))
        leg = rs["stops"][0]["travel"]
        check(leg["mode"] == "boat" and len(leg["path"]) > 2 and leg["dock_to_site_m"] <= 600,
              f"run sheet carries the water route ({len(leg['path'])} pts, dock->site {leg['dock_to_site_m']} m)")
        check(any(x["for"] == "jobs" and x["sku"] == cpe_sku for x in rs["load_list"]) and
              any(x["for"] == "spare kit" for x in rs["load_list"]), "load list = job BOM + boat spare kit")

        print("6. Outage -> P1 repair inserted next for the fastest crew")
        q("INSERT INTO outages (root_node, impacted_customers, status) VALUES ('BDN-LostBridge-T2-01', 37, 'open')", fetch="exec")
        o = ok(h.post("/outages/1/dispatch", params={"now": f"{D1}T07:45:00-05:00"}))
        check(o["assigned"] and o["next_stop"] == 1, f"P1 repair assigned to {o['crew_id']} by {o['mode']} as the next stop")
        rs = ok(h.get(f"/dispatch/runsheet/{o['crew_id']}", params={"day": str(D1)}))
        check(rs["stops"][0]["priority"] == "P1" and [s["seq"] for s in rs["stops"]] == list(range(1, len(rs["stops"]) + 1)),
              "run sheet re-sequenced with the repair first")
        rs1 = ok(h.get("/dispatch/runsheet/CREW-1", params={"day": str(D1)}))
        os.makedirs(os.path.join(REPO, "data", "dispatch"), exist_ok=True)
        json.dump(rs1, open(os.path.join(REPO, "data", "dispatch", "demo_runsheet.json"), "w"), indent=1, default=str)

        print("7. Crew PWA in headless Chromium (phone width)")
        installed_mac = "AA:BB:CC:9F:00:01"      # the unit on the boat, not the one registered at signup
        shot = os.path.join(REPO, "data", "dispatch", "crew_pwa_screenshot.png")
        pw = subprocess.run(["node", os.path.join(HERE, "pwa_check.mjs"), BASE, "CREW-1", str(D1),
                             str(wo["Ada Harper"]), installed_mac, str(wo["Ben Ortiz"])],
                            capture_output=True, text=True, timeout=180, env=dict(os.environ, SHOT=shot))
        res = json.loads(pw.stdout.strip().splitlines()[-1]) if pw.stdout.strip() else {"errors": [pw.stderr[-800:]]}
        check(not res["errors"], f"no page errors ({res['errors'][:2]})")
        check(not res["bodyScrollsSideways"], "no sideways scroll at 400 px")
        check(res["firstButton"].strip() == "Tied up at the dock" and res["secondButton"].strip() == "Start work",
              "boat stop flow: tie up -> start")
        check(res["completeDisabledBefore"] and not res["completeDisabledAfter"], "Complete stays disabled until readings are in")
        check("first bill" in res["toast"], f"toast: {res['toast']}")
        check("queued" in res["chipsOffline"] and "offline" in res["chipsOffline"] and "All synced" in res["chipsAfter"],
              "offline action queued, replayed on reconnect")

        print("8. What the crew's tap did to the business")
        a = q("""SELECT w.status, si.state, si.radius_username, si.cpe_id FROM work_orders w
                 JOIN service_instances si ON si.service_id=w.service_id WHERE w.wo_id=$1""", wo["Ada Harper"], fetch="row")
        check(a["status"] == "closed" and a["state"] == "active", "WO closed, service active")
        check(a["radius_username"] == "aa-bb-cc-9f-00-01", "RADIUS re-keyed to the CPE actually installed")
        inv = q("SELECT i.total_usd, lower(i.period) p FROM invoices i JOIN service_instances si ON si.sub_id=i.sub_id WHERE si.service_id=$1",
                svc["Ada Harper"]["service_id"], fetch="row")
        check(inv is not None, f"first bill issued by the crew closing the job (${inv['total_usd'] if inv else '?'})")
        check(q("SELECT serial FROM cpe WHERE cpe_id=$1", a["cpe_id"], fetch="val") == installed_mac, "CPE record created")
        check(q("SELECT count(*) FROM assets WHERE serial=$1 AND asset_class='cpe'", installed_mac, fetch="val") == 1,
              "CPE capitalized as an asset")
        st = q("SELECT qty_on_hand, qty_reserved FROM inventory WHERE sku=$1", cpe_sku, fetch="row")
        check(float(st["qty_on_hand"]) == 6 and float(st["qty_reserved"]) == 2, "stock: 7 on hand -> 6; reserved 3 -> 2")
        kinds = [r["kind"] for r in q("SELECT kind FROM wo_events WHERE wo_id=$1 ORDER BY event_id", wo["Ada Harper"])]
        check(kinds[-5:] == ["arrived", "started", "captured", "completed", "departed"], f"field events {kinds[-5:]}")
        check(q("SELECT count(*) FROM wo_events WHERE wo_id=$1 AND kind='arrived'", wo["Ben Ortiz"], fetch="val") == 1,
              "offline 'tied up' landed once")

        print("9. Idempotency, refusals, send-back, outage close")
        cid = q("SELECT client_action_id FROM wo_events WHERE wo_id=$1 AND kind='arrived'", wo["Ben Ortiz"], fetch="val")
        r = ok(h.post("/field/actions", json={"actions": [{"client_action_id": cid, "wo_id": wo["Ben Ortiz"], "kind": "arrived"}]}))
        check(r["results"][0].get("duplicate"), "replayed action is a no-op")
        r = ok(h.post("/field/actions", json={"actions": [
            {"client_action_id": "t-c1", "wo_id": wo["Cora Blake"], "kind": "started"},
            {"client_action_id": "t-c2", "wo_id": wo["Cora Blake"], "kind": "completed"}]}))
        check(r["results"][1]["ok"] is False and "device_mac" in r["results"][1]["missing"], "completion refused without readings")
        r = ok(h.post("/field/actions", json={"actions": [
            {"client_action_id": "t-d1", "wo_id": wo["Dev Patel"], "kind": "cant_complete", "data": {"reason": "Member not home"}}]}))
        dv = q("SELECT status, assigned_crew, note FROM work_orders WHERE wo_id=$1", wo["Dev Patel"], fetch="row")
        check(dv["status"] == "released" and dv["assigned_crew"] is None and "Member not home" in dv["note"],
              "can't complete -> back to dispatch with the reason")
        rep = o["wo_id"]
        r = ok(h.post("/field/actions", json={"actions": [
            {"client_action_id": "t-r1", "wo_id": rep, "kind": "started"},
            {"client_action_id": "t-r2", "wo_id": rep, "kind": "capture", "data": {"resolution": "Reseated backhaul PoE; NOC confirms up"}},
            {"client_action_id": "t-r3", "wo_id": rep, "kind": "completed"}]}))
        check(all(x["ok"] for x in r["results"]) and q("SELECT status FROM outages WHERE outage_id=1", fetch="val") == "resolved",
              "repair closed -> outage resolved")

        print("10. Measured dock turnaround feeds the planner")
        t0 = dt.datetime(2026, 10, 7, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=-5)))
        for i in range(5):
            wid = ok(h.post("/work-orders", json={"wo_type": "survey", "lon": shore[0], "lat": shore[1]}))["wo_id"]
            q("UPDATE work_orders SET vehicle_id='BOAT-1', status='scheduled' WHERE wo_id=$1", wid, fetch="exec")
            b = t0 + dt.timedelta(hours=i)
            acts = [("arrived", b), ("started", b + dt.timedelta(minutes=6)),
                    ("capture", b + dt.timedelta(minutes=30)), ("completed", b + dt.timedelta(minutes=40)),
                    ("departed", b + dt.timedelta(minutes=43))]
            ok(h.post("/field/actions", json={"actions": [
                {"client_action_id": f"m{i}{k}", "wo_id": wid, "kind": k, "at": at.isoformat(),
                 "data": {"dock_access": "yes", "gps": f"{shore[1]:.5f}, {shore[0]:.5f}"} if k == "capture" else {}}
                for k, at in acts]}))
        m = ok(h.get("/metrics/turnaround"))
        check(m["planner_boat_tieup_min"] == 9.0 and m["source"].startswith("measured"),
              f"boat turnaround measured: {m['planner_boat_tieup_min']} min ({m['source']})")
        D2 = D1 + dt.timedelta(days=1)
        ok(h.post("/weather/override", json={"day": str(D2), "reason": "clear", "classes": {}}))
        p2 = ok(h.post("/dispatch/plan", json={"day": str(D2)}))
        check(p2["boat_tieup_min"] == 9.0, "next day's plan uses the measured turnaround")
    print(f"\nALL {PASS} CHECKS PASSED")

if __name__ == "__main__":
    main()
