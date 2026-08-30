#!/usr/bin/env bash
# Live verifier for the Model Armor second opinion behind the injection gate.
#
# Opt-in: it calls Google and needs credentials, so it is not part of the default
# suite. `packages/policy/tests/test_armor.py` covers the composition against a
# fake transport and runs everywhere. What can only be checked here is that the
# pinned endpoint, template and response shape are still the real ones — a fake
# transport agrees with whatever this repository believes, including a stale
# belief.
#
# Every check executes code. The four documents below are screened through the
# product's own `screen_untrusted_text`, and the expected verdicts are the ones
# measured against the live template, not ones a model asserted.
#
#   PATCHAPI_MODEL_ARMOR_LIVE=1 ./scripts/verify_policy_model_armor.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="PATCHAPI_MODEL_ARMOR_LIVE=1 ./scripts/verify_policy_model_armor.sh"
STATUS="FAIL"

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-policy-model-armor","status":"%s","command":"%s","at":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LEDGER"
}

step() { printf '\n== %s\n' "$1"; }

# A skip is not a pass and not a failure. Recording it as either would make the
# ledger claim this gate was verified on a machine that never called Google.
skip() { STATUS="SKIP"; printf 'SKIP: %s\n' "$1"; exit 0; }

if [ "${PATCHAPI_MODEL_ARMOR_LIVE:-}" != "1" ]; then
  skip "set PATCHAPI_MODEL_ARMOR_LIVE=1 to call the live Model Armor template"
fi

trap record EXIT

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is not installed (see setup.md §3)"
  exit 1
fi

# The grant is on the deployment service accounts, not on a developer's own
# account, so a bare `gcloud auth application-default login` resolves to an
# identity with no `roles/modelarmor.user` and every call 403s. The key file the
# other bootstrap scripts use is the identity that holds the role.
step "credentials"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$REPO_ROOT/.secrets/gcp-service-account.json}"
if [ ! -f "$KEY_FILE" ]; then
  skip "no GCP credentials at $KEY_FILE (set GOOGLE_APPLICATION_CREDENTIALS)"
fi
export GOOGLE_APPLICATION_CREDENTIALS="$KEY_FILE"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$(
  uv run python -c "import json,sys;print(json.load(open(sys.argv[1]))['project_id'])" "$KEY_FILE"
)}"
export PATCHAPI_MODEL_ARMOR_ENABLED=1
printf 'project: %s\ncredentials: %s\n' "$GOOGLE_CLOUD_PROJECT" "$KEY_FILE"

# `demo/` is a local working area in this repository, so the measured verdicts
# below are only checkable where it is present. The composition itself is covered
# by `packages/policy/tests/test_armor.py`, which needs neither.
step "fixtures"
for fixture in \
  demo/adversarial/prompt-injection-provider-note.md \
  demo/adversarial/ci-workflow-edit-request.md \
  demo/adversarial/unrelated-imagen-prose.md \
  demo/adversarial/injected-change-manifest.json \
  demo/fixtures/google-imagen4-deprecation.json; do
  [ -f "$fixture" ] || skip "missing $fixture"
done
echo "all five present"

step "the template is reachable on the regional endpoint"
uv run python - <<'PY'
from packages.policy.armor import ModelArmorClient, model_armor_unavailable_reason
from packages.policy.config import ARMOR_ENDPOINT_HOST

reason = model_armor_unavailable_reason()
assert reason is None, f"Model Armor is not configured: {reason}"

client = ModelArmorClient.from_env()
print("template:", client.template)
# Pinned, because the global host serves only floor settings and answers a
# template call with a 403 that names permission rather than the wrong host.
assert ARMOR_ENDPOINT_HOST == "modelarmor.{location}.rep.googleapis.com", ARMOR_ENDPOINT_HOST

screening = client.sanitize_user_prompt("The provider retired one model identifier.")
assert screening.consulted, screening.detail
print("reachable:", screening.state.value, "|", screening.detail)
PY

step "measured verdicts on the repository's own fixtures"
uv run python - <<'PY'
from pathlib import Path

from packages.policy.armor import ArmorState, screen_untrusted_text
from packages.policy.decision import PolicyOutcome
from packages.policy.injection import normalize_untrusted_text

# (document, deterministic verdict, Model Armor state, injection confidence).
# Measured against the live template. The interesting row is the second: the
# deterministic rules clear the CI-edit request and Model Armor does not, which
# is the whole reason for consulting it.
EXPECTED = [
    (
        "demo/adversarial/prompt-injection-provider-note.md",
        PolicyOutcome.BLOCKED,
        ArmorState.NOT_CONSULTED,
        "",
    ),
    (
        "demo/adversarial/ci-workflow-edit-request.md",
        PolicyOutcome.BLOCKED,
        ArmorState.MATCH,
        "MEDIUM_AND_ABOVE",
    ),
    (
        "demo/adversarial/unrelated-imagen-prose.md",
        PolicyOutcome.ALLOW,
        ArmorState.CLEAN,
        "",
    ),
    (
        "demo/fixtures/google-imagen4-deprecation.json",
        PolicyOutcome.ALLOW,
        ArmorState.CLEAN,
        "",
    ),
]

