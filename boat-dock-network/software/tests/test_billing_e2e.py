#!/usr/bin/env python3
"""End-to-end: billing API + provisioning engine + governance + LIVE FreeRADIUS (doc 22).

Walks two members through the full lifecycle and checks both the money and the
network policy (real Access-Request / Accounting-Request packets via radtest/radclient):

  Ada (member, node host, paid a $100 reservation deposit):
    subscribe -> Reject while pending -> engine provisions -> Accept for turn-up ->
    activate (prorated first bill: host credit, taxed router, deposit credit) ->
    accounting -> pay -> November bill -> dunning notice -> 21-day walled garden +
    CoA -> WAKE accrual paused -> pay -> restored -> plan upgrade (instant) ->
    seasonal hold ($10, still accrues WAKE) -> resume -> cancel -> terminated at the
    next run: Reject + WAKE forfeited to the Commons Pool
  Bo (marina, business plan): PPPoE + static IPv4; residential static IPv4 refused.
  Plus: idempotent billing runs and the least-privilege radius DB role.

Prereqs: Postgres with the DockOS schemas incl. billing_schema.sql loaded into
$TEST_DB, FreeRADIUS configured by software/radius/setup_freeradius.sh and running on
127.0.0.1 (secret testing123), radtest/radclient on PATH.
Run: TEST_DB=dockos_bill python3 software/tests/test_billing_e2e.py
"""
import os, sys, re, asyncio, subprocess, datetime as dt
from decimal import Decimal

DB_NAME = os.environ.get("TEST_DB", "dockos_bill")
DSN = os.environ.setdefault("DATABASE_URL", f"postgresql://dockos:dockos@127.0.0.1:5432/{DB_NAME}")
os.environ.setdefault("IPV6_POOL", "2001:db8::/36")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "api"), os.path.join(HERE, "..", "provisioning")]

import asyncpg
from fastapi.testclient import TestClient
import billing, governance, engine

SECRET = "testing123"
D = dt.date

# ---------------------------------------------------------------- helpers
def q(sql, *args, fetch="all"):
    async def go():
        c = await asyncpg.connect(DSN)
        try:
            return await getattr(c, {"all": "fetch", "row": "fetchrow", "val": "fetchval", "exec": "execute"}[fetch])(sql, *args)
        finally:
            await c.close()
    return asyncio.run(go())

def radius_auth(user, pw):
    out = subprocess.run(["radtest", user, pw, "127.0.0.1", "0", SECRET],
                         capture_output=True, text=True, timeout=20).stdout
    code = re.search(r"Received (Access-\w+)", out)
    attrs = dict(re.findall(r"^\s+([\w-]+) = \"?([^\"\n]*)\"?$", out, re.M))
    return (code.group(1) if code else "NO-REPLY"), attrs

def radius_acct(**avps):
    body = "\n".join(f"{k} = {v}" for k, v in avps.items()) + "\n"
    out = subprocess.run(["radclient", "-x", "127.0.0.1:1813", "acct", SECRET], input=body,
                         capture_output=True, text=True, timeout=20).stdout
    return "Accounting-Response" in out

def run_engine():
    async def go():
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
        try:
            eng = engine.Engine(pool, engine.DryRunAccess("olt"), engine.DryRunAccess("wireless"),
                                engine.CoaAdapter(dry_run=True))
            return await eng.run_once()
        finally:
            await pool.close()
    return asyncio.run(go())

PASS = 0
def check(cond, msg):
    global PASS
    if not cond:
        raise AssertionError(msg)
    PASS += 1
    print(f"  ✓ {msg}")

def ok(resp):
    assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
    return resp.json()

