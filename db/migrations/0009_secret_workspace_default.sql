-- Secrets belong to a workspace. `/` is that workspace's repo root, not a
-- project-wide shared bucket. Attach leftover NULL workspace_id rows to the
-- project's root workspace (empty path first, else oldest).

UPDATE project_secrets s
SET workspace_id = (
    SELECT w.id
    FROM workspaces w
    WHERE w.project_id = s.project_id
    ORDER BY
        (w.workspace_path IS NULL OR btrim(coalesce(w.workspace_path, '')) = '') DESC,
        w.created_at ASC
    LIMIT 1
)
WHERE s.workspace_id IS NULL
  AND EXISTS (
      SELECT 1 FROM workspaces w WHERE w.project_id = s.project_id
  );
