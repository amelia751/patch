-- DEMO SEED DATA — not production truth.
--
-- Every row this script writes uses a UUID in the reserved `5eedda7a-` prefix
-- so seeded rows are identifiable by primary key alone, and the seed
-- organization's display name says so in plain text.
--
-- Sources for the values below (nothing here is invented):
--   demo/fixtures/google-imagen4-deprecation.json  — the provider change
--   demo/egaki/baseline.json                       — the pinned fork and SHA
--   demo/egaki/artifacts/imagen-inventory.json     — the file/line usages
--
-- The seeded pull request points at `example.invalid`, a reserved domain that
-- can never resolve. PatchAPI has not opened a real pull request; a placeholder
-- github.com URL here would read as evidence that it had.
--
-- Re-runnable: fixed keys plus upserts, and the two append-only tables
-- (`run_state_transitions`, `audit_events`) delete their own seeded rows first.

-- ---------------------------------------------------------------- tenancy ---

INSERT INTO organizations (id, slug, display_name)
VALUES (
    '5eedda7a-0001-4000-8000-000000000001',
    'patchapi-demo',
    'PatchAPI Demo Organization (seed data)'
)
ON CONFLICT (id) DO UPDATE
SET slug = EXCLUDED.slug,
    display_name = EXCLUDED.display_name,
    updated_at = now();

INSERT INTO installations (
    id, organization_id, vcs_provider, external_installation_id, account_login
)
VALUES (
    '5eedda7a-0002-4000-8000-000000000001',
    '5eedda7a-0001-4000-8000-000000000001',
    'github',
    'seed-installation-0',
    'amelia751'
)
ON CONFLICT (id) DO UPDATE
SET account_login = EXCLUDED.account_login,
    updated_at = now();

INSERT INTO repositories (
    id, organization_id, installation_id, owner, name, default_branch,
    owner_team, criticality, indexed_sha, indexed_at
)
VALUES
(
    '5eedda7a-0003-4000-8000-000000000001',
    '5eedda7a-0001-4000-8000-000000000001',
    '5eedda7a-0002-4000-8000-000000000001',
    'amelia751',
    'egaki',
    'main',
    'media-platform',
    'medium',
    'c09e1a44200ff5e951746e013035e68aeb3a14b1',
    '2026-08-11T23:41:00Z'
),
(
    '5eedda7a-0003-4000-8000-000000000002',
    '5eedda7a-0001-4000-8000-000000000001',
    '5eedda7a-0002-4000-8000-000000000001',
    'amelia751',
    'image-studio',
    'main',
    'growth',
    'high',
    'c09e1a44200ff5e951746e013035e68aeb3a14b1',
    '2026-08-11T23:41:00Z'
)
ON CONFLICT (id) DO UPDATE
SET owner_team = EXCLUDED.owner_team,
    criticality = EXCLUDED.criticality,
    indexed_sha = EXCLUDED.indexed_sha,
    indexed_at = EXCLUDED.indexed_at,
    updated_at = now();

-- ------------------------------------------------------ API usage inventory ---
-- Real hits from the pinned Egaki SHA. Confidence 1.0 marks exact-literal
-- matches; the family-handling row is a lower-confidence semantic finding.

INSERT INTO api_usages (
    repository_id, provider, identifier, surface, file_path, line_start,
    detection_layer, confidence, observed_sha
)
VALUES
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-generate-001',
 NULL, 'cli/src/cli/cli.ts', 418, 'A_DETERMINISTIC', 1.00,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-generate-001',
 NULL, 'cli/src/cli/cli.ts', 1627, 'A_DETERMINISTIC', 1.00,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-generate-001',
 NULL, 'cli/src/cli/model-catalog.ts', 292, 'A_DETERMINISTIC', 1.00,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-generate-001',
 NULL, 'cli/src/cli/generate.test.ts', 38, 'A_DETERMINISTIC', 1.00,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-ultra-generate-001',
 NULL, 'cli/src/cli/cli.ts', 408, 'A_DETERMINISTIC', 1.00,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-ultra-generate-001',
 NULL, 'cli/src/cli/model-catalog.ts', 299, 'A_DETERMINISTIC', 1.00,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-fast-generate-001',
 NULL, 'cli/src/cli/generate.ts', 53, 'A_DETERMINISTIC', 1.00,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-fast-generate-001',
 NULL, 'cli/src/cli/model-catalog.ts', 306, 'A_DETERMINISTIC', 1.00,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000001', 'google', 'imagen-4.0-generate-001',
 'imagen-* family option handling (seed, aspectRatio, numberOfImages)',
 'cli/src/cli/generate.ts', 55, 'C_SEMANTIC', 0.90,
 'c09e1a44200ff5e951746e013035e68aeb3a14b1'),
