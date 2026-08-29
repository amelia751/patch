-- Which remediation workers are on the air, and when each last said so.
--
-- The lease on `remediation_runs` records who is performing a run. It cannot
-- record that nobody is available to perform one, and those are the two
-- situations an operator most needs told apart. A run sitting at RECEIVED looks
-- identical in both: queued behind work a healthy worker is busy with, or
-- stranded because no worker is polling at all.
--
-- Observed: a worker's pooled connections to Cloud SQL died of idleness, the
-- poll loop blocked in `Pool.acquire()` with no timeout, and the process stayed
-- alive and silent for four hours. Two runs waited. The console counted upwards
-- and told the operator to check whether a worker was running, which was the
-- right thing to check and not something the console could answer.
--
-- A heartbeat is the standard answer and it is one row per instance. It is
-- diagnostic only: no claim reads it, and losing the table would slow nothing
-- down. Deliberately not the source of truth for anything, so a worker that
-- fails to write its heartbeat still performs runs.

BEGIN;

CREATE TABLE IF NOT EXISTS remediation_workers (
    worker_id   text PRIMARY KEY,
    lane        text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    -- The run this worker is performing, or NULL when it is idle and polling.
    -- Denormalized from the lease so one read answers "is anyone free".
    current_run uuid
);

COMMENT ON TABLE remediation_workers IS
    'Liveness of remediation workers, written on every poll. Diagnostic only: '
    'no claim consults it, and the run lease remains authoritative about who is '
    'performing a run.';

COMMENT ON COLUMN remediation_workers.last_seen_at IS
    'When this worker last completed a poll. Older than a few poll intervals '
    'means the instance is gone or wedged, which is why a RECEIVED run is not '
    'being claimed.';

CREATE INDEX IF NOT EXISTS remediation_workers_by_lane
    ON remediation_workers (lane, last_seen_at DESC);

COMMIT;
