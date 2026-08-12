#!/usr/bin/env bash
# Verifies the PatchAPI Terraform tree: fmt, init, validate, and a real plan
# against the target GCP project.
#
# The plan is the point. `validate` only proves the HCL parses; a plan proves
# the provider authenticated, the project exists, and every resource this
# configuration would create is one the credentials are allowed to describe.
#
# Apply is human-gated and off by default. Set APPLY_INFRA=1 to apply, and read
# infra/terraform/README.md first — gated modules (GKE, Cloud SQL, Cloud Run)
# cost money and are separately switched in terraform.tfvars.
#
#   ./scripts/verify_infra_terraform.sh              # fmt + init + validate + plan
#   APPLY_INFRA=1 ./scripts/verify_infra_terraform.sh  # ... then apply
#
# Exit codes: 0 PASS or explicit SKIP, 1 FAIL.
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TF_ROOT="infra/terraform"
ENV_DIR="${INFRA_ENV_DIR:-$TF_ROOT/environments/dev}"
LEDGER="demo/setup-ledger.ndjson"
TASK="T-infra-terraform"
PLAN_FILE="$(mktemp -t patchapi-tfplan.XXXXXX)"
PLAN_LOG="$(mktemp -t patchapi-tfplanlog.XXXXXX)"

# Terraform writes state and plan files that can contain resource detail. Both
# live outside the repository and are removed on every exit path.
cleanup() {
  rm -f "$PLAN_FILE" "$PLAN_LOG"
}
trap cleanup EXIT

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

ledger() {
  # $1 status, $2 command, $3 notes
  mkdir -p "$(dirname "$LEDGER")"
  python3 - "$TASK" "$1" "$2" "$(now)" "$3" >>"$LEDGER" <<'PY'
import json, sys
task, status, command, at, notes = sys.argv[1:6]
line = {"task": task, "status": status, "command": command, "at": at}
if notes:
    line["notes"] = notes
print(json.dumps(line))
PY
}

skip() {
  printf 'SKIP: %s\n' "$1"
  ledger SKIP "./scripts/verify_infra_terraform.sh" "$1"
  exit 0
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  ledger FAIL "./scripts/verify_infra_terraform.sh" "$1"
  exit 1
}

# --- preconditions ----------------------------------------------------------

command -v terraform >/dev/null 2>&1 || skip "terraform is not installed; see infra/terraform/README.md"
command -v python3 >/dev/null 2>&1 || fail "python3 is required to append the ledger line"
[ -d "$ENV_DIR" ] || fail "$ENV_DIR does not exist"

printf 'terraform %s\n' "$(terraform version -json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || echo unknown)"

# Application Default Credentials: prefer an explicit key, fall back to gcloud
# ADC. Without either, plan cannot reach the project and the honest answer is
# SKIP, not a validate-only pass dressed up as success.
if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
  for candidate in \
    "$ROOT/.secrets/gcp-service-account.json" \
    "${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/application_default_credentials.json"; do
    if [ -f "$candidate" ]; then
      export GOOGLE_APPLICATION_CREDENTIALS="$candidate"
      break
    fi
  done
fi

# `terraform -chdir` runs from the environment directory, so a relative
# credentials path — the form .env.example uses — would resolve against the
# wrong directory and surface as a confusing "no credentials loaded" error.
case "${GOOGLE_APPLICATION_CREDENTIALS:-}" in
  "" | /*) ;;
  *) GOOGLE_APPLICATION_CREDENTIALS="$ROOT/$GOOGLE_APPLICATION_CREDENTIALS" ;;
esac
export GOOGLE_APPLICATION_CREDENTIALS

if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] || [ ! -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]; then
  skip "no GCP credentials (set GOOGLE_APPLICATION_CREDENTIALS or run: gcloud auth application-default login)"
fi
printf 'credentials: %s\n' "$GOOGLE_APPLICATION_CREDENTIALS"

# --- no state or credentials may be committed -------------------------------

# State snapshots hold every resource attribute, including ones the provider
# marks sensitive. Committed *.tfvars are fine and intended — they carry project
# ids and feature flags — but they must never carry a value.
tracked_junk="$(git -C "$ROOT" ls-files -- "$TF_ROOT" \
  | grep -E '(\.tfstate($|\.)|/\.terraform/|\.json$|\.pem$|\.p12$|\.key$)' \
  | grep -v -E '\.terraform\.lock\.hcl' || true)"
if [ -n "$tracked_junk" ]; then
  fail "state or credential-shaped files are tracked under $TF_ROOT: $(echo "$tracked_junk" | tr '\n' ' ')"
fi

leaks="$(git -C "$ROOT" grep -lIE \
  -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
  -e '"type"[[:space:]]*:[[:space:]]*"service_account"' \
  -e '(password|private_key|api_key|client_secret)[[:space:]]*=[[:space:]]*"[^"$]+"' \
  -- "$TF_ROOT" || true)"
if [ -n "$leaks" ]; then
  fail "credential-shaped literals found under $TF_ROOT: $(echo "$leaks" | tr '\n' ' ')"
fi
printf 'ok   no state snapshots or credential literals tracked under %s\n' "$TF_ROOT"

# --- fmt --------------------------------------------------------------------

if ! terraform fmt -check -recursive -no-color "$TF_ROOT" >/dev/null; then
  unformatted="$(terraform fmt -check -recursive -no-color "$TF_ROOT" || true)"
  fail "terraform fmt: unformatted files: $(echo "$unformatted" | tr '\n' ' ')(run: terraform fmt -recursive $TF_ROOT)"
fi
printf 'ok   terraform fmt -check -recursive\n'

# --- init + validate, every environment -------------------------------------
#
# Every environment is validated so an unplanned one cannot rot behind a module
# change. Only $ENV_DIR gets a plan, because a plan costs live API calls.

for env_dir in "$TF_ROOT"/environments/*/; do
  env_dir="${env_dir%/}"
  [ -n "$(find "$env_dir" -maxdepth 1 -name '*.tf' -print -quit)" ] || continue

  if ! terraform -chdir="$env_dir" init -input=false -no-color -upgrade=false >/dev/null; then
    terraform -chdir="$env_dir" init -input=false -no-color -upgrade=false || true
    fail "terraform init failed in $env_dir"
  fi

  if ! terraform -chdir="$env_dir" validate -no-color >/dev/null; then
    terraform -chdir="$env_dir" validate -no-color || true
    fail "terraform validate failed in $env_dir"
  fi

  printf 'ok   terraform init + validate (%s)\n' "$env_dir"
