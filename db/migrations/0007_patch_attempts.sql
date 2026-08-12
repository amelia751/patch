-- Patch attempts and their sandbox outcomes (roadmap §8.4, §13).
--
-- A patch that has not been executed in isolation has no build or test exit
-- code here, which is how the orchestrator distinguishes "not run yet" from
-- "ran and passed". It never infers success from the absence of a failure.

CREATE TABLE patch_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    attempt_number integer NOT NULL CHECK (attempt_number >= 1),
    status patch_attempt_status NOT NULL DEFAULT 'PENDING',
    plan_schema_version text,
    plan jsonb,
    -- Model and prompt that produced the diff. Recorded so the independence
    -- check in `verification_results` can be audited rather than trusted.
    patch_agent text NOT NULL,
    patch_model text NOT NULL,
    prompt_version text,
    -- Sandbox instance the attempt executed in. Local temp workspaces record a
    -- file:// path during Phase 1; GKE records the sandbox claim name.
    sandbox_ref text,
    build_exit_code integer,
    test_exit_code integer,
    diff_sha256 text CHECK (diff_sha256 IS NULL OR diff_sha256 ~ '^[0-9a-f]{64}$'),
    files_changed integer CHECK (files_changed IS NULL OR files_changed >= 0),
    failure_summary text,
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    -- A successful attempt must be able to point at the isolated execution that
    -- proved it (constraint 5).
    CONSTRAINT patch_attempts_success_ran_in_sandbox CHECK (
        status <> 'SUCCEEDED'
        OR (sandbox_ref IS NOT NULL AND build_exit_code = 0 AND test_exit_code = 0)
    ),
    UNIQUE (run_id, attempt_number)
);

CREATE INDEX patch_attempts_run_id_idx ON patch_attempts (run_id, attempt_number);
