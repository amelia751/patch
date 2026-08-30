#!/usr/bin/env bash
# Dynamic verifier for setup.md T-packages-remaining.
#
# Covers packages/github, packages/repo_scan, packages/policy, packages/events,
# packages/memory, and packages/observability. Every check executes code: the
# packages are imported for real, the forbidden-path rule is exercised against
# `.github/workflows/release.yml`, an adversarial provider note is scanned, and
# a span is emitted through the OpenTelemetry console exporter and read back out
# of captured output. Exits non-zero on any failure and records the outcome in
# the shared setup ledger.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PACKAGES=(github repo_scan policy events memory observability)
LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_packages_remaining.sh"
STATUS="FAIL"

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-packages-remaining","status":"%s","command":"%s","at":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LEDGER"
}
trap record EXIT

step() { printf '\n== %s\n' "$1"; }

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is not installed (see setup.md §3)"
  exit 1
fi

# Preferred path: the shared workspace environment. A workspace member in
# another tree that is mid-flight makes `uv sync` fail for every tree, which is
# not a defect in these packages — fall back to an isolated environment built
# from their own pinned dependencies so they stay verifiable.
step "environment"
if uv sync --all-packages >/dev/null 2>&1; then
  echo "workspace environment"
  RUN=(uv run --all-packages)
  COMMAND="$COMMAND (workspace)"
else
  echo "NOTE: 'uv sync --all-packages' failed; another workspace member is likely incomplete."
  echo "isolated environment"
  RUN=(
    uv run --no-project
    --with "opentelemetry-api>=1.30,<2"
    --with "opentelemetry-sdk>=1.30,<2"
    --with "pytest>=8.3,<9"
    --with "ruff>=0.14,<0.15"
  )
  COMMAND="$COMMAND (isolated)"
fi

step "packages import"
"${RUN[@]}" python - <<'PY'
from importlib import import_module

expected = {
    "packages.github": ["Capability", "resolve_capability", "ForbiddenCapabilityError"],
    "packages.repo_scan": ["scan_tree", "classify_path", "UsageKind"],
    "packages.policy": [
        "evaluate_path",
        "evaluate_change",
        "scan_untrusted_text",
        "screen_untrusted_text",
    ],
    "packages.events": ["EventEnvelope", "EventType", "idempotency_key"],
    "packages.memory": ["MemoryBankClient", "LocalMemoryBank", "RepositoryProfile"],
    "packages.observability": ["configure_tracing", "span"],
}

for name, symbols in expected.items():
    module = import_module(name)
    missing = [symbol for symbol in symbols if not hasattr(module, symbol)]
    assert not missing, f"{name} is missing {missing}"
    print(f"{name}: {', '.join(symbols)}")
PY

step "forbidden path is BLOCKED"
"${RUN[@]}" python - <<'PY'
from packages.policy import PolicyOutcome, evaluate_change, evaluate_path

target = ".github/workflows/release.yml"
finding = evaluate_path(target)
assert finding.outcome is PolicyOutcome.BLOCKED, f"expected BLOCKED, got {finding.outcome}"
assert finding.rule_id == "policy.path.ci_definition", finding.rule_id
print(f"{target} -> {finding.outcome.value} ({finding.rule_id}, matched {finding.matched})")

# A blocked path poisons the whole patch, and the denial is visible.
evaluation = evaluate_change(proposed_paths=["cli/src/image.ts", target])
assert evaluation.outcome is PolicyOutcome.BLOCKED
assert not evaluation.permits_patching
record = evaluation.blocking_findings[0].to_audit_record()
print(f"audit: attempted={record['attempted']!r} outcome={record['outcome']} tier={record['tier']}")

# Denial of service in the other direction would be just as wrong.
assert evaluate_path("cli/src/image.ts").outcome is PolicyOutcome.ALLOW
print("cli/src/image.ts -> allow")
PY

step "prompt injection in provider text is BLOCKED"
"${RUN[@]}" python - <<'PY'
from pathlib import Path

from packages.policy import PolicyOutcome, scan_untrusted_text

fixtures = Path("packages/policy/tests/adversarial")
hostile = (fixtures / "prompt-injection-release-note.md").read_text(encoding="utf-8")
benign = (fixtures / "benign-release-note.md").read_text(encoding="utf-8")

