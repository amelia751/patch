"""The orchestrator: a state machine that calls agents, not an agent that decides.

Roadmap §9 is explicit that the critical workflow must not be "supervisor agent,
decide what everyone should do". So the orchestrator here is ordinary Python. It
owns the run state, advances it through `packages.schemas.run_state` — which
refuses an illegal transition — and invokes exactly one specialist per stage.
Specialists cannot transfer to each other, so the sequence in this file is the
only sequence that can happen.

What a stage produced is read from `RunContext`, never from the model's closing
sentence. A stage whose agent recorded nothing is a failed stage even if the
agent said it succeeded. The Patch stage goes further: the orchestrator re-reads
the workspace and re-runs the checks itself, so "the migration landed" is a fact
about the files on disk and an exit code, never a claim in a final message.
"""

import difflib
import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Final

from agents import live_check
from agents.adk import TurnResult, new_session_service, run_turn
from agents.config import AgentId
from agents.context import RunContext
from agents.journal import RunJournal
from agents.specialists.change_intelligence import build as build_change_intelligence
from agents.specialists.impact import build as build_impact
from agents.specialists.patch import build as build_patch
from agents.specialists.verification import build as build_verification
from agents.tools import build_tool_index, is_refusal
from agents.tools.patch.skill import SKILLS_DIRNAME
from agents.tools.pr import github_tools_base_url, invoke_github_capability
from agents.tools.results import ReasonCode
from agents.trace import ToolStatus, ToolTrace
from packages.providers.google.normalize import manifest_from_feed_file
from packages.schemas.change_manifest import ChangeManifest
from packages.schemas.impact_report import ImpactReport
from packages.schemas.patch_plan import PatchPlan
from packages.schemas.policy_decision import PolicyDecision
from packages.schemas.run_state import RunState, assert_transition, is_terminal
from packages.schemas.verification_report import VerificationReport

# Agent -> the contract a completed stage must have committed.
STAGE_CONTRACTS: Final[dict[AgentId, str]] = {
    AgentId.CHANGE_INTELLIGENCE: "change_manifest",
    AgentId.IMPACT: "impact_report",
    AgentId.POLICY: "policy_decision",
    AgentId.PATCH: "patch_plan",
    AgentId.VERIFICATION: "verification_report",
}

_BUILDERS: Final[dict[AgentId, Any]] = {
    AgentId.CHANGE_INTELLIGENCE: build_change_intelligence,
    AgentId.IMPACT: build_impact,
    AgentId.PATCH: build_patch,
    AgentId.VERIFICATION: build_verification,
}

# Set to "1" to run the slice with no model in the loop at all: the migration is
# the deterministic rewrite of the pinned binding, and every judgement field is
# derived from the manifest and the scanner. It exists so the isolation and
# state-machine halves of the slice stay testable and demonstrable when Vertex
# is unreachable — never as a fallback the live path silently degrades into.
log = logging.getLogger(__name__)

DETERMINISTIC_ENV_VAR: Final[str] = "PATCHAPI_PATCH_LOOP_DETERMINISTIC"

# A module-level assignment of a quoted string, which is the shape the pinned
# slice's model binding takes. Accepts `NAME =`, `const NAME =`, and
# `export const NAME =` so the same check reads Python and the Next.js
# entry point. Deliberately not a general parse: the orchestrator's post-patch
# check has to be something a reviewer can read.
_BINDING_ASSIGNMENT: Final[re.Pattern[str]] = re.compile(
    r"^(?:export\s+)?(?:const\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)",
    re.MULTILINE,
)


def binding_value(source: str, name: str) -> str | None:
    """The string `name` is assigned to at module level in `source`, or `None`.

    The check a Patch turn is graded on. It reads the binding rather than
    searching the whole file because a migration target legitimately keeps the
    retired identifiers around — `demo/storygen` lists them in the set it
    checks against — and a substring search would call a correct patch a failure.
    """
    for match in _BINDING_ASSIGNMENT.finditer(source):
        if match.group("name") == name:
            return match.group("value")
    return None


@dataclass(frozen=True, slots=True)
class VerticalSlice:
    """The pinned Phase 1 target: one fixture, one workspace, two checks.

    Everything provider- or repository-specific about the slice is here rather
    than inlined in a stage, so a second slice is a second constant.
    """

    change_id: str
    repo: str
    skill_id: str
    entrypoint: str
    binding: str
    build_command: str
    test_command: str


# Roadmap Phase 1: the smallest target whose exit code is decided entirely by
# the model identifier in its source, so a green run proves the patch landed
# rather than proving a provider was reachable. Fixture: demo/storygen.
GEMINI20_SLICE: Final[VerticalSlice] = VerticalSlice(
    change_id="gemini20-flash-shutdown-2026-06-01",
    repo="amelia751/storygen",
    skill_id="google_gemini20_migration",
    entrypoint="lib/gemini.ts",
    binding="MODEL",
    build_command="python3 generate.py",
    test_command="python3 -m unittest test_generate.py",
)


def build_fleet(context: RunContext, trace: ToolTrace) -> dict[AgentId, Any]:
    """Construct the four reasoning agents against one run context and trace.

    Building the fleet is how the smoke proves the topology is real: every
    LlmAgent constructs, every allowlist resolves to implemented tools, and
    every tool callback is attached, before any model is called. Policy and
    PR are not in this map — they are Python stages.
    """
    return {agent: builder(context, trace) for agent, builder in _BUILDERS.items()}


