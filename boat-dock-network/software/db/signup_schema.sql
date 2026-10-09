-- DockOS signup / pre-sales / member-capital schema — v0.1
-- Production store for the public serviceability + member signup portal.
-- Load after schema.sql + governance_schema.sql.

CREATE TYPE signup_kind AS ENUM ('lead','reservation','member','founding','host');
CREATE TYPE pledge_status AS ENUM ('interested','committed','collected','refunded','cancelled');
-- the three member-capital instruments (doc 18 §1)
CREATE TYPE pledge_kind AS ENUM ('reservation_deposit','membership_share','founding_capital');
-- lifecycle of a per-zone capital campaign
CREATE TYPE campaign_status AS ENUM ('draft','open','gate_met','building','funded','cancelled');

-- every submission from the portal (lead capture + intent)
CREATE TABLE IF NOT EXISTS signups (
    signup_id   bigserial PRIMARY KEY,
    created_at  timestamptz DEFAULT now(),
    zone_id     text REFERENCES zones(zone_id),
    address     text,
    geom        geometry(Point,4326),        -- pin location, if provided
    name        text, email text, phone text,
    plan_id     text REFERENCES plans(plan_id),
    want_reservation boolean DEFAULT false,
    want_member      boolean DEFAULT false,
    want_founding    boolean DEFAULT false,
    want_host        boolean DEFAULT false,
    source      text DEFAULT 'portal',
    consent_ts  timestamptz,                 -- explicit consent to store contact info
    notes       text
);
CREATE INDEX IF NOT EXISTS signups_zone_idx ON signups(zone_id);
CREATE INDEX IF NOT EXISTS signups_geom_idx ON signups USING gist(geom);

