#!/usr/bin/env python3
"""Boat Dock Network — provisioning engine (doc 22). DockOS step 6.

Billing never touches the network directly: it writes provisioning_jobs. This worker
claims jobs (FOR UPDATE SKIP LOCKED, so several workers can run safely), applies them
through adapters, and records the outcome.

  activate     access adapter configures the ONT (fiber) or CPE (wireless) with the
               plan profile + VLANs, then service_instances pending -> provisioned
               (RADIUS then accepts it for the tech's turn-up speed test).
  suspend      \
  resume        >  policy already changed in billing (the RADIUS views follow state);
  change_plan  /   the CoA adapter sends an RFC 5176 Disconnect-Request so the live
                   session re-authenticates into its new group (plan / walled garden).
  terminate    Disconnect + access adapter deprovisions the ONT/CPE.

Adapters are pluggable. The vendor adapters (OLT via NETCONF/vendor API, Tarana/
Cambium CPE APIs) are interfaces to implement against the chosen gear (doc 10/21);
DryRun adapters log what would happen so the whole pipeline runs in dev/CI.

Usage:
  DATABASE_URL=postgresql://dockos:dockos@localhost/dockos python3 engine.py --once --dry-run
  python3 engine.py --interval 10            # long-running worker
"""
from __future__ import annotations
import os, sys, json, asyncio, argparse, subprocess, logging
from typing import Optional
import asyncpg

log = logging.getLogger("bdn.provisioning")
DB = os.environ.get("DATABASE_URL", "postgresql://dockos:dockos@localhost:5432/dockos")
MAX_ATTEMPTS = int(os.environ.get("PROV_MAX_ATTEMPTS", 5))
COA_PORT = int(os.environ.get("COA_PORT", 3799))

# ---------------------------------------------------------------- adapters
class AccessAdapter:
    """Configures the subscriber's access device. Implement per vendor."""
    def activate(self, svc: dict) -> dict: raise NotImplementedError
    def deprovision(self, svc: dict) -> dict: raise NotImplementedError

class DryRunAccess(AccessAdapter):
    def __init__(self, kind: str): self.kind = kind
    def activate(self, svc):
        return {"adapter": f"dryrun-{self.kind}", "would": "activate", "device": svc["radius_username"],
                "profile": svc["radius_group"], "s_vlan": svc["s_vlan"], "c_vlan": svc["c_vlan"],
                "ipv6_pd": svc["ipv6_pd"]}
    def deprovision(self, svc):
        return {"adapter": f"dryrun-{self.kind}", "would": "deprovision", "device": svc["radius_username"]}

class OltAdapter(AccessAdapter):
    """XGS-PON OLT (doc 21 §5.1): register ONT serial on its PON port, bind the service
    profile (rate = plan) and S/C-VLANs, via the OLT's NETCONF/REST API. Vendor TBD by
    quote (doc 10) — implement activate/deprovision against it."""

class WirelessCpeAdapter(AccessAdapter):
    """nLOS/PtMP CPE (Tarana G1 / Cambium, doc 21 §6.1): authorize the RN/SM on its base
    node and push the plan profile via the vendor cloud API."""

class CoaAdapter:
    """RFC 5176 Disconnect-Request to the NAS/BNG for each open session (from radacct),
    using the NAS secret from the `nas` table. The re-authenticating session lands in
    whatever group the RADIUS views now say (plan, walled garden, or reject)."""
    def __init__(self, dry_run: bool = False, radclient: str = "radclient"):
        self.dry_run, self.radclient = dry_run, radclient

    @staticmethod
    def build_request(session: dict) -> str:
        attrs = [f'User-Name = "{session["username"]}"',
                 f'Acct-Session-Id = "{session["acctsessionid"]}"',
                 f'NAS-IP-Address = {session["nasipaddress"]}']
        if session.get("framedipaddress"):
            attrs.append(f'Framed-IP-Address = {session["framedipaddress"]}')
        return "\n".join(attrs) + "\n"

    def disconnect(self, sessions: list[dict]) -> list[dict]:
        results = []
        for s in sessions:
            payload = self.build_request(s)
            target = f'{s["nasipaddress"]}:{COA_PORT}'
            cmd = [self.radclient, "-x", "-t", "3", "-r", "2", target, "disconnect", s["secret"]]
            if self.dry_run or not s.get("secret"):
                results.append({"would_send": "Disconnect-Request", "to": target, "attrs": payload.strip().split("\n"),
                                "skipped": None if self.dry_run else "no NAS secret"})
                continue
            p = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=15)
            ok = p.returncode == 0 and ("Disconnect-ACK" in p.stdout)
            results.append({"to": target, "ok": ok, "out": p.stdout[-300:], "err": p.stderr[-300:]})
            if not ok:
                raise RuntimeError(f"CoA to {target} failed: {p.stdout[-200:]} {p.stderr[-200:]}")
        return results

