# PatchAPI — provider registry and endpoint connections

**Version:** 2026-08-17
**Status:** Implemented. DDL is `db/migrations/0008_providers.sql`. Seed Google
with `./scripts/seed_google_provider.sh`. Authoritative applied DDL remains
[`db/migrations/`](./db/migrations/).
**Related:** [`roadmap.md`](./roadmap.md) §8 / §10.5 (intake + polling),
[`schema.md`](./schema.md) (eventual Postgres), [`docs/data-model.md`](./docs/data-model.md)
(storage split), [`packages/providers/`](./packages/providers/) (ChangeManifest
adapter — a different layer).

This document is the build for making `/provider` **live**: register a vendor,
connect a catalog URL, connect a changes URL, disconnect either, and persist
the result in Postgres. It is the file-by-file counterpart to the hardcoded
portal that currently writes nothing.

---

## 1. What this component is for

PatchAPI has two audiences that both say "provider" and must not share a table:

| Audience | Surface | Meaning |
|---|---|---|
| **Enterprise** | `/` Subscription tab | A project *watches* a vendor for deprecations |
| **Vendor** | `/provider` | A vendor *registers* and *connects ingest endpoints* |

A **provider** is an API vendor in the marketplace (`google`, later `acme-ai`).
It is not a PatchAPI console organization (`schema.md` §6.1) and not a GCP
organization. Console orgs own projects and BYOK keys. Providers own catalogs.

**Google Cloud is a system provider.** Seed it. Do not invent a Google employee
as `created_by`. Do not assign `owner_user_id` or `owner_organization_id`.
Nobody from Google logs into PatchAPI to publish Imagen retirements. PatchAPI
operators connect the two public endpoints; enterprise projects subscribe.

A registered third-party vendor *does* have an owner: the signed-in user who
submitted the register form. Until `organizations` exists, that owner is a
user, not an org. Leave `owner_organization_id` NULL.

### Non-goals

- Publishing a service by hand. Services come from a connected catalog URL.
- Inventing Project / Dataset / Table form fields. Those are parsed from the
  one link the human pasted.
- Giving a provider agent unrestricted source access. Connected endpoints are
  untrusted input (`roadmap.md` constraint 4).
- Merging, deploying, or rotating secrets.
- Waiting on `organizations` (`schema.md` 0008). Providers do not need it.

---

## 2. Where the code is today

Honest inventory. Do not rewrite working ingest; persist it.

| Path | What it does | Gap |
|---|---|---|
| `GET /api/providers/google` | Serves `packages/state/data/google_services.json` | No provider row. No connection row. Hardcoded slug. |
| `GET /api/providers/google/changes` | Serves `packages/state/data/google_release_notes.json` | Same. Filter is real; ownership is not. |
| `packages/state/gcp_catalog.py` | Service Usage client + snapshot load/refresh | Refresh writes a file, not Postgres. |
| `packages/state/google_release_notes.py` | BigQuery job + snapshot load/refresh | Table id is a constant, not a connection. |
| `apps/web/.../provider-portal.tsx` | Register dialog, Services / Changes tabs | Register is local state. Dialogs show Project / Dataset / Table / Fetched. No disconnect. |
| `apps/web/.../subscription-tab/` | Marketplace = Google Cloud only | Subscribe is `localStorage`. |
| `db/migrations/0007_provider_usages.sql` | Identifier inventory in *customer repos* | Unrelated. Do not store catalogs there. |
| `schema.md` §8 `change_events` | Normalized workflow object after Change Intelligence | Do not dump raw release notes into it. |

The JSON snapshots stay as **bootstrap evidence** until the first successful
live ingest for that connection. After that, Postgres is the read model and
GCS (or the local `data/` stand-in) holds the hashed snapshot the row points at.

---

## 3. Target UX

Both connection dialogs are the same chrome. Kind is the only difference.

### Disconnected

```text
Source
Paste the catalog (or changes) endpoint. Project, dataset, and table
are read from the URL.

[ https://…                                        ]

[ Cancel ]                         [ Connect ]
```

