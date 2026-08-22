-- The corpus a notice becomes, and the impact one repository takes from it.
--
-- Change Intelligence used to run per project and attach prose to a row shared
-- by every project. That produced cards reading "no usages in this project"
-- beside an inventory of fourteen hits: a provider-wide row cannot hold a
-- project-scoped sentence. So the two concerns are split by table here.
--
-- change_events + change_event_identifiers is what a notice means, understood
-- once, true for every subscriber. change_impacts + change_impact_findings is
-- what one commit of one repository does about it. A sentence about somebody's
-- tree has nowhere to live except the second pair, which is scoped to exactly
-- the repository it describes.
--
-- The identifier, not the event, is the join grain. Each identifier in a notice
-- carries its own replacement target and its own liveness: the ultra and fast
-- Imagen variants need not move where the base one moves, and one may already
-- 404 while another still serves.

-- Who said so. Ordered by authority when two sources disagree: committed
-- lifecycle data and a live surface outrank a reading of prose.
CREATE TYPE change_provenance AS ENUM (
    'catalog',
    'live',
    'notice_parse',
    'watchlist',
    'agent'
);

CREATE TYPE identifier_role AS ENUM (
    'retired',
    'replacement',
    'mentioned'
);

-- `rationale` is deliberately not `summary`. Enrichment used to overwrite the
-- summary, destroying what the provider actually wrote; keeping both lets a
-- card show the notice and the reading of it, and lets them be compared when
-- they disagree.
--
-- notice_sha256 with normalizer_version is the re-read key. Bumping the version
-- re-normalizes the corpus from notices already ingested, the same way
-- INDEXER_VERSION re-indexes a tree already cloned.
ALTER TABLE change_events
    ADD COLUMN notice_id          uuid REFERENCES provider_change_notes (id),
    ADD COLUMN notice_sha256      text NOT NULL DEFAULT '',
    ADD COLUMN provenance         change_provenance NOT NULL DEFAULT 'watchlist',
    ADD COLUMN rationale          text NOT NULL DEFAULT '',
    ADD COLUMN normalizer_version text NOT NULL DEFAULT '',
    ADD COLUMN normalized_at      timestamptz;

-- Insertion was `WHERE NOT EXISTS (external_id = ...)`, so a corrected notice
-- could never correct the row it produced. Re-normalization needs a conflict
-- target.
CREATE UNIQUE INDEX change_events_identity ON change_events (provider, external_id);

CREATE TABLE change_event_identifiers (
    change_event_id  uuid NOT NULL REFERENCES change_events (id) ON DELETE CASCADE,
    identifier       text NOT NULL CHECK (length(btrim(identifier)) > 0),
    role             identifier_role NOT NULL,

    replacement      text,
    -- Whether moving is a change of request surface rather than a string
    -- rewrite. Imagen to Gemini native image generation is the former.
    semantic         boolean NOT NULL DEFAULT false,

    asserted_by      change_provenance NOT NULL,
    -- Evidence, not a gate. Recording which deterministic source agreed costs
    -- nothing at runtime and gives a card something honest to show; the
    -- pull request, which a human still reviews, is where risk is actually
    -- held.
    corroborated_by  change_provenance,
    live_status      probe_status,
    observed_at      timestamptz,

    PRIMARY KEY (change_event_id, identifier, role)
);

-- The join the Releases tab runs: corpus identifiers against indexed usage.
CREATE INDEX change_event_identifiers_join
    ON change_event_identifiers (identifier) WHERE role = 'retired';

-- One repository, one commit, one change. base_sha is in the key because an
-- impact assessment is only true of the tree it read: a push produces a new
-- sha and therefore a new assessment, leaving the previous one as history
-- rather than a quietly stale claim.
CREATE TABLE change_impacts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    change_event_id     uuid NOT NULL REFERENCES change_events (id) ON DELETE CASCADE,
    project_id          uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    repository          text NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),
    base_sha            text NOT NULL,

    affected            boolean NOT NULL,
    confidence          real CHECK (confidence BETWEEN 0 AND 1),
    migration_character text,
    required_checks     text[] NOT NULL DEFAULT '{}',
    owners              text[] NOT NULL DEFAULT '{}',
    -- Where a sentence about this repository belongs, and the reason the
    -- provider-wide rationale must never carry one.
    notes               text NOT NULL DEFAULT '',

    run_id              text NOT NULL DEFAULT '',
    contract_version    text NOT NULL DEFAULT '',
    assessed_at         timestamptz NOT NULL DEFAULT now(),

    UNIQUE (change_event_id, project_id, repository, base_sha)
);

CREATE INDEX change_impacts_inbox
    ON change_impacts (project_id, change_event_id, assessed_at DESC);

CREATE TABLE change_impact_findings (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    impact_id   uuid NOT NULL REFERENCES change_impacts (id) ON DELETE CASCADE,
    identifier  text NOT NULL,
    path        text NOT NULL,
    usage_kind  usage_kind NOT NULL,
    line        integer CHECK (line >= 1),
    symbol      text,
    excerpt     text NOT NULL DEFAULT ''
);

CREATE INDEX change_impact_findings_by_impact
    ON change_impact_findings (impact_id);

-- Fleet view: every repository in the organization that touches one identifier.
CREATE INDEX change_impact_findings_by_identifier
    ON change_impact_findings (identifier);

-- Backfill the corpus rows that already exist so the join has something to read
-- before the first agent run. Provenance is 'watchlist' by column default,
-- which is what those rows in fact are.
INSERT INTO change_event_identifiers (
    change_event_id, identifier, role, replacement, semantic, asserted_by
)
SELECT e.id,
       identifier,
       'retired'::identifier_role,
       NULLIF(
           (SELECT r ->> 'to'
            FROM jsonb_array_elements(e.replacements) AS r
            WHERE r ->> 'from' = identifier
            LIMIT 1),
           ''
       ),
       COALESCE(e.migration = 'semantic', false),
       e.provenance
FROM change_events e, unnest(e.affected_identifiers) AS identifier
ON CONFLICT DO NOTHING;
