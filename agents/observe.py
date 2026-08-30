"""Stage spans for one remediation run.

`packages/observability` owns the span names, the attribute keys, and the
exporter a process installs. This module is the orchestrator's side of that
contract, and it exists for two reasons.

*Structure.* ADK auto-instruments its model and tool calls and attaches those
spans to whatever span is current. Opening one span per pipeline stage therefore
turns a flat list of model calls into the run's reasoning chain: which stage
caused which call, in what order, and how long each took.

*Containment.* A trace leaves the trust boundary — it is exported to a
third-party backend and read by people who are not reviewing this repository. So
the two ways of writing to a span here are narrow on purpose. `StageSpan.set`
accepts only the pinned keys from `packages.observability.config`, and only
values shaped like an identifier: no whitespace, one line, bounded length.
Provider text, model output, file contents and credentials have neither a key to
travel under nor a shape that would be accepted.

Nothing here installs a tracer provider. That happens once, in a process entry
point (`services/agent_runner/.../telemetry.py`); OpenTelemetry ignores a second
global provider, so a library that installed one would win or lose by import
order. With no provider installed — a unit test, a slim image, a broken
OpenTelemetry install — every call degrades to a span that records nothing, and
a run proceeds exactly as it would have. Tracing is never the reason a
remediation fails.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from typing import Any, Final

from packages.observability.config import (
    ATTR_ATTEMPT,
    ATTR_BASE_SHA,
    ATTR_CHANGE_ID,
    ATTR_MODEL_ID,
    ATTR_POLICY_OUTCOME,
    ATTR_REPO,
    ATTR_RUN_ID,
    ATTR_TRUST,
)

log = logging.getLogger(__name__)

# The whole vocabulary a stage span may use. A key outside this set is dropped
# rather than renamed, because the alternative — accepting it — is how a trace
# acquires a field nobody pinned and a dashboard query silently stops matching.
PINNED_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    {
        ATTR_ATTEMPT,
        ATTR_BASE_SHA,
        ATTR_CHANGE_ID,
        ATTR_MODEL_ID,
        ATTR_POLICY_OUTCOME,
        ATTR_REPO,
        ATTR_RUN_ID,
        ATTR_TRUST,
    }
)

# The run-level parent the stage spans hang from. Without one, each stage is its
# own trace root and a single remediation arrives at the backend as seven
# unrelated traces, which is not a chain anyone can read.
#
# It is pinned here rather than in `packages/observability/config.py` only
# because this is not a stage: that module names the seven stages of roadmap §8,
# and a run is the thing that contains them. Both names should end up in one
# registry; see the note in the change that introduced this.
SPAN_RUN: Final[str] = "patchapi.run"

# Span events, not attributes: these mark a moment inside a stage rather than
# describing it, and they carry no payload precisely because the payload would
# be prose. What the run could not reach, and why, goes to the log.
EVENT_MEMORY_RECALLED: Final[str] = "patchapi.memory.recalled"
EVENT_MEMORY_UNAVAILABLE: Final[str] = "patchapi.memory.unavailable"
EVENT_MEMORY_RECORDED: Final[str] = "patchapi.memory.recorded"
EVENT_MEMORY_NOT_RECORDED: Final[str] = "patchapi.memory.not_recorded"

MAX_ATTRIBUTE_CHARS: Final[int] = 200

# An identifier, a digest, a repository path, or a lowercase enum value. The
# absence of whitespace is the load-bearing part: every untrusted document this
# product handles is prose, and prose does not survive this pattern.
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")


def run_identity(
    *,
    run_id: str = "",
    repo: str = "",
    change_id: str = "",
    base_sha: str = "",
    attempt: int = 0,
    model_id: str = "",
) -> dict[str, Any]:
    """The identity attributes a stage span opens with, keyed by the pinned names.

    Empty values are omitted rather than exported as empty strings, so a stage
    that genuinely has no base_sha yet does not claim one.
    """
    candidates: dict[str, Any] = {
        ATTR_RUN_ID: run_id,
        ATTR_REPO: repo,
        ATTR_CHANGE_ID: change_id,
        ATTR_BASE_SHA: base_sha,
        ATTR_MODEL_ID: model_id,
    }
    attributes = {key: value for key, value in candidates.items() if value}
    if attempt > 0:
        attributes[ATTR_ATTEMPT] = attempt
    return attributes


class StageSpan:
    """One stage's span, and the only two ways of writing to it.

    Wraps the OpenTelemetry span rather than exposing it, so a call site cannot
    reach `set_attribute` and put an unpinned key or a paragraph of provider
    text on a record that leaves the trust boundary.
    """

    __slots__ = ("_span",)

    def __init__(self, span: Any | None = None) -> None:
        self._span = span

    @property
    def recording(self) -> bool:
        """Whether anything written here will actually be exported."""
        try:
            return self._span is not None and bool(self._span.is_recording())
        except Exception:
            return False

    def set(self, key: str, value: Any) -> bool:
        """Attach one pinned attribute. Returns whether it was accepted.

        Returning the verdict rather than raising: a rejected attribute is a
        programming error worth a test, and never worth a failed run.
        """
        if key not in PINNED_ATTRIBUTES:
            log.debug("refusing unpinned span attribute %r", key)
            return False
        if isinstance(value, bool) or isinstance(value, int):
            return self._write(key, value)
        text = str(value)
        if not text or len(text) > MAX_ATTRIBUTE_CHARS or _IDENTIFIER.match(text) is None:
            log.debug("refusing span attribute %r: not an identifier-shaped value", key)
            return False
        return self._write(key, text)

    def outcome(self, token: str, *, ok: bool) -> None:
        """Record how the stage ended, as one enum token.

        Carried on the span status rather than an attribute because there is no
        pinned key for a run state or a verification verdict. `ok=False` means
        this stage did not produce what it set out to — a blocked intake or a
        human-required exit says so here — not that the system malfunctioned.
        """
        if self._span is None:
            return
        try:
            from opentelemetry.trace import Status, StatusCode

            safe = token if _IDENTIFIER.match(token or "") else ""
            self._span.set_status(
                Status(StatusCode.OK) if ok else Status(StatusCode.ERROR, safe or "stage_failed")
            )
        except Exception as exc:  # pragma: no cover - tracing never fails a run
            log.debug("could not set span status: %s", exc)

    def note(self, event: str) -> None:
        """Mark a moment inside the stage. Name only, never a payload."""
        if self._span is None:
            return
        try:
            self._span.add_event(event)
        except Exception as exc:  # pragma: no cover - tracing never fails a run
            log.debug("could not add span event %r: %s", event, exc)

    def _write(self, key: str, value: Any) -> bool:
        if self._span is None:
            return False
        try:
            self._span.set_attribute(key, value)
        except Exception as exc:  # pragma: no cover - tracing never fails a run
            log.debug("could not set span attribute %r: %s", key, exc)
            return False
        return True


@contextmanager
def stage_span(name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[StageSpan]:
    """Open one pipeline stage's span and make it the current one.

    Current across the stage's `await`s, which is the point: ADK's model and
    tool spans attach to whatever is current, so they nest under the stage that
    caused them instead of floating at the root of the trace.

    A tracing failure yields a `StageSpan` that records nothing and the stage
    runs unchanged.
    """
    with ExitStack() as stack:
        raw: Any | None = None
        try:
            from packages.observability import span as open_span

            raw = stack.enter_context(open_span(name))
        except Exception as exc:
            # Nothing was pushed onto the stack, so the stage runs with a span
            # that records nothing rather than not running.
            log.warning("running %s untraced: %s", name, exc)
        stage = StageSpan(raw)
        for key, value in (attributes or {}).items():
            stage.set(key, value)
        yield stage


def current_stage_span() -> StageSpan:
    """The stage span in scope, so nested code can write to it without plumbing.

    Returns a span that records nothing when no stage is open, which is what a
    directly-invoked stage method or a unit test sees.
    """
    try:
        from opentelemetry import trace

        return StageSpan(trace.get_current_span())
    except Exception as exc:  # pragma: no cover - tracing never fails a run
        log.debug("no current span: %s", exc)
        return StageSpan(None)


__all__ = [
    "EVENT_MEMORY_NOT_RECORDED",
    "EVENT_MEMORY_RECALLED",
    "EVENT_MEMORY_RECORDED",
    "EVENT_MEMORY_UNAVAILABLE",
    "MAX_ATTRIBUTE_CHARS",
    "PINNED_ATTRIBUTES",
    "SPAN_RUN",
    "StageSpan",
    "current_stage_span",
    "run_identity",
    "stage_span",
]
