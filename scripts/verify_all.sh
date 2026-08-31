#!/usr/bin/env bash
# Aggregate verifier for the setup batch (setup.md T-qa-aggregate).
#
# Runs every scripts/verify_*.sh except itself, derives PASS / SKIP / FAIL from
# what each script actually did, scans the tracked tree for credential material,
# and writes demo/setup-report.md.
#
# Status is never assumed. A script's exit code and the line it appended to
# demo/setup-ledger.ndjson must agree; when they disagree the run is reported as
# FAIL with the discrepancy named, because a self-reported PASS that exits
# non-zero (or the reverse) is exactly the fabrication this task exists to catch.
#
# Exit codes: 0 = no required FAIL and no secret finding, 1 = otherwise.
#
# Usage:
#   ./scripts/verify_all.sh                 # everything
#   ./scripts/verify_all.sh --list          # show the plan, run nothing
#   ./scripts/verify_all.sh --only gemini --only docs
#   ./scripts/verify_all.sh --skip sandbox_gke
#   ./scripts/verify_all.sh --no-scan       # skip the credential scan
#   ./scripts/verify_all.sh --self-test     # prove the credential scan can fail
#
# Environment:
#   PATCHAPI_VERIFY_TIMEOUT   override the per-script timeout (seconds)
#   PATCHAPI_VERIFY_LOG_DIR   where per-script logs land (default: mktemp -d)
#   PATCHAPI_VERIFY_OPTIONAL  comma-separated scripts whose FAIL does not gate
#                             the exit code (still reported as FAIL)
#   PATCHAPI_REQUIRE_LIVE     exported as 1 unless already set; setup.md §10
#                             requires the live Gemini checks, so a credential
#                             SKIP is a failure of the aggregate run
#
# Deliberately not `set -e`: one broken tree must not hide the state of the
# other seventeen.
set -uo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SELF="scripts/verify_all.sh"
REPORT="demo/setup-report.md"
LEDGER="demo/setup-ledger.ndjson"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# setup.md §10 lists the live Gemini smokes as exit criteria, so the aggregate
# run asks for them rather than accepting a credential SKIP.
export PATCHAPI_REQUIRE_LIVE="${PATCHAPI_REQUIRE_LIVE:-1}"

DO_SCAN=1
LIST_ONLY=0
SELF_TEST=0
ONLY_PATTERNS=()
SKIP_PATTERNS=()
# Counted separately: bash 3.2 (the system bash on macOS) treats ${#arr[@]} on an
# empty array as an unbound variable under set -u.
ONLY_COUNT=0
SKIP_COUNT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --list) LIST_ONLY=1 ;;
    --self-test) SELF_TEST=1 ;;
    --no-scan) DO_SCAN=0 ;;
    --only) shift; ONLY_PATTERNS[$ONLY_COUNT]="${1:-}"; ONLY_COUNT=$((ONLY_COUNT + 1)) ;;
    --skip) shift; SKIP_PATTERNS[$SKIP_COUNT]="${1:-}"; SKIP_COUNT=$((SKIP_COUNT + 1)) ;;
    --report) shift; REPORT="${1:-$REPORT}" ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) printf 'unknown argument: %s (try --help)\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

LOG_DIR="${PATCHAPI_VERIFY_LOG_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/patchapi-verify-all-XXXXXX")}"
mkdir -p "$LOG_DIR"
RESULTS="$LOG_DIR/results.tsv"
: >"$RESULTS"

