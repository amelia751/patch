-- One inbox card per Need-you finding (or verifier pause) per project.
--
-- `project_notifications` was a write-once log with no identity, so a refresh
-- could not upsert and a dismissed row could not stay dismissed. `dedupe_key`
-- is that identity. A user dismiss still wins: INSERT ON CONFLICT does nothing.

ALTER TABLE project_notifications
    ADD COLUMN dedupe_key text;

CREATE UNIQUE INDEX project_notifications_project_dedupe_key
    ON project_notifications (project_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL;
