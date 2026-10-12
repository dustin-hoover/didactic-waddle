-- DockOS billing + provisioning + RADIUS schema — v0.1  (doc 22)
-- Load after schema.sql, governance_schema.sql, signup_schema.sql.
--
-- Design rule ("one truth", doc 14 §5): RADIUS authorization is a PURE FUNCTION of
-- billing/service state. FreeRADIUS's authorize tables (radcheck, radreply,
-- radusergroup, radgroupcheck, radgroupreply) are VIEWS over service_instances +
-- plans, so there is no sync job that can drift: suspend a service in billing and the
-- very next authentication lands in the walled garden. Stock FreeRADIUS 3.2 rlm_sql
-- (postgresql dialect) queries work unmodified. Accounting (radacct/radpostauth) and
-- the NAS/CoA registry (nas) are real tables with FreeRADIUS's own DDL.

CREATE TYPE service_state AS ENUM ('pending','provisioned','active','suspended','terminated');
CREATE TYPE access_kind   AS ENUM ('ipoe_mac','pppoe','ont_serial');
CREATE TYPE prov_action   AS ENUM ('activate','suspend','resume','change_plan','terminate');
CREATE TYPE job_status    AS ENUM ('queued','running','done','failed');

-- ---------------------------------------------------------------- plans / catalog
ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS radius_group   text,                 -- RADIUS group = QoS profile
    ADD COLUMN IF NOT EXISTS priority_class text DEFAULT 'standard', -- doc 21 §9 (business = CIR)
    ADD COLUMN IF NOT EXISTS active         boolean DEFAULT true;

-- Plan catalog = the portal's plans (doc 21 §6.3). Edit here; RADIUS follows automatically.
INSERT INTO plans (plan_id, name, down_mbps, up_mbps, monthly_usd, is_business, radius_group, priority_class) VALUES
  ('cove',       'Cove',              300,  300,  69, false, 'plan_cove',       'standard'),
  ('shoreline',  'Shoreline',        1000, 1000,  89, false, 'plan_shoreline',  'standard'),
  ('deepwater',  'Deep Water',       2000, 2000, 129, false, 'plan_deepwater',  'standard'),
  ('deepwater5', 'Deep Water 5G',    5000, 5000, 199, false, 'plan_deepwater5', 'standard'),
  ('business',   'Business / Marina',1000, 1000, 199, true,  'plan_business',   'business')
ON CONFLICT (plan_id) DO UPDATE SET
  name=EXCLUDED.name, down_mbps=EXCLUDED.down_mbps, up_mbps=EXCLUDED.up_mbps,
  monthly_usd=EXCLUDED.monthly_usd, is_business=EXCLUDED.is_business,
  radius_group=EXCLUDED.radius_group, priority_class=EXCLUDED.priority_class;

-- ---------------------------------------------------------------- subscriptions
-- status: pending | active | suspended | cancelled
ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS address_id         bigint REFERENCES service_addresses(address_id),
    ADD COLUMN IF NOT EXISTS stripe_customer_id text,
    ADD COLUMN IF NOT EXISTS created_at         timestamptz DEFAULT now();

