# 24 — NOC: Monitoring, Root Cause & Outage Management (DockOS step 7)

> The NOC's job is not "what is down?". Collectors answer that. It answers **"what broke,
> who is dark, and what happens next?"**: one root cause instead of an alarm storm, a crew
> sent to the right site, members told once, and credits that apply themselves.
> Tested end-to-end on the real designed topology (52 checks, §7). **Building this showed that
> the backbone we called a ring is not one (§2).**

## 1. What was built
| Piece | File | What it does |
|-------|------|--------------|
| Topology engine | `software/noc/topology.py` | graph of head-ends + 30 spine nodes + 41 spine links; reachability, **root-cause correlation**, bridges / cut nodes (Tarjan), greedy redundancy planner |
| SPOF analysis | `software/noc/spof_analysis.py` | → `data/noc/spof_report.json`, `data/noc/redundancy_plan.csv` |
| Topology loader | `software/noc/load_topology.py` | zones, nodes, links and 87 monitored devices into PostGIS (idempotent) |
| Schema | `software/db/noc_schema.sql` | alerts (Alertmanager fingerprints), incidents (outage / degraded / power), outage_services, notifications, site_power, public `status_zones`, `noc_board`, `outage_kpis` |
| NOC API | `software/api/noc.py` | webhook ingest → state → correlation → incidents → dispatch → notices → recovery → credits; status page; board; SPOF; Prometheus targets |
| Board | `software/noc/make_board.py` → `data/noc/noc_board.html` (artifact "DockOS NOC") | the operations board, rendered from a real test run: live map, incident, alarm triage, member notice, ring audit, run log, public status |

Monitoring collectors are still off-the-shelf (doc 14 §3): Prometheus with the snmp and
blackbox exporters, vendor controllers, and Alertmanager. The NOC consumes Alertmanager's standard
webhook. `GET /noc/targets` emits Prometheus `file_sd` from the device inventory, so
every alert already carries its `node`, `link` or `service_id` label.

## 2. Finding: the "ring" has single points of failure
Doc 03 said the spine is "built as a ring so any one break heals." Measured on the designed
topology, weighted by Year-5 members (premises × 44% take):

- The 41 spine hops contain **9 bridges**: links whose loss splits the spine. With both head-ends
  attached, that is still **5 bridge links and 8 cut nodes**.
- **2,367 of 4,211 members (56%) sit behind a single point of failure.**
- The worst is **SP-06-13, a land hop.** It carries 13 nodes and **2,243 members** (half the
  network), as does its end node BDN-Z-02-N13. The NW head-end is single-homed into that
  same node.
- The spine is a tree with a few loops, not a ring. Each loop protects only its own part.

| Single point of failure | Type | Nodes cut off | Members |
|---|---|---:|---:|
| SP-06-13 / BDN-Z-02-N13 | land hop / T2 node | 13 | 2,243 |
| SP-06-10 / BDN-Z-01-N06 | lake crossing / T2 node | 12 | 1,751 |
| SP-10-14 / BDN-Z-08-N10 | land hop / T3 node | 11 | 1,537 |
| SP-14-18 / BDN-Z-06-N14 | land hop / T2 node | 10 | 1,350 |
| BDN-Z-18-N18 | T2 node | 9 | 1,310 |
| SP-11-28 / BDN-Z-10-N11 | lake crossing / T2 node | 3 | 429 |
| BDN-Z-10-N28 | T3 node | 2 | 311 |
| BDN-Z-16-N05 | T2 node | 2 | 124 |

**Fix: close the ring with 5 more hops.** The greedy planner adds the cheapest hop, up to
7 km, that removes the worst remaining SPOF:

| # | Removes | Add hop | km | Radio (spine class) | If it must be aerial fiber |
|---|---|---|---:|---:|---:|
| 1 | SP-06-13 | N10 ↔ N29 | 6.4 | $8,000 | $149,975 |
| 2 | SP-10-14 | N18 ↔ N10 | 5.4 | $8,000 | $125,055 |
| 3 | N10 (node) | N18 ↔ N06 | 6.6 | $8,000 | $153,415 |
| 4 | N18 (node) | N12 ↔ N06 | 6.6 | $8,000 | $153,711 |
| 5 | SP-11-28 | N04 ↔ N11 | 4.6 | $8,000 | $107,290 |
| | | | | **$40,000** | **$689,446** |

