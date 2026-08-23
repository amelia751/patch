-- The remediation run: what PatchAPI did about one change in one repository.
--
-- Everything up to now has been detection — a corpus of notices, an inventory of
-- usage, and an impact assessment joining the two. None of it changes anybody's
-- code. This is where the product acts, and therefore where it has to be able to
-- prove what it did. A run is not a chat transcript; it is an auditable record
-- with a state machine, evidence, and exactly one external side effect at the
-- end.
--
-- `schema.md` §8 specified these tables against a `repositories` table that was
-- never built. The rest of the system keys repositories by their `owner/name`
-- text — `provider_usages.repository`, `change_impacts.repository` — so that is
-- the grain used here. Inventing the missing table now would leave two ways to
-- name a repository and a join that silently drops rows when they disagree.

CREATE TYPE run_state AS ENUM (
    'RECEIVED', 'SANITIZED', 'NORMALIZED', 'IMPACT_SCANNING',
    'UNAFFECTED', 'POLICY_EVALUATION', 'HUMAN_REQUIRED',
    'WAITING_ON_OPERATOR', 'BLOCKED',
    'PATCHING', 'BUILDING', 'RETRY_PATCH', 'TESTING', 'VERIFYING',
    'FAILED', 'PR_CREATING', 'PR_CREATED'
);

CREATE TYPE policy_outcome  AS ENUM ('allow', 'human_required', 'blocked');
CREATE TYPE verdict         AS ENUM ('pass', 'fail', 'inconclusive');
CREATE TYPE attempt_status  AS ENUM ('running', 'succeeded', 'failed');
CREATE TYPE pr_state        AS ENUM ('open', 'closed', 'merged');
CREATE TYPE audit_outcome   AS ENUM ('SUCCEEDED', 'DENIED', 'FAILED');

CREATE TYPE evidence_kind AS ENUM (
    'build_log', 'test_log', 'live_api_artifact',
    'diff', 'source_snapshot', 'sandbox_log'
);

-- Legal transitions live in `packages/schemas/run_state.py`, not in a trigger.
-- The database records what happened; the state machine decides what is allowed.
-- Splitting it that way keeps one definition readable in one language, and lets
-- a stage refuse an illegal move before it has done any external work.
CREATE TABLE remediation_runs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    change_event_id  uuid NOT NULL REFERENCES change_events (id) ON DELETE CASCADE,
    project_id       uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    repository       text NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),

    state            run_state NOT NULL DEFAULT 'RECEIVED',
    -- The commit the run reasoned about. Evidence is only true of one tree, so a
    -- verdict without the sha it was reached at is not evidence.
    base_sha         text NOT NULL DEFAULT '',
    trace_id         text NOT NULL DEFAULT '',

    attempts_used    integer NOT NULL DEFAULT 0 CHECK (attempts_used >= 0),
    attempt_budget   integer NOT NULL DEFAULT 3 CHECK (attempt_budget > 0),
    failure_reason   text NOT NULL DEFAULT '',

    started_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    ended_at         timestamptz,

    -- One run per change per repository. This is what makes the console button
    -- idempotent: a double click, or a retry after a failure, returns the run
    -- that already exists rather than opening a second pull request for the
    -- same migration.
    UNIQUE (change_event_id, project_id, repository)
);

CREATE INDEX remediation_runs_inbox ON remediation_runs (project_id, started_at DESC);
CREATE INDEX remediation_runs_open
    ON remediation_runs (state)
    WHERE state NOT IN ('UNAFFECTED', 'HUMAN_REQUIRED', 'BLOCKED', 'FAILED', 'PR_CREATED');

-- Append-only. A run that ends at FAILED and is restarted keeps the first
-- attempt's transitions in front of the second's, because "this failed once and
-- was retried" is a different fact from "this failed", and the console is the
-- place a reviewer finds that out.
CREATE TABLE run_state_transitions (
    run_id      uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    sequence    integer NOT NULL CHECK (sequence >= 1),
    from_state  run_state,
    to_state    run_state NOT NULL,
    -- Which agent or service moved it. A transition nobody owns is not auditable.
    actor       text NOT NULL,
    reason      text NOT NULL DEFAULT '',
    occurred_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (run_id, sequence)
);

-- What the console renders as the live agent worklog, and what remains
-- afterwards as the record of how a conclusion was reached. The orchestrator
-- already produces this shape in `ToolTrace`; persisting it is what makes a run
-- reviewable after the process that produced it is gone.
CREATE TABLE run_trace_events (
    run_id      uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    sequence    integer NOT NULL CHECK (sequence >= 1),
    state       run_state NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('thought', 'action', 'result', 'narration', 'block')),

    verb        text NOT NULL DEFAULT '',
    body        text NOT NULL DEFAULT '',
    tool_type   text NOT NULL DEFAULT '',
    tool_use_id text NOT NULL DEFAULT '',
    file_path   text NOT NULL DEFAULT '',
    occurred_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (run_id, sequence)
);

