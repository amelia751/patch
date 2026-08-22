-- Live evidence that an identifier no longer resolves.
--
-- Before this, "already broken" was decided from `change_events.effective_at`,
-- a date copied off a provider page or typed into the watchlist. That is a
-- claim about the world. `imagen-4.0-generate-001` returned 404 from v1beta
-- while its pinned date still read as future, so a live call site sat in
-- Watching. A probe records what the surface actually publishes.
--
-- `unknown` is a first-class outcome and is stored, not discarded: "the probe
-- could not run" must be distinguishable from "the model is gone", because
-- only one of those may escalate a finding.

ALTER TYPE finding_reason ADD VALUE IF NOT EXISTS 'probe_404';

CREATE TYPE probe_status AS ENUM (
    'resolves',
    'not_found',
    'unknown'
);

CREATE TABLE identifier_probes (
    identifier    text         NOT NULL,
    surface       text         NOT NULL,
    provider      text         NOT NULL DEFAULT 'google',
    status        probe_status NOT NULL,
    detail        text         NOT NULL DEFAULT '',
    source_url    text         NOT NULL DEFAULT '',
    checked_at    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (identifier, surface)
);

-- Refresh reads every probe for a provider in one shot before classifying.
CREATE INDEX identifier_probes_provider_checked
    ON identifier_probes (provider, checked_at DESC);
