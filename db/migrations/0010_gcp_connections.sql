-- Viewer service-account JSON lives in Secret Manager. This row stores the
-- pointer and non-secret metadata only, scoped to an imported repo workspace.

CREATE TABLE gcp_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    workspace_id uuid REFERENCES workspaces (id) ON DELETE SET NULL,
    environment text NOT NULL DEFAULT 'development'
        CHECK (environment IN ('development', 'staging', 'production')),
    gcp_project_id text NOT NULL CHECK (length(btrim(gcp_project_id)) > 0),
    gcp_project_number text,
    service_account_email text NOT NULL CHECK (position('@' in service_account_email) > 1),
    default_region text NOT NULL DEFAULT 'us-central1',
    secret_arn text NOT NULL CHECK (length(btrim(secret_arn)) > 0),
    last_validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, workspace_id, environment)
);

CREATE INDEX gcp_connections_project_id_idx ON gcp_connections (project_id);