('5eedda7a-0003-4000-8000-000000000002', 'google', 'imagen-4.0-generate-001',
 'model id referenced in provider configuration', 'src/providers/google.ts', 12,
 'A_DETERMINISTIC', 1.00, 'c09e1a44200ff5e951746e013035e68aeb3a14b1')
ON CONFLICT (repository_id, provider, identifier, file_path, line_start) DO UPDATE
SET surface = EXCLUDED.surface,
    detection_layer = EXCLUDED.detection_layer,
    confidence = EXCLUDED.confidence,
    observed_sha = EXCLUDED.observed_sha,
    last_seen_at = now(),
    removed_at = NULL;

-- ----------------------------------------------------------- change event ---
-- `source_sha256` is NULL on purpose: the fixture records the provider snapshot
-- as NOT_CAPTURED. A run that needs provider evidence must fail closed here.

INSERT INTO change_events (
    id, provider, external_id, change_kind, title, source_urls, source_sha256,
    affected_identifiers, recommended_replacement, effective_at,
    manifest_schema_version, manifest
)
VALUES (
    '5eedda7a-0004-4000-8000-000000000001',
    'google',
    'imagen4-retirement-2026-08-17',
    'MODEL_RETIREMENT',
    'Imagen 4 model family retirement',
    ARRAY[
        'https://ai.google.dev/gemini-api/docs/deprecations',
        'https://ai.google.dev/gemini-api/docs/changelog',
        'https://ai.google.dev/gemini-api/docs/models/imagen'
    ],
    NULL,
    ARRAY[
        'imagen-4.0-generate-001',
        'imagen-4.0-ultra-generate-001',
        'imagen-4.0-fast-generate-001'
    ],
    'gemini-3.1-flash-image',
    '2026-08-17',
    '1.0.0',
    '{
       "fixture": "demo/fixtures/google-imagen4-deprecation.json",
       "trust": "untrusted_provider_input",
       "source_snapshot": {"status": "NOT_CAPTURED"}
     }'::jsonb
)
ON CONFLICT (id) DO UPDATE
SET title = EXCLUDED.title,
    affected_identifiers = EXCLUDED.affected_identifiers,
    recommended_replacement = EXCLUDED.recommended_replacement,
    manifest = EXCLUDED.manifest;

-- ------------------------------------------------------------------- runs ---

INSERT INTO remediation_runs (
    id, change_event_id, repository_id, state, base_sha, trace_id,
    attempt_budget, attempts_used, started_at, ended_at
)
VALUES
(
    '5eedda7a-0005-4000-8000-000000000001',
    '5eedda7a-0004-4000-8000-000000000001',
    '5eedda7a-0003-4000-8000-000000000001',
    'PR_CREATED',
    'c09e1a44200ff5e951746e013035e68aeb3a14b1',
    'seed-trace-egaki-0001',
    3, 2,
    '2026-08-11T23:45:00Z',
    '2026-08-11T23:58:00Z'
),
-- Fail-closed example: high-criticality repository, analysis-only verdict.
(
    '5eedda7a-0005-4000-8000-000000000002',
    '5eedda7a-0004-4000-8000-000000000001',
    '5eedda7a-0003-4000-8000-000000000002',
    'HUMAN_REQUIRED',
    'c09e1a44200ff5e951746e013035e68aeb3a14b1',
    'seed-trace-image-studio-0001',
    3, 0,
    '2026-08-11T23:45:00Z',
    '2026-08-11T23:47:00Z'
)
ON CONFLICT (id) DO UPDATE
SET state = EXCLUDED.state,
    attempts_used = EXCLUDED.attempts_used,
    ended_at = EXCLUDED.ended_at,
    updated_at = now();

DELETE FROM run_state_transitions
WHERE run_id IN (
    '5eedda7a-0005-4000-8000-000000000001',
    '5eedda7a-0005-4000-8000-000000000002'
);

INSERT INTO run_state_transitions (run_id, sequence, from_state, to_state, actor, reason)
VALUES
('5eedda7a-0005-4000-8000-000000000001', 1, NULL, 'RECEIVED', 'orchestrator',
 'provider-change-detected'),
('5eedda7a-0005-4000-8000-000000000001', 2, 'RECEIVED', 'SANITIZED', 'orchestrator',
 'provider text treated as data'),
('5eedda7a-0005-4000-8000-000000000001', 3, 'SANITIZED', 'NORMALIZED',
 'change_intelligence_agent', 'ChangeManifest produced'),