-- `auto_merge` is a column rather than an omission so that every stored decision
-- states it, and the CHECK makes the product's hardest promise unrepresentable
-- rather than merely unimplemented. PatchAPI stops at the pull request.
CREATE TABLE policy_decisions (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,

    decision              policy_outcome NOT NULL,
    risk                  text NOT NULL DEFAULT '',
    auto_patch            boolean NOT NULL DEFAULT false,
    auto_pr               boolean NOT NULL DEFAULT false,
    auto_merge            boolean NOT NULL DEFAULT false CHECK (NOT auto_merge),
    human_review_required boolean NOT NULL DEFAULT true,

    forbidden_globs       text[] NOT NULL DEFAULT '{}',
    required_checks       text[] NOT NULL DEFAULT '{}',
    rule_ids              text[] NOT NULL DEFAULT '{}',
    reason                text NOT NULL DEFAULT '',
    policy_version        text NOT NULL DEFAULT '',
    evaluated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX policy_decisions_by_run ON policy_decisions (run_id, evaluated_at DESC);

CREATE TABLE patch_attempts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    attempt_number  integer NOT NULL CHECK (attempt_number >= 1),
    status          attempt_status NOT NULL DEFAULT 'running',

    -- Recorded per attempt, not read from configuration at display time.
    -- Configuration says which model should have run; this says which one did.
    patch_agent     text NOT NULL DEFAULT '',
    patch_model     text NOT NULL DEFAULT '',
    prompt_version  text NOT NULL DEFAULT '',

    sandbox_ref     text NOT NULL DEFAULT '',
    diff_uri        text NOT NULL DEFAULT '',
    diff_sha256     text NOT NULL DEFAULT '',
    files_changed   text[] NOT NULL DEFAULT '{}',
    build_exit_code integer,
    test_exit_code  integer,
    failure_summary text NOT NULL DEFAULT '',

    started_at      timestamptz NOT NULL DEFAULT now(),
    ended_at        timestamptz,

    UNIQUE (run_id, attempt_number)
);

-- The patch author does not grade its own work, so both agents are recorded and
-- a reviewer can confirm they differ.
CREATE TABLE verification_results (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    patch_attempt_id uuid REFERENCES patch_attempts (id) ON DELETE CASCADE,

    verdict          verdict NOT NULL,
    verifier_agent   text NOT NULL DEFAULT '',
    verifier_model   text NOT NULL DEFAULT '',
    patch_agent      text NOT NULL DEFAULT '',
    patch_model      text NOT NULL DEFAULT '',

    checks           jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_summary text NOT NULL DEFAULT '',
    report_uri       text NOT NULL DEFAULT '',
    evaluated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX verification_results_by_run ON verification_results (run_id, evaluated_at DESC);

CREATE TABLE artifacts (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    patch_attempt_id uuid REFERENCES patch_attempts (id) ON DELETE CASCADE,

    kind             evidence_kind NOT NULL,
    uri              text NOT NULL,
    -- Evidence that cannot be shown to be the same bytes the verifier read is
    -- not evidence.
    content_sha256   text NOT NULL DEFAULT '',
    size_bytes       bigint CHECK (size_bytes >= 0),
    media_type       text NOT NULL DEFAULT '',
    -- Small logs live here rather than in object storage: a build log is the
    -- thing a reviewer opens first, and a bucket round trip to render it makes
    -- the console depend on a second system for its most-used read.
    body             text NOT NULL DEFAULT '',
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX artifacts_by_run ON artifacts (run_id, created_at);

CREATE TABLE pull_requests (
    run_id             uuid PRIMARY KEY REFERENCES remediation_runs (id) ON DELETE CASCADE,
    number             integer NOT NULL CHECK (number > 0),
    url                text NOT NULL,
    title              text NOT NULL DEFAULT '',
    head_branch        text NOT NULL,
    base_branch        text NOT NULL,
    head_sha           text NOT NULL DEFAULT '',
    state              pr_state NOT NULL DEFAULT 'open',
    -- Asserted in the schema so the claim survives a code change that forgets it.
    merged_by_patchapi boolean NOT NULL DEFAULT false CHECK (NOT merged_by_patchapi),
    opened_at          timestamptz NOT NULL DEFAULT now(),
    observed_at        timestamptz NOT NULL DEFAULT now()
);

-- Claimed before the side effect, not written after it. A job that dies between
-- opening a pull request and recording that it did must not open a second one on
-- restart, so the key is the permission to act and `result_ref` is filled in
-- once the action returns.
CREATE TABLE idempotency_keys (
    run_id      uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    action_type text NOT NULL,
    base_sha    text NOT NULL,
    result_ref  text NOT NULL DEFAULT '',
    claimed_at  timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (run_id, action_type, base_sha)
);

-- Every privileged act, whether it succeeded or was refused. Denials are the
-- point: a fleet that never records what it was stopped from doing cannot show
-- that the controls are load-bearing.
CREATE TABLE audit_events (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor       text NOT NULL,
    action      text NOT NULL,
    target      text NOT NULL DEFAULT '',
    outcome     audit_outcome NOT NULL,
    reason      text NOT NULL DEFAULT '',
    trace_id    text NOT NULL DEFAULT '',
    run_id      uuid REFERENCES remediation_runs (id) ON DELETE SET NULL,
    project_id  uuid REFERENCES projects (id) ON DELETE SET NULL,
    repository  text,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_events_recent ON audit_events (occurred_at DESC);
CREATE INDEX audit_events_denied ON audit_events (occurred_at DESC) WHERE outcome = 'DENIED';
