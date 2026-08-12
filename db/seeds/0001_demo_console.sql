-- DEMO SEED DATA — not production truth.
--
-- Console tenancy only: one user, a GitHub App connection, one imported
-- project pointing at the pinned Egaki fork. No password hashes, no GitHub
-- tokens, no secret values.
--
-- Every row uses a UUID in the reserved `5eedda7a-` prefix.
-- Re-runnable: fixed keys plus upserts.

INSERT INTO users (
    id, identity_platform_uid, email, display_name, avatar_url,
    email_verified, type, settings
)
VALUES (
    '5eedda7a-0001-4000-8000-000000000001',
    NULL,
    'demo@patchapi.invalid',
    'PatchAPI Demo User (seed data)',
    NULL,
    true,
    'personal',
    '{"theme": "dark"}'::jsonb
)
ON CONFLICT (id) DO UPDATE
SET email = EXCLUDED.email,
    display_name = EXCLUDED.display_name,
    email_verified = EXCLUDED.email_verified,
    settings = EXCLUDED.settings,
    updated_at = now();

INSERT INTO user_identities (
    id, user_id, provider, provider_user_id, username, email
)
VALUES (
    '5eedda7a-0002-4000-8000-000000000001',
    '5eedda7a-0001-4000-8000-000000000001',
    'github',
    '0',
    'amelia751',
    'demo@patchapi.invalid'
)
ON CONFLICT (id) DO UPDATE
SET username = EXCLUDED.username,
    email = EXCLUDED.email;

INSERT INTO github_connections (
    id, user_id, installation_id, account_login, account_type
)
VALUES (
    '5eedda7a-0003-4000-8000-000000000001',
    '5eedda7a-0001-4000-8000-000000000001',
    'seed-installation-0',
    'amelia751',
    'User'
)
ON CONFLICT (id) DO UPDATE
SET account_login = EXCLUDED.account_login,
    updated_at = now();

INSERT INTO projects (
    id, owner_id, name, description, status, cloud_provider
)
VALUES (
    '5eedda7a-0004-4000-8000-000000000001',
    '5eedda7a-0001-4000-8000-000000000001',
    'egaki',
    'Pinned demo fork (seed data)',
    'draft',
    'gcp'
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    status = EXCLUDED.status,
    cloud_provider = EXCLUDED.cloud_provider,
    updated_at = now();

INSERT INTO project_repositories (
    id, project_id, kind, name, full_name, default_branch, private, html_url
)
VALUES (
    '5eedda7a-0005-4000-8000-000000000001',
    '5eedda7a-0004-4000-8000-000000000001',
    'backend',
    'egaki',
    'amelia751/egaki',
    'main',
    false,
    'https://github.com/amelia751/egaki'
)
ON CONFLICT (id) DO UPDATE
SET full_name = EXCLUDED.full_name,
    default_branch = EXCLUDED.default_branch,
    html_url = EXCLUDED.html_url;

INSERT INTO workspaces (
    id, project_id, repository_id, name, repo_url, repo_branch,
    workspace_path, environment
)
VALUES (
    '5eedda7a-0006-4000-8000-000000000001',
    '5eedda7a-0004-4000-8000-000000000001',
    '5eedda7a-0005-4000-8000-000000000001',
    'egaki Workspace',
    'https://github.com/amelia751/egaki.git',
    'main',
    NULL,
    'dev'
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    repo_url = EXCLUDED.repo_url,
    repo_branch = EXCLUDED.repo_branch,
    environment = EXCLUDED.environment,
    updated_at = now();
