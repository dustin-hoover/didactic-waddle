-- DockOS NOC: monitoring, correlation, outage management (doc 24)
-- Load after schema.sql, governance_schema.sql, signup_schema.sql, billing_schema.sql,
-- dispatch_schema.sql. Idempotent (IF NOT EXISTS / OR REPLACE).
--
-- Collectors (Prometheus + snmp/blackbox exporters, doc 21 §10) say what is DOWN; the NOC
-- decides what BROKE and who it affects from the topology (software/noc/topology.py):
--   Alertmanager webhook -> alerts -> element state (hold-down, flap damping)
--   -> reachability from the head-ends -> root cause(s) + dark nodes
--   -> outage (members, businesses, impact area) -> P1 boat/truck dispatch (doc 23)
--   -> member notices -> telemetry recovery -> resolve -> automatic credits (doc 22).

-- ---------------------------------------------------------------- topology
ALTER TABLE links
    ADD COLUMN IF NOT EXISTS kind  text,                 -- water_long | water_short | land | headend_fiber
    ADD COLUMN IF NOT EXISTS km    numeric,
    ADD COLUMN IF NOT EXISTS cost_usd numeric,
    ADD COLUMN IF NOT EXISTS planned boolean DEFAULT false;   -- redundancy-plan hop, not built yet

-- device inventory = the monitoring target list (GET /noc/targets emits Prometheus file_sd)
ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS name       text,
    ADD COLUMN IF NOT EXISTS role       text,            -- router | radio | olt | ups | solar_ctrl | cpe | ont
    ADD COLUMN IF NOT EXISTS link_id    text REFERENCES links(link_id),
    ADD COLUMN IF NOT EXISTS service_id bigint REFERENCES service_instances(service_id),
    ADD COLUMN IF NOT EXISTS active     boolean DEFAULT true;
CREATE UNIQUE INDEX IF NOT EXISTS devices_name_uidx ON devices(name);

-- ---------------------------------------------------------------- alerts
-- One row per Alertmanager alert instance (fingerprint + startsAt). The element label
-- (node / link / service) comes from relabeling against the device inventory.
ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS fingerprint  text,
    ADD COLUMN IF NOT EXISTS alertname    text,
    ADD COLUMN IF NOT EXISTS element_kind text,          -- node | link | service | site
    ADD COLUMN IF NOT EXISTS element      text,          -- node_id | link_id | service_id
    ADD COLUMN IF NOT EXISTS labels       jsonb DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS annotations  jsonb DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS status       text DEFAULT 'firing',   -- firing | resolved
    ADD COLUMN IF NOT EXISTS starts_at    timestamptz,
    ADD COLUMN IF NOT EXISTS ends_at      timestamptz,
    ADD COLUMN IF NOT EXISTS last_seen    timestamptz DEFAULT now(),
    ADD COLUMN IF NOT EXISTS disposition  text,          -- root_cause | suppressed | ring_open | ticket | ignored_inactive | flapping | info
    ADD COLUMN IF NOT EXISTS outage_id    bigint REFERENCES outages(outage_id);
CREATE UNIQUE INDEX IF NOT EXISTS alerts_fp_start_uidx ON alerts(fingerprint, starts_at);
CREATE INDEX IF NOT EXISTS alerts_element_idx ON alerts(element_kind, element, status);

-- ---------------------------------------------------------------- outages / incidents
-- kind: outage   = members dark (isolation, dead node, dead sector) -> notify + credit
--       degraded = redundancy lost, nobody dark (ring open, flapping element) -> P2, no notice
--       power    = a solar/battery site forecast to go dark -> proactive P2 before it does
ALTER TABLE outages
    ADD COLUMN IF NOT EXISTS kind              text DEFAULT 'outage',
    ADD COLUMN IF NOT EXISTS cause             text,          -- member-facing (status page, notices)
    ADD COLUMN IF NOT EXISTS detail            text,          -- NOC-facing root cause
    ADD COLUMN IF NOT EXISTS root_elements     text[],
    ADD COLUMN IF NOT EXISTS dark_nodes        text[],
    ADD COLUMN IF NOT EXISTS zones             text[],
    ADD COLUMN IF NOT EXISTS impacted_services int,
    ADD COLUMN IF NOT EXISTS impacted_business int,
    ADD COLUMN IF NOT EXISTS detected_at       timestamptz,
    ADD COLUMN IF NOT EXISTS eta               timestamptz,   -- member-facing restore estimate
    ADD COLUMN IF NOT EXISTS field_fixed_at    timestamptz,   -- crew says fixed; telemetry confirms
    ADD COLUMN IF NOT EXISTS noc_managed       boolean DEFAULT false,
    ADD COLUMN IF NOT EXISTS credited_at       timestamptz,
    ADD COLUMN IF NOT EXISTS credits_usd       numeric(12,2),
    ADD COLUMN IF NOT EXISTS updated_at        timestamptz DEFAULT now();