# task | script | required | default timeout (s) | note shown in the report
# Order is cheapest-first so a broken workspace surfaces before the 20-minute
# trees. Tasks with no verifier of their own still get a row.
PLAN=$(cat <<'PLAN'
T-docs-scaffold|verify_docs.sh|yes|300|
T-root-workspace|verify_root.sh|yes|900|
T-packages-schemas|verify_packages_schemas.sh|yes|600|
T-packages-providers-google|verify_packages_providers_google.sh|yes|900|live Vertex reasoning call
T-packages-remaining|verify_packages_remaining.sh|yes|900|
T-skills|verify_skills.sh|yes|600|
T-services-control_api|verify_services_control_api.sh|yes|900|
T-services-repo_indexer|verify_services_repo_indexer.sh|yes|900|
T-services-github_tools|verify_services_github_tools.sh|yes|900|live GitHub App read is deferred, expect an internal SKIP
T-agents-adk|verify_agents_adk.sh|yes|1200|live ADK turn against Gemini 3.5 Flash
T-gemini-live|verify_gemini_live.sh|yes|900|live reasoning + live image, both required
T-db|verify_db.sh|yes|1200|needs a running Docker daemon
T-control-api-reads|verify_control_api_reads.sh|yes|1200|dashboard read path against seeded Postgres; needs a running Docker daemon
T-sandbox-local|verify_sandbox_local.sh|yes|1800|needs a running Docker daemon
T-apps-web|verify_apps_web.sh|yes|1800|npm ci + next build + HTTP probe
T-apps-web-browser|verify_apps_web_browser.sh|yes|1800|Playwright against a local Next server
T-infra-terraform|verify_infra_terraform.sh|yes|1800|terraform init/validate/plan against GCP
T-sandbox-gke|verify_sandbox_gke.sh|yes|2700|builds the runner image; claims and destroys a live sandbox when a cluster is reachable
T-github-app-live|-|no|0|deferred by setup.md §8 — no verifier in this batch
PLAN
)

matches_any() {
  local needle="$1"; shift
  local p
  for p in "$@"; do
    case "$needle" in *"$p"*) return 0 ;; esac
  done
  return 1
}

is_optional() {
  local script="$1"
  local list="${PATCHAPI_VERIFY_OPTIONAL:-}"
  case ",$list," in *",$script,"*) return 0 ;; esac
  return 1
}

# Run a command in its own process group so a timeout kills the whole tree
# (npm, docker, kubectl children included), not just the wrapper shell.
run_with_timeout() {
  local secs="$1" log="$2"; shift 2
  local pid rc=0 waited=0
  set -m
  # stdin from /dev/null: a verifier (or anything it spawns) that reads stdin
  # would otherwise swallow the caller's plan heredoc and silently truncate the
  # run — every verifier after it would simply never execute.
  ( "$@" ) >"$log" 2>&1 </dev/null &
  pid=$!
  set +m
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$secs" -gt 0 ] && [ "$waited" -ge "$secs" ]; then
      kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
      sleep 5
      kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
      wait "$pid" 2>/dev/null
      return 124
    fi
    sleep 2
    waited=$((waited + 2))
  done
  wait "$pid" || rc=$?
  return "$rc"
}

ledger_lines() {
  [ -f "$LEDGER" ] || { echo 0; return; }
  wc -l <"$LEDGER" | tr -d ' '
}