('5eedda7a-0005-4000-8000-000000000001', 4, 'NORMALIZED', 'IMPACT_SCANNING', 'impact_agent',
 'inventory lookup'),
('5eedda7a-0005-4000-8000-000000000001', 5, 'IMPACT_SCANNING', 'POLICY_EVALUATION',
 'impact_agent', '9 usages across 6 files'),
('5eedda7a-0005-4000-8000-000000000001', 6, 'POLICY_EVALUATION', 'PATCHING', 'policy_agent',
 'ALLOW at risk=medium'),
('5eedda7a-0005-4000-8000-000000000001', 7, 'PATCHING', 'BUILDING', 'patch_agent',
 'diff applied in sandbox'),
('5eedda7a-0005-4000-8000-000000000001', 8, 'BUILDING', 'TESTING', 'sandbox_runner',
 'pnpm --dir cli build exit 0'),
('5eedda7a-0005-4000-8000-000000000001', 9, 'TESTING', 'VERIFYING', 'sandbox_runner',
 'pnpm --dir cli test exit 0'),
('5eedda7a-0005-4000-8000-000000000001', 10, 'VERIFYING', 'PR_CREATING',
 'verification_agent', 'independent PASS'),
('5eedda7a-0005-4000-8000-000000000001', 11, 'PR_CREATING', 'PR_CREATED', 'pr_agent',
 'pull request opened for human review'),
('5eedda7a-0005-4000-8000-000000000002', 1, NULL, 'RECEIVED', 'orchestrator',
 'provider-change-detected'),
('5eedda7a-0005-4000-8000-000000000002', 2, 'RECEIVED', 'SANITIZED', 'orchestrator',
 'provider text treated as data'),
('5eedda7a-0005-4000-8000-000000000002', 3, 'SANITIZED', 'NORMALIZED',
 'change_intelligence_agent', 'ChangeManifest produced'),
('5eedda7a-0005-4000-8000-000000000002', 4, 'NORMALIZED', 'IMPACT_SCANNING', 'impact_agent',
 'inventory lookup'),
('5eedda7a-0005-4000-8000-000000000002', 5, 'IMPACT_SCANNING', 'POLICY_EVALUATION',
 'impact_agent', '1 usage in provider configuration'),
('5eedda7a-0005-4000-8000-000000000002', 6, 'POLICY_EVALUATION', 'HUMAN_REQUIRED',
 'policy_agent', 'criticality=high requires human review before patching');

-- -------------------------------------------------------- policy verdicts ---

INSERT INTO policy_decisions (
    id, run_id, decision, risk, auto_patch, auto_pr, forbidden_globs,
    required_checks, reason, policy_version
)
VALUES
(
    '5eedda7a-0006-4000-8000-000000000001',
    '5eedda7a-0005-4000-8000-000000000001',
    'ALLOW', 'medium', true, true,
    ARRAY['.github/workflows/**', 'infra/**', 'terraform/**', '.env*'],
    ARRAY['build', 'unit_tests', 'live_api_smoke_test'],
    'Provider model-family migration changes runtime semantics.',
    '2026.08.1'
),
(
    '5eedda7a-0006-4000-8000-000000000002',
    '5eedda7a-0005-4000-8000-000000000002',
    'HUMAN_REQUIRED', 'high', false, false,
    ARRAY['.github/workflows/**', 'infra/**', 'terraform/**', '.env*'],
    ARRAY['build', 'unit_tests'],
    'Repository criticality is high; policy is analysis-only.',
    '2026.08.1'
)
ON CONFLICT (id) DO UPDATE
SET decision = EXCLUDED.decision,
    risk = EXCLUDED.risk,
    auto_patch = EXCLUDED.auto_patch,
    auto_pr = EXCLUDED.auto_pr,
    reason = EXCLUDED.reason;

-- --------------------------------------------------------- patch attempts ---
-- Attempt 1 failed its tests, attempt 2 passed. Both ran in isolation.

