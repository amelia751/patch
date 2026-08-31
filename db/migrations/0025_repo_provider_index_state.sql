-- Per-provider index completion, so onboarding a provider is not a global reindex.
--
-- `repo_index_state` is keyed `(repository, branch)` and records the shard: the
-- tree is indexed once regardless of who is asking. That is still true, and this
-- migration does not touch it.
--
-- What is *not* a property of the tree is the question a scan asked of it. Layer
-- A searches for one provider's identifiers and family patterns, and the answer
-- "no usages" only means "no usages of what we looked for". The freshness check
-- compared `indexer_version` and `scanner_version` alone, so a repository
-- indexed for Google read as current the moment a second provider was
-- registered, and was skipped — reporting a repository nobody had ever searched
-- for Stripe as a repository with no Stripe usage. Those two are the same row
-- downstream, and only one of them is true.
--
-- `search_intent` is the fix. It hashes what a scan would look for — the
-- descriptor version, the queried family patterns, the pinned literals — so
-- widening a descriptor invalidates exactly the scans whose question changed.
-- Adding a provider invalidates nothing that already ran for another one.

CREATE TABLE repo_provider_index_state (
    repository       text        NOT NULL CHECK (repository ~ '^[^/]+/[^/]+$'),
    branch           text        NOT NULL,
    provider         text        NOT NULL CHECK (length(btrim(provider)) > 0),
    indexed_sha      text        NOT NULL,
    -- sha256 of the resolved pattern and identifier set. Not a version number:
    -- an operator who widens a watchlist should not also have to remember to
    -- bump something, and a hash cannot be forgotten.
    search_intent    text        NOT NULL,
    indexer_version  text        NOT NULL,
    scanner_version  text        NOT NULL,
    -- `full_tree` or `changed_paths`. A delta pass proves the provider was
    -- searched for in the files a push touched, never that the whole tree was,
    -- so it must not satisfy a first-time full index for that provider.
    scope            text        NOT NULL DEFAULT 'full_tree',
    indexed_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (repository, branch, provider),
    FOREIGN KEY (repository, branch)
        REFERENCES repo_index_state (repository, branch) ON DELETE CASCADE
);

CREATE INDEX repo_provider_index_state_provider
    ON repo_provider_index_state (provider, indexed_at DESC);

COMMENT ON TABLE repo_provider_index_state IS
    'One row per (repository, branch, provider) naming the last scan that '
    'completed for that provider and the question it asked. Sibling of '
    'repo_index_state, which stays per-(repository, branch) because the shard '
    'is built once however many providers are searched for in it.';

COMMENT ON COLUMN repo_provider_index_state.search_intent IS
    'sha256 over the provider descriptor version, its queried family patterns '
    'and its pinned identifiers. A stored inventory is current for a provider '
    'only when this still matches, so widening a watchlist re-scans and '
    'registering an unrelated provider does not.';

-- Backfill: every target already indexed was indexed for Google, under whatever
-- descriptor shipped at the time. The intent is left empty rather than guessed,
-- which reads as "unknown question" and re-scans once on the next event. That is
-- the safe direction — the alternative is claiming a Google scan asked today's
-- question when nobody recorded what it asked.
INSERT INTO repo_provider_index_state (
    repository, branch, provider, indexed_sha, search_intent,
    indexer_version, scanner_version, scope, indexed_at
)
SELECT repository, branch, 'google', indexed_sha, '',
       indexer_version, scanner_version, 'full_tree', COALESCE(last_full_index, now())
FROM repo_index_state
WHERE indexed_sha IS NOT NULL
ON CONFLICT (repository, branch, provider) DO NOTHING;