# The task-level status of the last line a script appended, empty when it
# appended nothing. Deliberately the *first* "status" key on the line: several
# verifiers nest a per-step array whose objects carry their own status, and a
# greedy match reads the last step instead of the task verdict.
ledger_status_since() {
  local before="$1" after="$2"
  [ "$after" -gt "$before" ] || return 0
  tail -n 1 "$LEDGER" | awk '
    {
      i = index($0, "\"status\"")
      if (i == 0) next
      s = substr($0, i)
      if (match(s, /"status"[ \t]*:[ \t]*"[^"]*"/)) {
        v = substr(s, RSTART, RLENGTH)
        sub(/^"status"[ \t]*:[ \t]*"/, "", v)
        sub(/"$/, "", v)
        print v
      }
    }'
}

sanitize() { printf '%s' "$1" | tr '\t\n' '  ' | sed 's/|/\\|/g'; }

SCAN_LOG="$LOG_DIR/secret-scan.txt"
SCAN_STATUS="NOT RUN"
SCAN_HITS=0
SCAN_REVIEW=0
# Split so this file's own pattern cannot match another file's scan output.
PAT_KEY="BEGIN [A-Z ]*PRIVATE"' KEY'
PAT_SA='"private_key"[[:space:]]*:[[:space:]]*"'
PAT_GH='gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}'
PAT_GOOG='AIza[0-9A-Za-z_-]{35}'
PAT_AWS='AKIA[0-9A-Z]{16}'
# The report quotes findings and this script defines the patterns, so both are
# excluded to keep the scan from flagging its own vocabulary.
SCAN_EXCLUDE="$SELF
$REPORT"

# A key header on its own is not a leaked key — sandbox/runner's tests carry
# bare `BEGIN ... PRIVATE KEY` markers to prove credentials are stripped. So a
# key-material match is only a blocking FINDING when the header (or a
# `private_key` field) is followed by something that looks like actual key
# body; otherwise it is a non-blocking REVIEW line that still gets printed.
# Nothing is suppressed silently.
triage_key_material() {
  awk -v f="$1" '
    { L[NR] = $0 }
    END {
      for (i = 1; i <= NR; i++) {
        if (L[i] !~ /BEGIN[ A-Z]*PRIVATE KEY/ && L[i] !~ /"private_key"[ \t]*:/) continue
        body = L[i] " " L[i + 1]
        gsub(/-----[^-]*-----/, " ", body)
        gsub(/"private_key"[ \t]*:/, " ", body)
        sev = (body ~ /[A-Za-z0-9+\/=]{40,}/) ? "FINDING" : "REVIEW"
        printf("%s:%d: %s: key material pattern\n", f, i, sev)
      }
    }
  ' "$1"
}

# --self-test exercises the classifier against a key that is real key material
# and one that is only a marker. Without it the blocking branch of the scan
# would ship untested, and a scan that cannot fail is not a scan.
self_test() {
  local dir="$LOG_DIR/self-test" rc=0 out
  mkdir -p "$dir"
  printf '{"private_key": "%sMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDaaaaaaaaaaaa%s"}\n' \
    '-----BEGIN PRIVATE KEY-----\n' '\n-----END PRIVATE KEY-----\n' >"$dir/real.json"
  printf 'HOST = {"GITHUB_APP_PRIVATE_KEY": "%s"}\n' \
    '-----BEGIN RSA PRIVATE KEY-----' >"$dir/marker.py"
  # 36 characters after the prefix: the shape a real GitHub token has.
  printf 'token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"\n' >"$dir/token.py"
  printf 'placeholder = "ghp_example"\n' >"$dir/placeholder.py"

  out="$(triage_key_material "$dir/real.json")"
  case "$out" in
    *FINDING*) printf 'ok   key material is a blocking FINDING\n' ;;
    *) printf 'FAIL key material was not classified FINDING: %s\n' "$out"; rc=1 ;;
  esac

  out="$(triage_key_material "$dir/marker.py")"
  case "$out" in
    *REVIEW*) printf 'ok   bare header is a non-blocking REVIEW\n' ;;
    *) printf 'FAIL bare header was not classified REVIEW: %s\n' "$out"; rc=1 ;;
  esac

  if grep -IqE "$PAT_GH" "$dir/token.py"; then
    printf 'ok   live-shaped GitHub token matches\n'
  else
    printf 'FAIL live-shaped GitHub token did not match\n'; rc=1
  fi
  if grep -IqE "$PAT_GH" "$dir/placeholder.py"; then
    printf 'FAIL placeholder token matched the live-token pattern\n'; rc=1
  else
    printf 'ok   placeholder token does not match\n'
  fi

  [ "$rc" -eq 0 ] && printf '\nPASS: verify_all.sh self-test\n' || printf '\nFAIL: verify_all.sh self-test\n'
  return "$rc"
}

# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

if [ "$SELF_TEST" = "1" ]; then
  self_test
  exit $?
fi

PLANNED_SCRIPTS=""
while IFS='|' read -r task script required budget note; do
  [ -n "$task" ] || continue
  [ "$script" = "-" ] || PLANNED_SCRIPTS="$PLANNED_SCRIPTS $script"
done <<EOF
$PLAN
EOF

# Anything on disk that the table does not know about still runs; an unlisted
# verifier must not be silently dropped from the report.
UNMAPPED=""
for path in scripts/verify_*.sh; do
  [ -f "$path" ] || continue
  base="${path##*/}"
  [ "$path" = "$SELF" ] && continue
  case " $PLANNED_SCRIPTS " in
    *" $base "*) ;;
    *) UNMAPPED="$UNMAPPED $base" ;;
  esac
done
for base in $UNMAPPED; do
  PLAN="$PLAN
(unmapped)|$base|yes|1800|not listed in setup.md §5 — running it anyway"
done