One field. The human pastes a link. Connect is disabled until the string is
non-empty. The client does not parse Project / Dataset / Table — the server
does, and 422s if it cannot.

### Connected

```text
Source
Imported from the destination endpoint.

[ https://serviceusage.googleapis.com/v1/projects/…/services  ↗ ]

[ Disconnect ]                     [ Done ]
```

The URL is the only fact on the card. It is the same string that was stored
(`source_url`), not a reconstructed host. No Project, Dataset, Table, or
Fetched rows. Those remain on the connection row for the pipeline and for
support logs; they are not a dialog.

Toolbar chip:

- **Connected** (green) when that kind has `status = connected`.
- **Connect** (neutral outline) when missing or `disconnected`.

Click opens the dialog above. Disconnect confirms, then `DELETE`s the
connection. The list for that tab goes empty. The last snapshot stays on disk
as evidence; it is not re-served.

### Register

`POST /api/providers` with the existing form (name, slug, website, contact
email, category, description, attestation). The dialog copy today says
"Hardcoded for now — nothing is written." That sentence goes away when the
route exists. Success returns the persisted profile; the portal loads it the
same way it loads Google.

Google is not created by this form. The seed row is already there. The
landing-page button "Open Google Cloud catalog" is `GET /api/providers/google`,
not a register.

---

## 4. URL parse rules

One module: `packages/state/provider_urls.py`. Fail closed. Do not guess a
project id. Do not default to the PatchAPI GCP project when the URL omitted
one.

### 4.1 Catalog — `kind = catalog`

Accepted shapes (first match wins):

| Input | Adapter | Parsed |
|---|---|---|
| `https://serviceusage.googleapis.com/v1/projects/{project}/services` | `service_usage` | `{project}` |
| same with query (`filter`, `pageSize`) | `service_usage` | `{project}` — query ignored |

`{project}` must match `^[a-z][a-z0-9-]{4,28}[a-z0-9]$` or a numeric project
number. Anything else is 422.

Not accepted (yet): Cloud Console API dashboard URLs, OpenAPI document URLs,
GitHub raw markdown. Those 422 with `unsupported_catalog_url`. A third-party
vendor cannot connect a random docs page and have us invent a service list.

### 4.2 Changes — `kind = changes`

Accepted shapes:

| Input | Adapter | Parsed |
|---|---|---|
| `https://console.cloud.google.com/bigquery?p={project}&d={dataset}&t={table}` | `bigquery_release_notes` | project, dataset, table |
| `https://console.cloud.google.com/bigquery?project={project}&ws=…!1s{project}!2s{dataset}!3s{table}` | `bigquery_release_notes` | same, from `ws` |
| `https://bigquery.googleapis.com/bigquery/v2/projects/{project}/datasets/{dataset}/tables/{table}` | `bigquery_release_notes` | same |
| `{project}.{dataset}.{table}` (three dotted idents, no scheme) | `bigquery_release_notes` | same |

The public Google table the portal already uses:

```text
https://console.cloud.google.com/bigquery?p=bigquery-public-data&d=google_cloud_release_notes&t=release_notes
```

parses to `bigquery-public-data.google_cloud_release_notes.release_notes`.
That is how Project / Dataset / Table disappear from the dialog: they are in
the link.

Not accepted: `cloud.google.com/release-notes` HTML, RSS, a Google Doc. 422
`unsupported_changes_url`. Changelog HTML is untrusted and unstructured; we
do not scrape it into identifiers.

### 4.3 Canonical `source_url`

Store the URL the human pasted, trimmed. Also store `canonical_url`, the
adapter's fetch target:

- catalog: `https://serviceusage.googleapis.com/v1/projects/{project}/services`
- changes: `bigquery-public-data.google_cloud_release_notes.release_notes`
  (qualified table, not a console permalink)

The dialog renders `source_url`. The job fetches `canonical_url`.

---

## 5. Schema

