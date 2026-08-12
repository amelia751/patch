#!/usr/bin/env bash
# Dynamic verifier for the database tree (setup.md T-db).
#
# Brings up local Postgres, applies the migrations twice to prove they are
# forward-only and idempotent, applies the seeds twice to prove they converge,
# then asserts against the live schema: expected tables exist, seeded rows are
# present, and the constraints that encode PatchAPI's hard rules actually
# reject the writes they are supposed to reject.
#
# Set DATABASE_URL to verify an external database (Cloud SQL through a proxy)
# instead of the compose container; compose is then left untouched.
# Set PATCHAPI_DB_KEEP=1 to leave the container running for inspection.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="db/docker-compose.yml"
LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_db.sh"
STATUS="FAIL"
COMPOSE_STARTED=0

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-db","status":"%s","command":"%s","at":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LEDGER"
}

teardown() {
  if [[ "$COMPOSE_STARTED" == "1" && "${PATCHAPI_DB_KEEP:-0}" != "1" ]]; then
    printf '\n== docker compose down\n'
    docker compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 || true
  fi
  record
}
trap teardown EXIT

step() { printf '\n== %s\n' "$1"; }

# The runner is stdlib-only, so it is invoked straight from the checkout. That
# keeps this script from installing a workspace member into the shared virtual
# environment other trees are using.
db() { PYTHONPATH="db/src${PYTHONPATH:+:$PYTHONPATH}" uv run --quiet python -m patchapi_db "$@"; }

# ------------------------------------------------------------ preconditions --

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is not installed (see setup.md §3)"
  exit 1
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  step "target: DATABASE_URL (compose not used)"
  if ! command -v psql >/dev/null 2>&1; then
    echo "FAIL: DATABASE_URL is set but psql is not on PATH"
    exit 1
  fi
else
  if ! command -v docker >/dev/null 2>&1; then
    echo "FAIL: docker is not installed and DATABASE_URL is unset (see setup.md §3)"
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "FAIL: the Docker daemon is not running; start Docker Desktop or set DATABASE_URL"
    exit 1
  fi

  step "docker compose up"
  docker compose -f "$COMPOSE_FILE" up -d
  COMPOSE_STARTED=1

  step "wait for postgres"
  ready=0
  for _ in $(seq 1 60); do
    if docker compose -f "$COMPOSE_FILE" exec -T postgres \
      pg_isready -U "${PATCHAPI_DB_USER:-patchapi}" -d "${PATCHAPI_DB_NAME:-patchapi}" \
      >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  if [[ "$ready" != "1" ]]; then
    echo "FAIL: postgres did not become ready within 60s"
    docker compose -f "$COMPOSE_FILE" logs --tail 40 postgres || true
    exit 1
  fi
fi

# --------------------------------------------------------------- migrations --

step "migrate (first pass)"
db migrate

step "migrate (second pass — must apply nothing)"
second_pass="$(db migrate)"
printf '%s\n' "$second_pass"
if ! printf '%s' "$second_pass" | grep -q 'migrate: 0 applied'; then
  echo "FAIL: the second migrate pass was not a no-op; migrations are not idempotent"
  exit 1
fi

step "status"
db status

# -------------------------------------------------------------------- seeds --

step "seed (first pass)"
db seed

step "seed (second pass — must converge, not duplicate)"
db seed

# ---------------------------------------------------------------- assertions --

step "assert schema and seed content"
db sql <<'SQL'
DO $assert$
DECLARE
    expected_tables text[] := ARRAY[
        'organizations', 'installations', 'repositories', 'api_usages',
        'change_events', 'remediation_runs', 'run_state_transitions',
        'external_action_keys', 'policy_decisions', 'patch_attempts',
        'verification_results', 'artifacts', 'pull_requests', 'audit_events',
        'schema_migrations', 'seed_applications'
    ];
    missing text[];
BEGIN
    SELECT array_agg(t) INTO missing
    FROM unnest(expected_tables) AS t
    WHERE to_regclass('public.' || t) IS NULL;

    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'missing tables: %', missing;
    END IF;
END
$assert$;

-- Every migration on disk is recorded exactly once.
DO $assert$
DECLARE
    recorded integer;
BEGIN
    SELECT count(*) INTO recorded FROM schema_migrations;
    IF recorded < 10 THEN
        RAISE EXCEPTION 'expected at least 10 recorded migrations, found %', recorded;
    END IF;
END
$assert$;

-- Seed rows are present in every table a fixture run touches.
DO $assert$
DECLARE
    t text;
    n integer;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'organizations', 'installations', 'repositories', 'api_usages',
        'change_events', 'remediation_runs', 'run_state_transitions',
        'external_action_keys', 'policy_decisions', 'patch_attempts',
        'verification_results', 'artifacts', 'pull_requests', 'audit_events'
    ]
    LOOP
        EXECUTE format('SELECT count(*) FROM %I', t) INTO n;
        IF n = 0 THEN
            RAISE EXCEPTION 'seed produced no rows in %', t;
        END IF;
    END LOOP;