@dataclass(slots=True)
class StageResult:
    """What one stage of the run produced."""

    agent: AgentId
    state: RunState
    turn: TurnResult | None
    output: Any | None
    human_required: tuple[dict[str, str], ...]
    detail: str = ""

    @property
    def completed(self) -> bool:
        """Whether the stage committed the contract it is responsible for."""
        return self.output is not None


@dataclass(slots=True)
class SliceResult:
    """The end state of a vertical-slice run and the stages that produced it."""

    state: RunState
    detail: str
    stages: list[StageResult] = field(default_factory=list)

    @property
    def reached_testing(self) -> bool:
        """Whether the patch built and its tests ran green in the workspace."""
        if self.state in {
            RunState.TESTING,
            RunState.VERIFYING,
            RunState.PR_CREATING,
            RunState.PR_CREATED,
        }:
            return True
        return any(stage.state is RunState.TESTING for stage in self.stages)


class Orchestrator:
    """Drives one remediation run through the deterministic state machine.

    The fleet is constructed on first use rather than in `__init__`, so a
    deterministic slice — the path that exists for when Vertex is unreachable —
    does not require google-adk to be importable.
    """

    def __init__(
        self, context: RunContext, trace: ToolTrace, journal: RunJournal | None = None
    ) -> None:
        self._context = context
        self._trace = trace
        # Optional so a script or a test stays a two-argument construction. The
        # journal is how a long-running job publishes progress; nothing in the
        # state machine depends on one being attached.
        self._journal = journal
        self._state = RunState.RECEIVED
        self._agents: dict[AgentId, Any] | None = None
        self._session_service: Any | None = None
        self._evidence_uris: list[str] = []
        self._entrypoint_digest: str = ""
        self._last_build: dict[str, Any] = {}
        self._last_tests: dict[str, Any] = {}
        # One index, so the impact scan and the report that commits its findings
        # share a closure, and so an orchestrator-driven check runs exactly the
        # tool an agent would have run.
        self._tools = build_tool_index(context, AgentId.ORCHESTRATOR)

    def _sessions(self) -> Any:
        """One ADK session service for this run. Created on first live turn."""
        if self._session_service is None:
            self._session_service = new_session_service()
        return self._session_service

    @property
    def state(self) -> RunState:
        return self._state

    @property
    def context(self) -> RunContext:
        return self._context

    @property
    def trace(self) -> ToolTrace:
        return self._trace

    @property
    def fleet(self) -> dict[AgentId, Any]:
        """The constructed specialists, keyed by identity."""
        if self._agents is None:
            self._agents = build_fleet(self._context, self._trace)
        return dict(self._agents)

    def agent(self, agent: AgentId) -> Any:
        """The constructed ADK agent for `agent`."""
        if self._agents is None:
            self._agents = build_fleet(self._context, self._trace)
        return self._agents[agent]

    # -- deterministic tool calls ----------------------------------------

    def _call(self, tool_name: str, *, on_behalf_of: AgentId, **arguments: Any) -> dict[str, Any]:
        """Call one tool directly and trace it as an orchestrator action.

        The event is attributed to the orchestrator, not to the specialist that
        owns the tool, because no model chose this call. `detail` names the
        owning agent so a trace still reads as a chain.
        """
        function: Callable[..., Any] = self._tools[tool_name]
        shown = ", ".join(f"{key}={value!r}"[:80] for key, value in sorted(arguments.items()))
        self._trace.emit(f"  → {on_behalf_of}.{tool_name}({shown})")
        started = perf_counter()
        result = function(**arguments)
        duration_ms = (perf_counter() - started) * 1000.0
        self._trace.record(
            agent=AgentId.ORCHESTRATOR,
            tool=tool_name,
            status=ToolStatus.REFUSED if is_refusal(result) else ToolStatus.OK,
            arguments=arguments,
            result=result,
            duration_ms=duration_ms,
            detail=f"deterministic call on behalf of {on_behalf_of}; no model in the loop",
        )
        return result

    def _advance(self, target: RunState) -> None:
        assert_transition(self._state, target)
        if self._journal is not None:
            self._journal.record(self._state, target)
        self._state = target

    def _fail(self, agent: AgentId, detail: str, turn: TurnResult | None = None) -> StageResult:
        self._advance(RunState.FAILED)
        return self._stage(agent, turn, None, detail)

    def _park_for_operator(
        self, agent: AgentId, turn: TurnResult | None, detail: str = ""
    ) -> StageResult:
        """Hold the run until the operator adds a secret or connects GCP.

        Distinct from HUMAN_REQUIRED: that exit is terminal. This one resumes.
        """
        request = self._context.operator_requests[-1] if self._context.operator_requests else {}
        self._advance(RunState.WAITING_ON_OPERATOR)
        return self._stage(
            agent,
            turn,
            None,
            detail or str(request.get("message") or "waiting on the operator"),
        )

    def resume_after_operator(self) -> RunState:
        """Leave the hold and return to the specialist that asked.

        Clears the request so a later turn can ask again if the vault is
        still missing the name. The secret value never enters this method.
        """
        request = self._context.operator_requests[-1] if self._context.operator_requests else {}
        nxt = (
            RunState.VERIFYING
            if str(request.get("agent") or "") == str(AgentId.VERIFICATION)
            else RunState.PATCHING
        )
        self._context.operator_requests.clear()
        self._advance(nxt)
        return nxt

    def _stage(
        self, agent: AgentId, turn: TurnResult | None, output: Any | None, detail: str
    ) -> StageResult:
        return StageResult(
            agent=agent,
            state=self._state,
            turn=turn,
            output=output,
            human_required=tuple(self._context.human_required),
            detail=detail,
        )

    # -- stages -----------------------------------------------------------

    async def run_change_intelligence(self, change_id: str) -> StageResult:
        """Normalize one provider notice into a `ChangeManifest`.

        RECEIVED → SANITIZED once the notice has passed the untrusted-text gate
        the tool applies, then → NORMALIZED once a manifest is committed. A
        stage that commits nothing ends the run FAILED rather than leaving the
        state where a later stage could read it as success.
        """
        agent = AgentId.CHANGE_INTELLIGENCE
        self._advance(RunState.SANITIZED)

        prompt = (
            f"Produce the ChangeManifest for provider change {change_id!r}. "
            "Read the notice, compare it against the deterministic parse, "
            "corroborate identifiers and dates with search_web, then call "
            "record_change_manifest if they agree or record_human_required if "
            "they do not. search_web is not the finish — you must record."
        )
        turn = await run_turn(
            self.agent(agent), prompt, trace=self._trace, session_service=self._sessions()
        )
        output = self._context.output(STAGE_CONTRACTS[agent])
        if output is None:
            # Gemini often treats the search child as the end of the turn.
            # Same ADK session: continue, do not search again.
            turn = await run_turn(
                self.agent(agent),
                (
                    "You already have the notice, the parse, and search hits. "
                    "Call record_change_manifest now if they agree, or "
                    "record_human_required if they do not. Do not call "
                    "search_web again."
                ),
                trace=self._trace,
                session_service=self._sessions(),
            )
            output = self._context.output(STAGE_CONTRACTS[agent])

        if output is None:
            self._advance(RunState.FAILED)
        else:
            self._advance(RunState.NORMALIZED)

        return self._stage(agent, turn, output, "" if output else "no manifest was recorded")

    def seed_change_manifest(self, change_id: str) -> StageResult:
        """Commit the pinned deterministic parse of a notice as this run's manifest.

        The vertical slice starts from a known change rather than from a model's
        reading of one, so the stage that is under test is the Patch loop. The
        manifest is the provider adapter's total mapping of the feed document —
        no model confirmed it, which is why it is recorded under the
        orchestrator's identity and not Change Intelligence's.

        RECEIVED → SANITIZED → NORMALIZED, so the run reaches the Impact stage
        through the same transitions a live Change Intelligence turn would use.
        """
        agent = AgentId.ORCHESTRATOR
        self._advance(RunState.SANITIZED)

        path = self._notice_path(change_id)
        if path is None:
            return self._fail(agent, f"no provider notice with change_id {change_id!r}")

        started = perf_counter()
        try:
            # Captured-snapshot paths in the pinned fixtures are written
            # repository-relative, so the repository root is what they resolve
            # against. A capture the adapter cannot re-hash raises here rather
            # than downgrading to a manifest with no evidence.
            manifest = manifest_from_feed_file(path, base_dir=self._context.repo_root)
        except ValueError as exc:
            self._trace.record(
                agent=agent,
                tool="seed_change_manifest",
                status=ToolStatus.ERROR,
                arguments={"change_id": change_id},
                result={"error": str(exc)},
                duration_ms=(perf_counter() - started) * 1000.0,
                detail="the feed document did not normalize",
            )
            return self._fail(agent, f"{path.name} did not normalize into a ChangeManifest: {exc}")

        self._context.record(STAGE_CONTRACTS[AgentId.CHANGE_INTELLIGENCE], agent, manifest)
        self._trace.record(
            agent=agent,
            tool="seed_change_manifest",
            status=ToolStatus.OK,
            arguments={"change_id": change_id},
            result={
                "change_id": manifest.change_id,
                "affected_identifiers": list(manifest.affected_identifiers),
                "recommended_replacement": manifest.recommended_replacement,
                "has_verifiable_evidence": manifest.has_verifiable_evidence,
            },
            duration_ms=(perf_counter() - started) * 1000.0,
            detail="pinned deterministic parse; the Change Intelligence agent did not run",
        )
        self._advance(RunState.NORMALIZED)
        return self._stage(agent, None, manifest, "manifest seeded from the pinned feed document")

    def seed_static_manifest(self, path: Path) -> StageResult:
        """Commit a pre-written ChangeManifest JSON. No Change Intelligence turn.

        The live provider crawl is not wired; this is the input the rest of the
        loop already knows how to consume. The file must validate as
        `ChangeManifest` — a feed document still goes through
        `seed_change_manifest`.
        """
        agent = AgentId.ORCHESTRATOR
        self._advance(RunState.SANITIZED)
        started = perf_counter()
        try:
            manifest = ChangeManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._trace.record(
                agent=agent,
                tool="seed_static_manifest",
                status=ToolStatus.ERROR,
                arguments={"path": str(path)},
                result={"error": str(exc)},
                duration_ms=(perf_counter() - started) * 1000.0,
                detail="the static manifest did not validate",
            )
            return self._fail(agent, f"{path} is not a ChangeManifest: {exc}")

        self._context.record(STAGE_CONTRACTS[AgentId.CHANGE_INTELLIGENCE], agent, manifest)
        self._trace.record(
            agent=agent,
            tool="seed_static_manifest",
            status=ToolStatus.OK,
            arguments={"path": str(path), "change_id": manifest.change_id},
            result={
                "change_id": manifest.change_id,
                "affected_identifiers": list(manifest.affected_identifiers),
                "recommended_replacement": manifest.recommended_replacement,
            },
            duration_ms=(perf_counter() - started) * 1000.0,
            detail="static ChangeManifest; the Change Intelligence agent did not run",
        )
        self._advance(RunState.NORMALIZED)
        return self._stage(agent, None, manifest, f"manifest seeded from {path.name}")

    def _notice_path(self, change_id: str) -> Path | None:
        """The feed document whose `change_id` matches, or `None`."""
        for path in sorted(self._context.feed_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("change_id") == change_id:
                return path
        return None

    async def run_impact(
        self, slice_: VerticalSlice, *, base_sha: str, deterministic: bool = False
    ) -> StageResult:
        """Inventory the workspace for the retired identifiers and judge the hits.

        NORMALIZED → IMPACT_SCANNING, then → UNAFFECTED when the deterministic
        scan finds nothing, or → POLICY_EVALUATION when it does. The findings
        that reach the report are the scanner's; the stage cannot report a file
        `packages.repo_scan` never saw.
        """
        agent = AgentId.IMPACT
        manifest = self._context.output(STAGE_CONTRACTS[AgentId.CHANGE_INTELLIGENCE])
        if not isinstance(manifest, ChangeManifest):
            self._advance(RunState.FAILED)
            return self._stage(agent, None, None, "the run has no ChangeManifest to scan for")

        self._advance(RunState.IMPACT_SCANNING)
        turn: TurnResult | None = None
        if deterministic:
            self._impact_deterministically(manifest, slice_, base_sha=base_sha)
        else:
            prompt = self._impact_prompt(manifest, slice_, base_sha)
            turn = await run_turn(
                self.agent(agent), prompt, trace=self._trace, session_service=self._sessions()
            )

        report = self._context.output(STAGE_CONTRACTS[agent])
        if not isinstance(report, ImpactReport):
            return self._fail(agent, "no ImpactReport was recorded", turn)
        if not report.affected:
            self._advance(RunState.UNAFFECTED)
            return self._stage(agent, turn, report, "the workspace uses none of the retired IDs")

        self._advance(RunState.POLICY_EVALUATION)
        return self._stage(agent, turn, report, f"{len(report.findings)} findings")

    def _impact_prompt(self, manifest: ChangeManifest, slice_: VerticalSlice, base_sha: str) -> str:
        identifiers = ", ".join(manifest.affected_identifiers)
        return (
            f"Provider change {manifest.change_id!r} retires these identifiers: {identifiers}. "
            f"Scan the workspace for them, then record the ImpactReport for repository "
            f"{slice_.repo!r} at base_sha {base_sha!r}. The checks a patch must pass are "
            f"{slice_.build_command!r} and {slice_.test_command!r}."
        )

    def _impact_deterministically(
        self, manifest: ChangeManifest, slice_: VerticalSlice, *, base_sha: str
    ) -> None:
        scan = self._call(
            "scan_repository",
            on_behalf_of=AgentId.IMPACT,
            identifiers=list(manifest.affected_identifiers),
        )
        affected = not is_refusal(scan) and bool(scan.get("total_hits"))
        character = "semantic" if manifest.semantic_migration_required else "mechanical"
        self._call(
            "record_impact_report",
            on_behalf_of=AgentId.IMPACT,
            change_id=manifest.change_id,
            repo=slice_.repo,
            base_sha=base_sha,
            affected=affected,
            # A literal identifier match is exact, and no model weighed it.
            confidence=1.0 if affected else 0.0,
            migration_character=character if affected else "",
            required_checks=[slice_.build_command, slice_.test_command] if affected else [],
            notes=(
                "Deterministic slice: findings are the scanner's and the migration "
                "character is the manifest's. No model judged this repository."
            ),
        )

    async def run_policy(
        self, slice_: VerticalSlice, *, deterministic: bool = False
    ) -> StageResult:
        """Clear the files the Impact stage found through the deterministic gate.

        POLICY_EVALUATION → PATCHING only when the recorded decision permits an
        automatic patch. Everything else is a terminal state: BLOCKED when a rule
        denied a path, HUMAN_REQUIRED when evidence or risk needs a person.
        """
        agent = AgentId.POLICY
        report = self._context.output(STAGE_CONTRACTS[AgentId.IMPACT])
        if not isinstance(report, ImpactReport):
            return self._fail(agent, "the run has no ImpactReport to evaluate")

        proposed = sorted({finding.file for finding in report.findings})
        # §8.3: policy is Python, not an LlmAgent. The flag is kept so callers
        # do not change; both paths hit the same gate.
        turn: TurnResult | None = None
        self._policy_deterministically(report, slice_, proposed)

        decision = self._context.output(STAGE_CONTRACTS[agent])
        if not isinstance(decision, PolicyDecision):
            return self._fail(agent, "no PolicyDecision was recorded", turn)
        if str(decision.outcome) == "blocked":
            self._advance(RunState.BLOCKED)
            return self._stage(agent, turn, decision, decision.reason)
        if not decision.auto_patch or decision.human_review_required:
            self._advance(RunState.HUMAN_REQUIRED)
            return self._stage(agent, turn, decision, decision.reason)

        self._advance(RunState.PATCHING)
        return self._stage(agent, turn, decision, decision.reason)

    def _policy_deterministically(
        self, report: ImpactReport, slice_: VerticalSlice, proposed: list[str]
    ) -> None:
        self._call("evaluate_policy", on_behalf_of=AgentId.POLICY, proposed_paths=proposed)
        self._call(
            "record_policy_decision",
            on_behalf_of=AgentId.POLICY,
            change_id=report.change_id,
            repo=slice_.repo,
            risk="high" if str(report.migration_character) == "semantic" else "medium",
            reason=(
                "Deterministic slice: the risk tier follows the manifest's migration "
                "character and the outcome is the policy gate's. No model judged this."
            ),
            escalate_to_human=False,
        )

    async def run_patch(
        self, slice_: VerticalSlice, *, base_sha: str, deterministic: bool = False
    ) -> StageResult:
        """Migrate the workspace, then prove it independently of what was said.

        PATCHING → BUILDING once the pinned entry point exits 0, then → TESTING
        once its unit tests do. Both commands are run by the orchestrator through
        the session, not by the agent: a model reporting its own green build is
        exactly the evidence this product does not accept. The binding check runs
        first, so a patch that made the checks pass without removing the retired
        identifier still fails the stage.
        """
        agent = AgentId.PATCH
        manifest = self._context.output(STAGE_CONTRACTS[AgentId.CHANGE_INTELLIGENCE])
        report = self._context.output(STAGE_CONTRACTS[AgentId.IMPACT])
        if not isinstance(manifest, ChangeManifest) or not isinstance(report, ImpactReport):
            return self._fail(agent, "the Patch stage needs a manifest and an impact report")

        turn: TurnResult | None = None
        if deterministic:
            self._patch_deterministically(manifest, slice_, base_sha=base_sha)
        else:
            self._trace.emit("=== PATCH agent live — inspect, edit, run, look ===")
            prompt = self._patch_prompt(manifest, report, slice_)
            turn = await run_turn(
                self.agent(agent), prompt, trace=self._trace, session_service=self._sessions()
            )
            if self._context.waiting_on_operator or (turn is not None and turn.paused):
                return self._park_for_operator(agent, turn)

        source = self._read_entrypoint(slice_)
        if source is None:
            return self._fail(agent, f"{slice_.entrypoint} could not be read after the turn", turn)
        binding = binding_value(source, slice_.binding)
        if binding is None:
            return self._fail(
                agent, f"{slice_.entrypoint} no longer assigns {slice_.binding}", turn
            )
        if binding in manifest.affected_identifiers:
            return self._fail(
                agent,
                f"{slice_.entrypoint} still binds {slice_.binding} to the retired "
                f"{binding!r}; the migration did not land",
                turn,
            )

        build = self._call("run_command", on_behalf_of=agent, command=slice_.build_command)
        if is_refusal(build) or build["exit_code"] != 0:
            return self._fail(agent, f"{slice_.build_command} did not exit 0", turn)
        self._last_build = build
        self._advance(RunState.BUILDING)

        tests = self._call("run_command", on_behalf_of=agent, command=slice_.test_command)
        if is_refusal(tests) or tests["exit_code"] != 0:
            return self._fail(agent, f"{slice_.test_command} did not exit 0", turn)
        self._last_tests = tests
        self._advance(RunState.TESTING)

        plan = self._context.output(STAGE_CONTRACTS[agent])
        return self._stage(
            agent,
            turn,
            plan,
            f"{slice_.binding} now binds {binding!r}; both checks exited 0",
        )

    def _run_computer_use(self, slice_: VerticalSlice) -> dict[str, Any]:
        """Screenshot the workspace viewer after the checks wrote it."""
        replacement = ""
        manifest = self._context.output(STAGE_CONTRACTS[AgentId.CHANGE_INTELLIGENCE])
        if isinstance(manifest, ChangeManifest) and manifest.recommended_replacement:
            replacement = manifest.recommended_replacement
        goal = (
            f"Confirm the viewer shows the migrated {slice_.binding} binding"
            + (f" ({replacement})" if replacement else "")
            + " and no retired identifier."
        )
        return self._call("computer_use_step", on_behalf_of=AgentId.PATCH, goal=goal, url="")

    def _patch_prompt(
        self,
        manifest: ChangeManifest,
        report: ImpactReport,
        slice_: VerticalSlice,
    ) -> str:
        """The Patch turn's task.

        `repo` and `base_sha` are stated rather than left to the agent. They are
        already fixed by the ImpactReport, and a model asked to supply them has
        nothing to supply them from — it invents a null SHA, and the PatchPlan it
        records then names a tree that does not exist.
        """
        findings = "\n".join(
            f"  - {finding.file}:{finding.line} uses {finding.identifier}"
            for finding in report.findings
        )
        return (
            f"Provider change {manifest.change_id!r} retires "
            f"{', '.join(manifest.affected_identifiers)}. The Impact agent found these "
            f"usages in the sandbox workspace:\n{findings}\n\n"
            f"This is repository {report.repo!r} at base_sha {report.base_sha!r}; record "
            f"those verbatim. Load migration skill {slice_.skill_id!r} first. Inspect "
            "how this app actually calls the provider (API routes and env vars), not "
            "only the identifier binding. A green local check is not a live call. If "
            "a live path needs a secret that list_runtime_credentials does not show, "
            "call request_runtime_credentials and stop — do not invent a key. Then "
            f"iterate with apply_patch and run_command until {slice_.build_command!r} "
            "exits 0, and record_patch_plan with what you changed. Do not edit any "
            "file outside the ones listed above."
        )

    def _patch_deterministically(
        self, manifest: ChangeManifest, slice_: VerticalSlice, *, base_sha: str
    ) -> None:
        source = self._read_entrypoint(slice_)
        if source is None:
            return
        diff = self._known_good_diff(source, slice_, manifest)
        if diff is None:
            return
        version = self._skill_version(slice_.skill_id)
        self._call("apply_patch", on_behalf_of=AgentId.PATCH, diff=diff)
        self._call(
            "record_patch_plan",
            on_behalf_of=AgentId.PATCH,
            change_id=manifest.change_id,
            repo=slice_.repo,
            base_sha=base_sha,
            attempt=1,
            files_expected=[slice_.entrypoint],
            migration_summary=(
                f"Rebind {slice_.binding} in {slice_.entrypoint} from the retired identifier "
                f"to {manifest.recommended_replacement}."
            ),
            assumptions=[
                "Deterministic slice: the rewrite is the manifest's recommended "
                "replacement applied to the pinned binding, with no model in the loop."
            ],
            verification_commands=[slice_.build_command, slice_.test_command],
            # PatchPlan records a skill and its version together or not at all,
            # so an unreadable skill package yields neither rather than a plan
            # that names a provenance it cannot support.
            skill_id=slice_.skill_id if version else "",
            skill_version=version,
        )

    def _skill_version(self, skill_id: str) -> str:
        """The pinned version of a migration skill package, or an empty string."""
        manifest_path = self._context.repo_root / SKILLS_DIRNAME / skill_id / "skill.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        skill = payload.get("skill") if isinstance(payload, dict) else None
        version = skill.get("version") if isinstance(skill, dict) else None
        return version if isinstance(version, str) else ""

    # -- workspace inspection ---------------------------------------------

    def _read_entrypoint(self, slice_: VerticalSlice) -> str | None:
        """The pinned entry point's current text, read through the session."""
        result = self._call("read_file", on_behalf_of=AgentId.PATCH, path=slice_.entrypoint)
        if is_refusal(result):
            return None
        return str(result["content"])

    @staticmethod
    def _known_good_diff(
        source: str, slice_: VerticalSlice, manifest: ChangeManifest
    ) -> str | None:
        """A one-line unified diff rebinding the pinned identifier, or `None`.

        Built from the file that is actually on disk rather than stored as a
        fixture, so the deterministic path cannot succeed against a workspace
        whose entry point has drifted from what the diff expects.
        """
        replacement = manifest.recommended_replacement
        if not replacement:
            return None
        for match in _BINDING_ASSIGNMENT.finditer(source):
            if match.group("name") != slice_.binding:
                continue
            start, end = match.span("value")
            patched = source[:start] + replacement + source[end:]
            return "".join(
                difflib.unified_diff(
                    source.splitlines(keepends=True),
                    patched.splitlines(keepends=True),
                    fromfile=f"a/{slice_.entrypoint}",
                    tofile=f"b/{slice_.entrypoint}",
                )
            )
        return None

    # -- verification and PR ----------------------------------------------

    def _run_live_check(self, slice_: VerticalSlice) -> live_check.LiveCheck | None:
        """Ask the provider whether the replacement identifier actually exists.

        The offline checks cannot answer this. A build compiles a wrong model id
        as happily as a right one, and a test suite that never leaves the
        machine agrees. Since the one thing PatchAPI must not do is write an
        identifier that does not exist, the replacement is put to the provider
        before a pull request claims the migration is verified.
        """
        manifest = self._context.output(STAGE_CONTRACTS[AgentId.CHANGE_INTELLIGENCE])
        replacement = ""
        if isinstance(manifest, ChangeManifest) and manifest.recommended_replacement:
            replacement = manifest.recommended_replacement
        if not replacement:
            replacement = binding_value(self._read_entrypoint(slice_) or "", slice_.binding) or ""
        if not replacement:
            return None

        broker = self._context.live_credentials
        available: dict[str, str] = {}
        if callable(broker):
            try:
                available = broker(live_check.CREDENTIAL_NAMES)
            except Exception as exc:  # a vault that will not answer is "not asked"
                log.warning("run %s could not broker a live credential: %s", self.run_id, exc)
        return live_check.run(self._context.sandbox, replacement, available)

    def _write_evidence(
        self,
        slice_: VerticalSlice,
        *,
        source: str,
        build: dict[str, Any],
        tests: dict[str, Any],
        live: live_check.LiveCheck | None = None,
    ) -> None:
        """Write orchestrator logs the Verification agent may read. Host path only."""
        root = Path(tempfile.mkdtemp(prefix=f"patchapi-evidence-{self._context.run_id}-"))
        build_log = (
            f"exit {build.get('exit_code')}\n{build.get('stdout', '')}\n{build.get('stderr', '')}"
        )
        test_log = (
            f"exit {tests.get('exit_code')}\n{tests.get('stdout', '')}\n{tests.get('stderr', '')}"
        )
        files = {
            "build.log": build_log,
            "test.log": test_log,
            slice_.entrypoint: source,
            "binding.txt": f"{slice_.binding}={binding_value(source, slice_.binding) or ''}\n",
        }
        if live is not None:
            files["live.log"] = live.log
        uris: list[str] = []
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            uris.append(path.as_uri())
        workspace = getattr(self._context.sandbox, "working_dir", None)
        ui_src = Path(workspace) / ".patchapi-ui" if isinstance(workspace, Path) else None
        if ui_src is not None and ui_src.is_dir():
            dest = root / "ui"
            dest.mkdir(parents=True, exist_ok=True)
            for item in ui_src.iterdir():
                if item.is_file():
                    target = dest / item.name
                    target.write_bytes(item.read_bytes())
                    uris.append(target.as_uri())
        self._context.evidence_root = root
        self._evidence_uris = uris
        self._entrypoint_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()

    async def run_verification(
        self, slice_: VerticalSlice, *, deterministic: bool = False
    ) -> StageResult:
        """Grade orchestrator evidence. Blind to the Patch turn's transcript."""
        agent = AgentId.VERIFICATION
        manifest = self._context.output(STAGE_CONTRACTS[AgentId.CHANGE_INTELLIGENCE])
        if not isinstance(manifest, ChangeManifest):
            return self._fail(agent, "verification needs a ChangeManifest")
        if self._context.evidence_root is None:
            return self._fail(agent, "verification needs an evidence_root the orchestrator wrote")

        self._advance(RunState.VERIFYING)
        turn: TurnResult | None = None
        if deterministic:
            self._verification_deterministically(manifest, slice_)
        else:
            self._trace.emit("=== VERIFICATION agent live — evidence only ===")
            impact = self._context.output(STAGE_CONTRACTS[AgentId.IMPACT])
            base_sha = impact.base_sha if isinstance(impact, ImpactReport) else ""
            prompt = (
                f"Grade the sandbox evidence for change {manifest.change_id!r} on "
                f"{slice_.repo!r} at base_sha {base_sha}. The orchestrator hashed the "
                f"patched entry point as {self._entrypoint_digest}. List and read the "
                "evidence. Do not use a patch plan or an inner-loop transcript. A check "
                "you did not run is skip, never pass. Record the VerificationReport. If "
                "generate.py and the unit tests exited 0 and the retired identifiers are "
                "gone from the entry point. generate.py is a local identifier check, "
                "not live_api. If the app's live path needs an API key, "
                "list_runtime_credentials and request_runtime_credentials rather than "
                "inventing one or marking live_api pass."
            )
            turn = await run_turn(
                self.agent(agent), prompt, trace=self._trace, session_service=self._sessions()
            )
            if self._context.waiting_on_operator or (turn is not None and turn.paused):
                return self._park_for_operator(agent, turn)

        report = self._context.output(STAGE_CONTRACTS[agent])
        if not isinstance(report, VerificationReport):
            return self._fail(agent, "no VerificationReport was recorded", turn)
        if str(report.verdict) == "fail":
            return self._fail(agent, report.notes or "verification failed", turn)
        if str(report.verdict) != "pass":
            self._advance(RunState.HUMAN_REQUIRED)
            return self._stage(agent, turn, report, report.notes or str(report.verdict))
        return self._stage(agent, turn, report, f"verdict {report.verdict}")

    def _verification_deterministically(
        self, manifest: ChangeManifest, slice_: VerticalSlice
    ) -> None:
        listed = self._call("list_verification_evidence", on_behalf_of=AgentId.VERIFICATION)
        if is_refusal(listed):
            return
        impact = self._context.output(STAGE_CONTRACTS[AgentId.IMPACT])
        repo = slice_.repo
        base_sha = impact.base_sha if isinstance(impact, ImpactReport) else ""
        self._call(
            "record_verification_report",
            on_behalf_of=AgentId.VERIFICATION,
            change_id=manifest.change_id,
            repo=repo,
            base_sha=base_sha,
            patched_sha_or_diff_hash=self._entrypoint_digest,
            verdict="pass",
            build="pass",
            tests="pass",
            live_api="pass",
            policy="pass",
            deprecated_identifiers_absent=True,
            unexpected_files=[],
            evidence_uris=self._evidence_uris,
            notes=(
                "Deterministic slice: verdict follows the orchestrator's evidence "
                "run. No model graded this."
            ),
        )

    # Matches the tool service's refusal to move a branch that is not where the
    # caller expected. Read rather than re-derived so the two cannot drift.
    _BRANCH_CONFLICT: Final[str] = "branch_exists_at_other_commit"

    async def run_pr(self, slice_: VerticalSlice) -> StageResult:
        """Open a PR only after VerificationReport.verdict == PASS."""
        agent = AgentId.PR
        report = self._context.output(STAGE_CONTRACTS[AgentId.VERIFICATION])
        if not isinstance(report, VerificationReport) or not report.permits_pull_request:
            return self._fail(agent, "a pull request requires VerificationReport.verdict == PASS")

        head = f"patchapi/{slice_.change_id}"
        if not github_tools_base_url():
            self._call(
                "record_human_required",
                on_behalf_of=agent,
                reason=("the GitHub tool service is not configured; no pull request was opened"),
            )
            self._advance(RunState.HUMAN_REQUIRED)
            return self._stage(
                agent, None, None, "GitHub tool service is not configured; no PR opened"
            )

        self._advance(RunState.PR_CREATING)
        branch = invoke_github_capability(
            "create_patch_branch",
            run_id=self._context.run_id,
            arguments={"repo": slice_.repo, "branch": head, "base_sha": report.base_sha},
        )
        head_sha = _existing_patch_branch_head(branch)
        if is_refusal(branch) and not head_sha:
            return self._fail(agent, str(branch.get("message", "create_patch_branch refused")))
        files = []
        plan = self._context.output(STAGE_CONTRACTS[AgentId.PATCH])
        expected = list(getattr(plan, "files_expected", None) or [slice_.entrypoint])
        for relpath in expected:
            content = self._read_entrypoint(slice_) if relpath == slice_.entrypoint else None
            if content is None:
                read = self._call("read_file", on_behalf_of=AgentId.PATCH, path=relpath)
                if is_refusal(read):
                    continue
                content = str(read["content"])
            files.append({"path": relpath, "content": content})
        if not head_sha and isinstance(branch, dict):
            payload = branch.get("result") if "result" in branch else branch
            if isinstance(payload, dict):
                head_sha = str(payload.get("sha") or payload.get("head_sha") or "")
        if files and head_sha:
            invoke_github_capability(
                "commit_verified_patch",
                run_id=self._context.run_id,
                arguments={
                    "repo": slice_.repo,
                    "branch": head,
                    "message": (
                        plan.migration_summary
                        if isinstance(plan, PatchPlan) and plan.migration_summary.strip()
                        else f"Migrate {slice_.repo} off retired identifiers"
                    ),
                    "files": files,
                    "expected_head_sha": head_sha,
                },
            )

        opened = self._call(
            "open_pull_request",
            on_behalf_of=agent,
            title=(
                plan.migration_summary.strip()[:72]
                if isinstance(plan, PatchPlan) and plan.migration_summary.strip()
                else f"Migrate {slice_.repo} off retired API identifiers"
            ),
            head_branch=head,
            base_branch="main",
        )
        if is_refusal(opened):
            return self._fail(agent, str(opened.get("message", "open_pull_request refused")))
        self._advance(RunState.PR_CREATED)
        return self._stage(agent, None, opened, "pull request opened")

    # -- the slice --------------------------------------------------------

    async def run_vertical_slice(
        self,
        slice_: VerticalSlice = GEMINI20_SLICE,
        *,
        base_sha: str,
        deterministic: bool | None = None,
        setup_deterministic: bool = False,
        static_manifest: Path | None = None,
    ) -> SliceResult:
        """Run seed → impact → policy → patch → UI check → verify → PR.

        Verification grades orchestrator evidence, not the Patch turn. A PR is
        attempted only after PASS. Missing GitHub tools is HUMAN_REQUIRED, not
        a claimed pull request. `static_manifest` skips the provider crawl.
        `setup_deterministic` keeps Impact off the model so a live Patch turn
        still starts from a real scan.
        """
        if deterministic is None:
            deterministic = os.environ.get(DETERMINISTIC_ENV_VAR) == "1"
        setup = deterministic or setup_deterministic

        result = SliceResult(state=self._state, detail="")

        def keep(stage: StageResult) -> bool:
            result.stages.append(stage)
            result.state = self._state
            result.detail = stage.detail
            return not (
                is_terminal(self._state)
                or self._state is RunState.WAITING_ON_OPERATOR
                or self._context.stopped_for_human
                or self._context.waiting_on_operator
            )

        seeded = (
            self.seed_static_manifest(static_manifest)
            if static_manifest is not None
            else self.seed_change_manifest(slice_.change_id)
        )
        if not keep(seeded):
            return result
        if not keep(await self.run_impact(slice_, base_sha=base_sha, deterministic=setup)):
            return result
        if not keep(await self.run_policy(slice_, deterministic=setup)):
            return result
        patch = await self.run_patch(slice_, base_sha=base_sha, deterministic=deterministic)
        if not keep(patch):
            return result
        source = self._read_entrypoint(slice_)
        if source is None:
            keep(self._fail(AgentId.VERIFICATION, f"{slice_.entrypoint} missing after patch"))
            return result
        # Looking at the running page is evidence when a repository produces
        # one, and most do not. Requiring it would mean PatchAPI could only
        # migrate repositories that happen to render a status page — the demo
        # fixture writes one, an arbitrary customer repository does not. So a
        # missing page is recorded and the run continues to verification, which
        # grades the diff and the checks. A page that *is* there and shows a
        # retired identifier still fails: that is the patch being wrong, not the
        # repository being ordinary.
        ui = self._run_computer_use(slice_)
        if is_refusal(ui) and ui.get("reason_code") != ReasonCode.STAGE_NOT_READY.value:
            keep(self._fail(AgentId.PATCH, str(ui.get("message", "computer_use_step refused"))))
            return result
        if not is_refusal(ui) and not ui.get("goal_met"):
            keep(
                self._fail(
                    AgentId.PATCH,
                    f"computer_use_step did not confirm the viewer: {ui.get('visible_tail', '')}",
                )
            )
            return result
        live = self._run_live_check(slice_)
        if live is not None and live.resolved is False:
            # The provider says the identifier does not exist. No amount of
            # green checks makes that a migration worth proposing.
            keep(
                self._fail(
                    AgentId.VERIFICATION,
                    f"{live.identifier} does not resolve against the provider, so the "
                    f"patch would replace a retired identifier with one that is not "
                    f"served. {live.detail}",
                )
            )
            return result
        self._write_evidence(
            slice_,
            source=source,
            build=self._last_build,
            tests=self._last_tests,
            live=live,
        )
        if not keep(await self.run_verification(slice_, deterministic=deterministic)):
            return result
        keep(await self.run_pr(slice_))
        return result


def _existing_patch_branch_head(result: dict[str, Any]) -> str:
    """The head of a `patchapi/` branch a previous attempt already pushed.

    The tool service refuses to move a branch that is not where the caller
    expected, and it is right to: silently repointing one discards whatever is
    on it. But re-running a change is not a rare accident — it is the resume
    button — and the branch in the way is the one this product created for this
    change, on its second attempt at it.

    Returning the existing head lets the new commit be *parented* on it rather
    than replacing it. Nothing is discarded, the history reads as two attempts,
    and the open pull request updates instead of a second one appearing beside
    it. Only the conflict the tool service names, and only for a branch in
    PatchAPI's own namespace — anything else stays a refusal.
    """
    if not is_refusal(result):
        return ""
    message = str(result.get("message", ""))
    if Orchestrator._BRANCH_CONFLICT not in message:
        return ""
    try:
        detail = json.loads(message[message.index("{") :])["detail"]
    except (ValueError, KeyError, TypeError):
        return ""
    branch = str(detail.get("branch", ""))
    if not branch.startswith("patchapi/"):
        return ""
    return str(detail.get("actual_sha", ""))


__all__ = [
    "DETERMINISTIC_ENV_VAR",
    "GEMINI20_SLICE",
    "STAGE_CONTRACTS",
    "Orchestrator",
    "SliceResult",
    "StageResult",
    "VerticalSlice",
    "binding_value",
    "build_fleet",
]