-- per-zone member-capital campaign (doc 18 §3): the build-gate lives here
CREATE TABLE IF NOT EXISTS capital_campaigns (
    campaign_id     bigserial PRIMARY KEY,
    zone_id         text UNIQUE REFERENCES zones(zone_id),
    status          campaign_status DEFAULT 'draft',
    premises        integer,                  -- addressable premises in the zone (from GIS)
    -- build-gate dials (doc 18 §3); defaults match the doc
    reservation_pct_target numeric DEFAULT 0.25,   -- reservations >= 25% of premises
    gate_dollars_per_premise numeric DEFAULT 75,   -- capital >= premises * $75
    opened_at       timestamptz,
    gate_met_at     timestamptz,
    building_at     timestamptz,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS capital_campaigns_status_idx ON capital_campaigns(status);

-- pre-sale deposits + member-capital pledges (the grant-free funding engine)
CREATE TABLE IF NOT EXISTS pledges (
    pledge_id   bigserial PRIMARY KEY,
    signup_id   bigint REFERENCES signups(signup_id),
    customer_id bigint REFERENCES customers(customer_id),
    campaign_id bigint REFERENCES capital_campaigns(campaign_id),
    kind        pledge_kind,                  -- reservation_deposit|membership_share|founding_capital
    amount_usd  numeric NOT NULL CHECK (amount_usd >= 0),
    status      pledge_status DEFAULT 'interested',
    refundable  boolean DEFAULT true,
    zone_id     text REFERENCES zones(zone_id),
    -- Stripe money-flow references (doc 18 §4) — never store card data
    stripe_customer_id       text,
    stripe_checkout_session  text,
    stripe_payment_intent    text,
    stripe_charge_id         text,
    payment_ref text,                         -- generic escrow/other reference
    collected_at timestamptz,                 -- webhook: funds cleared to escrow
    refunded_at  timestamptz,
    created_at  timestamptz DEFAULT now(),
    updated_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pledges_zone_idx ON pledges(zone_id);
CREATE INDEX IF NOT EXISTS pledges_campaign_idx ON pledges(campaign_id);
CREATE INDEX IF NOT EXISTS pledges_status_idx ON pledges(status);

-- one row per member share held (co-op equity; refundable on exit) — doc 18 §1
CREATE TABLE IF NOT EXISTS member_shares (
    share_id    bigserial PRIMARY KEY,
    member_id   bigint REFERENCES members(member_id),
    pledge_id   bigint REFERENCES pledges(pledge_id),
    amount_usd  numeric NOT NULL DEFAULT 200,
    issued_at   timestamptz DEFAULT now(),
    redeemed_at timestamptz,                  -- set when returned on member exit
    notes       text
);
CREATE INDEX IF NOT EXISTS member_shares_member_idx ON member_shares(member_id);

-- per-zone demand rollup (materialized view or refreshed table) for gating builds
CREATE OR REPLACE VIEW zone_demand AS
SELECT z.zone_id, z.name,
  count(s.*)                                   AS leads,
  count(s.*) FILTER (WHERE s.want_reservation) AS reservations,
  count(s.*) FILTER (WHERE s.want_member)      AS members,
  count(s.*) FILTER (WHERE s.want_founding)    AS founding,
  count(s.*) FILTER (WHERE s.want_host)        AS host_offers,
  coalesce(sum(p.amount_usd) FILTER (WHERE p.status IN ('committed','collected')),0) AS capital_committed_usd
FROM zones z
LEFT JOIN signups s ON s.zone_id = z.zone_id
LEFT JOIN pledges p ON p.zone_id = z.zone_id
GROUP BY z.zone_id, z.name;

-- Campaign cockpit rollup (doc 18 §3/§5): per-zone capital vs the build-gate,
-- reservations vs the demand target, and whether both gates clear.
CREATE OR REPLACE VIEW campaign_progress AS
WITH pl AS (
  SELECT zone_id,
    count(*) FILTER (WHERE kind='reservation_deposit'
                      AND status IN ('committed','collected'))      AS reservation_count,
    coalesce(sum(amount_usd) FILTER (WHERE status IN ('committed','collected')),0)
                                                                    AS capital_committed_usd,
    coalesce(sum(amount_usd) FILTER (WHERE status='collected'),0)   AS capital_collected_usd,
    coalesce(sum(amount_usd) FILTER (WHERE kind='reservation_deposit'
                      AND status IN ('committed','collected')),0)   AS deposits_usd,
    coalesce(sum(amount_usd) FILTER (WHERE kind='membership_share'
                      AND status IN ('committed','collected')),0)   AS shares_usd,
    coalesce(sum(amount_usd) FILTER (WHERE kind='founding_capital'
                      AND status IN ('committed','collected')),0)   AS founding_usd
  FROM pledges GROUP BY zone_id
)
SELECT c.campaign_id, c.zone_id, z.name, c.status,
  c.premises,
  ceil(c.premises * c.reservation_pct_target)::int          AS reservation_target,
  coalesce(pl.reservation_count,0)                          AS reservation_count,
  (c.premises * c.gate_dollars_per_premise)::numeric        AS gate_target_usd,
  coalesce(pl.capital_committed_usd,0)                       AS capital_committed_usd,
  coalesce(pl.capital_collected_usd,0)                       AS capital_collected_usd,
  coalesce(pl.deposits_usd,0)   AS deposits_usd,
  coalesce(pl.shares_usd,0)     AS shares_usd,
  coalesce(pl.founding_usd,0)   AS founding_usd,
  (coalesce(pl.reservation_count,0) >= ceil(c.premises * c.reservation_pct_target))
                                                            AS demand_gate_met,
  (coalesce(pl.capital_committed_usd,0) >= c.premises * c.gate_dollars_per_premise)
                                                            AS capital_gate_met,
  (coalesce(pl.reservation_count,0) >= ceil(c.premises * c.reservation_pct_target)
   AND coalesce(pl.capital_committed_usd,0) >= c.premises * c.gate_dollars_per_premise)
                                                            AS build_gate_met
FROM capital_campaigns c
JOIN zones z ON z.zone_id = c.zone_id
LEFT JOIN pl ON pl.zone_id = c.zone_id;

-- Build-gate rule of thumb (see docs/13, doc 18 §3): release a zone to construction
-- when reservations >= 25% of zone premises AND capital_committed >= premises * $75.
-- campaign_progress.build_gate_met surfaces both; enforced in the app.
