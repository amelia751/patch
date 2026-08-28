-- Resuming an agent turn that paused for the operator.
--
-- A remediation that needs a credential parks and its Cloud Run job exits;
-- Continue starts a new execution. Without somewhere to write down which ADK
-- invocation stopped and which tool call is unanswered, the next execution can
-- only start the agent's turn over — the model re-reads every file and re-runs
-- every command it already ran, which is what made Continue look like a restart.
--
-- Two things are needed and they belong in different places.
--
-- 1. `remediation_runs.agent_hold` — the pointer. Workflow state, so it lives
--    with the run in the authoritative store (roadmap §7), not in Memory Bank
--    and not in an artifact: artifacts are evidence, and a pointer is not
--    evidence of anything.
--
-- 2. Schema `adk` — the conversation. ADK's own session service owns these
--    tables and their names (`sessions`, `events`, `app_states`, `user_states`)
--    are generic enough to collide with PatchAPI's, so they are kept out of
--    `public` rather than mixed into a schema we migrate by hand.

BEGIN;

ALTER TABLE remediation_runs
    ADD COLUMN IF NOT EXISTS agent_hold jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN remediation_runs.agent_hold IS
    'The ADK invocation this run paused inside: session id, unanswered '
    'function-call id, tool name and agent. Empty when no turn is parked. '
    'Cleared when the turn is answered or the run is restarted.';

CREATE SCHEMA IF NOT EXISTS adk;

COMMENT ON SCHEMA adk IS
    'Google ADK session storage (DatabaseSessionService). Created and migrated '
    'by ADK itself; no PatchAPI migration writes these tables.';

COMMIT;