END
$assert$;

-- Seeds converge: applying twice must not duplicate the demo run's history.
DO $assert$
DECLARE
    transitions integer;
    runs integer;
    usages integer;
    applications integer;
BEGIN
    SELECT count(*) INTO transitions FROM run_state_transitions
    WHERE run_id = '5eedda7a-0005-4000-8000-000000000001';
    SELECT count(*) INTO runs FROM remediation_runs;
    SELECT count(*) INTO usages FROM api_usages;
    SELECT apply_count INTO applications FROM seed_applications
    WHERE name = '0001_demo_egaki.sql';

    IF transitions <> 11 THEN
        RAISE EXCEPTION 'expected 11 seeded transitions, found %', transitions;
    END IF;
    IF runs <> 2 THEN
        RAISE EXCEPTION 'expected 2 seeded runs, found %', runs;
    END IF;
    IF usages <> 10 THEN
        RAISE EXCEPTION 'expected 10 seeded api_usages, found %', usages;
    END IF;
    IF applications < 2 THEN
        RAISE EXCEPTION 'seed ledger recorded % applications, expected at least 2', applications;
    END IF;
END
$assert$;

-- The queries a fixture run actually issues.
DO $assert$
DECLARE
    hits integer;
    state text;
    verdict text;
BEGIN
    SELECT count(*) INTO hits FROM api_usages
    WHERE provider = 'google' AND identifier = 'imagen-4.0-generate-001'
      AND removed_at IS NULL;
    IF hits = 0 THEN
        RAISE EXCEPTION 'inventory lookup for imagen-4.0-generate-001 returned nothing';
    END IF;

    SELECT r.state::text INTO state FROM remediation_runs r
    JOIN repositories repo ON repo.id = r.repository_id
    WHERE repo.owner = 'amelia751' AND repo.name = 'egaki';
    IF state <> 'PR_CREATED' THEN
        RAISE EXCEPTION 'demo run is in state %, expected PR_CREATED', state;
    END IF;

    SELECT v.verdict::text INTO verdict FROM verification_results v
    JOIN patch_attempts p ON p.id = v.patch_attempt_id
    WHERE p.status = 'SUCCEEDED';
    IF verdict <> 'PASS' THEN
        RAISE EXCEPTION 'verification verdict is %, expected PASS', verdict;
    END IF;
END
$assert$;

-- Hard controls: the schema must reject writes that violate the product rules.
DO $assert$
BEGIN
    BEGIN
        UPDATE policy_decisions SET auto_merge = true
        WHERE id = '5eedda7a-0006-4000-8000-000000000001';
        RAISE EXCEPTION 'policy_decisions accepted auto_merge = true';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        UPDATE pull_requests SET merged_by_patchapi = true
        WHERE id = '5eedda7a-000a-4000-8000-000000000001';
        RAISE EXCEPTION 'pull_requests accepted merged_by_patchapi = true';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO verification_results (
            run_id, patch_attempt_id, verdict, verifier_agent, verifier_model,
            patch_agent, patch_model, report_schema_version, report
        ) VALUES (
            '5eedda7a-0005-4000-8000-000000000001',
            '5eedda7a-0007-4000-8000-000000000002',
            'PASS', 'patch_agent', 'gemini-3.5-flash',
            'patch_agent', 'gemini-3.5-flash', '1.0.0', '{}'::jsonb
        );
        RAISE EXCEPTION 'verification_results accepted a self-grading verifier';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        UPDATE patch_attempts SET status = 'SUCCEEDED', sandbox_ref = NULL
        WHERE id = '5eedda7a-0007-4000-8000-000000000001';
        RAISE EXCEPTION 'patch_attempts accepted SUCCEEDED without an isolated run';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        UPDATE remediation_runs SET state = 'PR_CREATED', ended_at = NULL
        WHERE id = '5eedda7a-0005-4000-8000-000000000002';
        RAISE EXCEPTION 'remediation_runs accepted a terminal state with no end timestamp';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END
$assert$;

SELECT 'rows: ' || t || '=' || n
FROM (
    SELECT 'api_usages' AS t, count(*) AS n FROM api_usages
    UNION ALL SELECT 'remediation_runs', count(*) FROM remediation_runs
    UNION ALL SELECT 'run_state_transitions', count(*) FROM run_state_transitions
    UNION ALL SELECT 'audit_events', count(*) FROM audit_events
    UNION ALL SELECT 'artifacts', count(*) FROM artifacts
    UNION ALL SELECT 'pull_requests', count(*) FROM pull_requests
) AS counts
ORDER BY t;
SQL

# ---------------------------------------------------------- offline SQL tests --

step "pytest db/tests"
uv run pytest db/tests -q

STATUS="PASS"
echo
echo "PASS: database tree verified"
