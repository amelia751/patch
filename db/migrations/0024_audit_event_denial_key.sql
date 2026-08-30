-- The identity of a refusal, so `audit_events` can hold denials as well as acts.
--
-- The table was built for both — `audit_events_denied` indexes exactly the rows
-- this migration exists to make writable — and has only ever held successful
-- pull requests. What the product refuses lives in `run_trace_events`, which is
-- scoped to one run, is cleared when that run restarts, and therefore cannot
-- answer "what did PatchAPI refuse to do, across every run, last month".
--
-- Mirroring a refusal here means writing it more than once. A run that parks
-- for the operator and continues screens its intake again and evaluates policy
-- again; a restarted run does both from the beginning. `dedupe_key` makes that
-- repetition free.
--
-- It names the refusal and not the occasion: the run, the gate, the act, and the
-- rule that fired. A replayed execution therefore conflicts with itself, and the
-- audit keeps one row per thing a run was stopped from doing rather than one row
-- per time it was stopped. How often a model retried a refused command is a
-- property of that run's worklog, and stays there.
--
-- Nullable because a success has no such identity and needs none: whether a pull
-- request may be opened at all is decided by `idempotency_keys` before the call,
-- so the audit row that follows it cannot be a duplicate.

ALTER TABLE audit_events
    ADD COLUMN dedupe_key text;

-- Partial so the index covers denials only. Every row written before this
-- migration, and every successful act after it, leaves the column NULL.
CREATE UNIQUE INDEX audit_events_dedupe_key
    ON audit_events (dedupe_key)
    WHERE dedupe_key IS NOT NULL;

COMMENT ON COLUMN audit_events.dedupe_key IS
    'Identity of one refusal inside one run: the gate that refused, the act it '
    'refused, and the rule or reason code that fired. NULL for events with no '
    'such identity. A retried or resumed run conflicts here instead of counting '
    'its denials twice.';
