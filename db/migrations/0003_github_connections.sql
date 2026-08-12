-- GitHub App installation used for repo listing and import.
--
-- Distinct from `user_identities` (OAuth login). The UI flag
-- `github_app_installed` is "a row exists here", not a column on `users`.
-- Installation tokens and the App private key never touch this database.

CREATE TABLE github_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
    installation_id text NOT NULL UNIQUE,
    account_login text NOT NULL,
    account_type text NOT NULL DEFAULT 'User'
        CHECK (account_type IN ('User', 'Organization')),
    suspended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
