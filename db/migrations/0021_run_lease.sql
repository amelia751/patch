-- Leasing a run to one warm worker.
--
-- A remediation used to be one Cloud Run job execution per run, and the run id
-- was an argument to it, so nothing had to decide who was performing a run:
-- exactly one container existed and it had been told. Measured on the Cloud Run
-- task API, that container waited 136s for an instance and then lived 5.6s, and
-- the wait was paid twice because an operator hold ends one execution and
-- Continue starts another.
--
-- A warm worker pool removes both waits and introduces the question the job
-- model never had to answer: several always-on instances can see the same
-- RECEIVED row. `state = 'RECEIVED'` is the whole queue — `open_run` puts a new
-- run, a restart and a resume all into it — so the lease is what turns that
-- queue into work exactly one instance is doing.
--
-- A lease is not a claim on the state machine. The orchestrator still owns every
-- transition; these two columns only record which instance is driving it, so a
-- second instance skips the row and an instance that died before doing any work
-- does not strand it.

BEGIN;

ALTER TABLE remediation_runs
    ADD COLUMN IF NOT EXISTS leased_by text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS leased_at timestamptz;

COMMENT ON COLUMN remediation_runs.leased_by IS
    'The worker instance performing this run. Empty when no worker holds it. '
    'Set under FOR UPDATE SKIP LOCKED so two instances cannot take one run.';

COMMENT ON COLUMN remediation_runs.leased_at IS
    'When the lease was taken. A lease older than the worker''s lease window on '
    'a run still at RECEIVED is reclaimable: the holder died before it started.';

-- The claim runs on every poll of every instance, so it reads an index rather
-- than the table. Partial, because only RECEIVED rows are ever claimable.
CREATE INDEX IF NOT EXISTS remediation_runs_claimable
    ON remediation_runs (started_at)
    WHERE state = 'RECEIVED';

COMMIT;