New migration **`db/migrations/0008_providers.sql`**. This takes the 0008 slot
[`schema.md` §14](./schema.md) reserved for `organizations`. Organizations
slide to 0009; `change_events` and later bump by one. Providers do not
reference `organizations`, so the slide is safe.

`provider_usages` (0007) stays the customer-repo inventory. These tables are
the **vendor catalog**.

### 5.1 Enums

```sql
CREATE TYPE provider_status AS ENUM (
  'draft',         -- registered, no live connection yet
  'live',          -- at least one connection is connected
  'retired'
);

CREATE TYPE provider_category AS ENUM (
  'ai', 'cloud', 'payments', 'communications', 'data', 'identity'
);

CREATE TYPE provider_connection_kind AS ENUM (
  'catalog',
  'changes'
);

CREATE TYPE provider_connection_status AS ENUM (
  'pending',       -- URL accepted, ingest not finished
  'connected',
  'error',
  'disconnected'
);

CREATE TYPE provider_adapter AS ENUM (
  'service_usage',
  'bigquery_release_notes'
);

CREATE TYPE provider_service_status AS ENUM (
  'live', 'preview', 'deprecated'
);
```

### 5.2 `providers`

```sql
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
  -- Both NULL = system provider (Google). Do not invent an owner.
  owner_user_id           uuid REFERENCES users (id),
  owner_organization_id   uuid,          -- NULL until organizations exists
  verified                boolean NOT NULL DEFAULT false,
  status                  provider_status NOT NULL DEFAULT 'draft',
  hq                      text,
  since                   date,
  console_url             text,
  docs_url                text,
  status_url              text,
  logo_url                text,
  registered_at           timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  retired_at              timestamptz,
  CONSTRAINT providers_owner_or_system CHECK (
    owner_organization_id IS NULL
    OR owner_user_id IS NOT NULL
  )
);

CREATE INDEX providers_status_live ON providers (status) WHERE retired_at IS NULL;
```

`owner_organization_id` has no FK in 0008. When `organizations` lands, a
follow-up `ALTER … ADD CONSTRAINT` attaches it. Google's seed row keeps both
owner columns NULL forever.

`verified` is an operator flag, not a self-serve checkbox. Google is
`verified = true`. A self-registered vendor is `false`.

### 5.3 `provider_connections`

One live row per `(provider_id, kind)`. Reconnect after disconnect inserts a
new row; the old row stays with `disconnected_at` set. That is the audit
trail. Do not upsert away a previous URL.

```sql
CREATE TABLE provider_connections (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id      uuid NOT NULL REFERENCES providers (id),
  kind             provider_connection_kind NOT NULL,
  adapter          provider_adapter NOT NULL,
  source_url       text NOT NULL,          -- exactly what was pasted
  canonical_url    text NOT NULL,          -- what the job fetches
  parsed           jsonb NOT NULL,         -- {project} or {project,dataset,table}
  status           provider_connection_status NOT NULL DEFAULT 'pending',
  last_error       text,
  snapshot_uri     text,                   -- file: or gs://
  snapshot_sha256  text,
  fetched_at       timestamptz,
  connected_at     timestamptz,
  disconnected_at  timestamptz,
  created_by       uuid REFERENCES users (id),   -- NULL when seeded
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

-- At most one non-disconnected connection per kind.
CREATE UNIQUE INDEX provider_connections_one_live
  ON provider_connections (provider_id, kind)
  WHERE disconnected_at IS NULL;
```

`parsed` examples:

```json
{"project": "amelia-patchapi"}
{"project": "bigquery-public-data", "dataset": "google_cloud_release_notes", "table": "release_notes"}
```

Never store credentials. Service Usage and BigQuery use the existing
`.secrets/gcp-service-account.json` / ADC path already used by
`refresh_google_catalog`. A vendor URL that needs a customer token is
unsupported — fail closed.

### 5.4 `provider_services`

Materialized catalog. Replaces `google_services.json` as the Services tab
read model.

