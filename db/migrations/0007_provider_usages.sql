-- Provider-identifier inventory (schema.md §7, repo-indexer.md §5.1).
--
-- Findings are facts about (repository, branch, commit). No project_id: one
-- file-and-line is one row however many projects import the repository.
-- Attribution is the project_provider_usages view.

CREATE TYPE detection_layer AS ENUM (
    'A_DETERMINISTIC',
    'B_STRUCTURAL',
    'C_SEMANTIC',
    'D_TYPE_PRECISE'
);

CREATE TYPE usage_kind AS ENUM (
    'runtime_source',
    'configuration',
    'test',
    'example',
    'documentation_example',
    'dead_code'
);

CREATE TYPE index_status AS ENUM (
    'idle',
    'indexing',
    'ready',
    'error'
);

CREATE TABLE provider_usages (
    id               bigserial PRIMARY KEY,
    repository       text            NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),
    branch           text            NOT NULL,
    provider         text            NOT NULL,
    identifier       text            NOT NULL,
    surface          text,
    file_path        text            NOT NULL,
    line_start       integer         NOT NULL CHECK (line_start >= 1),
    line_end         integer,
    usage_kind       usage_kind      NOT NULL,
    detection_layer  detection_layer NOT NULL,
    confidence       real            NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    excerpt          text            NOT NULL,
    observed_sha     text            NOT NULL,
    first_seen_at    timestamptz     NOT NULL DEFAULT now(),
    last_seen_at     timestamptz     NOT NULL DEFAULT now(),
    retired_at       timestamptz,
    UNIQUE (repository, branch, file_path, line_start, identifier, detection_layer)
);

CREATE INDEX provider_usages_lookup
    ON provider_usages (provider, identifier) WHERE retired_at IS NULL;
CREATE INDEX provider_usages_repo
    ON provider_usages (repository, branch) WHERE retired_at IS NULL;

-- One row per indexed (repository, branch). Shared by every project that
-- imported it; reference_count is why one project's cleanup cannot blind
-- another. status / progress_percent feed the Codebase tab banner.
CREATE TABLE repo_index_state (
    repository         text         NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),
    branch             text         NOT NULL,
    status             index_status NOT NULL DEFAULT 'idle',
    progress_percent   smallint     NOT NULL DEFAULT 0
                         CHECK (progress_percent BETWEEN 0 AND 100),
    indexed_sha        text,
    shard_path         text,
    indexer_version    text         NOT NULL,
    scanner_version    text         NOT NULL,
    last_full_index    timestamptz,
    last_delta_index   timestamptz,
    file_count         integer      NOT NULL DEFAULT 0,
    reference_count    integer      NOT NULL DEFAULT 0 CHECK (reference_count >= 0),
    error_message      text,
    PRIMARY KEY (repository, branch)
);

-- Project-scoped read path. The workspace_path prefix filter is here so a
-- call site cannot forget it and show one team another team's files.
CREATE VIEW project_provider_usages AS
SELECT p.id AS project_id, pr.id AS project_repository_id, pr.kind, u.*
FROM provider_usages u
JOIN project_repositories pr ON pr.full_name = u.repository
JOIN projects p             ON p.id = pr.project_id
LEFT JOIN workspaces w      ON w.repository_id = pr.id
                           AND w.repo_branch = u.branch
WHERE u.retired_at IS NULL
  AND u.branch = COALESCE(w.repo_branch, pr.default_branch)
  AND (w.workspace_path IS NULL
       OR u.file_path LIKE w.workspace_path || '/%');