if [ "$LIST_ONLY" = "1" ]; then
  printf 'verify_all plan (logs would go to %s)\n\n' "$LOG_DIR"
  printf '%-30s %-42s %-9s %s\n' TASK SCRIPT REQUIRED TIMEOUT
  while IFS='|' read -r task script required budget note; do
    [ -n "$task" ] || continue
    printf '%-30s %-42s %-9s %ss\n' "$task" "$script" "$required" "$budget"
  done <<EOF
$PLAN
EOF
  exit 0
fi

printf '== PatchAPI aggregate verification\n'
printf 'started    %s\n' "$STARTED_AT"
printf 'logs       %s\n' "$LOG_DIR"
printf 'live       PATCHAPI_REQUIRE_LIVE=%s\n\n' "$PATCHAPI_REQUIRE_LIVE"

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

# The plan is read on fd 3 rather than stdin, so nothing a verifier does to
# stdin can truncate the run.
while IFS='|' read -r task script required budget note <&3; do
  [ -n "$task" ] || continue

  if [ "$script" = "-" ]; then
    printf '%-42s DEFERRED\n' "$task"
    printf '%s\t%s\t%s\tDEFERRED\t0\t-\t0\t%s\t-\n' \
      "$task" "$script" "$required" "$(sanitize "$note")" >>"$RESULTS"
    continue
  fi

  path="scripts/$script"

  if [ "$ONLY_COUNT" -gt 0 ] && ! matches_any "$script" "${ONLY_PATTERNS[@]}"; then
    printf '%s\t%s\t%s\tNOT_RUN\t0\t-\t0\t%s\t-\n' \
      "$task" "$script" "$required" "excluded by --only" >>"$RESULTS"
    continue
  fi
  if [ "$SKIP_COUNT" -gt 0 ] && matches_any "$script" "${SKIP_PATTERNS[@]}"; then
    printf '%-42s NOT RUN (--skip)\n' "$task"
    printf '%s\t%s\t%s\tNOT_RUN\t0\t-\t0\t%s\t-\n' \
      "$task" "$script" "$required" "excluded by --skip" >>"$RESULTS"
    continue
  fi

  if [ ! -f "$path" ]; then
    printf '%-42s MISSING (%s)\n' "$task" "$path"
    printf '%s\t%s\t%s\tMISSING\t0\t-\t0\t%s\t-\n' \
      "$task" "$script" "$required" "no such file: $path" >>"$RESULTS"
    continue
  fi

  budget="${PATCHAPI_VERIFY_TIMEOUT:-$budget}"
  log="$LOG_DIR/${script%.sh}.log"
  before="$(ledger_lines)"

  printf -- '-- %s (%s, timeout %ss)\n' "$task" "$script" "$budget"
  start=$SECONDS
  rc=0
  run_with_timeout "$budget" "$log" bash "$path" || rc=$?
  elapsed=$((SECONDS - start))

  after="$(ledger_lines)"
  recorded="$(ledger_status_since "$before" "$after")"
  skips="$(grep -c '^[[:space:]]*SKIP:' "$log" 2>/dev/null || true)"
  skips="${skips:-0}"
  detail=""

  if [ "$rc" -eq 124 ]; then
    status=TIMEOUT
    detail="killed after ${budget}s"
  elif [ "$rc" -ne 0 ]; then
    status=FAIL
    detail="exit $rc"
    case "$recorded" in
      *PASS*) detail="$detail; script recorded \"$recorded\" in the ledger — exit code and self-report disagree" ;;
    esac
  else
    status=PASS
    case "$recorded" in
      *FAIL*)
        status=FAIL
        detail="exit 0 but the script recorded \"$recorded\" in the ledger — exit code and self-report disagree"
        ;;
      SKIP*|*"SKIP")
        status=SKIP
        detail="script recorded \"$recorded\""
        ;;
    esac
    # verify_sandbox_gke.sh and verify_apps_web.sh keep no ledger line, so fall
    # back to the printed contract: a SKIP: line with no PASS: line is a SKIP.
    if [ "$status" = "PASS" ] && [ -z "$recorded" ] && [ "$skips" -gt 0 ] &&
       ! grep -q '^[[:space:]]*PASS' "$log"; then
      status=SKIP
      detail="$(grep -m1 '^[[:space:]]*SKIP:' "$log")"
    fi
    if [ "$status" = "PASS" ] && [ "$skips" -gt 0 ]; then
      detail="$skips internal SKIP(s): $(grep -m1 '^[[:space:]]*SKIP:' "$log")"
    fi
  fi

  if [ "$status" = "FAIL" ] || [ "$status" = "TIMEOUT" ]; then
    firstfail="$(grep -m1 -E '^[[:space:]]*(FAIL|Error|error:)' "$log" || true)"
    [ -n "$firstfail" ] && detail="$detail | $firstfail"
  fi

  printf '   %-8s %-40s %ss\n\n' "$status" "$task" "$elapsed"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$task" "$script" "$required" "$status" "$elapsed" "$rc" "$skips" \
    "$(sanitize "$detail")" "$log" >>"$RESULTS"
