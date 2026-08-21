-- Provider change events and the per-project inbox (schema.md §8.1, plus
-- the Subscribe / Changes join that document left implicit).
--
-- change_events is global: one Imagen retirement, many projects.
-- project_change_findings is the inbox row (Need you / Watching / Dismissed).
-- project_change_scans is the Subscribe overlay. Runs stay a later migration.

CREATE TYPE change_kind AS ENUM (
    'deprecation',
    'replacement',
    'new_identifier',
    'breaking_change',
    'feature',
    'fix',
    'issue',
    'security',
    'announcement',
    'change',
    'libraries',
    'other'
);

CREATE TYPE change_severity AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TYPE finding_status AS ENUM (
    'needs_you',
    'watching',
    'dismissed'
);

CREATE TYPE finding_reason AS ENUM (
    'runtime_hit',
    'docs_only',
    'no_usage',
    'false_positive',
    'fail_closed',
    'not_an_identifier',
    'new_identifier',
    'user'
);

CREATE TYPE change_scan_status AS ENUM (
    'idle',
    'scanning',
    'ready',
    'error'
);

CREATE TABLE change_events (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id             text        NOT NULL,
    provider                text        NOT NULL,
    product                 text        NOT NULL DEFAULT '',
    change_kind             change_kind NOT NULL,
    severity                change_severity NOT NULL DEFAULT 'medium',
    title                   text        NOT NULL,
    summary                 text        NOT NULL DEFAULT '',
    source_urls             text[]      NOT NULL DEFAULT '{}',
    source_sha256           text,
    source_uri              text,
    affected_identifiers    text[]      NOT NULL DEFAULT '{}',
    replacements            jsonb       NOT NULL DEFAULT '[]',
    source_conflicts        jsonb       NOT NULL DEFAULT '[]',
    announced_at            date,
    effective_at            date,
    fail_closed             boolean     NOT NULL DEFAULT false,
    false_positive          boolean     NOT NULL DEFAULT false,
    migration               text,
    detected_at             timestamptz NOT NULL DEFAULT now(),
    manifest_uri            text
);

CREATE INDEX change_events_external_id_detected_at
    ON change_events (external_id, detected_at DESC);

CREATE INDEX change_events_provider
    ON change_events (provider, detected_at DESC);

CREATE TABLE project_change_findings (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id           uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    change_event_id      uuid NOT NULL REFERENCES change_events (id) ON DELETE CASCADE,
    status               finding_status NOT NULL,
    status_reason        finding_reason NOT NULL,
    repos                text[] NOT NULL DEFAULT '{}',
    file_hits            integer NOT NULL DEFAULT 0 CHECK (file_hits >= 0),
    file_count           integer NOT NULL DEFAULT 0 CHECK (file_count >= 0),
    identifier_counts    jsonb NOT NULL DEFAULT '{}',
    files                jsonb NOT NULL DEFAULT '[]',
    classified_at        timestamptz NOT NULL DEFAULT now(),
    dismissed_at         timestamptz,
    dismissed_by         uuid REFERENCES users (id),
    UNIQUE (project_id, change_event_id)
);

CREATE INDEX project_change_findings_inbox
    ON project_change_findings (project_id, status);

CREATE TABLE project_change_scans (
    project_id         uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    provider           text NOT NULL,
    status             change_scan_status NOT NULL DEFAULT 'idle',
    progress_percent   smallint NOT NULL DEFAULT 0
                         CHECK (progress_percent BETWEEN 0 AND 100),
    started_at         timestamptz,
    finished_at        timestamptz,
    error_message      text,
    PRIMARY KEY (project_id, provider)
);
