-- DockOS governance schema (WAKE units + cooperative voting) — v0.1
-- See docs/16-governance-and-tokenomics.md. Governance-only, non-transferable units.
-- Load after schema.sql (references customers).

CREATE TYPE wake_event AS ENUM ('accrual','host_bonus','forfeit','redistribute','adjust');
CREATE TYPE proposal_status AS ENUM ('draft','open','passed','failed','executed','withdrawn');

-- a member is a customer enrolled in the cooperative
CREATE TABLE IF NOT EXISTS members (
    member_id    bigserial PRIMARY KEY,
    customer_id  bigint REFERENCES customers(customer_id),
    joined_at    date NOT NULL,
    status       text DEFAULT 'active',        -- active|lapsed
    lapsed_at    date,
    is_host      boolean DEFAULT false,        -- hosts a node (1.5x accrual)
    delegate_to  bigint REFERENCES members(member_id)  -- liquid democracy (nullable)
);

-- append-only ledger of every WAKE event (source of truth)
CREATE TABLE IF NOT EXISTS wake_ledger (
    id         bigserial PRIMARY KEY,
    member_id  bigint REFERENCES members(member_id),
    event      wake_event NOT NULL,
    amount     numeric NOT NULL,               -- + accrual/bonus/redistribute, - forfeit
    period     date,                           -- accrual month
    note       text,
    created_at timestamptz DEFAULT now()
);

-- materialized balance (rebuilt from ledger)
CREATE TABLE IF NOT EXISTS wake_balances (
    member_id  bigint PRIMARY KEY REFERENCES members(member_id),
    units      numeric NOT NULL DEFAULT 0,
    updated_at timestamptz DEFAULT now()
);

-- the Commons Pool: forfeited units awaiting redistribution
CREATE TABLE IF NOT EXISTS commons_pool (
    id         int PRIMARY KEY DEFAULT 1,
    units      numeric NOT NULL DEFAULT 0,
    updated_at timestamptz DEFAULT now(),
    CONSTRAINT one_row CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id  bigserial PRIMARY KEY,
    title        text NOT NULL,
    body         text,
    category     text,                         -- build_priority|pricing|host_terms|surplus|bylaw|...
    status       proposal_status DEFAULT 'draft',
    threshold_pct numeric DEFAULT 0.5,         -- % active weight to table
    quorum_pct   numeric DEFAULT 15,
    pass_pct     numeric DEFAULT 50,           -- 66.7 for bylaws
    opens_at     timestamptz, closes_at timestamptz,
    created_by   bigint REFERENCES members(member_id),
    created_at   timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS votes (
    id          bigserial PRIMARY KEY,
    proposal_id bigint REFERENCES proposals(proposal_id),
    member_id   bigint REFERENCES members(member_id),
    choice      text NOT NULL,                 -- for|against|abstain
    weight      numeric NOT NULL,              -- capped + anti-whale weight at cast time
    cast_at     timestamptz DEFAULT now(),
    UNIQUE (proposal_id, member_id)
);

-- voting weight helper: base 1 + min(units,120); anti-whale 2% clip applied at tally
-- SELECT member_id, 1 + LEAST(units,120) AS raw_weight FROM wake_balances;
