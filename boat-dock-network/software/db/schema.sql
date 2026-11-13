-- DockOS core schema (PostGIS) — planning skeleton, v0.1
-- Boat Dock Network. See docs/14-software-architecture.md and docs/05-gis-plan.md.
--
-- This is a starting DDL for the single source of truth. It is intentionally
-- pragmatic (not fully normalized) so a small team can run with it, and is meant to
-- evolve. Geometry SRID 4326 for web interop; reproject for measurement as needed.
--
-- Prereqs: CREATE EXTENSION postgis; (and optionally timescaledb for device_metrics)

CREATE EXTENSION IF NOT EXISTS postgis;
-- CREATE EXTENSION IF NOT EXISTS timescaledb;  -- optional, for device_metrics

-- ---------------------------------------------------------------------------
-- Enums / reference
-- ---------------------------------------------------------------------------
CREATE TYPE node_tier      AS ENUM ('T0','T1','T2','T3');
CREATE TYPE node_status    AS ENUM ('candidate','permitted','built','live','retired');
CREATE TYPE medium_type    AS ENUM ('fiber','wireless_nlos','wireless_ptmp','unserved_candidate');
CREATE TYPE svc_status     AS ENUM ('not_passed','passed','presale','active','suspended','churned');
CREATE TYPE power_type      AS ENUM ('grid','grid_ups','solar_battery','poe');
CREATE TYPE wo_status      AS ENUM ('draft','permitting','released','scheduled','in_progress','asbuilt','closed','cancelled');
CREATE TYPE permit_status  AS ENUM ('identified','applied','approved','denied','not_required');

-- ---------------------------------------------------------------------------
-- GIS / OSP inventory
-- ---------------------------------------------------------------------------
CREATE TABLE zones (
    zone_id     text PRIMARY KEY,          -- e.g. Z-RB
    name        text NOT NULL,
    phase       int,                        -- build phase (doc 15)
    status      text DEFAULT 'planned',
    geom        geometry(MultiPolygon,4326)
);

CREATE TABLE nodes (
    node_id       text PRIMARY KEY,         -- e.g. BDN-RockyBranch-T2-01
    zone_id       text REFERENCES zones(zone_id),
    tier          node_tier NOT NULL,
    status        node_status NOT NULL DEFAULT 'candidate',
    power         power_type,
    host_property boolean DEFAULT false,    -- host-node site?
    host_customer_id bigint,                -- FK set after customers exists
    elevation_ft  numeric,
    asbuilt_ref   text,
    notes         text,
    geom          geometry(Point,4326)
);
CREATE INDEX ON nodes USING gist (geom);

CREATE TABLE node_equipment (
    id           bigserial PRIMARY KEY,
    node_id      text REFERENCES nodes(node_id),
    category     text,                       -- radio|optics|switch|ups|solar...
    make         text, model text, serial text,
    install_date date,
    wo_id        bigint,                     -- FK to work_orders
    status       text DEFAULT 'active'       -- active|spare|failed|removed
);

CREATE TABLE links (
    link_id       text PRIMARY KEY,
    a_node        text REFERENCES nodes(node_id),
    b_node        text REFERENCES nodes(node_id),
    band          text,                       -- 6GHz|11GHz|60GHz|CBRS|fiber...
    licensed      boolean DEFAULT false,
    capacity_mbps int,
    los_status    text,                       -- LOS|nLOS|blocked
    fresnel_ok    boolean,
    fade_margin_db numeric,
    pathcalc_ref  text,
    geom          geometry(LineString,4326)
);
CREATE INDEX ON links USING gist (geom);

CREATE TABLE service_addresses (
    address_id    bigserial PRIMARY KEY,
    parcel_id     text,
    address       text,
    owner_name    text,
    building_type text,                       -- home|business|marina|resort|dock
    occupancy     text,                       -- year_round|seasonal
    zone_id       text REFERENCES zones(zone_id),
    serviceability svc_status DEFAULT 'not_passed',
    medium        medium_type,
    assigned_node text REFERENCES nodes(node_id),
    demand_flag   boolean DEFAULT false,      -- expressed pre-sale interest
    dock_present  boolean,
    boat_reachable boolean,
    launch_ramp   text,
    customer_id   bigint,
    geom          geometry(Point,4326)
);
CREATE INDEX ON service_addresses USING gist (geom);