done

# --- plan -------------------------------------------------------------------

set +e
terraform -chdir="$ENV_DIR" plan \
  -input=false -no-color -lock-timeout=120s \
  -out="$PLAN_FILE" >"$PLAN_LOG" 2>&1
plan_status=$?
set -e

if [ "$plan_status" -ne 0 ]; then
  tail -40 "$PLAN_LOG" >&2
  fail "terraform plan exited $plan_status in $ENV_DIR"
fi

# Summarize what an apply would do, from the machine-readable plan rather than
# by scraping human output.
PLAN_JSON="$(mktemp -t patchapi-tfplanjson.XXXXXX)"
if ! terraform -chdir="$ENV_DIR" show -json "$PLAN_FILE" >"$PLAN_JSON" 2>"$PLAN_LOG"; then
  tail -20 "$PLAN_LOG" >&2
  rm -f "$PLAN_JSON"
  fail "terraform show -json could not read the saved plan"
fi

# A delete in the plan is a signal, not a pass: this tree is additive
# scaffolding, so a destroy means drift or a flag switched off unintentionally.
set +e
summary="$(python3 -c '
import collections, json, sys

with open(sys.argv[1]) as fh:
    plan = json.load(fh)

counts = collections.Counter()
doomed = []
for change in plan.get("resource_changes", []):
    actions = change["change"]["actions"]
    counts.update(actions)
    if "delete" in actions:
        doomed.append(change["address"])

parts = [f"{a}={counts[a]}" for a in ("create", "update", "delete", "read") if counts[a]]
print(" ".join(parts) or "no resource changes")
if doomed:
    print("WOULD DESTROY: " + " ".join(doomed), file=sys.stderr)
' "$PLAN_JSON")"
summary_status=$?
set -e
rm -f "$PLAN_JSON"

[ "$summary_status" -eq 0 ] || fail "could not summarize the saved plan"
printf 'ok   terraform plan: %s\n' "$summary"

# --- gated modules still plan ------------------------------------------------
#
# GKE, Cloud SQL, and Cloud Run are off by default, so the plan above never
# touches them. `validate` proves their HCL parses but not that the provider
# accepts the arguments — an attribute removed in a provider upgrade would sit
# undetected until the day someone needs a cluster. This speculative plan turns
# every gate on, discards the result, and applies nothing.
#
# Set INFRA_PLAN_GATED=0 to skip when offline or in a hurry.

if [ "${INFRA_PLAN_GATED:-1}" = "1" ] && [ "$ENV_DIR" = "$TF_ROOT/environments/dev" ]; then
  GATED_PLAN="$(mktemp -t patchapi-tfgated.XXXXXX)"
  set +e
  terraform -chdir="$ENV_DIR" plan \
    -input=false -no-color -lock-timeout=120s \
    -var 'enable_gke_sandbox=true' \
    -var 'enable_cloud_sql=true' \
    -var 'enable_cloud_run=true' \
    -var 'cloud_run_images={"control-api":"us-central1-docker.pkg.dev/x/y/control-api:probe","github-tools":"us-central1-docker.pkg.dev/x/y/github-tools:probe","repo-indexer":"us-central1-docker.pkg.dev/x/y/repo-indexer:probe"}' \
    -out="$GATED_PLAN" >"$PLAN_LOG" 2>&1
  gated_status=$?
  set -e
  rm -f "$GATED_PLAN"

  if [ "$gated_status" -ne 0 ]; then
    tail -40 "$PLAN_LOG" >&2
    fail "gated modules (GKE, Cloud SQL, Cloud Run) do not plan; exit $gated_status"
  fi
  printf 'ok   gated modules plan (GKE + Cloud SQL + Cloud Run; discarded, nothing applied)\n'
fi

# --- apply (human-gated) ----------------------------------------------------

if [ "${APPLY_INFRA:-0}" = "1" ]; then
  printf 'APPLY_INFRA=1 — applying the plan above\n'
  if ! terraform -chdir="$ENV_DIR" apply -input=false -no-color "$PLAN_FILE"; then
    fail "terraform apply failed in $ENV_DIR"
  fi
  printf 'ok   terraform apply\n'
  ledger PASS "APPLY_INFRA=1 ./scripts/verify_infra_terraform.sh" "fmt+init+validate+plan+apply against $ENV_DIR ($summary)"
  printf 'PASS: verify_infra_terraform.sh (applied)\n'
  exit 0
fi

ledger PASS "./scripts/verify_infra_terraform.sh" "fmt+init+validate+plan against $ENV_DIR ($summary); apply skipped, set APPLY_INFRA=1 to apply"
printf 'PASS: verify_infra_terraform.sh (plan only; set APPLY_INFRA=1 to apply)\n'
