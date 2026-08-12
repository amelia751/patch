-- Independent verification (constraint 6, roadmap §8.5).
--
-- `verification_results_independent_verifier` is the database half of the rule:
-- the agent that wrote the patch cannot be the agent that grades it. Rows that
-- would record self-grading are rejected, not flagged.

CREATE TABLE verification_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    patch_attempt_id uuid NOT NULL REFERENCES patch_attempts (id) ON DELETE CASCADE,
    verdict verification_verdict NOT NULL,
    verifier_agent text NOT NULL,
    verifier_model text NOT NULL,
    -- Copied from the attempt at write time so the independence constraint is
    -- enforceable in a single row.
    patch_agent text NOT NULL,
    patch_model text NOT NULL,
    -- One entry per required check: {"name": "build", "passed": true, ...}.
    checks jsonb NOT NULL DEFAULT '[]',
    report_schema_version text NOT NULL,
    report jsonb NOT NULL,
    evidence_summary text,
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT verification_results_independent_verifier CHECK (verifier_agent <> patch_agent),
    CONSTRAINT verification_results_checks_is_array CHECK (jsonb_typeof(checks) = 'array'),
    UNIQUE (patch_attempt_id, verifier_agent)
);

CREATE INDEX verification_results_run_id_idx ON verification_results (run_id);

-- Evidence metadata. The bytes live in Cloud Storage (roadmap §10.3); this
-- table holds the pointer, the content hash, and what produced it.
CREATE TABLE artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    patch_attempt_id uuid REFERENCES patch_attempts (id) ON DELETE CASCADE,
    kind artifact_kind NOT NULL,
    -- gs:// in deployed phases, file:// for the local vertical slice.
    uri text NOT NULL CHECK (uri ~ '^(gs|file|https)://'),
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    media_type text NOT NULL DEFAULT 'application/octet-stream',
    created_at timestamptz NOT NULL DEFAULT now(),
    -- Re-uploading identical evidence for the same run is a no-op.
    UNIQUE (run_id, kind, content_sha256)
);

CREATE INDEX artifacts_run_id_idx ON artifacts (run_id);

CREATE INDEX artifacts_patch_attempt_id_idx ON artifacts (patch_attempt_id)
WHERE patch_attempt_id IS NOT NULL;
