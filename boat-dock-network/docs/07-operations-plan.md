# 07 — Operations Plan (Boat-Native)

The operating premise: **the lake is the road.** Field work is dispatched, delivered,
and repaired by boat. Operations are organized around three engines — **Build**,
**Service/Repair**, and the **NOC** — all coordinated by DockOS (doc 14).

## 1. Marine field operations

### Fleet
| Vessel | Purpose |
|--------|---------|
| Utility/work pontoon(s) | Node builds, material haul, mast/antenna work, splicing setup |
| Fast center-console(s) | Rapid service/repair dispatch, survey, sales visits |
| Small jon boats / kayaks | Tight coves, quick CPE installs |
| Optional barge/lift | Heavy dock-node sets, subaqueous cable lay |

Each work vessel is a **rolling truck**: standardized tool kits, spares (BOM kits, doc
10), fusion splicer, test gear (OTDR, power meter, spectrum analyzer), safety kit,
and a rugged tablet running the field PWA with offline maps.

### Launch/staging
- One or more **shoreline yards/ramps** (owned or leased — candidate use for a small
  purchased parcel) for boat storage, materials, fueling, and dispatch staging.
- Zone-level **cache sites** at host-node/marina partners hold common spares to cut
  travel time.

### Safety (non-negotiable)
- USCG-compliant vessels, PFDs, marine radio, float plans logged in DockOS.
- Weather go/no-go SOP; lightning and high-wind stand-downs.
- RF safety for mast/antenna work; fall protection on masts/towers.
- Electrical/battery safety; **zero-spill discipline** near the drinking-water source
  (Beaver Water District) — sealed batteries, spill kits, no fueling over water.
- Buddy system for mid-lake and mast work; check-in cadence to NOC.

## 2. Build operations (new plant)

Pipeline (each stage is a DockOS state + work-order type):
1. **Survey** — boat crew captures dock access, power, LOS photos, GPS; updates GIS.
2. **Design validate** — GIS LOS/link budget passes; permits identified.
3. **Permit** — USACE/county/pole/ARDOT as needed (doc 12); auto-checklist per WO.
4. **Node build (T1/T2/T3)** — set mast/enclosure/power/solar, mount radios/OLT, backhaul
   up, test.
5. **Drop/CPE install (T4)** — fiber drop or wireless CPE, activate, speed-test,
   customer sign-off.
6. **As-built** — serials, photos, GPS captured; node marked live.

## 3. Service & repair operations

- **Tiered response:** NOC triage → remote fix → boat dispatch if physical.
- **SLA targets (planning):** residential next-business-day; business same-day;
  marina/resort priority + spares on-site.
- **Outage flow:** device-down alert → DockOS computes impacted customers + outage
  polygon → auto-ticket + status page update → nearest qualified boat crew dispatched
  with the right BOM kit → repair → as-built + customer comms.
- **Truck-roll-by-boat efficiency:** dispatch routes by water from nearest ramp/cache;
  batch nearby jobs; carry standard spare kits so most repairs are one trip.
- **Preventive maintenance:** seasonal node inspections (mounts, solar, batteries,
  enclosure seals), vegetation checks on wireless paths, spare-battery rotation.

## 4. Network Operations Center (NOC)

- **Monitoring stack:** LibreNMS/Zabbix + Prometheus/Grafana pulling SNMP/streaming
  telemetry from all T0–T3 devices; UISP for Ubiquiti; vendor controllers for
  Tarana/Cambium/Cambium cnMaestro.
- **Alerting/on-call:** thresholds + flap detection → paging; runbooks per alert.
- **Capacity management:** per-zone utilization trends drive spine/transit upgrades and
  the fiber-overbuild backlog.
- **Status page + customer comms:** automated outage notices (SMS/email) from DockOS.
- **Security:** device hardening, segmented management network, backups, change control.

## 5. Customer operations

- **Signup → install:** self-serve serviceability + plan selection + scheduling (doc
  14); boat-install appointment windows.
- **Support:** phone/text/portal; local, boat-dispatched when physical.
- **Billing:** automated invoicing, autopay, host-node credits, seasonal pause plans.
- **Onboarding:** in-home/dock Wi-Fi setup, speed test, education.

## 6. Standards, docs & continuous improvement

- **Standard build specs** per node tier so any tech services any node.
- **Runbooks** for common faults; **as-built discipline** enforced by DockOS gating.
- **KPIs:** install cycle time, mean-time-to-repair, truck(boat)-rolls per fix, uptime
  per zone, NPS, cost-per-install, cost-per-repair — all dashboarded from DockOS.
- **Weekly ops review** against KPIs; feed learnings into BOM kits and standards.

## 7. Seasonality

- **Peak season (spring–fall):** maximize builds/installs; marina/resort demand peaks.
- **Winter:** node hardening, PM, backlog design/permitting, indoor work; solar sizing
  assumes winter minimums so nodes ride through.