CREATE TABLE poles (
    pole_id      text PRIMARY KEY,
    owner        text,                        -- Ozarks|Carroll|SWEPCO
    make_ready   text,                        -- none|pending|complete
    permit_ref   text,
    geom         geometry(Point,4326)
);

CREATE TABLE fiber_cables (
    cable_id     text PRIMARY KEY,
    kind         text,                         -- adss|armored|microduct|subaqueous
    count        int,
    zone_id      text REFERENCES zones(zone_id),
    wo_id        bigint,
    geom         geometry(LineString,4326)
);
CREATE INDEX ON fiber_cables USING gist (geom);

CREATE TABLE drops (
    drop_id      bigserial PRIMARY KEY,
    address_id   bigint REFERENCES service_addresses(address_id),
    kind         text,                         -- aerial|underground
    length_ft    numeric,
    wo_id        bigint,
    geom         geometry(LineString,4326)
);

CREATE TABLE cpe (
    cpe_id       bigserial PRIMARY KEY,
    address_id   bigint REFERENCES service_addresses(address_id),
    kind         text,                         -- nlos|ptmp|ont
    make text, model text, serial text,
    node_id      text REFERENCES nodes(node_id),
    status       text DEFAULT 'active'
);

-- ---------------------------------------------------------------------------
-- Customers / billing
-- ---------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id  bigserial PRIMARY KEY,
    name         text NOT NULL,
    email text, phone text,
    address_id   bigint REFERENCES service_addresses(address_id),
    created_at   timestamptz DEFAULT now()
);

CREATE TABLE plans (
    plan_id      text PRIMARY KEY,            -- cove|shoreline|deepwater|biz...
    name         text, down_mbps int, up_mbps int,
    monthly_usd  numeric, is_business boolean DEFAULT false
);

CREATE TABLE subscriptions (
    sub_id       bigserial PRIMARY KEY,
    customer_id  bigint REFERENCES customers(customer_id),
    plan_id      text REFERENCES plans(plan_id),
    status       text DEFAULT 'active',        -- active|suspended|paused|cancelled
    start_date date, end_date date
);

CREATE TABLE host_node_agreements (
    id           bigserial PRIMARY KEY,
    customer_id  bigint REFERENCES customers(customer_id),
    node_id      text REFERENCES nodes(node_id),
    tier_hosted  node_tier,
    monthly_credit_usd numeric,
    access_terms text, easement_ref text,
    start_date date, end_date date
);

CREATE TABLE invoices (
    invoice_id   bigserial PRIMARY KEY,
    customer_id  bigint REFERENCES customers(customer_id),
    period       daterange, amount_usd numeric,
    status       text DEFAULT 'open', issued_at timestamptz DEFAULT now()
);

CREATE TABLE payments (
    payment_id   bigserial PRIMARY KEY,
    invoice_id   bigint REFERENCES invoices(invoice_id),
    amount_usd   numeric, method text, ref text, paid_at timestamptz
);

-- ---------------------------------------------------------------------------
-- Work orders / dispatch / outages
-- ---------------------------------------------------------------------------
CREATE TABLE work_orders (
    wo_id        bigserial PRIMARY KEY,
    wo_type      text NOT NULL,               -- matches data/bom/wo-*.csv kit
    status       wo_status DEFAULT 'draft',
    zone_id      text REFERENCES zones(zone_id),
    node_id      text REFERENCES nodes(node_id),
    address_id   bigint REFERENCES service_addresses(address_id),
    link_id      text REFERENCES links(link_id),
    params       jsonb,                        -- LEN_FT, N_SECTORS, mast height...
    scheduled_for date,
    assigned_crew text,
    geom         geometry(Geometry,4326),
    created_at   timestamptz DEFAULT now()
);

CREATE TABLE work_order_items (
    id           bigserial PRIMARY KEY,
    wo_id        bigint REFERENCES work_orders(wo_id),
    sku          text, category text, spec text,
    qty          numeric, unit text, unit_cost_usd numeric,
    consumed     boolean DEFAULT false
);

