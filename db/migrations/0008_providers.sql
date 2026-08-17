-- Vendor registry and ingest connections (provider.md).
--
-- Distinct from provider_usages (0007): those rows are facts about customer
-- repositories. These tables are the marketplace catalog.
-- Google Cloud is a system provider: both owner columns stay NULL.

CREATE TYPE provider_status AS ENUM (
    'draft',
    'live',
    'retired'
);

CREATE TYPE provider_category AS ENUM (
    'ai',
    'cloud',
    'payments',
    'communications',
    'data',
    'identity'
);

CREATE TYPE provider_connection_kind AS ENUM (
    'catalog',
    'changes'
);

CREATE TYPE provider_connection_status AS ENUM (
    'pending',
    'connected',
    'error',
    'disconnected'
);

CREATE TYPE provider_adapter AS ENUM (
    'service_usage',
    'bigquery_release_notes'
);

CREATE TYPE provider_service_status AS ENUM (
    'live',
    'preview',
    'deprecated'
);

CREATE TABLE providers (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                    text NOT NULL UNIQUE
                              CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    name                    text NOT NULL CHECK (length(btrim(name)) > 0),
    website                 text,
    contact_email           text,
    contact_url             text,
    category                provider_category NOT NULL,
    description             text NOT NULL,
    owner_user_id           uuid REFERENCES users (id),
    owner_organization_id   uuid,
    verified                boolean NOT NULL DEFAULT false,
    status                  provider_status NOT NULL DEFAULT 'draft',
    hq                      text,
    since                   date,
    console_url             text,
    docs_url                text,
    status_url              text,
    logo_url                text,
    featured_products       text[] NOT NULL DEFAULT '{}',
    registered_at           timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    retired_at              timestamptz,
    CONSTRAINT providers_owner_or_system CHECK (
        owner_organization_id IS NULL
        OR owner_user_id IS NOT NULL
    )
);

CREATE INDEX providers_status_live
    ON providers (status)
    WHERE retired_at IS NULL;

CREATE TABLE provider_connections (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id      uuid NOT NULL REFERENCES providers (id),
    kind             provider_connection_kind NOT NULL,
    adapter          provider_adapter NOT NULL,
    source_url       text NOT NULL,
    canonical_url    text NOT NULL,
    parsed           jsonb NOT NULL,
    status           provider_connection_status NOT NULL DEFAULT 'pending',
    last_error       text,
    snapshot_sha256  text,
    fetched_at       timestamptz,
    connected_at     timestamptz,
    disconnected_at  timestamptz,
    created_by       uuid REFERENCES users (id),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX provider_connections_one_live
    ON provider_connections (provider_id, kind)
    WHERE disconnected_at IS NULL;

CREATE TABLE provider_services (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id         uuid NOT NULL REFERENCES providers (id),
    connection_id       uuid NOT NULL REFERENCES provider_connections (id),
    external_id         text NOT NULL,
    name                text NOT NULL,
    slug                text NOT NULL,
    product             text NOT NULL,
    service_group       text NOT NULL,
    summary             text NOT NULL,
    status              provider_service_status NOT NULL,
    identifiers         text[] NOT NULL,
    docs_url            text,
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    retired_at          timestamptz,
    UNIQUE (provider_id, external_id)
);

CREATE INDEX provider_services_live
    ON provider_services (provider_id)
    WHERE retired_at IS NULL;

CREATE TABLE provider_change_notes (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id         uuid NOT NULL REFERENCES providers (id),
    connection_id       uuid NOT NULL REFERENCES provider_connections (id),
    external_id         text NOT NULL,
    product             text NOT NULL,
    kind                text NOT NULL,
    release_note_type   text,
    title               text NOT NULL,
    summary             text NOT NULL,
    source_url          text NOT NULL,
    published_at        timestamptz NOT NULL,
    ingested_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider_id, external_id)
);

CREATE INDEX provider_change_notes_page
    ON provider_change_notes (provider_id, published_at DESC);

CREATE TABLE project_provider_subscriptions (
    project_id      uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    provider_id     uuid NOT NULL REFERENCES providers (id),
    subscribed_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, provider_id)
);

-- System provider. No owner. Connecting endpoints is a later operator action.
INSERT INTO providers (
    id, slug, name, website, contact_url, category, description,
    verified, status, hq, since, console_url, docs_url, status_url,
    logo_url, featured_products
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'google',
    'Google Cloud',
    'https://cloud.google.com',
    'https://cloud.google.com/contact',
    'cloud',
    'A suite of cloud services for compute, storage, data analytics, and machine learning.',
    true,
    'draft',
    '1600 Amphitheatre Parkway, Mountain View, CA',
    '2008-04-07',
    'https://console.cloud.google.com',
    'https://cloud.google.com/docs',
    'https://status.cloud.google.com',
    '/google-cloud.svg',
    ARRAY[
        'Vertex AI',
        'Gemini API',
        'Imagen',
        'Cloud Storage',
        'GKE',
        'Cloud Run',
        'BigQuery',
        'Cloud SQL'
    ]
);
