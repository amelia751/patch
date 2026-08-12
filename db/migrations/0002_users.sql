-- App profile for a console user.
--
-- Identity Platform is the IdP. This table stores what the dashboard renders
-- (`User` in apps/web/src/lib/auth-context.tsx). Passwords, ID tokens, and
-- refresh tokens never land here.

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Firebase / Identity Platform localId. NULL until the account is linked.
    identity_platform_uid text UNIQUE,
    email text NOT NULL UNIQUE CHECK (position('@' IN email) > 1),
    display_name text NOT NULL,
    avatar_url text,
    email_verified boolean NOT NULL DEFAULT false,
    type user_type NOT NULL DEFAULT 'personal',
    settings jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_settings_is_object CHECK (jsonb_typeof(settings) = 'object')
);

-- One row per linked login provider. `User.github_id` / `github_username`
-- are the github row; they are not duplicated on `users`.
CREATE TABLE user_identities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider identity_provider NOT NULL,
    -- GitHub numeric id or Google `sub`, stored as text so providers share a column.
    provider_user_id text NOT NULL,
    username text,
    email text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_user_id),
    UNIQUE (user_id, provider)
);

CREATE INDEX user_identities_user_id_idx ON user_identities (user_id);