for path, outcome, state, confidence in EXPECTED:
    text = normalize_untrusted_text(Path(path).read_text(encoding="utf-8"))
    screening = screen_untrusted_text(text, source=path)
    assert not screening.degraded, f"{path}: no verdict was obtained ({screening.armor.detail})"
    assert screening.outcome is outcome, f"{path}: expected {outcome}, got {screening.outcome}"
    assert screening.armor.state is state, f"{path}: expected {state}, got {screening.armor.state}"
    assert screening.armor.confidence == confidence, (
        f"{path}: expected confidence {confidence!r}, got {screening.armor.confidence!r}"
    )
    print(
        f"{Path(path).name}: {screening.outcome.value}"
        f" | model_armor={screening.armor.state.value}"
        f"{' ' + screening.armor.confidence if screening.armor.confidence else ''}"
        f" | screened_by={len(screening.screened_by)}"
    )
PY

step "a hostile document is never forwarded to the service"
uv run python - <<'PY'
from pathlib import Path

from packages.policy.armor import ArmorState, screen_untrusted_text
from packages.policy.injection import normalize_untrusted_text

# The deterministic gate short-circuits, so the one document here that is
# unambiguously an attack is refused without leaving the process.
path = "demo/adversarial/prompt-injection-provider-note.md"
screening = screen_untrusted_text(
    normalize_untrusted_text(Path(path).read_text(encoding="utf-8")), source=path
)
assert screening.armor.state is ArmorState.NOT_CONSULTED, screening.armor.state
assert "already refused" in screening.armor.detail, screening.armor.detail
print("not forwarded:", screening.armor.detail)
PY

step "a misconfigured template degrades visibly and does not refuse the run"
PATCHAPI_MODEL_ARMOR_TEMPLATE="does-not-exist-$$" uv run python - <<'PY'
from pathlib import Path

from packages.policy.armor import ArmorState, screen_untrusted_text
from packages.policy.decision import PolicyOutcome
from packages.policy.injection import normalize_untrusted_text

# Google's Vertex integration fails open. This asserts the property that makes
# that survivable here: the run keeps the verdict it has, and says it is the
# only one it got.
path = "demo/fixtures/google-imagen4-deprecation.json"
screening = screen_untrusted_text(
    normalize_untrusted_text(Path(path).read_text(encoding="utf-8")), source=path
)
assert screening.outcome is PolicyOutcome.ALLOW, screening.outcome
assert screening.armor.state is ArmorState.UNAVAILABLE, screening.armor.state
assert screening.degraded
assert not screening.armor.consulted
assert len(screening.screened_by) == 1, screening.screened_by
record = screening.to_audit_record()
assert record["degraded"] is True
print("degraded:", record["model_armor"]["state"], "|", record["model_armor"]["detail"][:120])
PY

step "the intake choke point reports which gates cleared a notice"
uv run python - <<'PY'
from pathlib import Path

from agents.context import RunContext
from agents.tools.change.feed import build_provider_feed_tools
from packages.policy.armor import GATE_DETERMINISTIC, GATE_MODEL_ARMOR

root = Path.cwd()
context = RunContext(
    run_id="run-verify-armor", repo_root=root, feed_dir=root / "demo" / "fixtures"
)
tools = {fn.__name__: fn for fn in build_provider_feed_tools(context)}
result = tools["load_provider_notice"]("imagen4-retirement-2026-08-17")

assert result["status"] == "ok", result
assert result["screened_by"] == [GATE_DETERMINISTIC, GATE_MODEL_ARMOR], result["screened_by"]
assert result["screening_degraded"] is False
print("load_provider_notice screened_by:", ", ".join(result["screened_by"]))
PY

step "a seeded run reaches SANITIZED only through the gate"
uv run python - <<'PY'
from pathlib import Path

from agents.context import RunContext
from agents.orchestrator import Orchestrator
from agents.trace import ToolTrace
from packages.policy.armor import GATE_MODEL_ARMOR
from packages.schemas.run_state import RunState

root = Path.cwd()


def seed(manifest: Path) -> tuple[RunState, ToolTrace]:
    context = RunContext(
        run_id="run-verify-armor", repo_root=root, feed_dir=root / "demo" / "fixtures"
    )
    trace = ToolTrace(run_id=context.run_id)
    orchestrator = Orchestrator(context, trace)
    orchestrator.seed_static_manifest(manifest)
    return orchestrator.state, trace


state, trace = seed(root / "agents" / "fixtures" / "change_manifest.gemini20.json")
assert state is RunState.NORMALIZED, state
event = trace.calls("screen_untrusted_text")[0]
assert GATE_MODEL_ARMOR in (event.detail or ""), event.detail
print("clean manifest:", state.value, "|", event.detail)

state, trace = seed(root / "demo" / "adversarial" / "injected-change-manifest.json")
assert state is RunState.BLOCKED, f"an injected manifest reached {state}"
print("injected manifest:", state.value, "| ADV-09 holds")
PY

step "pytest packages/policy agents"
uv run pytest packages/policy agents -q

# Scoped to what this change owns. `agents/` as a whole carries formatting drift
# from files other work is mid-flight on, and a verifier that fails on those
# reports someone else's tree rather than this gate.
OWNED=(
  packages/policy
  agents/orchestrator.py
  agents/tools/change/feed.py
  agents/tests/test_intake_screening.py
)

step "ruff"
uv run ruff check "${OWNED[@]}"
uv run ruff format --check "${OWNED[@]}"

STATUS="PASS"
echo
echo "PASS: Model Armor verified live against ${GOOGLE_CLOUD_PROJECT}"