After the plan: **0 bridges**, and members behind a SPOF drop from **2,367 to 553**. Two
cut nodes remain, BDN-Z-10-N11 (429 members) and BDN-Z-16-N05 (124). Neither has another
site within 7 km. Each needs a new relay site, or a dual-radio node with a hot spare.

**Recommendation:**
1. Do a path survey on the five hops (LiDAR LOS, doc 05) **before Phase-2 spine
   procurement**.
2. Budget **$40k** for them as unlicensed PtP where the path is clear, and fall back to
   licensed µW or fiber only per failed hop.
3. **Dual-home the NW head-end.** Today its only lateral lands on the worst cut node; a
   second lateral to another node removes the SPOF that matters most. This ties into the
   doc 17 path-diversity checklist.

This is a planning estimate. The land-hop class price assumes line of sight, and LiDAR
showed canopy blocks about half of clean paths (backlog). **The pro forma is unchanged**, and
the $40k–$690k range is a decision for you. Docs 03 and 21 now carry this correction.

## 3. Root cause, not alarm storms
Each evaluation tick runs this chain:
```
alerts ─▶ element state ─▶ reachability from head-ends (R) ─▶ classify every alarm:
  down node with a working path into R (or a down head-end)  = ROOT CAUSE
  down node behind a root                                    = SUPPRESSED (just unreachable)
  down link from R into the dark side                        = ROOT CAUSE (unless its far end is a root)
  down link with both ends in R                              = RING OPEN (degraded, nobody dark)
  dark node that hasn't alarmed yet                          = SILENT (predicted dark)
  each connected dark component                              = ONE incident
```
- **Hold-down 60 s / clear-hold 120 s.** A blip opens nothing. Recovery must hold before
  anything closes.
- **Flap damping.** Three episodes in 30 min hold the element down until it has been
  stable for 15 min. The result is one incident instead of a stream of open/close notices.
- **Member radios (CPE).**
  - A radio on a dark node is suppressed.
  - A radio on **seasonal hold or suspended is ignored**; it is expected to be off.
  - ≥ 3 radios and ≥ 30% of a node's active members down while the node is up is an
    **access-sector outage**.
  - One radio down ≥ 30 min gets a **P3 ticket**, cancelled if the radio comes back on its own.
- **Power.** The NOC fits the SOC trend at each solar/battery (T3) site. If a site will hit
  the 20% low-voltage cutoff before the panels recover (09:00) or within 12 h, the NOC opens
  a **proactive visit before members go dark**: P1 if the cutoff is ≤ 6 h away, else P2. If
  the site dies anyway, the outage **adopts** that crew, and the cause reads *power*.

## 4. Incident lifecycle
| Kind | Trigger | Crew | Members |
|---|---|---|---|
| **outage** | members dark: isolation, dead node, dead sector | **P1 inserted as the next stop** of the crew that gets there first (doc 23) | notices (SMS + email) with ETA; status page; credits |
| **degraded** | ring open, a lost head-end, a flapping hop | P2 for the day planner | none |
| **power** | battery forecast to trip before sunrise | P1 or P2, proactive | none (yet) |

- **Opening.** The outage records who was dark. Only **active** services count, with
  business flags and plan price. It also records the impact polygon, zones, root elements,
  a member-facing cause and a NOC-facing detail. The ETA is crew arrival plus the repair
  estimate.
- **Growing.** Newly dark members join the outage and are notified once. Alertmanager
  repeats are idempotent.
- **Closing is telemetry, not the crew's word.** A crew closing the repair WO sets
  `field_fixed_at`. The outage resolves when the elements are back and have held for 120 s,
  at the **actual recovery time**. A fix that happens before the crew starts (power returns,
  a hop re-aligns) **cancels the WO and takes it off the run sheet**.