evaluation = scan_untrusted_text(hostile, source="prompt-injection-release-note.md")
assert evaluation.outcome is PolicyOutcome.BLOCKED, evaluation.outcome
tripped = sorted({finding.rule_id for finding in evaluation.blocking_findings})
assert "policy.injection.instruction_override" in tripped, tripped
assert "policy.injection.merge_or_approve" in tripped, tripped
print("adversarial release note -> blocked:", ", ".join(tripped))

assert scan_untrusted_text(benign, source="benign-release-note.md").outcome is PolicyOutcome.ALLOW
print("benign release note -> allow")
PY

step "the composed gate refuses without Model Armor"
"${RUN[@]}" python - <<'PY'
from pathlib import Path

from packages.policy import ArmorState, PolicyOutcome, screen_untrusted_text

# `screen_untrusted_text` layers Model Armor behind the regex gate. This asserts
# the property that makes that safe to deploy: with no Model Armor configured —
# which is this environment, and the default everywhere — the composed verdict is
# exactly the deterministic one, and it says so rather than implying two gates.
fixtures = Path("packages/policy/tests/adversarial")
hostile = (fixtures / "prompt-injection-release-note.md").read_text(encoding="utf-8")

blocked = screen_untrusted_text(hostile, source="prompt-injection-release-note.md", env={})
assert blocked.outcome is PolicyOutcome.BLOCKED, blocked.outcome
assert not blocked.armor.consulted
assert len(blocked.screened_by) == 1, blocked.screened_by
assert not blocked.degraded, "an unconfigured second opinion is not a degraded one"
print(f"unconfigured -> {blocked.outcome.value} by {blocked.screened_by[0]}")

benign = (fixtures / "benign-release-note.md").read_text(encoding="utf-8")
allowed = screen_untrusted_text(benign, source="benign-release-note.md", env={})
assert allowed.allowed
assert allowed.armor.state is ArmorState.NOT_CONSULTED
print("benign release note -> allow (one gate, reported as one)")
PY

step "span reaches the console exporter"
"${RUN[@]}" python - <<'PY'
import io
import json

from packages.observability import ATTR_RUN_ID, SPAN_POLICY, configure_tracing, span

buffer = io.StringIO()
provider = configure_tracing(service_name="patchapi-verify", out=buffer)
with span(SPAN_POLICY, attributes={ATTR_RUN_ID: "run-verify-001"}, provider=provider):
    pass
provider.force_flush()

captured = buffer.getvalue()
assert SPAN_POLICY in captured, "span name did not reach the console exporter"
record = json.loads(captured[captured.index("{") :])
assert record["name"] == SPAN_POLICY, record["name"]
assert record["attributes"][ATTR_RUN_ID] == "run-verify-001"
print(f"exported span: {record['name']} ({record['resource']['attributes']['service.name']})")
PY

step "event envelope refuses to carry source code"
"${RUN[@]}" python - <<'PY'
from packages.events import ActionType, EventEnvelope, EventType, PayloadError, TrustLevel, idempotency_key

base_sha = "c09e1a44200ff5e951746e013035e68aeb3a14b1"
envelope = EventEnvelope(
    event_type=EventType.PROVIDER_CHANGE_DETECTED,
    event_id="evt-verify",
    run_id="run-verify-001",
    occurred_at="2026-08-11T23:00:00Z",
    trust=TrustLevel.UNTRUSTED_PROVIDER_INPUT,
    payload={"change_id": "google-imagen4-retirement"},
).with_idempotency_key(idempotency_key("run-verify-001", ActionType.OPEN_PULL_REQUEST, base_sha))

assert EventEnvelope.from_json(envelope.to_json()) == envelope
print("envelope round-trip ok;", envelope.idempotency_key)

try:
    EventEnvelope(
        event_type=EventType.PATCH_REQUESTED,
        event_id="evt-verify-2",
        run_id="run-verify-001",
        occurred_at="2026-08-11T23:00:00Z",
        trust=TrustLevel.INTERNAL_ANALYSIS,
        payload={"diff": "x" * 3000},
    )
except PayloadError as exc:
    print("oversized payload refused:", str(exc).split(";")[0])
else:
    raise AssertionError("an event carrying a diff was accepted")
PY

for package in "${PACKAGES[@]}"; do
  step "pytest packages/$package"
  "${RUN[@]}" pytest "packages/$package" -q
done

step "ruff check"
"${RUN[@]}" ruff check "${PACKAGES[@]/#/packages/}"

step "ruff format --check"
"${RUN[@]}" ruff format --check "${PACKAGES[@]/#/packages/}"

STATUS="PASS"
echo
echo "PASS: packages/{$(IFS=,; echo "${PACKAGES[*]}")} verified"