CREATE INDEX IF NOT EXISTS outages_open_idx ON outages(status) WHERE status = 'open';

-- who was dark (active services only; seasonal holds and suspended services are not impacted)
CREATE TABLE IF NOT EXISTS outage_services (
    outage_id   bigint NOT NULL REFERENCES outages(outage_id),
    service_id  bigint NOT NULL REFERENCES service_instances(service_id),
    customer_id bigint NOT NULL REFERENCES customers(customer_id),
    node_id     text,
    is_business boolean NOT NULL DEFAULT false,
    monthly_usd numeric(12,2),
    added_at    timestamptz DEFAULT now(),
    credit_usd  numeric(12,2),
    PRIMARY KEY (outage_id, service_id)
);

-- member notices (dry-run adapters by default; the sender marks them sent)
CREATE TABLE IF NOT EXISTS notifications (
    notification_id bigserial PRIMARY KEY,
    customer_id     bigint REFERENCES customers(customer_id),
    outage_id       bigint REFERENCES outages(outage_id),
    template        text NOT NULL,          -- outage_opened | outage_eta | outage_resolved
    channel         text NOT NULL,          -- sms | email
    subject         text,
    body            text NOT NULL,
    status          text NOT NULL DEFAULT 'queued',   -- queued | sent | failed | suppressed
    created_at      timestamptz DEFAULT now(),
    sent_at         timestamptz,
    UNIQUE (customer_id, outage_id, template, channel)
);

-- ---------------------------------------------------------------- site power (T3 solar/battery)
CREATE TABLE IF NOT EXISTS site_power (
    node_id  text NOT NULL REFERENCES nodes(node_id),
    ts       timestamptz NOT NULL,
    soc_pct  numeric,          -- battery state of charge
    load_w   numeric,
    pv_w     numeric,
    PRIMARY KEY (node_id, ts)
);

-- ---------------------------------------------------------------- views
-- Public status page: per zone, no member data beyond an aggregate count.
CREATE OR REPLACE VIEW status_zones AS
WITH o AS (SELECT ou.outage_id, ou.started_at, ou.eta, ou.cause, unnest(ou.zones) AS zone_id
           FROM outages ou WHERE ou.status = 'open' AND ou.kind = 'outage'),
     m AS (SELECT n.zone_id, count(DISTINCT s.service_id) AS members
           FROM outage_services s
           JOIN outages ou ON ou.outage_id = s.outage_id AND ou.status = 'open' AND ou.kind = 'outage'
           JOIN nodes n ON n.node_id = s.node_id GROUP BY n.zone_id)
SELECT z.zone_id, z.name,
       CASE WHEN count(o.outage_id) = 0 THEN 'operational' ELSE 'outage' END AS state,
       min(o.started_at) AS since, max(o.eta) AS eta, string_agg(DISTINCT o.cause, '; ') AS cause,
       COALESCE(max(m.members), 0) AS members_affected
FROM zones z LEFT JOIN o ON o.zone_id = z.zone_id LEFT JOIN m ON m.zone_id = z.zone_id
GROUP BY z.zone_id, z.name ORDER BY z.zone_id;

-- NOC board: everything open, worst first
CREATE OR REPLACE VIEW noc_board AS
SELECT o.outage_id, o.kind, o.status, o.cause, o.root_elements, o.dark_nodes, o.zones,
       o.impacted_services, o.impacted_business, o.started_at, o.detected_at, o.eta,
       o.wo_id, w.status AS wo_status, w.assigned_crew, w.travel_mode, w.eta AS crew_eta, o.detail
FROM outages o LEFT JOIN work_orders w ON w.wo_id = o.wo_id
WHERE o.status = 'open'
ORDER BY (o.kind = 'outage') DESC, o.impacted_services DESC NULLS LAST, o.started_at;

-- reliability KPIs (doc 21 §8 targets)
CREATE OR REPLACE VIEW outage_kpis AS
SELECT date_trunc('month', started_at) AS month,
       count(*) FILTER (WHERE kind = 'outage')                         AS outages,
       count(*) FILTER (WHERE kind = 'degraded')                       AS degraded,
       round(avg(extract(epoch FROM resolved_at - started_at) / 60)
             FILTER (WHERE kind = 'outage' AND resolved_at IS NOT NULL), 1) AS mttr_min,
       sum(impacted_services * extract(epoch FROM resolved_at - started_at) / 60)
             FILTER (WHERE kind = 'outage' AND resolved_at IS NOT NULL) AS member_minutes_lost,
       sum(credits_usd)                                                 AS credits_usd
FROM outages GROUP BY 1 ORDER BY 1;
