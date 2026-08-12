-- Tenancy: who PatchAPI acts for, and which repositories are in scope.

CREATE TABLE organizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    display_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- A GitHub App installation. The row records which installation to ask the
-- GitHub tool service to act as; the private key and installation tokens never
-- touch this database (constraint 8).
CREATE TABLE installations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    vcs_provider text NOT NULL DEFAULT 'github',
    external_installation_id text NOT NULL,
    account_login text NOT NULL,
    suspended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (vcs_provider, external_installation_id)
);

CREATE INDEX installations_organization_id_idx ON installations (organization_id);

CREATE TABLE repositories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    installation_id uuid REFERENCES installations (id) ON DELETE SET NULL,
    owner text NOT NULL,
    name text NOT NULL,
    default_branch text NOT NULL DEFAULT 'main',
    owner_team text,
    criticality criticality_tier NOT NULL DEFAULT 'medium',
    -- Commit the inventory in `api_usages` was last built from. A run compares
    -- its base SHA against this to decide whether the index is stale.
    indexed_sha text,
    indexed_at timestamptz,
    archived boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner, name)
);

CREATE INDEX repositories_organization_id_idx ON repositories (organization_id);