```sql
CREATE TABLE provider_services (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id         uuid NOT NULL REFERENCES providers (id),
  connection_id       uuid NOT NULL REFERENCES provider_connections (id),
  external_id         text NOT NULL,       -- e.g. aiplatform.googleapis.com
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
  ON provider_services (provider_id) WHERE retired_at IS NULL;
```

A refresh upserts on `(provider_id, external_id)`, bumps `last_seen_at`, and
sets `retired_at` on rows missing from the new snapshot. Do not delete.

### 5.5 `provider_change_notes`

Raw ingest cache. **Not** `change_events`. A note is changelog text. A
`change_events` row is a normalized, identifier-bearing object the Impact
Agent is allowed to see. Promotion is a later job (existing
`POST /v1/provider-checks` path). This table only answers the Changes tab.

```sql
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
```

Re-ingest of the same `external_id` updates summary/title in place. That is
a snapshot refresh, not a new detection. New `external_id`s are inserts.
Do not write `retired_identifiers` or `recommended_replacement` here — those
are Change Intelligence outputs, and inventing them from HTML is forbidden.

### 5.6 `project_provider_subscriptions`

Replaces `localStorage` key `patchapi.subscriptions.{projectId}`.

```sql
CREATE TABLE project_provider_subscriptions (
  project_id      uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  provider_id     uuid NOT NULL REFERENCES providers (id),
  subscribed_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, provider_id)
);
```

Subscribe is an enterprise action on `/`. It does not create connections.
Unsubscribe deletes the row. Historical `change_events` / runs are untouched.

### 5.7 Google seed

Same migration, after `CREATE TABLE`:

```sql
INSERT INTO providers (
  id, slug, name, website, contact_url, category, description,
  verified, status, hq, console_url, docs_url, status_url, logo_url, since
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
  'https://console.cloud.google.com',
  'https://cloud.google.com/docs',
  'https://status.cloud.google.com',
  '/google-cloud.svg',
  '2008-04-07'
);
```

`owner_user_id` and `owner_organization_id` omitted → NULL.
`status = draft` until an operator connects at least one endpoint. After the
first successful catalog or changes ingest, flip to `live`.

Do not seed connection rows. Connecting is an explicit action with a URL, even
for Google. The committed JSON files remain the 503 fallback only while no
`connected` row exists, so `/provider` does not go blank the day 0008 applies.

Stable UUID is intentional: frontend `prov_google` becomes this id (or keep
serving `slug=google` and stop using `prov_google`).

---

## 6. Pipelines

Four jobs. Same process as today's refresh functions; the new work is parse →
persist → retire.

```text
Register
  POST /api/providers
       → insert providers (owner = session user, status = draft)

Connect
  POST /api/providers/{slug}/connections  { kind, url }
       → parse URL (422 if unknown)
       → insert provider_connections (pending)
       → run ingest job
            success → status=connected, upsert services or notes,
                      providers.status = live
            failure → status=error, last_error set, no invented rows

Disconnect
  DELETE /api/providers/{slug}/connections/{kind}
       → disconnected_at = now(), status = disconnected
       → retire provider_services for that connection
       → stop serving notes from that connection
       → if no live connections remain, providers.status = draft

Subscribe (enterprise)
  PUT    /api/projects/{id}/providers/{slug}
  DELETE /api/projects/{id}/providers/{slug}
```

### 6.1 Catalog ingest (`service_usage`)

Reuse `packages/state/gcp_catalog.py`.

1. Read `parsed.project`.
2. Call the existing paged Service Usage client (1 QPS, already rate-limited).
3. Hash the normalized JSON. Write
   `packages/state/data/snapshots/{provider}/{connection_id}.json` locally;
   `gs://…/providers/{slug}/catalog/{sha}.json` when GCS is configured.
4. Upsert `provider_services`. Retire missing `external_id`s.
5. Store `snapshot_uri`, `snapshot_sha256`, `fetched_at` on the connection.

