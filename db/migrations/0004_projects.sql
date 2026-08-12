-- Console projects and the GitHub repos / workspaces they import.
--
-- Matches `Project` in apps/web (id, name, status, owner_id, cloud_provider,
-- repositories[]) and the import payloads:
--   POST /api/projects/                        { name }
--   POST /api/projects/{id}/workspaces/import-repo
--       { name, repo_url, repo_branch, workspace_path, environment }
--   POST /api/projects/{id}/repositories       { github_repo_full_name }

CREATE TABLE projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    team_id uuid,
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    description text,
    status project_status NOT NULL DEFAULT 'draft',
    cloud_provider cloud_provider,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX projects_owner_id_idx ON projects (owner_id);

CREATE TABLE project_repositories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    -- GitHub's own repo id when known; listing comes from the GitHub API, not
    -- a cache of every repo the user can see.
    github_repo_id bigint,
    kind repository_kind NOT NULL DEFAULT 'backend',
    name text NOT NULL,
    full_name text NOT NULL CHECK (full_name ~ '^[^/]+/[^/]+$'),
    default_branch text NOT NULL DEFAULT 'main',
    private boolean,
    html_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, full_name)
);

CREATE INDEX project_repositories_project_id_idx ON project_repositories (project_id);

CREATE TABLE workspaces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    repository_id uuid REFERENCES project_repositories (id) ON DELETE SET NULL,
    name text NOT NULL,
    repo_url text NOT NULL,
    repo_branch text NOT NULL DEFAULT 'main',
    -- Optional subfolder inside the repo ("backend entry point"). NULL = repo root.
    workspace_path text,
    environment text NOT NULL DEFAULT 'dev',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX workspaces_project_id_idx ON workspaces (project_id);
