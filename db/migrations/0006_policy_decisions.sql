-- Deterministic policy verdicts (roadmap §8.3).
--
-- The CHECK on `auto_merge` is the database half of constraint 3: PatchAPI
-- stops at the pull request. A prompt-injected or miswired agent cannot even
-- record a decision that says otherwise.

CREATE TABLE policy_decisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES remediation_runs (id) ON DELETE CASCADE,
    decision policy_decision_kind NOT NULL,
    risk risk_tier NOT NULL,
    auto_patch boolean NOT NULL,
    auto_pr boolean NOT NULL,
    auto_merge boolean NOT NULL DEFAULT false,
    forbidden_globs text[] NOT NULL DEFAULT '{}',
    required_checks text[] NOT NULL DEFAULT '{}',
    reason text NOT NULL,
    -- Pinned rule-set version, so a verdict stays explainable after the policy
    -- package changes.
    policy_version text NOT NULL,
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT policy_decisions_never_auto_merge CHECK (auto_merge IS FALSE),
    -- A BLOCKED verdict cannot simultaneously authorize work.
    CONSTRAINT policy_decisions_blocked_authorizes_nothing CHECK (
        decision <> 'BLOCKED' OR (auto_patch IS FALSE AND auto_pr IS FALSE)
    ),
    -- One verdict per rule-set version per run; a re-evaluation under the same
    -- version is a no-op rather than a duplicate.
    UNIQUE (run_id, policy_version)
);

CREATE INDEX policy_decisions_run_id_idx ON policy_decisions (run_id);
