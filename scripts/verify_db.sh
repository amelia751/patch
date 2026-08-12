#!/usr/bin/env bash
# Dynamic verifier for the database tree (setup.md T-db).
#
# Brings up local Postgres, applies the migrations twice to prove they are
# forward-only and idempotent, applies the seeds twice to prove they converge,
# then asserts against the live schema: expected tables exist, seeded rows are
# present, and the constraints that keep passwords, tokens, and secret values
# out of this database actually reject the writes they are supposed to reject.
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
        'users', 'user_identities', 'github_connections',
        'projects', 'project_repositories', 'workspaces', 'project_secrets',
        'schema_migrations', 'seed_applications'
    ];
    missing text[];
    forbidden text;
BEGIN
    SELECT array_agg(t) INTO missing
    FROM unnest(expected_tables) AS t
    WHERE to_regclass('public.' || t) IS NULL;

    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'missing tables: %', missing;
    END IF;

    -- Passwords, tokens, and secret payloads must not have a column to land in.
    FOREACH forbidden IN ARRAY ARRAY[
        'users.password', 'users.password_hash', 'users.hashed_password',
        'github_connections.token', 'github_connections.access_token',
        'github_connections.installation_token',
        'project_secrets.value', 'project_secrets.secret_value',
        'project_secrets.ciphertext'
    ]
    LOOP
        IF to_regclass('public.' || split_part(forbidden, '.', 1)) IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public'
                 AND table_name = split_part(forbidden, '.', 1)
                 AND column_name = split_part(forbidden, '.', 2)
           ) THEN
            RAISE EXCEPTION 'forbidden column present: %', forbidden;
        END IF;
    END LOOP;
END
$assert$;

DO $assert$
DECLARE
    recorded integer;
BEGIN
    SELECT count(*) INTO recorded FROM schema_migrations;
    IF recorded < 5 THEN
        RAISE EXCEPTION 'expected at least 5 recorded migrations, found %', recorded;
    END IF;
END
$assert$;

DO $assert$
DECLARE
    t text;
    n integer;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'users', 'user_identities', 'github_connections',
        'projects', 'project_repositories', 'workspaces'
    ]
    LOOP
        EXECUTE format('SELECT count(*) FROM %I', t) INTO n;
        IF n = 0 THEN
            RAISE EXCEPTION 'seed produced no rows in %', t;
        END IF;
    END LOOP;
END
$assert$;

DO $assert$
DECLARE
    users_n integer;
    projects_n integer;
    repos_n integer;
    applications integer;
BEGIN
    SELECT count(*) INTO users_n FROM users;
    SELECT count(*) INTO projects_n FROM projects;
    SELECT count(*) INTO repos_n FROM project_repositories;
    SELECT apply_count INTO applications FROM seed_applications
    WHERE name = '0001_demo_console.sql';

    IF users_n <> 1 THEN
        RAISE EXCEPTION 'expected 1 seeded user, found %', users_n;
    END IF;
    IF projects_n <> 1 THEN
        RAISE EXCEPTION 'expected 1 seeded project, found %', projects_n;
    END IF;
    IF repos_n <> 1 THEN
        RAISE EXCEPTION 'expected 1 seeded repository, found %', repos_n;
    END IF;
    IF applications < 2 THEN
        RAISE EXCEPTION 'seed ledger recorded % applications, expected at least 2', applications;
    END IF;
END
$assert$;

DO $assert$
DECLARE
    login text;
    full_name text;
    installed boolean;
BEGIN
    SELECT i.username INTO login
    FROM user_identities i
    WHERE i.provider = 'github'
      AND i.user_id = '5eedda7a-0001-4000-8000-000000000001';
    IF login <> 'amelia751' THEN
        RAISE EXCEPTION 'github username is %, expected amelia751', login;
    END IF;

    SELECT r.full_name INTO full_name FROM project_repositories r
    WHERE r.project_id = '5eedda7a-0004-4000-8000-000000000001';
    IF full_name <> 'amelia751/egaki' THEN
        RAISE EXCEPTION 'imported repo is %, expected amelia751/egaki', full_name;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM github_connections c
        WHERE c.user_id = '5eedda7a-0001-4000-8000-000000000001'
          AND c.suspended_at IS NULL
    ) INTO installed;
    IF NOT installed THEN
        RAISE EXCEPTION 'seed user has no GitHub App connection';
    END IF;
END
$assert$;

DO $assert$
BEGIN
    BEGIN
        INSERT INTO users (email, display_name)
        VALUES ('not-an-email', 'x');
        RAISE EXCEPTION 'users accepted an email without @';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO user_identities (user_id, provider, provider_user_id)
        VALUES (
            '5eedda7a-0001-4000-8000-000000000001',
            'github',
            '0'
        );
        RAISE EXCEPTION 'user_identities accepted a duplicate github account';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO project_repositories (
            project_id, name, full_name
        ) VALUES (
            '5eedda7a-0004-4000-8000-000000000001',
            'egaki',
            'not-a-full-name'
        );
        RAISE EXCEPTION 'project_repositories accepted a full_name without owner/repo';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO project_secrets (project_id, secret_name)
        VALUES (
            '5eedda7a-0004-4000-8000-000000000001',
            '   '
        );
        RAISE EXCEPTION 'project_secrets accepted a blank secret_name';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END
$assert$;

SELECT 'rows: ' || t || '=' || n
FROM (
    SELECT 'users' AS t, count(*) AS n FROM users
    UNION ALL SELECT 'user_identities', count(*) FROM user_identities
    UNION ALL SELECT 'github_connections', count(*) FROM github_connections
    UNION ALL SELECT 'projects', count(*) FROM projects
    UNION ALL SELECT 'project_repositories', count(*) FROM project_repositories
    UNION ALL SELECT 'workspaces', count(*) FROM workspaces
    UNION ALL SELECT 'project_secrets', count(*) FROM project_secrets
) AS counts
ORDER BY t;
SQL

# ---------------------------------------------------------- offline SQL tests --

step "pytest db/tests"
uv run pytest db/tests -q

STATUS="PASS"
echo
echo "PASS: database tree verified"