done 3<<EOF
$PLAN
EOF

# A run that stops early must never read as a complete one. Every plan row has
# to produce exactly one result row.
PLAN_ROWS="$(printf '%s\n' "$PLAN" | grep -c '|')"
RESULT_ROWS="$(wc -l <"$RESULTS" | tr -d ' ')"
TRUNCATED=0
if [ "$RESULT_ROWS" -ne "$PLAN_ROWS" ]; then
  TRUNCATED=1
  printf 'FAIL: the run covered %s of %s planned entries — results are incomplete\n\n' \
    "$RESULT_ROWS" "$PLAN_ROWS"
fi

# ---------------------------------------------------------------------------
# Credential scan over tracked paths
# ---------------------------------------------------------------------------

SCANNED=0
SCAN_REVIEW=0

if [ "$DO_SCAN" = "1" ]; then
  : >"$SCAN_LOG"
  # Tracked *and* untracked-but-not-ignored files: at this stage of the build
  # most of the tree is still uncommitted, so scanning `git ls-files` alone
  # would report a clean tree after reading five files. `--exclude-standard`
  # keeps .secrets/, .gemini/ and the other gitignored paths out.
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    case "$SCAN_EXCLUDE" in *"$f"*) continue ;; esac
    SCANNED=$((SCANNED + 1))
    # Line numbers only. Echoing the matched line would copy the credential
    # into the log this report links to.
    grep -InE "$PAT_GH|$PAT_GOOG|$PAT_AWS" "$f" 2>/dev/null |
      cut -d: -f1 | sed "s|^|$f:|;s|\$|: FINDING: live-shaped token|" >>"$SCAN_LOG"
    if grep -IqE "$PAT_KEY|$PAT_SA" "$f" 2>/dev/null; then
      triage_key_material "$f" >>"$SCAN_LOG"
    fi
  done <<EOF
$(git ls-files --cached --others --exclude-standard)
EOF

  # A tracked file under .secrets/ is a finding in itself, not just its contents.
  TRACKED_SECRETS="$(git ls-files .secrets 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$TRACKED_SECRETS" -gt 0 ]; then
    git ls-files .secrets |
      sed 's|$|: FINDING: tracked by git under .secrets/|' >>"$SCAN_LOG"
  fi

  SCAN_HITS="$(grep -c 'FINDING:' "$SCAN_LOG" 2>/dev/null || true)"
  SCAN_HITS="${SCAN_HITS:-0}"
  SCAN_REVIEW="$(grep -c 'REVIEW:' "$SCAN_LOG" 2>/dev/null || true)"
  SCAN_REVIEW="${SCAN_REVIEW:-0}"

  if [ "$SCAN_HITS" -eq 0 ]; then
    SCAN_STATUS=PASS
  else
    SCAN_STATUS=FAIL
  fi
  printf 'credential scan: %s (%s finding(s), %s review line(s), %s files)\n\n' \
    "$SCAN_STATUS" "$SCAN_HITS" "$SCAN_REVIEW" "$SCANNED"
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

count_status() { awk -F'\t' -v s="$1" '$4 == s' "$RESULTS" | wc -l | tr -d ' '; }

N_PASS="$(count_status PASS)"
N_SKIP="$(count_status SKIP)"
N_FAIL="$(count_status FAIL)"
N_TIMEOUT="$(count_status TIMEOUT)"
N_MISSING="$(count_status MISSING)"
N_NOTRUN="$(count_status NOT_RUN)"
N_DEFERRED="$(count_status DEFERRED)"

