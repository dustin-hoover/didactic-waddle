-- The Master Craftsman Layer — core operational data model
-- Postgres dialect.
--
-- Safety invariants enforced HERE, at the data layer, not in application policy:
--   1. No job closes without a supervisor sign_off_ts.
--   2. Gas / main-panel / roof-penetration tasks require a synchronous
--      supervisor live-view before completion.
--   3. Every diagnosis + code citation is logged with model, prompt, and
--      retrieved doc for audit.
-- Application code may add more checks; it may NEVER relax these.

CREATE TYPE hazard_class AS ENUM ('none', 'gas', 'main_panel', 'roof_penetration');
CREATE TYPE job_status  AS ENUM ('scheduled','en_route','on_site','diagnosed',
                                 'awaiting_signoff','closed','callback');

CREATE TABLE supervisors (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name          TEXT NOT NULL,
    license_number     TEXT NOT NULL,
    license_state      TEXT NOT NULL,          -- must match job jurisdiction
    license_class      TEXT NOT NULL,          -- master electrician/plumber/HVAC
    license_expires_on DATE NOT NULL,
    active             BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE technicians (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name     TEXT NOT NULL,
    level         SMALLINT NOT NULL DEFAULT 1, -- 1 = augmented field tech
    hired_on      DATE NOT NULL,
    active        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE code_citations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code_body     TEXT NOT NULL,               -- NEC / IMC / UPC / local
    section       TEXT NOT NULL,
    state         TEXT NOT NULL,
    jurisdiction  TEXT NOT NULL,
    edition_year  SMALLINT NOT NULL,
    source_url    TEXT NOT NULL,               -- provenance is mandatory
    CONSTRAINT code_citation_sourced CHECK (length(source_url) > 0)
);

CREATE TABLE jobs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market                 TEXT NOT NULL,
    service_line           TEXT NOT NULL,      -- hvac_service, hvac_install, ...
    technician_id          UUID NOT NULL REFERENCES technicians(id),
    supervising_master_id  UUID NOT NULL REFERENCES supervisors(id),
    hazard                 hazard_class NOT NULL DEFAULT 'none',
    status                 job_status  NOT NULL DEFAULT 'scheduled',
    scheduled_ts           TIMESTAMPTZ NOT NULL,
    ticket_amount_cents    INTEGER,
    -- Invariant #2: hazardous tasks require a synchronous live-view timestamp
    live_view_ts           TIMESTAMPTZ,
    -- Invariant #1: sign-off is required to reach 'closed'
    sign_off_ts            TIMESTAMPTZ,
    sign_off_supervisor_id UUID REFERENCES supervisors(id),

    -- #1: a closed job must carry a sign-off
    CONSTRAINT job_closed_requires_signoff CHECK (
        status <> 'closed' OR (sign_off_ts IS NOT NULL AND sign_off_supervisor_id IS NOT NULL)
    ),
    -- #2: a hazardous job cannot be signed off without a prior live-view
    CONSTRAINT hazard_requires_live_view CHECK (
        hazard = 'none' OR sign_off_ts IS NULL OR
        (live_view_ts IS NOT NULL AND live_view_ts <= sign_off_ts)
    )
);

-- Enforce that a job's supervisor is licensed in the job's market/state and
-- unexpired at sign-off time. (State<->market mapping lives in a markets table
-- omitted here; trigger is illustrative of the intent.)
CREATE OR REPLACE FUNCTION enforce_supervisor_license() RETURNS trigger AS $$
BEGIN
    IF NEW.sign_off_ts IS NOT NULL THEN
        PERFORM 1 FROM supervisors s
         WHERE s.id = NEW.sign_off_supervisor_id
           AND s.active
           AND s.license_expires_on >= NEW.sign_off_ts::date;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'sign-off supervisor % is inactive or license expired',
                NEW.sign_off_supervisor_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_supervisor_license
    BEFORE INSERT OR UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION enforce_supervisor_license();

CREATE TABLE sign_offs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id         UUID NOT NULL REFERENCES jobs(id),
    supervisor_id  UUID NOT NULL REFERENCES supervisors(id),
    signed_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    live_view      BOOLEAN NOT NULL,           -- was this a synchronous view?
    notes          TEXT
);

CREATE TABLE parts_orders (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id        UUID NOT NULL REFERENCES jobs(id),
    supplier      TEXT NOT NULL,               -- ferguson/grainger/hdsupply
    part_number   TEXT NOT NULL,
    qty           INTEGER NOT NULL CHECK (qty > 0),
    cost_cents    INTEGER NOT NULL,
    price_cents   INTEGER NOT NULL,
    ordered_ts    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE callbacks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_job  UUID NOT NULL REFERENCES jobs(id),
    reason        TEXT NOT NULL,
    opened_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_ts   TIMESTAMPTZ
);

CREATE TABLE sensor_readings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id        UUID NOT NULL REFERENCES jobs(id),
    metric        TEXT NOT NULL,               -- superheat, subcooling, static pressure...
    value         NUMERIC NOT NULL,
    unit          TEXT NOT NULL,
    captured_ts   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Invariant #3: every AI diagnosis + code citation is auditable.
CREATE TABLE diagnosis_audit (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id         UUID NOT NULL REFERENCES jobs(id),
    model          TEXT NOT NULL,              -- model id that produced output
    prompt         TEXT NOT NULL,
    retrieved_doc  TEXT NOT NULL,              -- doc/passage used for grounding
    citation_id    UUID REFERENCES code_citations(id),
    output         TEXT NOT NULL,
    created_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT diagnosis_fully_logged CHECK (
        length(model) > 0 AND length(prompt) > 0 AND length(retrieved_doc) > 0
    )
);
