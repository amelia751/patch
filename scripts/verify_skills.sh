#!/usr/bin/env bash
# Verifier for the skill packages under skills/.
#
# A skill is loaded at runtime by ADK's own reader, so the only verification
# worth having is that reader accepting every package and the agent being
# offered exactly the tools it was granted. A package that fails the Agent Skill
# specification does not error at startup — it is simply absent from
# `list_skills`, and the Patch agent plans from recall instead of from a method.
# Grepping for filenames would not catch that.
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LEDGER="demo/setup-ledger.ndjson"

failures=0
skips=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

ok() {
  printf 'ok   %s\n' "$*"
}

skip() {
  printf 'SKIP: %s\n' "$*"
  skips=$((skips + 1))
}

if command -v uv >/dev/null 2>&1; then
  PY=(uv run python)
elif command -v python3 >/dev/null 2>&1; then
  PY=(python3)
else
  printf 'FAIL: no python3 or uv on PATH\n' >&2
  exit 1
fi

# --- the packages load through ADK ------------------------------------------

if "${PY[@]}" - <<'PY'
import asyncio
import sys

from agents.adk import adk_unavailable_reason, build_skill_toolset, repo_root, skill_packages
from agents.config import SKILL_TOOLS, AgentId, tool_allowlist

reason = adk_unavailable_reason()
if reason is not None:
    print(f"google-adk unavailable: {reason}", file=sys.stderr)
    raise SystemExit(2)

root = repo_root() / "skills"
packages = skill_packages(root)
if not packages:
    print(f"no SKILL.md package under {root}", file=sys.stderr)
    raise SystemExit(1)

from google.adk.skills import load_skill_from_dir

problems = []
for package in packages:
    try:
        skill = load_skill_from_dir(package)
    except Exception as exc:
        problems.append(f"{package.name}: does not load ({exc})")
        continue
    if skill.name != package.name:
        problems.append(f"{package.name}: frontmatter name is {skill.name!r}")
    if not skill.frontmatter.description.strip():
        problems.append(f"{package.name}: no description for list_skills to show")
    if not skill.frontmatter.metadata.get("version"):
        problems.append(f"{package.name}: no metadata.version to record on a patch plan")
    print(f"  {skill.name} v{skill.frontmatter.metadata.get('version')}")

granted = {str(name) for name in tool_allowlist(AgentId.PATCH) & SKILL_TOOLS}
offered = {tool.name for tool in asyncio.run(build_skill_toolset(root).get_tools(None))}
if offered != granted:
    problems.append(f"toolset offers {sorted(offered)}, the Patch grant is {sorted(granted)}")

for problem in problems:
    print(problem, file=sys.stderr)
raise SystemExit(1 if problems else 0)
PY
then
  ok "every package loads through ADK and the toolset matches the Patch grant"
else
  status=$?
  if [ "$status" -eq 2 ]; then
    skip "google-adk not installed — the skill packages were not loaded"
  else
    fail "the skill packages did not load cleanly"
  fi
fi

# --- no package pins one provider change ------------------------------------
#
# The design this replaced kept one package per deprecation, with a bespoke
# skill.json naming the change. A skill is a method; a change is data on the
# ChangeManifest. A package that grows a manifest has drifted back.

if compgen -G 'skills/*/skill.json' >/dev/null; then
  fail "a package carries skill.json; the SKILL.md frontmatter is the manifest"
else
  ok "no package carries a per-change manifest"
fi

# --- unit tests and lint ----------------------------------------------------

if command -v uv >/dev/null 2>&1; then
  if uv run pytest agents/tests/test_skills.py -q >/tmp/verify_skills_pytest.out 2>&1; then
    ok "uv run pytest agents/tests/test_skills.py -q"
  else
    fail "uv run pytest agents/tests/test_skills.py -q"
    tail -30 /tmp/verify_skills_pytest.out >&2
  fi
else
  skip "uv not on PATH — the skill tests were not run"
fi

# ---------------------------------------------------------------------------

at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ "$failures" -ne 0 ]; then
  status=FAIL
else
  status=PASS
fi
printf '{"task":"T-skills","status":"%s","command":"./scripts/verify_skills.sh","at":"%s","notes":"%d skip(s)"}\n' \
  "$status" "$at" "$skips" >>"$LEDGER"

if [ "$failures" -ne 0 ]; then
  printf 'FAIL: verify_skills.sh — %d problem(s)\n' "$failures" >&2
  exit 1
fi

printf 'PASS: verify_skills.sh (%d skip(s))\n' "$skips"