BLOCKING=0
while IFS=$'\t' read -r task script required status elapsed rc skips detail log; do
  case "$status" in
    FAIL|TIMEOUT|MISSING)
      is_optional "$script" && continue
      [ "$required" = "yes" ] && BLOCKING=$((BLOCKING + 1))
      ;;
  esac
done <"$RESULTS"
[ "$SCAN_STATUS" = "FAIL" ] && BLOCKING=$((BLOCKING + 1))
[ "$TRUNCATED" -eq 1 ] && BLOCKING=$((BLOCKING + 1))

if [ "$BLOCKING" -eq 0 ]; then
  VERDICT="PASS — no required verifier failed"
else
  VERDICT="FAIL — $BLOCKING required check(s) did not pass"
fi

FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="clean"
[ -n "$(git status --porcelain 2>/dev/null)" ] && GIT_DIRTY="dirty (setup batch is uncommitted)"

TMP_REPORT="$LOG_DIR/setup-report.md"
{
  printf '# PatchAPI setup verification report\n\n'
  printf '_Generated by `./scripts/verify_all.sh`. Every status below comes from a\n'
  printf 'verifier that ran in this session; nothing here is transcribed from a\n'
  printf 'previous run or from a worker report._\n\n'
  printf '| | |\n|---|---|\n'
  printf '| Run started | `%s` |\n' "$STARTED_AT"
  printf '| Run finished | `%s` |\n' "$FINISHED_AT"
  printf '| Commit | `%s` (%s) |\n' "$GIT_SHA" "$GIT_DIRTY"
  printf '| Logs | `%s` |\n' "$LOG_DIR"
  printf '| Live checks required | `PATCHAPI_REQUIRE_LIVE=%s` |\n' "$PATCHAPI_REQUIRE_LIVE"
  printf '| **Verdict** | **%s** |\n\n' "$VERDICT"
  printf 'PASS %s · SKIP %s · FAIL %s · TIMEOUT %s · MISSING %s · NOT RUN %s · DEFERRED %s\n\n' \
    "$N_PASS" "$N_SKIP" "$N_FAIL" "$N_TIMEOUT" "$N_MISSING" "$N_NOTRUN" "$N_DEFERRED"

  if [ "$TRUNCATED" -eq 1 ]; then
    printf '> **This run is incomplete.** %s of %s planned entries produced a\n' \
      "$RESULT_ROWS" "$PLAN_ROWS"
    printf '> result. Treat every absent row as unverified, not as passing.\n\n'
  fi

  printf '## Broken or unfinished\n\n'
  if [ $((N_FAIL + N_TIMEOUT + N_MISSING)) -eq 0 ]; then
    printf 'Nothing. No verifier failed, timed out, or was missing in this run.\n\n'
  else
    printf '| Task | Verifier | Status | What happened | Log |\n|---|---|---|---|---|\n'
    awk -F'\t' '$4=="FAIL" || $4=="TIMEOUT" || $4=="MISSING" {
      printf("| `%s` | `%s` | **%s** | %s | `%s` |\n", $1, $2, $4, $8, $9) }' "$RESULTS"
    printf '\n'
  fi

  printf '## Verified but incomplete (SKIP / deferred / not run)\n\n'
  if [ $((N_SKIP + N_DEFERRED + N_NOTRUN)) -eq 0 ]; then
    printf 'None.\n\n'
  else
    printf '| Task | Verifier | Status | Reason |\n|---|---|---|---|\n'
    awk -F'\t' '$4=="SKIP" || $4=="DEFERRED" || $4=="NOT_RUN" {
      printf("| `%s` | `%s` | %s | %s |\n", $1, $2, $4, $8) }' "$RESULTS"
    printf '\n'
  fi

  printf '## Every setup task\n\n'
  printf 'One row per task in `setup.md` §5, in execution order.\n\n'
  printf '| Task | Verifier | Status | Exit | Duration | Notes |\n|---|---|---|---|---|---|\n'
  awk -F'\t' '{
    d = ($5 == 0 && $4 != "PASS" && $4 != "SKIP" && $4 != "FAIL" && $4 != "TIMEOUT") ? "—" : $5 "s"
    printf("| `%s` | `%s` | %s | %s | %s | %s |\n", $1, $2, $4, $6, d, ($8 == "" ? "—" : $8)) }' "$RESULTS"
  printf '\n'

  printf '## Credential scan\n\n'
  if [ "$DO_SCAN" != "1" ]; then
    printf 'NOT RUN — invoked with `--no-scan`.\n\n'
  else
    printf 'Scanned every tracked and untracked-but-not-ignored file\n'
    printf '(`git ls-files --cached --others --exclude-standard`) for private key\n'
    printf 'headers, service-account `private_key` fields, GitHub tokens, Google API\n'
    printf 'keys, and AWS access key IDs. `%s` and `%s` are excluded because one\n' "$SELF" "$REPORT"
    printf 'defines the patterns and the other quotes findings. Gitignored paths\n'
    printf '(`.secrets/`, `.gemini/`, `.fleet/`, `.claude/`) are out of scope by\n'
    printf 'design — the check is "would a commit leak a credential", so the scan\n'
    printf 'also asserts that nothing under `.secrets/` is tracked.\n\n'
    printf 'A bare `BEGIN ... PRIVATE KEY` header with no key body after it is\n'
    printf 'reported as REVIEW, not as a finding: `sandbox/runner` uses such markers\n'
    printf 'as test fixtures. Only a header followed by key material, a live-shaped\n'
    printf 'token, or a tracked file under `.secrets/` is a blocking FINDING.\n\n'
    printf -- '- Files scanned: %s\n' "$SCANNED"
    printf -- '- Result: **%s** — %s blocking finding(s), %s review line(s)\n' \
      "$SCAN_STATUS" "$SCAN_HITS" "$SCAN_REVIEW"
    printf -- '- Files under `.secrets/` tracked by git: %s\n' "${TRACKED_SECRETS:-0}"
    printf -- '- Raw output: `%s`\n\n' "$SCAN_LOG"
    if [ "$((SCAN_HITS + SCAN_REVIEW))" -gt 0 ]; then
      printf '```\n'
      head -40 "$SCAN_LOG"
      printf '```\n\n'
    fi
  fi

  printf '## Scope of this report\n\n'
  printf -- '- A verifier that exits 0 is PASS; a verifier that records `SKIP` in\n'
  printf '  `%s`, or prints `SKIP:` with no `PASS` line, is SKIP.\n' "$LEDGER"
  printf -- '- When a verifier'"'"'s exit code and its ledger line disagree, this report\n'
  printf '  calls it FAIL and names the discrepancy. It never resolves the conflict\n'
  printf '  in favour of the optimistic side.\n'
  printf -- '- `T-github-app-live` has no verifier in this batch. `setup.md` §8 defers\n'
  printf '  the GitHub App, so the live installation-token path is **unverified**,\n'
  printf '  not passing. `services/github_tools` is exercised offline only.\n'
  printf -- '- A PASS here means the verifier ran and exited 0 on this machine at the\n'
  printf '  time above. It is not a claim about production.\n\n'

  printf '## Reproduce\n\n'
  printf '```bash\n'
  printf './scripts/verify_all.sh              # this report\n'
  printf './scripts/verify_all.sh --list       # plan only\n'
  awk -F'\t' '$2 != "-" && $4 != "NOT_RUN" { printf("./scripts/%s\n", $2) }' "$RESULTS"
  printf '```\n'
} >"$TMP_REPORT"

mkdir -p "$(dirname "$REPORT")"
cp "$TMP_REPORT" "$REPORT"

printf '%s\n' "$VERDICT"
printf 'report     %s\n' "$REPORT"
printf 'logs       %s\n' "$LOG_DIR"

if [ "$BLOCKING" -eq 0 ]; then
  AGG_STATUS=PASS
else
  AGG_STATUS=FAIL
fi
printf '{"task":"T-qa-aggregate","status":"%s","command":"./scripts/verify_all.sh","at":"%s","notes":"pass=%s skip=%s fail=%s timeout=%s missing=%s not_run=%s deferred=%s secret_scan=%s"}\n' \
  "$AGG_STATUS" "$FINISHED_AT" "$N_PASS" "$N_SKIP" "$N_FAIL" "$N_TIMEOUT" \
  "$N_MISSING" "$N_NOTRUN" "$N_DEFERRED" "$SCAN_STATUS" >>"$LEDGER"

[ "$BLOCKING" -eq 0 ] || exit 1
