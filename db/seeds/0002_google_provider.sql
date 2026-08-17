-- Re-runnable Google Cloud provider profile. No owner.
-- Connections are not seeded; an operator pastes the catalog / changes URL.

INSERT INTO providers (
    id, slug, name, website, contact_email, contact_url, category, description,
    owner_user_id, owner_organization_id, verified, status, hq, since,
    console_url, docs_url, status_url, logo_url, featured_products
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'google',
    'Google Cloud',
    'https://cloud.google.com',
    NULL,
    'https://cloud.google.com/contact',
    'cloud',
    'A suite of cloud services for compute, storage, data analytics, and machine learning.',
    NULL,
    NULL,
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
)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    website = EXCLUDED.website,
    contact_email = EXCLUDED.contact_email,
    contact_url = EXCLUDED.contact_url,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    owner_user_id = NULL,
    owner_organization_id = NULL,
    verified = EXCLUDED.verified,
    hq = EXCLUDED.hq,
    since = EXCLUDED.since,
    console_url = EXCLUDED.console_url,
    docs_url = EXCLUDED.docs_url,
    status_url = EXCLUDED.status_url,
    logo_url = EXCLUDED.logo_url,
    featured_products = EXCLUDED.featured_products,
    updated_at = now();