# ---------------------------------------------------------------- fixtures
def seed():
    q("""TRUNCATE billing_events, provisioning_jobs, payments, invoice_lines, invoices, one_time_charges,
         account_credits, service_instances, subscriptions, host_node_agreements, pledges, signups,
         wake_ledger, wake_balances, votes, proposals, members, customers, service_addresses, zones,
         radacct, radpostauth, nas, commons_pool RESTART IDENTITY CASCADE""", fetch="exec")
    q("INSERT INTO zones(zone_id,name,phase) VALUES ('Z-01','Beaver Shores',1),('Z-02','Prairie Creek',1)", fetch="exec")
    q("INSERT INTO service_addresses(address,zone_id,building_type) VALUES ('12 Cove Rd','Z-01','home'),('1 Marina Way','Z-02','marina')", fetch="exec")
    q("INSERT INTO nas(nasname,shortname,type,secret) VALUES ('127.0.0.1','bng-test','other',$1)", SECRET, fetch="exec")
    ada = q("INSERT INTO customers(name,email,address_id) VALUES ('Ada','ada@example.com',1) RETURNING customer_id", fetch="val")
    mid = q("INSERT INTO members(customer_id,joined_at,is_host) VALUES ($1,'2026-04-01',true) RETURNING member_id", ada, fetch="val")
    q("""INSERT INTO wake_ledger(member_id,event,amount,period,note)
         SELECT $1,'accrual',1.5,('2026-04-01'::date + (g||' months')::interval)::date,'seed'
         FROM generate_series(0,5) g""", mid, fetch="exec")        # 6 months as a host = 9 units
    q("INSERT INTO wake_balances(member_id,units) VALUES ($1,9)", mid, fetch="exec")
    sid = q("""INSERT INTO signups(zone_id,name,email,want_reservation,want_member)
               VALUES ('Z-01','Ada','ada@example.com',true,true) RETURNING signup_id""", fetch="val")
    q("""INSERT INTO pledges(signup_id,kind,amount_usd,status,zone_id,collected_at)
         VALUES ($1,'reservation_deposit',100,'collected','Z-01',now())""", sid, fetch="exec")
    q("""INSERT INTO host_node_agreements(customer_id,monthly_credit_usd,start_date)
         VALUES ($1,15,'2026-09-01')""", ada, fetch="exec")
    return ada, mid