A page load **never** calls Google. `GET /api/providers/{slug}` reads
Postgres. Refresh happens on Connect and on the scheduler (below).

If Service Usage 403/404/429-exhausted: `status = error`, message safe to
show, no partial catalog. The previous connected snapshot stays until a
successful refresh replaces it — except on the *first* connect, when there
is no previous row.

### 6.2 Changes ingest (`bigquery_release_notes`)

Reuse `packages/state/google_release_notes.py`.

1. Read `parsed.{project,dataset,table}`. Substitute into the existing
   `SELECT … FROM \`{project}.{dataset}.{table}\`` — today `TABLE` is a
   constant.
2. Same 365-day window, same HTML strip, same kind map.
3. Hash + snapshot as above, under `…/changes/{sha}.json`.
4. Upsert `provider_change_notes`.
5. Do **not** insert `change_events`. Do **not** guess replacements.

Model Armor (`roadmap.md` § security table) sanitizes note text before it
is stored in `summary` / `title` once that template is wired. Until then,
store the stripped text and keep the `untrusted_provider_input` flag on the
GET payload.

### 6.3 Polling

`roadmap.md` §10.5: Cloud Scheduler every 15–60 minutes, hash, publish
`provider-change-detected` if the snapshot hash changed.

For this build, Connect *is* the poll. Add
`packages/state/provider_refresh.py` as the function Scheduler and
"Check now" both call. Do not invent a second fetcher.

`POST /v1/provider-checks` already exists and 503s because Pub/Sub is
missing. When the transport lands, it enqueues this same refresh for
`kind = changes`, then the Change Intelligence path. It does not parse URLs.

### 6.4 Who may mutate

| Action | Google (no owner) | Owned provider |
|---|---|---|
| GET profile / services / changes | signed-in console user | signed-in console user |
| POST register | n/a (seeded) | any signed-in user; slug unique |
| POST / DELETE connection | any signed-in user (operator) | `owner_user_id` only |
| subscribe | project owner / member | same |

A self-registered vendor cannot connect endpoints on `google`. An operator
can disconnect Google — the marketplace card remains; Services and Changes
go empty.

---

## 7. HTTP surface

Extend `packages/state/provider_routes.py`. Keep the Google-specific paths as
aliases for one release so the current portal does not break:

```text
GET    /api/providers/google            → GET /api/providers/google  (slug)
GET    /api/providers/google/changes    → unchanged query params
```

New:

```text
GET    /api/providers
GET    /api/providers/{slug}
POST   /api/providers
PATCH  /api/providers/{slug}            -- owner only; not for google
POST   /api/providers/{slug}/connections
GET    /api/providers/{slug}/connections
DELETE /api/providers/{slug}/connections/{kind}

GET    /api/providers/{slug}/services   -- page/filter; google alias stays
GET    /api/providers/{slug}/changes    -- existing q/kind/since/until/limit/offset

GET    /api/projects/{id}/providers
PUT    /api/projects/{id}/providers/{slug}
DELETE /api/projects/{id}/providers/{slug}
```

### 7.1 Register body

```json
{
  "name": "Acme AI",
  "slug": "acme-ai",
  "website": "https://acme.ai",
  "contact_email": "api@acme.ai",
  "category": "ai",
  "description": "Image APIs.",
  "attested": true
}
```

`attested: false` → 400. Slug collision → 409. Unauthenticated → 401.

### 7.2 Connect body

```json
{ "kind": "catalog", "url": "https://serviceusage.googleapis.com/v1/projects/amelia-patchapi/services" }
```

```json
{ "kind": "changes", "url": "https://console.cloud.google.com/bigquery?p=bigquery-public-data&d=google_cloud_release_notes&t=release_notes" }
```

Response (connected or pending):

```json
{
  "id": "…",
  "kind": "catalog",
  "adapter": "service_usage",
  "source_url": "https://serviceusage.googleapis.com/v1/projects/amelia-patchapi/services",
  "status": "connected",
  "parsed": { "project": "amelia-patchapi" }
}
```