- **Kind changes.** A ring-open hop that becomes part of an isolation folds into the new
  outage, and its P2 is cancelled. When the isolation ends, it reopens as ring-open.

## 5. Member communications & status page
- Notices are queued per customer and channel, and deduplicated. The "restored" notice
  states the duration and the credit. The sender adapter is dry-run until the SMS/email
  provider is chosen (doc 13).
- **Public status page** (`/status`, `/status.html`): per zone only (state, since, ETA,
  cause, a member count). No names, addresses or contacts; the test asserts this. Host it
  independently of the primary stack (doc 14 §9).

## 6. Member SLA credits (automatic)
| Member | Rule | Example |
|---|---|---|
| Business / marina | any outage **> 4 h** (the P1 restore target) credits **2×** the prorated time, rounded up to the hour | 5 h on $199 → **$2.76** |
| Residential | outages **≥ 24 h** credit whole days, prorated | 26 h on Shoreline $89 → 2 days = **$5.93** |

Both are capped at one month's charge and posted to `account_credits` (kind `outage`),
which billing applies to the next invoice (doc 22). Members never have to ask. These are the
co-op's proposed terms; the board sets them in the member agreement.

## 7. Verified (`software/tests/test_noc_e2e.py`, 52 checks)
Real topology, PostGIS, dispatch with real lake and road routing, 114 synthetic services on 30
nodes. Alerts posted exactly as Alertmanager v4 sends them:
- A blip opens nothing.
- **Backbone cut SP-06-13 with 5 of 13 nodes alarming: one outage.**
  - The root cause is the link; all 13 nodes are dark, 8 of them predicted before they alarm.
  - 47 active members are dark (8 businesses); 4 seasonal holds are excluded.
  - The P1 is the truck crew's next stop, with a member ETA.
  - 94 notices are sent once; repeats are idempotent.
  - Dispositions: 1 root cause and 13 suppressed.
  - The status page shows no PII.
- **The crew closes the WO; the outage waits for telemetry.** It resolves at 5 h 00 min, and 8
  business credits of $2.76 are issued.
- **Ring open:** degraded, with a P2 and no notices. A second cut isolates a node and becomes
  an outage. The first repair resolves it before the crew starts: the P1 is cancelled and
  removed from the run sheet, and the incident returns to ring-open, then closes.
- **Access sector down (3 of 4 radios): outage for those 3 only.** It resolves after 30 min and
  the visit is cancelled.
- **One member radio:** pending at 11 min, P3 at 32 min, then self-cleared. A seasonal home's
  radio is ignored.
- **A hop flapping in 20 s drops:** damped into one degraded incident, closed after 15 min
  stable.
- **Solar power:**
  - A site at 60% SOC falling 2.5%/h is forecast to cut off at 08:00, before the sun, and gets
    a proactive P2.
  - A second site recovers in sunshine and its visit is cancelled.
  - The first site dies: the outage adopts its crew as a P1, and the cause reads power loss
    (battery exhausted).
- **26 h outage:** residential 2-day credits, $19.13 across 3 members, posted to
  `account_credits`.
- Head-end loss is degraded (the other head-end carries the lake). Webhook bearer auth, 87
  Prometheus targets, the board and the dry-run sender all work.
- KPIs: MTTR, member-minutes lost, credits.

The dispatch (43) and billing + FreeRADIUS (46) suites still pass after the shared
`dispatch_outage()` refactor.

## 8. Next steps
- Close the ring (§2): run the path survey on the five hops, dual-home HE-NW, and decide on
  the remaining N11 and N05 cut nodes.
- Stand up Prometheus + Alertmanager with the rules this service expects: `NodeDown` (ICMP/BFD
  from both head-ends), `LinkDown` (ifOperStatus), `CPEDown` (controller API), and
  `MainsFail` / `OnBattery` / `BatteryLow`. Feed charge-controller SOC to `/telemetry/power`.
- Choose the SMS/email provider (doc 13) and replace the dry-run sender.
- Run the status page on separate hosting; add planned-maintenance windows.