INSERT INTO patch_attempts (
    id, run_id, attempt_number, status, plan_schema_version, plan, patch_agent,
    patch_model, prompt_version, sandbox_ref, build_exit_code, test_exit_code,
    diff_sha256, files_changed, failure_summary, started_at, ended_at
)
VALUES
(
    '5eedda7a-0007-4000-8000-000000000001',
    '5eedda7a-0005-4000-8000-000000000001',
    1, 'TESTS_FAILED', '1.0.0',
    '{"strategy": "model-id rewrite only"}'::jsonb,
    'patch_agent', 'gemini-3.5-flash', 'patch@1.0.0',
    'file:///tmp/patchapi-sandbox/seed-attempt-1',
    0, 1,
    '1111111111111111111111111111111111111111111111111111111111111111',
    4,
    'Rewriting model IDs alone left Imagen-only options unmapped; cli tests failed.',
    '2026-08-11T23:47:00Z', '2026-08-11T23:51:00Z'
),
(
    '5eedda7a-0007-4000-8000-000000000002',
    '5eedda7a-0005-4000-8000-000000000001',
    2, 'SUCCEEDED', '1.0.0',
    '{"strategy": "map request surface to gemini-3.1-flash-image, escalate unmapped options"}'::jsonb,
    'patch_agent', 'gemini-3.5-flash', 'patch@1.0.0',
    'file:///tmp/patchapi-sandbox/seed-attempt-2',
    0, 0,
    '2222222222222222222222222222222222222222222222222222222222222222',
    7,
    NULL,
    '2026-08-11T23:51:00Z', '2026-08-11T23:55:00Z'
)
ON CONFLICT (id) DO UPDATE
SET status = EXCLUDED.status,
    build_exit_code = EXCLUDED.build_exit_code,
    test_exit_code = EXCLUDED.test_exit_code,
    failure_summary = EXCLUDED.failure_summary,
    ended_at = EXCLUDED.ended_at;

-- --------------------------------------------------- independent verdicts ---
-- `verifier_agent` differs from `patch_agent`; the schema rejects anything else.

INSERT INTO verification_results (
    id, run_id, patch_attempt_id, verdict, verifier_agent, verifier_model,
    patch_agent, patch_model, checks, report_schema_version, report,
    evidence_summary
)
VALUES (
    '5eedda7a-0008-4000-8000-000000000001',
    '5eedda7a-0005-4000-8000-000000000001',
    '5eedda7a-0007-4000-8000-000000000002',
    'PASS', 'verification_agent', 'gemini-3.5-flash',
    'patch_agent', 'gemini-3.5-flash',
    '[
       {"name": "build", "passed": true},
       {"name": "unit_tests", "passed": true},
       {"name": "no_deprecated_identifier_in_exercised_path", "passed": true}
     ]'::jsonb,
    '1.0.0',
    '{"verdict": "PASS", "independent": true}'::jsonb,
    'Build and cli tests pass; no Imagen 4 identifier remains on the exercised path.'
)
ON CONFLICT (id) DO UPDATE
SET verdict = EXCLUDED.verdict,
    checks = EXCLUDED.checks,
    report = EXCLUDED.report;

-- -------------------------------------------------------------- artifacts ---

INSERT INTO artifacts (
    id, run_id, patch_attempt_id, kind, uri, content_sha256, size_bytes, media_type
)
VALUES
('5eedda7a-0009-4000-8000-000000000001', '5eedda7a-0005-4000-8000-000000000001',
 '5eedda7a-0007-4000-8000-000000000002', 'UNIFIED_DIFF',
 'file:///tmp/patchapi-sandbox/seed-attempt-2/patch.diff',
 '2222222222222222222222222222222222222222222222222222222222222222', 4821, 'text/x-diff'),
('5eedda7a-0009-4000-8000-000000000002', '5eedda7a-0005-4000-8000-000000000001',
 '5eedda7a-0007-4000-8000-000000000002', 'BUILD_LOG',
 'file:///tmp/patchapi-sandbox/seed-attempt-2/logs/build.txt',
 '3333333333333333333333333333333333333333333333333333333333333333', 18342, 'text/plain'),
('5eedda7a-0009-4000-8000-000000000003', '5eedda7a-0005-4000-8000-000000000001',
 '5eedda7a-0007-4000-8000-000000000002', 'TEST_LOG',
 'file:///tmp/patchapi-sandbox/seed-attempt-2/logs/test.txt',
 '4444444444444444444444444444444444444444444444444444444444444444', 9210, 'text/plain'),
('5eedda7a-0009-4000-8000-000000000004', '5eedda7a-0005-4000-8000-000000000001',
 NULL, 'AGENT_TRACE',
 'file:///tmp/patchapi-sandbox/seed-trace-egaki-0001.jsonl',
 '5555555555555555555555555555555555555555555555555555555555555555', 65536,
 'application/x-ndjson')
ON CONFLICT (id) DO UPDATE
SET uri = EXCLUDED.uri,
    size_bytes = EXCLUDED.size_bytes;

-- ---------------------------------------------------- idempotency and PRs ---

