-- Normalized provider change events.
--
-- Everything in this table originates outside the enterprise (constraint 4).
-- The manifest is stored as data and is never executed or treated as an
-- instruction; only PatchAPI's internal agents read it and decide impact.

CREATE TABLE change_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL,
    -- Provider-scoped identifier from the change source,
    -- e.g. 'imagen4-retirement-2026-08-17'.
    external_id text NOT NULL,
    change_kind change_kind NOT NULL,
    title text NOT NULL,
    source_urls text[] NOT NULL DEFAULT '{}',
    -- SHA-256 of the normalized source snapshot. NULL means no provider
    -- evidence was captured; a run must fail closed rather than proceed.
    source_sha256 text CHECK (source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'),
    source_artifact_uri text,
    affected_identifiers text[] NOT NULL DEFAULT '{}',
    recommended_replacement text,
    effective_at date,
    detected_at timestamptz NOT NULL DEFAULT now(),
    manifest_schema_version text NOT NULL,
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Re-polling an unchanged page must not create a second event; re-polling a
    -- changed page must. The source hash carries that distinction, and
    -- NULLS NOT DISTINCT keeps uncaptured-evidence events deduplicated too.
    UNIQUE NULLS NOT DISTINCT (provider, external_id, source_sha256)
);

CREATE INDEX change_events_detected_at_idx ON change_events (detected_at DESC);

CREATE INDEX change_events_affected_identifiers_idx
ON change_events USING gin (affected_identifiers);
