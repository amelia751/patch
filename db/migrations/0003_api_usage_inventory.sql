-- API usage inventory (roadmap §11.1). Maintained by the repo indexer on push
-- so impact analysis is an index lookup, not a fleet-wide clone-and-grep.

CREATE TABLE api_usages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    provider text NOT NULL,
    -- Exact provider identifier, e.g. 'imagen-4.0-generate-001'.
    identifier text NOT NULL,
    -- Free-text description of the API surface when the hit is a family or a
    -- call shape rather than a literal string, e.g. 'imagen-* family handling'.
    surface text,
    file_path text NOT NULL,
    -- 0 means "file-level, no specific line". NOT NULL so the uniqueness key
    -- below stays a plain constraint that ON CONFLICT can target.
    line_start integer NOT NULL DEFAULT 0 CHECK (line_start >= 0),
    line_end integer CHECK (line_end IS NULL OR line_end >= line_start),
    detection_layer detection_layer NOT NULL,
    confidence numeric(3, 2) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    -- Commit the hit was observed at, so a stale finding is identifiable.
    observed_sha text NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    -- Set when a later index pass no longer finds the usage. Rows are retired,
    -- never deleted, so an audit can explain why a run stopped firing.
    removed_at timestamptz,
    UNIQUE (repository_id, provider, identifier, file_path, line_start)
);

CREATE INDEX api_usages_identifier_idx ON api_usages (provider, identifier)
WHERE removed_at IS NULL;

CREATE INDEX api_usages_repository_id_idx ON api_usages (repository_id)
WHERE removed_at IS NULL;