`parsed` is on the API for the pipeline and for tests. The dialog does not
render it.

422 body when the URL is unknown:

```json
{ "error": "unsupported_catalog_url", "detail": "Could not read a Service Usage project from that link." }
```

Do not suggest a project id.

### 7.3 GET provider

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "slug": "google",
  "name": "Google Cloud",
  "owner": null,
  "verified": true,
  "status": "live",
  "connections": {
    "catalog": {
      "status": "connected",
      "source_url": "https://serviceusage.googleapis.com/v1/projects/…/services"
    },
    "changes": {
      "status": "disconnected",
      "source_url": null
    }
  }
}
```

`owner: null` is the Google case. Owned providers send
`{ "user_id": "…", "organization_id": null }`.

---

## 8. Files to create

| Path | Role |
|---|---|
| **`provider.md`** | This file. |
| `db/migrations/0008_providers.sql` | Enums, five tables, Google seed. |
| `db/seeds/providers_google.sql` | Optional re-seed for local reset; keep in sync with 0008. |
| `packages/schemas/provider.py` | Versioned `Provider`, `ProviderConnection`, `ConnectProvider`, `RegisterProvider`. Pin the schema version in `packages/schemas/config.py`. |
| `packages/state/provider_urls.py` | Parsers in §4. No I/O. |
| `packages/state/providers.py` | Postgres CRUD (same style as `packages/state/projects.py`). |
| `packages/state/provider_refresh.py` | Shared ingest entry: load connection → call catalog or notes refresh → persist. |
| `packages/state/tests/test_provider_urls.py` | Every accepted URL + every reject. |
| `packages/state/tests/test_providers.py` | Register, connect, disconnect, Google has no owner, unique live connection. |
| `packages/state/tests/test_provider_refresh.py` | File fixture → upsert; bad URL does not write services. |
| `apps/web/src/lib/providers.ts` | Typed fetch helpers for the new routes. |
| `apps/web/src/components/interface/provider/connection-dialog.tsx` | One dialog, `kind` prop. Connected = link + Disconnect. Disconnected = URL + Connect. |

---

## 9. Files to modify

| Path | Change |
|---|---|
| `schema.md` §4 map, §14 order | Insert `providers` / connections / services / notes / subscriptions. Slide organizations to 0009, `change_events` to 0010, runs to 0011, audit to 0012. State that Google has no owner. |
| `docs/data-model.md` | Add the five tables to the console-tenancy list. Snapshots stay in GCS; passwords still do not. |
| `packages/state/provider_routes.py` | Replace the google-only getters with slug routes + aliases. Add register / connections. |
| `packages/state/project_routes.py` | Subscribe / unsubscribe / list. |
| `packages/state/serve.py` | No new router if providers stay on `provider_router`. |
| `packages/state/gcp_catalog.py` | `refresh_google_catalog(project=…)` already takes a project — pass `parsed.project`. Add `persist_services(pool, connection, catalog)`. GET path: prefer Postgres when a live connection exists, else the committed JSON. |
| `packages/state/google_release_notes.py` | Stop hardcoding `TABLE`. Accept a qualified table. Persist notes the same way. |
| `packages/state/tests/test_gcp_catalog.py` | Assert the JSON fallback still works with zero connections. |
| `packages/state/tests/test_google_release_notes.py` | Parser-supplied table, not the constant. |
| `packages/schemas/__init__.py` | Export the new models. |
| `apps/web/.../provider-portal.tsx` | Register → `POST /api/providers`. Load profile from `GET /api/providers/{slug}`. Delete `CatalogSourceDialog` / `ReleaseNotesSourceDialog` extras. Use `connection-dialog.tsx`. Remove `GOOGLE_CLOUD_PROVIDER` as the source of truth (keep as a display fallback only until the seed is reachable). |
| `apps/web/.../provider/data.ts` | Keep types. Drop or shrink the hardcoded profile once GET works. |
| `apps/web/.../subscription-tab/` | Read/write ` /api/projects/{id}/providers`. Delete `localStorage` helper. |
| `apps/web/.../HowItWorksDialog` | Steps become Register → Connect catalog URL → Connect changes URL → enterprises subscribe. Not "Publish services". |

Do **not** modify `packages/providers/google/` for this. That package
normalizes a deprecation feed into a `ChangeManifest`. Connecting a BigQuery
table is intake, not normalization.

Do **not** put catalog rows in `provider_usages`.

---

## 10. Build order

One concern per commit. Do not open the UI onto routes that 404.

1. **DDL + seed.** `0008_providers.sql`. Apply locally. Test: Google row
   exists, both owner columns NULL, no connection rows.
2. **URL parsers + schema models.** `provider_urls.py`, `packages/schemas/provider.py`,
   tests. No HTTP yet.
3. **Store.** `packages/state/providers.py` — insert provider, insert/disconnect
   connection, upsert services/notes, subscribe. Unit tests against the
   migration.
4. **Refresh persist.** `provider_refresh.py` wires existing fetchers to the
   store. Offline tests use the committed JSON as a fake fetch result.
5. **HTTP.** Expand `provider_routes.py` + project subscribe. Alias
   `/api/providers/google` so the current portal keeps working.
6. **Portal live register.** `RegisterDialog` posts; on success `GET` the slug.
7. **One connection dialog.** Replace both source dialogs. Chip reflects
   `connections.{kind}.status`.
8. **Subscription tab.** Postgres instead of `localStorage`.
9. **Docs.** Update `schema.md` and `docs/data-model.md` in the same change
   as step 1 or immediately after — do not leave the migration order lying.

Scheduler / Pub/Sub / Model Armor / `change_events` promotion are out of
this sequence. They call `provider_refresh` when those planes exist.

---

## 11. Hard constraints (do not violate)

1. **Google has no owner.** Seed NULL. Tests must assert it.
2. **Do not invent.** Unparseable URL → 422. Failed fetch → `error`, empty
   write. Ambiguous adapter → 422, not a guessed `service_usage` call.
3. **Provider text is untrusted.** GET changes keeps
   `trust.classification = untrusted_provider_input`. Never treat a note as
   a typed shutdown catalog (`google_release_notes.py` already says this).
4. **No secrets in the row.** No tokens, no service-account JSON, no
   `parsed` field that is actually a key.
5. **Postgres is authoritative** for register / connection / subscribe
   state. JSON files are bootstrap and evidence, not the workflow database.
6. **Stop at the PR.** Connecting an endpoint does not open a run. A later
   hash change may.
7. **Narrow credentials.** Ingest uses the existing PatchAPI GCP identity.
   Vendors do not upload keys.
8. **Do not assign `change_events` from a raw note.** Identifiers and
   replacements are Change Intelligence's job. A FEATURE row in BigQuery is
   not a retirement.

---

## 12. Acceptance

The process is live when all of the following are true on a local stack
(Docker Postgres + `./scripts/serve_control_api.sh` + `apps/web`):

1. `GET /api/providers` returns Google with `"owner": null`.
2. Signed-in `POST /api/providers` with a new slug returns 201 and a
   subsequent `GET` shows `owner.user_id` = that session.
3. Connecting
   `https://serviceusage.googleapis.com/v1/projects/{real-project}/services`
   on Google fills the Services tab from Postgres, not from editing
   `google_services.json` by hand.
4. Connecting the BigQuery console link on Google fills the Changes tab.
   The dialog shows that one link. It does not show Project / Dataset / Table.
5. Disconnect on either tab empties that list and the chip becomes Connect.
   Reconnect with the same URL works (new connection row).
6. Subscribe on `/` survives a reload without `localStorage`.
7. A garbage URL returns 422 and writes zero `provider_services` rows.
8. `packages/providers/google` tests still pass unchanged.

Until those hold, the portal remains a viewer of committed snapshots and
this file is the plan, not the product.
