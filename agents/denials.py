"""What a run was refused, in the product's own words.

A fleet that cannot show what it was stopped from doing cannot show that its
controls are load-bearing, and until now PatchAPI could not: refusals were
written to the per-run worklog and nowhere else, so "what did this product
decline to do last month" had no answer that outlived a single run.

This module derives that answer from the record a run already produces. A
refused tool call and a blocked policy verdict are the truth; nothing here asks
a gate to report itself a second time, because a refusal remembered in two
places is a refusal that will be missing from one of them.

Three rules shape what a derived denial may say.

*The gate is named, not guessed.* `actor` is which control refused, taken from
the reason code the refusal already carries and, where several gates share one
code, from the tool that was called.

*The provider never speaks here.* Release notes, changelogs, and the spans an
injection rule matched inside them stay out. `matched` on a `PolicyFinding` is
literally the text of the document that fired the rule, so it is exactly what
must not be copied: an audit table that quotes hostile input has become a second
copy of it. What is carried instead is PatchAPI's vocabulary — the gate, the
reason code, the rule ids, and the path or command shape at issue.

*A tool that had no answer is not a denial.* `read_file` returning NOT_FOUND and
`run_command` returning POLICY_DENIED are both REFUSED, and only the second is a
control saying no. Recording both would make the audit answer wrong in the
direction that matters, by burying the refusals in absences.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Final

from agents.tools.results import ReasonCode
from agents.trace import ToolStatus, ToolTraceEvent
from packages.schemas.policy_decision import PolicyDecision

# The controls that can refuse a run, in the same `patchapi.*` namespace the
# audit log already uses for the acts it permits.
GATE_UNTRUSTED_TEXT: Final[str] = "patchapi.policy.untrusted_text"
GATE_COMMAND_ALLOWLIST: Final[str] = "patchapi.policy.command_allowlist"
GATE_FORBIDDEN_PATH: Final[str] = "patchapi.policy.forbidden_path"
GATE_TOOL_ALLOWLIST: Final[str] = "patchapi.policy.tool_allowlist"
GATE_WORKSPACE_BOUNDARY: Final[str] = "patchapi.policy.workspace_boundary"
GATE_POLICY: Final[str] = "patchapi.policy.gate"

# The act policy refuses when it blocks. Not a tool name, because no tool call is
# what was denied: the run asked to migrate a repository and was not allowed to.
ACTION_PATCH_REPOSITORY: Final[str] = "patch_repository"

# The reason codes that mean a control said no. The rest of the vocabulary
# describes a tool that could not answer — a missing file, a stage not reached, a
# contract that did not validate — and an unverifiable provider claim, which
# reaches this table through the policy verdict it produces rather than as a
# denial of its own.
DENIAL_REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        str(ReasonCode.POLICY_DENIED),
        str(ReasonCode.INJECTION_DETECTED),
        str(ReasonCode.OUT_OF_SCOPE),
    }
)

# POLICY_DENIED is the one code several gates share, so for that code the tool
# says which of them refused. Every other denial code belongs to one gate.
_GATE_BY_REASON_CODE: Final[Mapping[str, str]] = {
    str(ReasonCode.INJECTION_DETECTED): GATE_UNTRUSTED_TEXT,
    str(ReasonCode.OUT_OF_SCOPE): GATE_WORKSPACE_BOUNDARY,
}

_GATE_BY_TOOL: Final[Mapping[str, str]] = {
    "run_command": GATE_COMMAND_ALLOWLIST,
    "read_file": GATE_FORBIDDEN_PATH,
    "list_dir": GATE_FORBIDDEN_PATH,
    "apply_patch": GATE_FORBIDDEN_PATH,
}

# Arguments safe to name a target with. Each is a path, a source document, or a
# loopback URL — the shape of the thing refused. Free-text arguments a model
# wrote are deliberately absent.
_TARGET_ARGUMENTS: Final[tuple[str, ...]] = ("path", "source", "file_path", "url", "head_branch")

# The intake gate names its document by host path: a temp directory in a hosted
# run, a developer's checkout in a local one. Neither is a fact about the
# refusal, and both would make the same denial read differently depending on
# where it happened, so only the document's name is kept.
_BASENAME_ARGUMENTS: Final[frozenset[str]] = frozenset({"source"})

# Longest target kept. The trace has already bounded these; this is the audit
# table's own ceiling so one long argument cannot become the widest row in it.
MAX_TARGET_CHARS: Final[int] = 200


@dataclass(frozen=True, slots=True)
class Denial:
    """One thing a run was refused, ready to be audited.

    Four strings, all of them PatchAPI's: the gate that refused, the act it
    refused, the path or command shape at issue, and the rule or reason code
    that fired.
    """

    actor: str
    action: str
    target: str
    reason: str


def denials_in(events: Iterable[ToolTraceEvent]) -> list[Denial]:
    """Every refusal a control made during these tool calls, in order.

    Deduplicated on identity rather than on occurrence, because that is what the
    audit table stores: that the command allowlist refused `curl` in this run is
    one fact however many times the model tried it, and the retries are already
    in the worklog.
    """
    found: dict[tuple[str, str, str, str], Denial] = {}
    for event in events:
        denial = _from_event(event)
        if denial is None:
            continue
        found.setdefault((denial.actor, denial.action, denial.target, denial.reason), denial)
    return list(found.values())


def policy_denial(decision: Any) -> Denial | None:
    """The denial a blocked policy verdict is, or `None` for any other verdict.

    HUMAN_REQUIRED is not included. A run held for a reviewer was not refused;
    it was escalated, and recording an escalation as a denial would overstate
    what the controls stopped.
    """
    if not isinstance(decision, PolicyDecision) or str(decision.outcome) != "blocked":
        return None
    return Denial(
        actor=GATE_POLICY,
        action=ACTION_PATCH_REPOSITORY,
        target=decision.repo,
        # Rule ids, which are pinned configuration this product wrote. The
        # decision's `reason` is prose and is already stored with the decision.
        reason=", ".join(decision.rule_ids),
    )


def denials_for_run(events: Iterable[ToolTraceEvent], decision: Any = None) -> Sequence[Denial]:
    """Everything one execution of a run was refused."""
    denials = denials_in(events)
    verdict = policy_denial(decision)
    if verdict is not None:
        denials.append(verdict)
    return denials


def _from_event(event: ToolTraceEvent) -> Denial | None:
    """The denial this tool call records, or `None` if it is not one."""
    code = str(getattr(event, "reason_code", "") or "")
    if event.status is ToolStatus.DENIED:
        # The allowlist refused the call before the function was entered, so the
        # tool never had a chance to state a code of its own.
        return Denial(
            actor=GATE_TOOL_ALLOWLIST,
            action=event.tool,
            target=_target(event),
            reason=code or str(ReasonCode.POLICY_DENIED),
        )
    if event.status is not ToolStatus.REFUSED or code not in DENIAL_REASON_CODES:
        return None
    return Denial(
        actor=_GATE_BY_REASON_CODE.get(code) or _GATE_BY_TOOL.get(event.tool, GATE_POLICY),
        action=event.tool,
        target=_target(event),
        reason=code,
    )


def _target(event: ToolTraceEvent) -> str:
    """What was refused, said in a shape that carries no untrusted prose.

    A command is reduced to the program it would have run: that is the shape the
    allowlist matched on, and the whole argv a model proposed is not this table's
    to keep. Anything with no nameable target falls back to the digest of its
    arguments, which pins the call without quoting it.
    """
    arguments = dict(event.arguments or {})
    for name in _TARGET_ARGUMENTS:
        value = str(arguments.get(name) or "").strip()
        if not value:
            continue
        if name in _BASENAME_ARGUMENTS:
            value = PurePosixPath(value).name or value
        return value[:MAX_TARGET_CHARS]
    command = str(arguments.get("command") or "").strip()
    if command:
        return command.split()[0][:MAX_TARGET_CHARS]
    return f"sha256:{event.argument_digest}"


__all__ = [
    "ACTION_PATCH_REPOSITORY",
    "DENIAL_REASON_CODES",
    "GATE_COMMAND_ALLOWLIST",
    "GATE_FORBIDDEN_PATH",
    "GATE_POLICY",
    "GATE_TOOL_ALLOWLIST",
    "GATE_UNTRUSTED_TEXT",
    "GATE_WORKSPACE_BOUNDARY",
    "MAX_TARGET_CHARS",
    "Denial",
    "denials_for_run",
    "denials_in",
    "policy_denial",
]
