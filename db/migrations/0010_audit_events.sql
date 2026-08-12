-- Append-only audit trail.
--
-- Denials are as important as successes: a blocked capability call is the
-- evidence that the narrow GitHub tool surface and the policy allowlists are
-- actually holding. Rows are never updated or deleted by application code.

CREATE TABLE audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id uuid REFERENCES organizations (id) ON DELETE SET NULL,
    repository_id uuid REFERENCES repositories (id) ON DELETE SET NULL,
    run_id uuid REFERENCES remediation_runs (id) ON DELETE SET NULL,
    -- Agent, service, or human principal that attempted the action.
    actor text NOT NULL,
    -- Capability or operation name, e.g. 'github_tools.create_pull_request'.
    action text NOT NULL,
    target text,
    outcome audit_outcome NOT NULL,
    reason text,
    trace_id text,
    detail jsonb NOT NULL DEFAULT '{}',
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT audit_events_denied_has_reason CHECK (outcome <> 'DENIED' OR reason IS NOT NULL),
    CONSTRAINT audit_events_detail_is_object CHECK (jsonb_typeof(detail) = 'object')
);

CREATE INDEX audit_events_run_id_idx ON audit_events (run_id, occurred_at);

CREATE INDEX audit_events_occurred_at_idx ON audit_events (occurred_at DESC);

CREATE INDEX audit_events_denied_idx ON audit_events (occurred_at DESC)
WHERE outcome = 'DENIED';
