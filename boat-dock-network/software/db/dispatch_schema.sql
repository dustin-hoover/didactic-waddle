-- DockOS dispatch + work-order engine schema — v0.1  (doc 23, DockOS steps 4-5)
-- Load after schema.sql, governance_schema.sql, signup_schema.sql, billing_schema.sql.

CREATE TYPE vehicle_kind AS ENUM ('boat','truck');
CREATE TYPE wo_priority  AS ENUM ('P1','P2','P3','P4');   -- P1 outage/business same-day ... P4 build

-- ---------------------------------------------------------------- fleet
CREATE TABLE IF NOT EXISTS yards (                -- ops yards / boat bases (doc 20: owned lakeside parcel)
    yard_id   text PRIMARY KEY,
    name      text NOT NULL,
    geom      geometry(Point,4326) NOT NULL,      -- the dock / launch point
    notes     text
);
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id text PRIMARY KEY,
    name       text,
    kind       vehicle_kind NOT NULL,
    boat_class text,                              -- center_console | jon | pontoon | barge (boats)
    yard_id    text REFERENCES yards(yard_id),
    status     text DEFAULT 'available'           -- available | maintenance | retired
);
CREATE TABLE IF NOT EXISTS crews (
    crew_id     text PRIMARY KEY,
    name        text NOT NULL,
    skills      text[] NOT NULL DEFAULT '{}',     -- install_wireless|install_fiber|splice|repair|survey|tower|marine_ops
    yard_id     text REFERENCES yards(yard_id),
    size        int  DEFAULT 2,                   -- buddy system (doc 07 safety)
    shift_start time DEFAULT '07:30',
    shift_hours numeric DEFAULT 9,
    active      boolean DEFAULT true
);
-- which vehicle a crew runs on a given day (dispatcher sets; planner defaults it)
CREATE TABLE IF NOT EXISTS crew_days (
    crew_id    text REFERENCES crews(crew_id),
    day        date,
    vehicle_id text REFERENCES vehicles(vehicle_id),
    PRIMARY KEY (crew_id, day)
);

