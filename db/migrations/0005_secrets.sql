-- Secret *metadata* the Configure tab lists. The secret value lives in
-- Secret Manager (or AWS Secrets Manager); this row only stores the name and
-- the remote pointer (`secret_arn`). There is no value / ciphertext column
-- on purpose.

CREATE TABLE project_secrets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    workspace_id uuid REFERENCES workspaces (id) ON DELETE SET NULL,
    secret_name text NOT NULL CHECK (length(btrim(secret_name)) > 0),
    -- AWS Secrets Manager ARN, or a GCP Secret Manager resource name.
    secret_arn text,
    type text NOT NULL DEFAULT 'api_key',
    status secret_row_status NOT NULL DEFAULT 'configured',
    referenced_by text[] NOT NULL DEFAULT '{}',
    last_rotated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, secret_name)
);

CREATE INDEX project_secrets_project_id_idx ON project_secrets (project_id);
