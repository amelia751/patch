-- Which remediator is supposed to perform a run.
--
-- A warm worker polls for RECEIVED rows, and until now "RECEIVED" was the whole
-- of the question. One database serves the deployment and every developer's
-- laptop through the Cloud SQL proxy, so a run started in the hosted console
-- could be claimed by whichever worker polled first — a laptop, if one happened
-- to be running. The lease made that safe (never two workers on one run) and not
-- correct: the run is performed somewhere nobody was watching, against a
-- checkout and a sandbox that belong to a different environment.
--
-- It also swept up rows no worker should touch at all. A test fixture that
-- inserts a RECEIVED run for a repository that does not exist was claimed and
-- begun within a second.
--
-- So the dispatcher writes down which lane it handed the run to, and a worker
-- claims only its own. An empty lane is claimable by nobody, which is the right
-- default for the two push lanes: a Cloud Run job execution and a local
-- subprocess are told which run to perform and do not poll for one.

BEGIN;

ALTER TABLE remediation_runs
    ADD COLUMN IF NOT EXISTS lane text NOT NULL DEFAULT '';

COMMENT ON COLUMN remediation_runs.lane IS
    'The warm worker lane meant to perform this run, written at dispatch. '
    'Matches PATCHAPI_REMEDIATION_WORKER_POOL on the worker that may claim it. '
    'Empty means no worker polls for this run: it was pushed to a named '
    'executor, or nothing was dispatched at all.';

-- The claim reads this index on every poll of every instance, so the lane is in
-- it rather than filtered after. Still partial: only RECEIVED rows are ever
-- claimable, and a lane of '' can never match a polling worker.
DROP INDEX IF EXISTS remediation_runs_claimable;

CREATE INDEX IF NOT EXISTS remediation_runs_claimable
    ON remediation_runs (lane, started_at)
    WHERE state = 'RECEIVED' AND lane <> '';

COMMIT;
