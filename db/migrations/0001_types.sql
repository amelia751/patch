-- Enumerated domains shared by the workflow tables.
--
-- `run_state` is the state machine in roadmap §9 verbatim. Encoding it as a
-- database type means an agent cannot persist a state the orchestrator does not
-- define; an unknown value is rejected by Postgres rather than by review.

CREATE TYPE run_state AS ENUM (
    'RECEIVED',
    'SANITIZED',
    'NORMALIZED',
    'IMPACT_SCANNING',
    'UNAFFECTED',
    'POLICY_EVALUATION',
    'HUMAN_REQUIRED',
    'BLOCKED',
    'PATCHING',
    'BUILDING',
    'RETRY_PATCH',
    'TESTING',
    'VERIFYING',
    'FAILED',
    'PR_CREATING',
    'PR_CREATED'
);

CREATE TYPE policy_decision_kind AS ENUM (
    'ALLOW',
    'HUMAN_REQUIRED',
    'BLOCKED'
);

CREATE TYPE risk_tier AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TYPE criticality_tier AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

-- INCONCLUSIVE is a first-class verdict: the fail-closed path in constraint 10
-- needs somewhere truthful to land when the verifier cannot decide.
CREATE TYPE verification_verdict AS ENUM (
    'PASS',
    'FAIL',
    'INCONCLUSIVE'
);

CREATE TYPE patch_attempt_status AS ENUM (
    'PENDING',
    'BUILD_FAILED',
    'TESTS_FAILED',
    'SUCCEEDED',
    'ABANDONED'
);

-- Detection layers from roadmap §11.3. Stored per usage so the dashboard can
-- show which findings are deterministic and which came from a model.
CREATE TYPE detection_layer AS ENUM (
    'A_DETERMINISTIC',
    'B_SYNTAX_AWARE',
    'C_SEMANTIC'
);

CREATE TYPE change_kind AS ENUM (
    'DEPRECATION',
    'MODEL_RETIREMENT',
    'BREAKING_CHANGE',
    'REPLACEMENT',
    'ADVISORY'
);

CREATE TYPE artifact_kind AS ENUM (
    'SOURCE_SNAPSHOT',
    'UNIFIED_DIFF',
    'BUILD_LOG',
    'TEST_LOG',
    'IMAGE_PROOF',
    'EVIDENCE_BUNDLE',
    'AGENT_TRACE'
);

-- Observed GitHub state. PatchAPI never writes MERGED; it only records what it
-- reads back from the GitHub tool service.
CREATE TYPE pull_request_state AS ENUM (
    'OPEN',
    'CLOSED',
    'MERGED'
);

CREATE TYPE external_action_status AS ENUM (
    'CLAIMED',
    'COMPLETED',
    'ABANDONED'
);

CREATE TYPE audit_outcome AS ENUM (
    'SUCCEEDED',
    'DENIED',
    'FAILED'
);