CREATE TABLE field_visits (
    id           bigserial PRIMARY KEY,
    wo_id        bigint REFERENCES work_orders(wo_id),
    crew         text, started_at timestamptz, ended_at timestamptz,
    launch_ramp  text, gps_track geometry(LineString,4326),
    photos       jsonb, signoff text
);

CREATE TABLE outages (
    outage_id    bigserial PRIMARY KEY,
    started_at   timestamptz DEFAULT now(), resolved_at timestamptz,
    root_node    text REFERENCES nodes(node_id),
    impacted_customers int,
    impact_polygon geometry(MultiPolygon,4326),
    status       text DEFAULT 'open', wo_id bigint REFERENCES work_orders(wo_id)
);

-- ---------------------------------------------------------------------------
-- Procurement
-- ---------------------------------------------------------------------------
CREATE TABLE vendors ( vendor_id bigserial PRIMARY KEY, name text, category text, contact text );
CREATE TABLE skus (
    sku          text PRIMARY KEY, description text, category text,
    unit         text, standard_cost_usd numeric,
    vendor_primary text, vendor_alt text,
    serialized   boolean DEFAULT false, baba_compliant boolean, reorder_point numeric
);
CREATE TABLE inventory (
    id bigserial PRIMARY KEY, sku text REFERENCES skus(sku),
    location text,                              -- warehouse|zone cache|boat
    qty_on_hand numeric, qty_reserved numeric DEFAULT 0
);
CREATE TABLE purchase_orders (
    po_id bigserial PRIMARY KEY, vendor_id bigint REFERENCES vendors(vendor_id),
    status text DEFAULT 'draft', grant_program text, created_at timestamptz DEFAULT now()
);
CREATE TABLE po_lines (
    id bigserial PRIMARY KEY, po_id bigint REFERENCES purchase_orders(po_id),
    sku text REFERENCES skus(sku), qty numeric, unit_cost_usd numeric, wo_id bigint
);
CREATE TABLE assets (
    asset_id bigserial PRIMARY KEY, sku text, serial text,
    node_id text REFERENCES nodes(node_id), cost_basis_usd numeric,
    in_service_date date, asset_class text, grant_program text
);

-- ---------------------------------------------------------------------------
-- NOC / monitoring
-- ---------------------------------------------------------------------------
CREATE TABLE devices (
    device_id bigserial PRIMARY KEY, node_id text REFERENCES nodes(node_id),
    mgmt_ip inet, kind text, make text, model text, snmp_community text
);
CREATE TABLE device_metrics (
    device_id bigint, ts timestamptz, metric text, value double precision
);
-- SELECT create_hypertable('device_metrics','ts');  -- if timescaledb
CREATE TABLE alerts (
    alert_id bigserial PRIMARY KEY, device_id bigint, severity text,
    message text, opened_at timestamptz DEFAULT now(), closed_at timestamptz
);

-- ---------------------------------------------------------------------------
-- Permits / compliance / grants
-- ---------------------------------------------------------------------------
CREATE TABLE permits (
    permit_id bigserial PRIMARY KEY,
    kind text,                                  -- usace|ar 811|ardot|pole|faa_asr|county_row
    status permit_status DEFAULT 'identified',
    wo_id bigint REFERENCES work_orders(wo_id),
    node_id text REFERENCES nodes(node_id),
    ref text, filed_at date, approved_at date, geom geometry(Geometry,4326)
);
CREATE TABLE permit_rules (
    id bigserial PRIMARY KEY, wo_type text, condition_sql text, requires_permit text, note text
);
CREATE TABLE grant_opportunities (
    id bigserial PRIMARY KEY, program text, agency text, deadline date,
    eligible_zones text[], ask_usd numeric, match_required_usd numeric,
    status text DEFAULT 'watching', owner text, next_action text, url text
);
CREATE TABLE grant_tasks (
    id bigserial PRIMARY KEY, opp_id bigint REFERENCES grant_opportunities(id),
    task text, due date, status text DEFAULT 'open'
);

-- End v0.1
