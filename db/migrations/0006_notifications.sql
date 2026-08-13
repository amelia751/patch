-- In-app notifications for a console project.
--
-- Matches `Notification` in apps/web/src/components/interface/shared/notifications.tsx.
-- GET /api/notifications?project_id=&limit=20 returns `{ notifications: [...] }`.
-- An empty list is a real answer: a new import has nothing to show yet.

CREATE TYPE notification_kind AS ENUM (
    'success',
    'pending',
    'question',
    'info',
    'error'
);

CREATE TABLE project_notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    kind notification_kind NOT NULL DEFAULT 'info',
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    message text NOT NULL,
    priority text NOT NULL DEFAULT 'normal',
    read_at timestamptz,
    dismissed_at timestamptz,
    details jsonb,
    questions jsonb,
    actions jsonb NOT NULL DEFAULT '[]'::jsonb,
    contract_ids text[] NOT NULL DEFAULT '{}',
    source_commit text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX project_notifications_project_id_created_at_idx
    ON project_notifications (project_id, created_at DESC);
