-- Say "live" for the thing that asks a surface, and keep "runtime" for code.
--
-- `probe` named two unrelated ideas in one codebase: asking a provider whether
-- an identifier still resolves, and the HTTP checks that keep a Cloud Run
-- revision serving. Reading a stack trace meant deciding which one a line meant.
--
-- `runtime` was the obvious replacement and is already taken: `usage_kind`
-- has `runtime_source` and an ImpactReport counts runtime hits, both meaning
-- "code that executes", which is a different thing again. `live` is free and
-- says what the check does — it asks the live surface.
--
-- Renames only. No column changes, no data movement: `change_event_identifiers.
-- live_status` already reads correctly and simply follows its type here.

ALTER TYPE probe_status RENAME TO live_status;

ALTER TABLE identifier_probes RENAME TO identifier_liveness;
ALTER INDEX identifier_probes_provider_checked
    RENAME TO identifier_liveness_provider_checked;

-- The status a finding carries when a live surface, not a date on a page,
-- proved the identifier gone.
ALTER TYPE finding_reason RENAME VALUE 'probe_404' TO 'live_gone';