# ---------------------------------------------------------------- engine
class Engine:
    def __init__(self, pool: asyncpg.Pool, fiber: AccessAdapter, wireless: AccessAdapter, coa: CoaAdapter):
        self.pool, self.fiber, self.wireless, self.coa = pool, fiber, wireless, coa

    async def _claim(self, c, limit: int):
        return await c.fetch("""
            UPDATE provisioning_jobs j SET status='running', started_at=now(), attempts=attempts+1
            WHERE job_id IN (SELECT job_id FROM provisioning_jobs WHERE status='queued'
                             ORDER BY created_at, job_id FOR UPDATE SKIP LOCKED LIMIT $1)
            RETURNING j.*""", limit)

    async def _service(self, c, service_id: int) -> dict:
        r = await c.fetchrow("""SELECT si.*, si.ipv6_pd::text AS ipv6_pd, s.plan_id, p.radius_group
            FROM service_instances si JOIN subscriptions s ON s.sub_id=si.sub_id
            JOIN plans p ON p.plan_id=s.plan_id WHERE si.service_id=$1""", service_id)
        return dict(r)

    async def _open_sessions(self, c, username: str) -> list[dict]:
        rows = await c.fetch("""SELECT r.username, r.acctsessionid, host(r.nasipaddress) AS nasipaddress,
                host(r.framedipaddress) AS framedipaddress, n.secret
            FROM radacct r LEFT JOIN nas n ON n.nasname = host(r.nasipaddress)
            WHERE r.username=$1 AND r.acctstoptime IS NULL""", username)
        return [dict(r) for r in rows]

    async def handle(self, c, job) -> dict:
        svc = await self._service(c, job["service_id"])
        access = self.fiber if svc["medium"] == "fiber" else self.wireless
        act = job["action"]
        if act == "activate":
            out = {"access": access.activate(svc)}
            await c.execute("""UPDATE service_instances SET state='provisioned', provisioned_at=now(),
                updated_at=now() WHERE service_id=$1 AND state='pending'""", svc["service_id"])
            return out
        sessions = await self._open_sessions(c, svc["radius_username"])
        out = {"coa": self.coa.disconnect(sessions), "sessions": len(sessions)}
        if act == "terminate":
            out["access"] = access.deprovision(svc)
        return out

    async def run_once(self, limit: int = 50) -> list[dict]:
        results = []
        async with self.pool.acquire() as c:
            async with c.transaction():
                jobs = await self._claim(c, limit)
            for job in jobs:
                try:
                    async with c.transaction():
                        out = await self.handle(c, job)
                        await c.execute("""UPDATE provisioning_jobs SET status='done', finished_at=now(),
                            last_error=NULL, payload = payload || $2::jsonb WHERE job_id=$1""",
                            job["job_id"], json.dumps({"result": out}, default=str))
                    results.append({"job_id": job["job_id"], "action": job["action"], "ok": True, "result": out})
                except Exception as e:   # retry with the attempt budget, then park as failed
                    status = "failed" if job["attempts"] >= MAX_ATTEMPTS else "queued"
                    await c.execute("""UPDATE provisioning_jobs SET status=$2, last_error=$3
                        WHERE job_id=$1""", job["job_id"], status, str(e)[:500])
                    log.warning("job %s %s failed (%s): %s", job["job_id"], job["action"], status, e)
                    results.append({"job_id": job["job_id"], "action": job["action"], "ok": False, "error": str(e)})
        return results

async def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="log device + CoA actions instead of sending")
    ap.add_argument("--interval", type=float, default=10.0)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pool = await asyncpg.create_pool(DB, min_size=1, max_size=4)
    # Swap DryRunAccess for OltAdapter/WirelessCpeAdapter implementations in production.
    eng = Engine(pool, DryRunAccess("olt"), DryRunAccess("wireless"), CoaAdapter(dry_run=a.dry_run))
    while True:
        res = await eng.run_once()
        for r in res:
            log.info("job %s %s -> %s", r["job_id"], r["action"], "ok" if r["ok"] else r["error"])
        if a.once:
            print(json.dumps(res, default=str, indent=1))
            return res
        await asyncio.sleep(a.interval)

if __name__ == "__main__":
    asyncio.run(main())