-- ---------------------------------------------------------------- work orders
ALTER TABLE work_orders
    ADD COLUMN IF NOT EXISTS priority        wo_priority DEFAULT 'P3',
    ADD COLUMN IF NOT EXISTS service_id      bigint REFERENCES service_instances(service_id),
    ADD COLUMN IF NOT EXISTS outage_id       bigint REFERENCES outages(outage_id),
    ADD COLUMN IF NOT EXISTS sla_due         timestamptz,
    ADD COLUMN IF NOT EXISTS est_hours       numeric,
    ADD COLUMN IF NOT EXISTS required_skills text[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS requires_heavy  boolean DEFAULT false,     -- pontoon/barge or truck
    ADD COLUMN IF NOT EXISTS access_mode     text DEFAULT 'any',        -- any | boat_only | road_only
    ADD COLUMN IF NOT EXISTS vehicle_id      text REFERENCES vehicles(vehicle_id),
    ADD COLUMN IF NOT EXISTS route_seq       int,
    ADD COLUMN IF NOT EXISTS eta             timestamptz,
    ADD COLUMN IF NOT EXISTS travel_mode     text,                      -- boat | truck
    ADD COLUMN IF NOT EXISTS travel_min      numeric,
    ADD COLUMN IF NOT EXISTS captures        jsonb DEFAULT '{}'::jsonb, -- MAC/serial, speed test, RSSI, photos...
    ADD COLUMN IF NOT EXISTS blocked_reason  text,
    ADD COLUMN IF NOT EXISTS note            text,
    ADD COLUMN IF NOT EXISTS released_at     timestamptz,
    ADD COLUMN IF NOT EXISTS started_at      timestamptz,
    ADD COLUMN IF NOT EXISTS completed_at    timestamptz,
    ADD COLUMN IF NOT EXISTS closed_at       timestamptz;
CREATE INDEX IF NOT EXISTS work_orders_status_idx ON work_orders(status, priority);
CREATE INDEX IF NOT EXISTS work_orders_day_idx    ON work_orders(scheduled_for, assigned_crew);
-- at most one open install WO per service
CREATE UNIQUE INDEX IF NOT EXISTS work_orders_open_install_uidx ON work_orders(service_id)
    WHERE service_id IS NOT NULL AND status NOT IN ('closed','cancelled');

-- BOM lines: how much of each stocked line is reserved from the warehouse (released WO)
ALTER TABLE work_order_items
    ADD COLUMN IF NOT EXISTS stocked      boolean DEFAULT false,
    ADD COLUMN IF NOT EXISTS qty_reserved numeric DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS vendors_name_uidx ON vendors(name);
CREATE UNIQUE INDEX IF NOT EXISTS inventory_sku_loc_uidx ON inventory(sku, location);

-- Field event log. client_action_id makes offline replays from the crew PWA idempotent.
CREATE TABLE IF NOT EXISTS wo_events (
    event_id         bigserial PRIMARY KEY,
    wo_id            bigint REFERENCES work_orders(wo_id),
    kind             text NOT NULL,  -- created|released|shortfall|scheduled|arrived|started|captured|completed|closed|cant_complete|departed|note
    actor            text,
    client_action_id text UNIQUE,
    vehicle_kind     vehicle_kind,
    detail           jsonb DEFAULT '{}'::jsonb,
    geom             geometry(Point,4326),
    at               timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS wo_events_wo_idx ON wo_events(wo_id, at);

-- ---------------------------------------------------------------- day plans (run sheets)
CREATE TABLE IF NOT EXISTS dispatch_plans (
    day        date,
    crew_id    text REFERENCES crews(crew_id),
    vehicle_id text REFERENCES vehicles(vehicle_id),
    plan       jsonb NOT NULL,       -- ordered stops, legs (+ water route polylines), load list, weather
    created_at timestamptz DEFAULT now(),
    PRIMARY KEY (day, crew_id)
);
CREATE TABLE IF NOT EXISTS weather_calls (   -- NWS-based go/no-go per day (+ dispatcher override)
    day        date PRIMARY KEY,
    source     text,                  -- nws | override | unavailable
    data       jsonb NOT NULL,
    decided_at timestamptz DEFAULT now()
);

-- ---------------------------------------------------------------- measured dock turnaround
-- Minutes a stop costs beyond driving/boating and the job itself:
-- (started - arrived) + (departed - completed). The planner uses the measured median
-- per vehicle kind once there are enough samples (doc 23 §2: this decides boat vs truck).
CREATE OR REPLACE VIEW stop_turnaround AS
WITH ev AS (
  SELECT wo_id, vehicle_kind,
         min(at) FILTER (WHERE kind='arrived')   AS arrived,
         min(at) FILTER (WHERE kind='started')   AS started,
         max(at) FILTER (WHERE kind='completed') AS completed,
         max(at) FILTER (WHERE kind='departed')  AS departed
  FROM wo_events WHERE vehicle_kind IS NOT NULL
  GROUP BY wo_id, vehicle_kind
)
SELECT wo_id, vehicle_kind,
       extract(epoch FROM (started - arrived) + (departed - completed)) / 60.0 AS overhead_min,
       completed AS at
FROM ev
WHERE arrived IS NOT NULL AND started IS NOT NULL AND completed IS NOT NULL AND departed IS NOT NULL;

CREATE OR REPLACE VIEW turnaround_stats AS
SELECT vehicle_kind, count(*) AS stops,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY overhead_min) AS median_overhead_min
FROM stop_turnaround
WHERE at > now() - interval '60 days'
GROUP BY vehicle_kind;

-- Dispatcher board
CREATE OR REPLACE VIEW dispatch_board AS
SELECT w.wo_id, w.wo_type, w.priority, w.status, w.scheduled_for, w.assigned_crew, w.vehicle_id,
       w.route_seq, w.eta, w.travel_mode, w.travel_min, w.sla_due, w.blocked_reason,
       w.zone_id, sa.address, c.name AS customer, w.service_id, w.outage_id
FROM work_orders w
LEFT JOIN service_addresses sa ON sa.address_id = w.address_id
LEFT JOIN service_instances si ON si.service_id = w.service_id
LEFT JOIN customers c ON c.customer_id = si.customer_id;