INSERT INTO external_action_keys (
    idempotency_key, run_id, action_type, base_sha, status, result_ref, completed_at
)
VALUES
(
    '5eedda7a-0005-4000-8000-000000000001:create_pull_request:c09e1a44200ff5e951746e013035e68aeb3a14b1',
    '5eedda7a-0005-4000-8000-000000000001',
    'create_pull_request',
    'c09e1a44200ff5e951746e013035e68aeb3a14b1',
    'COMPLETED',
    'https://example.invalid/amelia751/egaki/pull/1',
    '2026-08-11T23:58:00Z'
),
(
    '5eedda7a-0005-4000-8000-000000000001:allocate_sandbox:c09e1a44200ff5e951746e013035e68aeb3a14b1',
    '5eedda7a-0005-4000-8000-000000000001',
    'allocate_sandbox',
    'c09e1a44200ff5e951746e013035e68aeb3a14b1',
    'COMPLETED',
    'file:///tmp/patchapi-sandbox/seed-attempt-2',
    '2026-08-11T23:55:00Z'
)
ON CONFLICT (idempotency_key) DO UPDATE
SET status = EXCLUDED.status,
    result_ref = EXCLUDED.result_ref,
    completed_at = EXCLUDED.completed_at;

INSERT INTO pull_requests (
    id, run_id, repository_id, number, url, title, head_branch, base_branch,
    head_sha, state, idempotency_key, opened_at, observed_at
)
VALUES (
    '5eedda7a-000a-4000-8000-000000000001',
    '5eedda7a-0005-4000-8000-000000000001',
    '5eedda7a-0003-4000-8000-000000000001',
    1,
    'https://example.invalid/amelia751/egaki/pull/1',
    '[seed] Migrate Imagen 4 usage to gemini-3.1-flash-image',
    'patchapi/imagen4-retirement-2026-08-17',
    'main',
    'c09e1a44200ff5e951746e013035e68aeb3a14b1',
    'OPEN',
    '5eedda7a-0005-4000-8000-000000000001:create_pull_request:c09e1a44200ff5e951746e013035e68aeb3a14b1',
    '2026-08-11T23:58:00Z',
    '2026-08-11T23:58:00Z'
)
ON CONFLICT (id) DO UPDATE
SET state = EXCLUDED.state,
    observed_at = EXCLUDED.observed_at;

-- ------------------------------------------------------------ audit trail ---
-- Append-only in production; the seed removes only rows it wrote itself.

DELETE FROM audit_events WHERE detail ->> 'seed' = 'true';

INSERT INTO audit_events (
    organization_id, repository_id, run_id, actor, action, target, outcome,
    reason, trace_id, detail, occurred_at
)
VALUES
('5eedda7a-0001-4000-8000-000000000001', '5eedda7a-0003-4000-8000-000000000001',
 '5eedda7a-0005-4000-8000-000000000001', 'orchestrator', 'run.start',
 'imagen4-retirement-2026-08-17', 'SUCCEEDED', NULL, 'seed-trace-egaki-0001',
 '{"seed": true}'::jsonb, '2026-08-11T23:45:00Z'),
('5eedda7a-0001-4000-8000-000000000001', '5eedda7a-0003-4000-8000-000000000001',
 '5eedda7a-0005-4000-8000-000000000001', 'patch_agent',
 'github_tools.merge_pull_request', 'amelia751/egaki#1', 'DENIED',
 'Capability is absent from the GitHub tool surface; PatchAPI stops at the pull request.',
 'seed-trace-egaki-0001', '{"seed": true}'::jsonb, '2026-08-11T23:57:00Z'),
('5eedda7a-0001-4000-8000-000000000001', '5eedda7a-0003-4000-8000-000000000001',
 '5eedda7a-0005-4000-8000-000000000001', 'patch_agent', 'patch.write_path',
 '.github/workflows/release.yml', 'DENIED',
 'Path matches a forbidden glob in policy version 2026.08.1.',
 'seed-trace-egaki-0001', '{"seed": true}'::jsonb, '2026-08-11T23:52:00Z'),
('5eedda7a-0001-4000-8000-000000000001', '5eedda7a-0003-4000-8000-000000000001',
 '5eedda7a-0005-4000-8000-000000000001', 'pr_agent',
 'github_tools.create_pull_request', 'amelia751/egaki#1', 'SUCCEEDED', NULL,
 'seed-trace-egaki-0001', '{"seed": true}'::jsonb, '2026-08-11T23:58:00Z'),
('5eedda7a-0001-4000-8000-000000000001', '5eedda7a-0003-4000-8000-000000000002',
 '5eedda7a-0005-4000-8000-000000000002', 'policy_agent', 'policy.evaluate',
 'amelia751/image-studio', 'SUCCEEDED', NULL, 'seed-trace-image-studio-0001',
 '{"seed": true}'::jsonb, '2026-08-11T23:47:00Z');
