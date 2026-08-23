"""The per-run context tools are bound to.

Tools are built as closures over one `RunContext` rather than reading globals or
the working directory. Two reasons, both structural.

*Containment.* A tool that reads files takes its roots from here, so "which tree
may this agent see" is a property of the run, not of whatever directory the
process happened to start in. `resolve_within` is the only way a tool turns a
model-supplied string into a path.

*Output.* An agent's output is what it recorded here through a `record_*` tool.
The final message of a turn is prose and is never parsed into a contract, so a
model cannot produce a `ChangeManifest` by describing one.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.config import AgentId


class PathOutsideRootError(ValueError):
    """A tool was asked for a path outside the root it is bound to."""


def resolve_within(root: Path, candidate: str) -> Path:
    """Resolve `candidate` under `root`, refusing anything that escapes it.

    Symlinks are resolved before the containment check, so a link planted inside
    the workspace cannot be used to read the developer's home directory.
    """
    resolved_root = root.resolve()
    target = (resolved_root / candidate).resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise PathOutsideRootError(
            f"{candidate!r} resolves outside the permitted root {resolved_root}"
        )
    return target


@dataclass(slots=True)
class RecordedOutput:
    """One contract an agent committed, with who committed it."""

    contract: str
    agent: AgentId
    value: Any


@dataclass(slots=True)
class RunContext:
    """Everything a run's tools are allowed to touch, and what they produced.

    Roots default to `None`, and a tool bound to a missing root returns a
    structured refusal rather than falling back to the process working
    directory. A stage that has no workspace yet has no workspace.

    `sandbox` is the `sandbox.session.SandboxSession` the run executes through
    when one has been opened. It is typed `Any` rather than imported: the agent
    tree must stay constructible without the sandbox tree, and a session is a
    duck-typed transport (local temp workspace or GKE Agent Sandbox claim), not
    a class the tools should be coupled to. When it is set, the workspace tools
    read, edit and execute through it instead of touching the filesystem
    directly; `workspace_root` still names the local tree a `LocalSession`
    exposes, so containment is checked against a real path wherever one exists.
    """

    run_id: str
    repo_root: Path
    feed_dir: Path
    workspace_root: Path | None = None
    evidence_root: Path | None = None
    sandbox: Any | None = None
    project_id: str | None = None
    credentials_inventory: Any | Callable[[], Any] | None = None
    index_usages: list[dict[str, Any]] = field(default_factory=list)
    outputs: dict[str, RecordedOutput] = field(default_factory=dict)
    human_required: list[dict[str, str]] = field(default_factory=list)
    operator_requests: list[dict[str, Any]] = field(default_factory=list)

    def record(self, contract: str, agent: AgentId, value: Any) -> None:
        """Commit `value` as this run's `contract`. Last write wins.

        Overwriting is allowed because a retried attempt legitimately replaces
        the previous plan; the trace, not this dict, is the history.
        """
        self.outputs[contract] = RecordedOutput(contract=contract, agent=agent, value=value)

    def output(self, contract: str) -> Any | None:
        """The recorded value for `contract`, or `None` if nothing committed it."""
        recorded = self.outputs.get(contract)
        return None if recorded is None else recorded.value

    @property
    def stopped_for_human(self) -> bool:
        """Whether any agent took the fail-closed exit during this run."""
        return bool(self.human_required)

    @property
    def waiting_on_operator(self) -> bool:
        """Whether a specialist asked the operator for a runtime secret or GCP."""
        return bool(self.operator_requests)