-- ---------------------------------------------------------------- service instances
-- One provisioned access service per subscription: the thing RADIUS authenticates.
CREATE TABLE IF NOT EXISTS service_instances (
    service_id      bigserial PRIMARY KEY,
    sub_id          bigint NOT NULL REFERENCES subscriptions(sub_id),
    customer_id     bigint NOT NULL REFERENCES customers(customer_id),
    address_id      bigint REFERENCES service_addresses(address_id),
    medium          medium_type,
    node_id         text   REFERENCES nodes(node_id),
    cpe_id          bigint REFERENCES cpe(cpe_id),
    access          access_kind NOT NULL,
    -- RADIUS credential. ipoe_mac: lowercase dash MAC (aa-bb-cc-dd-ee-ff) as user+pass;
    -- ont_serial: ONT serial; pppoe: generated user/pass. Cleartext is required for
    -- CHAP/MAC-auth — restrict this table to the billing + radius DB roles (doc 21 §11).
    radius_username text NOT NULL UNIQUE,
    radius_password text NOT NULL,
    s_vlan int, c_vlan int,                        -- QinQ per zone/sub (doc 21 §4)
    ipv6_pd         cidr,                          -- delegated /56 (doc 21 §3)
    ipv4_static     inet,                          -- business/marina static only
    state           service_state NOT NULL DEFAULT 'pending',
    suspend_reason  text,                          -- nonpay | member_request | abuse
    provisioned_at  timestamptz,
    activated_at    timestamptz,                   -- billing starts here
    suspended_at    timestamptz,
    terminated_at   timestamptz,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS service_instances_state_idx ON service_instances(state);
CREATE INDEX IF NOT EXISTS service_instances_sub_idx   ON service_instances(sub_id);
-- a delegated prefix belongs to at most one live service; reusable after termination
-- (the allocator also quarantines released prefixes for 90 days)
CREATE UNIQUE INDEX IF NOT EXISTS service_instances_pd_uidx
    ON service_instances(ipv6_pd) WHERE ipv6_pd IS NOT NULL AND state <> 'terminated';

-- ---------------------------------------------------------------- invoicing
-- invoices.status: open | paid | void   (past-due is derived from due_date)
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS sub_id            bigint REFERENCES subscriptions(sub_id),
    ADD COLUMN IF NOT EXISTS due_date          date,
    ADD COLUMN IF NOT EXISTS subtotal_usd      numeric(12,2),
    ADD COLUMN IF NOT EXISTS credits_usd       numeric(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tax_usd           numeric(12,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_usd         numeric(12,2),
    ADD COLUMN IF NOT EXISTS stripe_invoice_id text,
    ADD COLUMN IF NOT EXISTS paid_at           timestamptz;
-- idempotent billing runs: one invoice per subscription per period
CREATE UNIQUE INDEX IF NOT EXISTS invoices_sub_period_uidx ON invoices(sub_id, period);

CREATE TABLE IF NOT EXISTS invoice_lines (
    line_id     bigserial PRIMARY KEY,
    invoice_id  bigint NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    -- service | equipment | install | credit_deposit | credit_host | adjustment | late_fee
    kind        text NOT NULL,
    description text,
    quantity    numeric DEFAULT 1,
    unit_usd    numeric(12,2),
    amount_usd  numeric(12,2) NOT NULL,
    -- Internet access is exempt from state/local tax under the (Permanent) Internet
    -- Tax Freedom Act; equipment sales/rentals may be taxable — confirm with the CPA.
    taxable     boolean DEFAULT false,
    tax_usd     numeric(12,2) DEFAULT 0
);
CREATE INDEX IF NOT EXISTS invoice_lines_invoice_idx ON invoice_lines(invoice_id);

-- One-time charges (install, CPE/router sale, boat-roll for a customer-caused repair)
-- waiting for the next invoice; invoice_id is set when billed.
CREATE TABLE IF NOT EXISTS one_time_charges (
    charge_id   bigserial PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customers(customer_id),
    sub_id      bigint REFERENCES subscriptions(sub_id),
    kind        text NOT NULL,          -- install | equipment | boat_roll | adjustment
    description text,
    amount_usd  numeric(12,2) NOT NULL,
    taxable     boolean DEFAULT false,  -- equipment sales: yes (confirm with CPA)
    invoice_id  bigint REFERENCES invoices(invoice_id),
    created_at  timestamptz DEFAULT now()
);

-- Credits applied FIFO to future invoices: the doc 18 reservation deposit ($100,
-- credited to the first bill), goodwill/outage credits, etc. Host-node credits come
-- from host_node_agreements monthly and are added per invoice instead.
CREATE TABLE IF NOT EXISTS account_credits (
    credit_id        bigserial PRIMARY KEY,
    customer_id      bigint NOT NULL REFERENCES customers(customer_id),
    kind             text NOT NULL,        -- reservation_deposit | goodwill | outage | patronage
    amount_usd       numeric(12,2) NOT NULL CHECK (amount_usd > 0),
    remaining_usd    numeric(12,2) NOT NULL CHECK (remaining_usd >= 0),
    source_pledge_id bigint UNIQUE REFERENCES pledges(pledge_id),  -- never credit a deposit twice
    note             text,
    created_at       timestamptz DEFAULT now()
);

ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS customer_id           bigint REFERENCES customers(customer_id),
    ADD COLUMN IF NOT EXISTS stripe_payment_intent text UNIQUE,     -- webhook idempotency
    ADD COLUMN IF NOT EXISTS status                text DEFAULT 'succeeded';

-- ---------------------------------------------------------------- provisioning queue
-- Billing never touches devices directly: it enqueues jobs; the provisioning engine
-- (software/provisioning/engine.py) runs them against OLT / CPE / NAS (CoA) adapters.
CREATE TABLE IF NOT EXISTS provisioning_jobs (
    job_id      bigserial PRIMARY KEY,
    service_id  bigint NOT NULL REFERENCES service_instances(service_id),
    action      prov_action NOT NULL,
    status      job_status NOT NULL DEFAULT 'queued',
    payload     jsonb DEFAULT '{}'::jsonb,
    attempts    int DEFAULT 0,
    last_error  text,
    created_at  timestamptz DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS provisioning_jobs_queue_idx ON provisioning_jobs(status, created_at);

-- append-only audit trail of every billing / provisioning decision
CREATE TABLE IF NOT EXISTS billing_events (
    event_id    bigserial PRIMARY KEY,
    customer_id bigint REFERENCES customers(customer_id),
    sub_id      bigint REFERENCES subscriptions(sub_id),
    service_id  bigint REFERENCES service_instances(service_id),
    kind        text NOT NULL,     -- subscribed|activated|invoiced|paid|dunning_notice|suspended|resumed|terminated|credit
    detail      jsonb DEFAULT '{}'::jsonb,
    created_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS billing_events_customer_idx ON billing_events(customer_id, created_at);

-- ---------------------------------------------------------------- FreeRADIUS tables
-- Accounting, post-auth log, and NAS registry — DDL copied from FreeRADIUS 3.2.5
-- mods-config/sql/main/postgresql/schema.sql so stock queries.conf works as-is.
CREATE TABLE IF NOT EXISTS radacct (
    RadAcctId           bigserial PRIMARY KEY,
    AcctSessionId       text NOT NULL,
    AcctUniqueId        text NOT NULL UNIQUE,
    UserName            text,
    Realm               text,
    NASIPAddress        inet NOT NULL,
    NASPortId           text,
    NASPortType         text,
    AcctStartTime       timestamp with time zone,
    AcctUpdateTime      timestamp with time zone,
    AcctStopTime        timestamp with time zone,
    AcctInterval        bigint,
    AcctSessionTime     bigint,
    AcctAuthentic       text,
    ConnectInfo_start   text,
    ConnectInfo_stop    text,
    AcctInputOctets     bigint,
    AcctOutputOctets    bigint,
    CalledStationId     text,
    CallingStationId    text,
    AcctTerminateCause  text,
    ServiceType         text,
    FramedProtocol      text,
    FramedIPAddress     inet,
    FramedIPv6Address   inet,
    FramedIPv6Prefix    inet,
    FramedInterfaceId   text,
    DelegatedIPv6Prefix inet,
    Class               text
);
CREATE INDEX IF NOT EXISTS radacct_active_session_idx ON radacct (AcctUniqueId) WHERE AcctStopTime IS NULL;
CREATE INDEX IF NOT EXISTS radacct_bulk_close ON radacct (NASIPAddress, AcctStartTime) WHERE AcctStopTime IS NULL;
CREATE INDEX IF NOT EXISTS radacct_start_user_idx ON radacct (AcctStartTime, UserName);
CREATE INDEX IF NOT EXISTS radacct_class_idx ON radacct (Class);

CREATE TABLE IF NOT EXISTS radpostauth (
    id               bigserial PRIMARY KEY,
    username         text NOT NULL,
    pass             text,
    reply            text,
    CalledStationId  text,
    CallingStationId text,
    authdate         timestamp with time zone NOT NULL default now(),
    Class            text
);
CREATE INDEX IF NOT EXISTS radpostauth_username_idx ON radpostauth (username);

-- NAS/BNG registry: RADIUS clients + CoA/Disconnect targets (RFC 5176, port 3799)
CREATE TABLE IF NOT EXISTS nas (
    id          serial PRIMARY KEY,
    nasname     text NOT NULL,          -- NAS IP (or CIDR)
    shortname   text NOT NULL,
    type        text NOT NULL DEFAULT 'other',
    ports       integer,
    secret      text NOT NULL,
    server      text,
    community   text,
    description text
);

-- Extra/static group attributes (the walled garden, business extras). Per-plan rate
-- limits are DERIVED from `plans` in the radgroupreply view — no edits needed per plan.
CREATE TABLE IF NOT EXISTS radius_group_attrs (
    id        serial PRIMARY KEY,
    groupname text NOT NULL,
    attribute text NOT NULL,
    op        text NOT NULL DEFAULT ':=',
    value     text NOT NULL
);
INSERT INTO radius_group_attrs (groupname, attribute, op, value)
SELECT * FROM (VALUES
  ('suspended', 'Filter-Id',             ':=', 'walled-garden'),  -- BNG policy: portal + pay page only
  ('suspended', 'Mikrotik-Rate-Limit',   ':=', '1M/1M'),
  ('suspended', 'Acct-Interim-Interval', ':=', '300')
) v(g,a,o,val)
WHERE NOT EXISTS (SELECT 1 FROM radius_group_attrs WHERE groupname='suspended');

-- ---------------------------------------------------------------- RADIUS views
-- Who may authenticate: provisioned (tech turn-up/speed test), active, suspended
-- (walled garden so they can still reach the pay page). pending/terminated -> Reject.
CREATE OR REPLACE VIEW radcheck AS
SELECT si.service_id::int              AS id,
       si.radius_username              AS username,
       'Cleartext-Password'::text      AS attribute,
       ':='::text                      AS op,
       si.radius_password              AS value
FROM service_instances si
WHERE si.state IN ('provisioned','active','suspended');

-- Per-subscriber replies: delegated IPv6 prefix + static IPv4 where assigned.
CREATE OR REPLACE VIEW radreply AS
SELECT (si.service_id * 10 + 1)::int AS id, si.radius_username AS username,
       'Delegated-IPv6-Prefix'::text AS attribute, ':='::text AS op, si.ipv6_pd::text AS value
FROM service_instances si
WHERE si.state IN ('provisioned','active','suspended') AND si.ipv6_pd IS NOT NULL
UNION ALL
SELECT (si.service_id * 10 + 2)::int, si.radius_username,
       'Framed-IP-Address', ':=', host(si.ipv4_static)
FROM service_instances si
WHERE si.state IN ('provisioned','active') AND si.ipv4_static IS NOT NULL;

-- Group = the plan's QoS profile, or 'suspended' (walled garden).
CREATE OR REPLACE VIEW radusergroup AS
SELECT si.radius_username AS username,
       CASE WHEN si.state = 'suspended' THEN 'suspended' ELSE p.radius_group END AS groupname,
       1 AS priority
FROM service_instances si
JOIN subscriptions s ON s.sub_id = si.sub_id
JOIN plans p         ON p.plan_id = s.plan_id
WHERE si.state IN ('provisioned','active','suspended');

-- No group check items (all policy is in replies); empty but correctly shaped.
CREATE OR REPLACE VIEW radgroupcheck AS
SELECT NULL::int AS id, NULL::text AS groupname, NULL::text AS attribute,
       NULL::text AS op, NULL::text AS value
WHERE false;

-- Per-plan QoS derived from the catalog. Filter-Id (RFC 2865) names the BNG policy
-- (vendor-neutral: map it to a shaper/QoS policy on Juniper/Cisco/Nokia BNGs);
-- Mikrotik-Rate-Limit ("rx/tx" = up/down) drives MikroTik BNGs directly. WISPr
-- Bandwidth-Max-* is deliberately NOT used: it is a 32-bit bps integer and overflows
-- above ~4.29 Gbps (our 5G plan).
CREATE OR REPLACE VIEW radgroupreply AS
SELECT (row_number() OVER (ORDER BY groupname, ord))::int AS id,
       groupname, attribute, op, value
FROM (
  SELECT p.radius_group AS groupname, 1 AS ord, 'Filter-Id'::text AS attribute, ':='::text AS op,
         p.radius_group AS value
  FROM plans p WHERE p.active AND p.radius_group IS NOT NULL
  UNION ALL
  SELECT p.radius_group, 2, 'Mikrotik-Rate-Limit', ':=', p.up_mbps || 'M/' || p.down_mbps || 'M'
  FROM plans p WHERE p.active AND p.radius_group IS NOT NULL
  UNION ALL
  SELECT p.radius_group, 3, 'Acct-Interim-Interval', ':=', '300'
  FROM plans p WHERE p.active AND p.radius_group IS NOT NULL
  UNION ALL
  SELECT a.groupname, 100 + a.id, a.attribute, a.op, a.value FROM radius_group_attrs a
) g;

-- ---------------------------------------------------------------- reporting views
-- Receivables aging (dunning input, co-op accounting doc 09).
CREATE OR REPLACE VIEW ar_aging AS
SELECT i.invoice_id, i.customer_id, i.sub_id, i.total_usd, i.due_date,
       GREATEST(0, current_date - i.due_date) AS days_past_due,
       CASE WHEN current_date <= i.due_date      THEN 'current'
            WHEN current_date - i.due_date <= 30 THEN '1-30'
            WHEN current_date - i.due_date <= 60 THEN '31-60'
            ELSE '60+' END AS bucket
FROM invoices i
WHERE i.status = 'open' AND COALESCE(i.total_usd, 0) > 0;

-- Monthly usage per service from accounting (NOC capacity planning, fair-use review).
CREATE OR REPLACE VIEW usage_monthly AS
SELECT si.service_id, si.customer_id, date_trunc('month', r.acctstarttime)::date AS month,
       round(sum(COALESCE(r.acctinputoctets,0))  / 1e9, 3) AS upload_gb,
       round(sum(COALESCE(r.acctoutputoctets,0)) / 1e9, 3) AS download_gb,
       count(*) AS sessions
FROM radacct r JOIN service_instances si ON si.radius_username = r.username
GROUP BY si.service_id, si.customer_id, date_trunc('month', r.acctstarttime);

-- Least privilege (doc 21 §11) — run in the deploy script with real role names:
--   CREATE ROLE radius LOGIN PASSWORD '...';
--   GRANT SELECT ON radcheck, radreply, radusergroup, radgroupcheck, radgroupreply, nas TO radius;
--   GRANT SELECT, INSERT, UPDATE ON radacct, radpostauth TO radius;
--   GRANT USAGE ON SEQUENCE radacct_radacctid_seq, radpostauth_id_seq TO radius;
-- (Views run with the view owner's rights, so radius never sees service_instances directly.)
