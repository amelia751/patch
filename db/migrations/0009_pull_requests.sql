-- Pull requests PatchAPI opened, and what happened to them afterwards.
--
-- `merged_by_patchapi` exists only to be provably false. Merge state is read
-- back from GitHub into `state`; the boolean records that the merge, if any,
-- came from a human through normal CODEOWNERS and branch protection.

CREATE TABLE pull_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    repository_id uuid NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    number integer NOT NULL CHECK (number >= 1),
    url text NOT NULL,
    title text NOT NULL,
    head_branch text NOT NULL,
    base_branch text NOT NULL,
    head_sha text NOT NULL,
    state pull_request_state NOT NULL DEFAULT 'OPEN',
    merged_by_patchapi boolean NOT NULL DEFAULT false,
    -- The `run_id + action_type + base_sha` key that authorized creation.
    idempotency_key text NOT NULL UNIQUE
    REFERENCES external_action_keys (idempotency_key) ON DELETE RESTRICT,
    opened_at timestamptz NOT NULL DEFAULT now(),
    observed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pull_requests_never_self_merged CHECK (merged_by_patchapi IS FALSE),
    UNIQUE (repository_id, number),
    -- One PR per run. A retry resumes the existing record via the key above.
    UNIQUE (run_id)
);

CREATE INDEX pull_requests_state_idx ON pull_requests (state, observed_at DESC);
