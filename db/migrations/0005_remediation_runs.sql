-- Authoritative run state (roadmap §9). A run being TESTING rather than
-- PR_CREATED is a database fact, never an inference from Memory Bank.

CREATE TABLE remediation_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    change_event_id uuid NOT NULL REFERENCES change_events (id) ON DELETE CASCADE,
    repository_id uuid NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    state run_state NOT NULL DEFAULT 'RECEIVED',
    -- Commit the run reasons about. Part of every idempotency key.
    base_sha text NOT NULL,
    trace_id text,
    attempt_budget integer NOT NULL DEFAULT 3 CHECK (attempt_budget >= 1),
    attempts_used integer NOT NULL DEFAULT 0 CHECK (attempts_used >= 0),
    failure_reason text,
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (attempts_used <= attempt_budget),
    -- Terminal states carry an end timestamp; live states do not.
    CONSTRAINT remediation_runs_terminal_has_ended_at CHECK (
        (state IN ('UNAFFECTED', 'HUMAN_REQUIRED', 'BLOCKED', 'FAILED', 'PR_CREATED'))
        = (ended_at IS NOT NULL)
    ),
    -- Redelivery of the same Pub/Sub message must resume the existing run
    -- rather than start a competing one.
    UNIQUE (change_event_id, repository_id, base_sha)
);

CREATE INDEX remediation_runs_open_idx ON remediation_runs (state, started_at)
WHERE state NOT IN ('UNAFFECTED', 'HUMAN_REQUIRED', 'BLOCKED', 'FAILED', 'PR_CREATED');

CREATE INDEX remediation_runs_repository_id_idx ON remediation_runs (repository_id);

-- Append-only transition log. Written before and after external side effects so
-- a resumed process can tell what already happened.
CREATE TABLE run_state_transitions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    sequence integer NOT NULL CHECK (sequence >= 1),
    -- NULL only for the first transition into RECEIVED.
    from_state run_state,
    to_state run_state NOT NULL,
    actor text NOT NULL,
    reason text,
    trace_id text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_state IS DISTINCT FROM to_state),
    UNIQUE (run_id, sequence)
);

CREATE INDEX run_state_transitions_run_id_idx ON run_state_transitions (run_id, sequence);

-- Idempotency keys are `run_id + action_type + base_sha` (roadmap §9). A row is
-- CLAIMED before the external call and COMPLETED after, so a crash between the
-- two is visible instead of silently repeating a PR or a sandbox allocation.
CREATE TABLE external_action_keys (
    idempotency_key text PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    action_type text NOT NULL,
    base_sha text NOT NULL,
    status external_action_status NOT NULL DEFAULT 'CLAIMED',
    -- Identifier of whatever the action produced: PR URL, sandbox name, GCS URI.
    result_ref text,
    claimed_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT external_action_keys_completed_has_timestamp CHECK (
        (status = 'COMPLETED') = (completed_at IS NOT NULL)
    ),
    UNIQUE (run_id, action_type, base_sha)
);
