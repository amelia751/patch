"""The tool-trace stream the dashboard renders and an audit reads.

Roadmap §12.8 asks for one trace per run. This module is the record of what the
agents *did*: every tool call, its arguments, how long it took, and a digest of
what came back. It is deliberately not a log of what a model said. A model's
prose is not evidence; a denied tool call and a recorded contract are.

Arguments and results are stored as digests plus a bounded summary rather than
verbatim. Tool results carry untrusted provider text and repository excerpts,
and a trace is written to places — a dashboard, an audit table — that must not
become a second copy of material policy has already bounded.
"""

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

from agents.config import FLEET_VERSION, TRACE_DIGEST_CHARS, AgentId

# Longest human-readable summary kept alongside a digest.
_MAX_SUMMARY_CHARS: Final[int] = 200

# Argument names whose values are never summarised, only counted. These carry
# untrusted or bulky text; the digest still pins exactly what was passed.
_OPAQUE_ARGUMENT_NAMES: Final[frozenset[str]] = frozenset(
    {"content", "diff", "excerpt", "notice_text", "rationale", "text"}
)


class ToolStatus(StrEnum):
    """How a tool call ended."""

    OK = "ok"
    # The allowlist refused the call before the tool function ran.
    DENIED = "denied"
    # The tool ran and returned a structured refusal: it could not answer.
    REFUSED = "refused"
    ERROR = "error"


def digest(value: Any) -> str:
    """Stable short digest of any JSON-serialisable value.

    Sorted keys and no whitespace, so the same payload digests identically
    across processes and the digest in a stored trace can be re-derived.
    """
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:TRACE_DIGEST_CHARS]


def summarise(value: Any) -> str:
    """One bounded line describing `value`, safe to show in a UI cell."""
    if isinstance(value, Mapping):
        keys = ", ".join(sorted(str(key) for key in value))
        text = f"{{{keys}}}"
    elif isinstance(value, (list, tuple)):
        text = f"[{len(value)} items]"
    else:
        text = str(value)
    collapsed = " ".join(text.split())
    if len(collapsed) <= _MAX_SUMMARY_CHARS:
        return collapsed
    return collapsed[: _MAX_SUMMARY_CHARS - 1] + "…"


def _argument_view(arguments: Mapping[str, Any]) -> dict[str, str]:
    """Argument names mapped to a bounded description of each value."""
    view: dict[str, str] = {}
    for name, value in sorted(arguments.items()):
        if name in _OPAQUE_ARGUMENT_NAMES:
            view[name] = f"<{len(str(value))} chars, sha256:{digest(value)}>"
        else:
            view[name] = summarise(value)
    return view


@dataclass(frozen=True, slots=True)
class ToolTraceEvent:
    """One tool call, as the dashboard and the audit log see it."""

    sequence: int
    agent: AgentId
    tool: str
    status: ToolStatus
    started_at: str
    duration_ms: float
    arguments: Mapping[str, str]
    argument_digest: str
    result_digest: str
    result_summary: str
    fleet_version: str = FLEET_VERSION
    detail: str | None = None

    def to_record(self) -> dict[str, Any]:
        """A flat, JSON-safe record. What gets persisted and streamed."""
        record = asdict(self)
        record["agent"] = str(self.agent)
        record["status"] = str(self.status)
        record["arguments"] = dict(self.arguments)
        record["duration_ms"] = round(self.duration_ms, 3)
        return record

    def render(self) -> str:
        """One terminal line, aligned so a trace reads as a sequence."""
        marker = {
            ToolStatus.OK: "ok  ",
            ToolStatus.DENIED: "DENY",
            ToolStatus.REFUSED: "REFU",
            ToolStatus.ERROR: "ERR ",
        }[self.status]
        args = ", ".join(f"{name}={value}" for name, value in self.arguments.items())
        line = (
            f"  {self.sequence:>2}. [{marker}] {self.agent}.{self.tool}"
            f"({args}) {self.duration_ms:.0f}ms -> {self.result_summary}"
        )
        if self.detail:
            line += f"\n        {self.detail}"
        return line


@dataclass(slots=True)
class ToolTrace:
    """The ordered tool calls of one run.

    `record` takes an already-measured duration rather than timing anything
    itself: the caller is the tool callback, which is the only place that knows
    where the tool boundary actually is.
    """

    run_id: str
    events: list[ToolTraceEvent] = field(default_factory=list)

    def record(
        self,
        *,
        agent: AgentId,
        tool: str,
        status: ToolStatus,
        arguments: Mapping[str, Any],
        result: Any,
        duration_ms: float,
        detail: str | None = None,
        now: datetime | None = None,
    ) -> ToolTraceEvent:
        """Append one call and return the event that was stored."""
        moment = now or datetime.now(UTC)
        event = ToolTraceEvent(
            sequence=len(self.events) + 1,
            agent=agent,
            tool=tool,
            status=status,
            started_at=moment.isoformat(timespec="milliseconds"),
            duration_ms=duration_ms,
            arguments=_argument_view(arguments),
            argument_digest=digest(dict(arguments)),
            result_digest=digest(result),
            result_summary=summarise(result),
            detail=detail,
        )
        self.events.append(event)
        return event

    def __iter__(self) -> Iterator[ToolTraceEvent]:
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)

    def calls(self, tool: str) -> list[ToolTraceEvent]:
        """Every event for `tool`, in order."""
        return [event for event in self.events if event.tool == tool]

    @property
    def denied(self) -> list[ToolTraceEvent]:
        """Calls the allowlist refused. Empty is the expected state."""
        return [event for event in self.events if event.status is ToolStatus.DENIED]

    def to_records(self) -> list[dict[str, Any]]:
        return [event.to_record() for event in self.events]

    def to_ndjson(self) -> str:
        """Newline-delimited JSON — the shape the dashboard stream consumes."""
        return "".join(json.dumps(record, sort_keys=True) + "\n" for record in self.to_records())

    def render(self, events: Iterable[ToolTraceEvent] | None = None) -> str:
        """The whole trace as terminal lines, for the smoke and the demo."""
        return "\n".join(event.render() for event in (events or self.events))
