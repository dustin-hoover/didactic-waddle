-- DockOS signup / pre-sales / member-capital schema — v0.1
-- Production store for the public serviceability + member signup portal.
-- Load after schema.sql + governance_schema.sql.

CREATE TYPE signup_kind AS ENUM ('lead','reservation','member','founding','host');
CREATE TYPE pledge_status AS ENUM ('interested','committed','collected','refunded','cancelled');

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

-- pre-sale deposits + member-capital pledges (the grant-free funding engine)
CREATE TABLE IF NOT EXISTS pledges (
    pledge_id   bigserial PRIMARY KEY,
    signup_id   bigint REFERENCES signups(signup_id),
    customer_id bigint REFERENCES customers(customer_id),
    kind        text,                         -- presale_deposit|membership_share|founding_capital
    amount_usd  numeric,
    status      pledge_status DEFAULT 'interested',
    refundable  boolean DEFAULT true,
    zone_id     text REFERENCES zones(zone_id),
    payment_ref text,                         -- Stripe/escrow reference
    created_at  timestamptz DEFAULT now(),
    updated_at  timestamptz DEFAULT now()
);

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

-- Build-gate rule of thumb (see docs/13): release a zone to construction when
-- reservations >= threshold (e.g. 25% of zone premises) AND capital_committed
-- covers that zone's connection CapEx. Enforced in the app, surfaced to members.
