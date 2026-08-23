-- The bytes a change was read from, kept so a reviewer can re-hash them.
--
-- `change_events.source_urls` cites where a claim came from, which proves
-- nothing: a provider can rewrite a page between the run and the review, and a
-- URL in a pull request body is then a link to something other than what the
-- agents read. Policy already fails closed on this — `has_verifiable_evidence`
-- is false without a hashed snapshot, so every run stops at HUMAN_REQUIRED —
-- but nothing on the ingest side has ever captured one. This is that capture.
--
-- The body is stored inline rather than in object storage, mirroring
-- `artifacts`. Release notes are kilobytes, the row is the thing being cited,
-- and one fewer bucket is one fewer credential in the sandbox's blast radius.
--
-- Provider text is untrusted input. Nothing here parses or executes it; the
-- table holds bytes and a digest.

BEGIN;

CREATE TABLE change_event_snapshots (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    change_event_id  uuid NOT NULL REFERENCES change_events(id) ON DELETE CASCADE,

    -- The page as cited, so a reviewer can compare the capture against what the
    -- provider serves today.
    source_url       text NOT NULL CHECK (source_url <> ''),

    -- Lowercase hex, checked here so an unhashed "snapshot" cannot be written.
    content_sha256   text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    media_type       text NOT NULL DEFAULT 'text/html',
    body             text NOT NULL,
    size_bytes       bigint CHECK (size_bytes >= 0),

    -- When the bytes were fetched, which is the honest `retrieved_at` for the
    -- SourceSnapshot this row becomes.
    retrieved_at     timestamptz NOT NULL DEFAULT now(),

    UNIQUE (change_event_id, source_url)
);

-- Evidence is served by digest: a pull request body cites
-- <api>/v1/evidence/<sha256>, and that has to resolve without knowing which
-- change it belonged to.
CREATE INDEX change_event_snapshots_by_digest ON change_event_snapshots (content_sha256);

COMMIT;