# ---------------------------------------------------------------- the lifecycle
def main():
    ada, ada_mid = seed()
    bc, gc = TestClient(billing.app), TestClient(governance.app)
    with bc, gc:
        print("1. Subscribe Ada (Shoreline 1G, nLOS CPE, router purchase)")
        r = ok(bc.post("/subscriptions", json={"customer_id": ada, "address_id": 1, "plan_id": "shoreline",
               "access": "ipoe_mac", "device_id": "AA:BB:CC:11:22:33", "medium": "wireless_nlos",
               "equipment_usd": "120"}))
        user, sub, svc = r["radius_username"], r["sub_id"], r["service_id"]
        check(user == "aa-bb-cc-11-22-33", "MAC normalized for RADIUS (aa-bb-cc-11-22-33)")
        check(r["ipv6_pd"] == "2001:db8:100::/56", f"IPv6 /56 from zone Z-01's /44 ({r['ipv6_pd']})")
        check(r["deposits_credited"] == [1], "collected $100 reservation deposit found by email -> account credit")
        check(radius_auth(user, user)[0] == "Access-Reject", "pending service: RADIUS Access-Reject")

        print("2. Provisioning engine (dry-run adapters)")
        res = run_engine()
        check(res and res[0]["action"] == "activate" and res[0]["ok"], "activate job done")
        code, a = radius_auth(user, user)
        check(code == "Access-Accept", "provisioned: Access-Accept for tech turn-up")
        check(a.get("Filter-Id") == "plan_shoreline" and a.get("Mikrotik-Rate-Limit") == "1000M/1000M",
              f"plan QoS from the catalog view ({a.get('Filter-Id')}, {a.get('Mikrotik-Rate-Limit')})")
        check(a.get("Delegated-IPv6-Prefix") == "2001:db8:100::/56", "Delegated-IPv6-Prefix in reply")

        print("3. Activate Oct 10 -> prorated first bill")
        inv = ok(bc.post(f"/services/{svc}/activate", params={"as_of": "2026-10-10"}))["first_invoice"]
        # 89*22/31=63.16 ; host credit 15*22/31=10.65 ; router 120 + 9.5% tax 11.40 ; deposit -100
        check(inv["subtotal"] == "172.51" and inv["tax"] == "11.40", f"subtotal 172.51, tax 11.40 ({inv['subtotal']}, {inv['tax']})")
        check(inv["credits"] == "100.00" and inv["total"] == "83.91", f"deposit credited, total 83.91 ({inv['total']})")
        kinds = [l["kind"] for l in inv["lines"]]
        check(kinds == ["service", "credit_host", "equipment", "credit_deposit"], f"invoice lines {kinds}")
        first_inv = inv["invoice_id"]

        print("4. Accounting")
        check(radius_acct(**{"Acct-Status-Type": "Start", "User-Name": f'"{user}"', "Acct-Session-Id": '"s-ada-1"',
              "NAS-IP-Address": "127.0.0.1", "Framed-IP-Address": "100.64.0.10"}), "Accounting Start accepted")
        check(radius_acct(**{"Acct-Status-Type": "Interim-Update", "User-Name": f'"{user}"', "Acct-Session-Id": '"s-ada-1"',
              "NAS-IP-Address": "127.0.0.1", "Acct-Input-Octets": "2000000000", "Acct-Output-Octets": "410065408", "Acct-Output-Gigawords": "2",  # 2*2^32+410065408 = 9e9 B
              "Acct-Session-Time": "3600"}), "Interim-Update accepted")
        u = q("SELECT upload_gb, download_gb FROM usage_monthly WHERE service_id=$1", svc, fetch="row")
        check(u and float(u["download_gb"]) == 9.0 and float(u["upload_gb"]) == 2.0, "usage_monthly: 9 GB down / 2 GB up")

        print("5. Pay, then November run")
        ok(bc.post("/payments", json={"invoice_id": first_inv, "amount_usd": "83.91", "as_of": "2026-10-12"}))
        run = ok(bc.post("/billing/run", json={"period": "2026-11"}))
        check(run["invoices_issued"] == 1 and run["billed_usd"] == "74.00", f"Nov: 89 - 15 host credit = 74.00 ({run['billed_usd']})")
        check(ok(bc.post("/billing/run", json={"period": "2026-11"}))["invoices_issued"] == 0, "re-running a period is idempotent")

        print("6. Dunning (Nov invoice due Nov 16, unpaid)")
        d = ok(bc.post("/billing/dunning", json={"as_of": "2026-11-27"}))
        check(d["notices"] == [sub] and not d["suspended"], "11 days late: notice only")
        check(not ok(bc.post("/billing/dunning", json={"as_of": "2026-11-28"}))["notices"], "notice not repeated")
        d = ok(bc.post("/billing/dunning", json={"as_of": "2026-12-08"}))
        check(d["suspended"] == [sub], "22 days late: suspended")
        code, a = radius_auth(user, user)
        check(code == "Access-Accept" and a.get("Filter-Id") == "walled-garden" and a.get("Mikrotik-Rate-Limit") == "1M/1M",
              "suspended: walled garden (can still reach the pay page)")
        res = run_engine()
        coa = res[0]["result"]["coa"][0]
        check(res[0]["action"] == "suspend" and coa["to"] == "127.0.0.1:3799" and 'Acct-Session-Id = "s-ada-1"' in coa["attrs"],
              "engine: RFC 5176 Disconnect-Request built for the live session")
        check(q("SELECT status FROM members WHERE member_id=$1", ada_mid, fetch="val") == "suspended", "member status suspended")
        acc = ok(gc.post("/wake/accrue-month", json={"period": "2026-12-01"}))
        check(acc["accrued_members"] == 0, "nonpay suspension pauses WAKE accrual (no forfeiture)")

        print("7. Pay -> restored")
        nov = q("SELECT invoice_id FROM invoices WHERE sub_id=$1 AND lower(period)='2026-11-01'", sub, fetch="val")
        p = ok(bc.post("/payments", json={"invoice_id": nov, "amount_usd": "74.00", "as_of": "2026-12-09",
                                          "stripe_payment_intent": "pi_test_1"}))
        check(p["service_resumed"], "payment lifts the suspension")
        check(ok(bc.post("/payments", json={"invoice_id": nov, "amount_usd": "74.00",
                                            "stripe_payment_intent": "pi_test_1"})).get("duplicate"), "webhook retry is idempotent")
        check(radius_auth(user, user)[1].get("Filter-Id") == "plan_shoreline", "back on Shoreline")
        check(q("SELECT status FROM members WHERE member_id=$1", ada_mid, fetch="val") == "active", "member active again")

        print("8. Upgrade to Deep Water (instant QoS, price next period)")
        ok(bc.post(f"/subscriptions/{sub}/change-plan", json={"plan_id": "deepwater"}))
        a = radius_auth(user, user)[1]
        check(a.get("Filter-Id") == "plan_deepwater" and a.get("Mikrotik-Rate-Limit") == "2000M/2000M", "RADIUS shows 2G on next auth")
        run_engine()

        print("9. Seasonal hold")
        ok(bc.post(f"/subscriptions/{sub}/hold", json={"as_of": "2026-12-15"}))
        check(radius_auth(user, user)[1].get("Filter-Id") == "walled-garden", "hold: walled garden")
        run = ok(bc.post("/billing/run", json={"period": "2027-01"}))
        check(run["billed_usd"] == "10.00", f"January hold fee 10.00 ({run['billed_usd']})")
        acc = ok(gc.post("/wake/accrue-month", json={"period": "2027-01-01"}))
        check(acc["accrued_members"] == 1, "seasonal hold keeps membership: WAKE still accrues")
        check(bc.post(f"/subscriptions/{sub}/resume", json={}).status_code == 200, "resume from hold")
        check(radius_auth(user, user)[1].get("Filter-Id") == "plan_deepwater", "back on Deep Water")
        run_engine()

        print("10. Cancel -> terminated at next run, WAKE forfeited")
        units = float(q("SELECT units FROM wake_balances WHERE member_id=$1", ada_mid, fetch="val"))
        c = ok(bc.post(f"/subscriptions/{sub}/cancel", json={"as_of": "2027-01-20"}))
        check(c["effective"] == "2027-01-31" and c["wake_units_at_risk"] == units,
              f"cancel effective end of month; warns {units} WAKE at risk")
        run = ok(bc.post("/billing/run", json={"period": "2027-02"}))
        check(run["terminated_subs"] == [sub] and run["invoices_issued"] == 0, "Feb run terminates, no bill")
        check(radius_auth(user, user)[0] == "Access-Reject", "terminated: Access-Reject")
        pool_units = float(q("SELECT units FROM commons_pool WHERE id=1", fetch="val"))
        check(pool_units == units and q("SELECT status FROM members WHERE member_id=$1", ada_mid, fetch="val") == "lapsed",
              f"{units} WAKE forfeited to the Commons Pool; member lapsed (doc 16)")
        res = run_engine()
        check(res[-1]["action"] == "terminate" and "access" in res[-1]["result"], "engine: disconnect + deprovision")

        print("11. Bo's marina: PPPoE + static IPv4 (business only)")
        bad = bc.post("/subscriptions", json={"name": "Nope", "plan_id": "cove", "access": "pppoe", "ipv4_static": "198.51.100.9"})
        check(bad.status_code == 400, "static IPv4 refused on a residential plan")
        r = ok(bc.post("/subscriptions", json={"name": "Bo's Marina", "email": "bo@example.com", "address_id": 2,
                       "plan_id": "business", "access": "pppoe", "medium": "fiber", "ipv4_static": "198.51.100.9"}))
        check(r["ipv6_pd"].startswith("2001:db8:110:"), f"zone Z-02 gets its own /44 ({r['ipv6_pd']})")
        run_engine(); ok(bc.post(f"/services/{r['service_id']}/activate", params={"as_of": "2026-10-01"}))
        code, a = radius_auth(r["radius_username"], r["radius_password"])
        check(code == "Access-Accept" and a.get("Framed-IP-Address") == "198.51.100.9" and a.get("Filter-Id") == "plan_business",
              "PPPoE Accept with static Framed-IP-Address + business profile")
        check(radius_auth(r["radius_username"], "wrong-password")[0] == "Access-Reject", "wrong PPPoE password rejected")

        print("12. Least privilege: the radius DB role")
        def as_radius(sql):
            async def go():
                c = await asyncpg.connect(f"postgresql://radius:radpass@127.0.0.1:5432/{DB_NAME}")
                try:
                    return await c.fetchval(sql)
                finally:
                    await c.close()
            try:
                return asyncio.run(go())
            except asyncpg.InsufficientPrivilegeError:
                return "DENIED"
        check(as_radius("SELECT count(*) FROM radcheck") >= 1, "radius role reads the radcheck view")
        check(as_radius("SELECT count(*) FROM service_instances") == "DENIED", "radius role cannot read service_instances")
        check(as_radius("SELECT count(*) FROM invoices") == "DENIED", "radius role cannot read invoices")

        acct = ok(bc.get(f"/customers/{ada}/account"))
        check(acct["membership"]["status"] == "lapsed" and acct["balance_due"] == "10.00",
              "account view: lapsed; unpaid January hold fee stays collectible after termination")
    print(f"\nALL {PASS} CHECKS PASSED")

if __name__ == "__main__":
    main()
