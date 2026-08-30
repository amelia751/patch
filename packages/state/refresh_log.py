"""One log entry per refresh, with a severity that means something.

The job used to print seven lines an hour, every hour, all of them at Cloud
Run's default severity because `basicConfig` wrote to stdout. Three consequences
followed, and only the third was cosmetic.

A failed refresh was indistinguishable from a successful one: `log.error` went
to the same stream as everything else, so Cloud Run inferred DEFAULT and no
log-based alert could find it. Second, the steady state was the noise — the same
five retired identifiers, enumerated hourly, at the same weight as new
information. Third, four of the seven lines shared a millisecond, so Cloud
Logging broke the tie arbitrarily and displayed the summary above the census it
summarised.

So a refresh emits one structured entry instead, and puts the judgement in the
severity rather than leaving it to whoever is reading:

    INFO     nothing changed
    NOTICE   something moved, and the next stage of the product will hear
    WARNING  the poll could not tell, so a conclusion is missing
    ERROR    the refresh did not finish

`WARNING` outranks `NOTICE` deliberately. A transition that reached the topic is
finished work; an identifier the poll could not reach is an unanswered question,
and answering it may yet change what the product does. Constraint 10 is why it
cannot stay quiet: a poll whose every probe failed used to exit 0 and read as a
clean bill of health.

Identifiers are named only when the set they belong to changed. The census stays
available under `--verbose` and is reconstructible from `provider_liveness`,
which is the authoritative record either way.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Final, TextIO

SEVERITY_INFO: Final[str] = "INFO"
SEVERITY_NOTICE: Final[str] = "NOTICE"
SEVERITY_WARNING: Final[str] = "WARNING"
SEVERITY_ERROR: Final[str] = "ERROR"

# Cloud Logging lifts these keys out of a JSON object on stdout and promotes
# them onto the entry itself. Everything else stays queryable as
# `jsonPayload.<field>`.
SEVERITY_KEY: Final[str] = "severity"
MESSAGE_KEY: Final[str] = "message"
LABELS_KEY: Final[str] = "logging.googleapis.com/labels"

# Cloud Run sets these on every job task. They are already Cloud Run labels on
# the entry, so this is not what makes an execution findable — it is what lets
# one execution be joined against a `jsonPayload` filter in a single query.
EXECUTION_VAR: Final[str] = "CLOUD_RUN_EXECUTION"
ATTEMPT_VAR: Final[str] = "CLOUD_RUN_TASK_ATTEMPT"

# How many identifiers the one-line message names before it starts counting. The
# entry carries the whole list in its fields regardless; this bounds only the
# sentence a human reads in the log list.
NAMED_LIMIT: Final[int] = 3

# Written to stderr as well as carrying an explicit severity. The severity is
# what Cloud Logging honours; the stream is what still says "this failed" if the
# JSON never parses.
STDERR_SEVERITIES: Final[frozenset[str]] = frozenset({SEVERITY_ERROR})


@dataclass(frozen=True, slots=True)
class RefreshSummary:
    """What one refresh observed, in the shape the entry needs.

    Statuses arrive as full identifier lists because severity depends on which
    sets are non-empty, not on their sizes. What reaches the entry is narrowed
    in `entry`.
    """

    provider: str
    checked: int = 0
    resolves: tuple[str, ...] = ()
    not_found: tuple[str, ...] = ()
    # We asked and the call failed. Not a transition in either direction, and
    # not evidence that nothing moved.
    unknown: tuple[str, ...] = ()
    transitions: tuple[dict[str, str], ...] = ()
    announced: tuple[str, ...] = ()
    # Identifiers this poll held no stored answer for. A new one means the
    # indexer found a call nothing had watched before, which changes what is
    # being watched even when nothing the provider serves has moved.
    first_seen: tuple[str, ...] = ()
    # Transitions whose event did not reach the topic, so their liveness row was
    # withheld for the next poll to retry.
    held_back: tuple[str, ...] = ()
    notices: int = 0
    reclassified: tuple[str, ...] = ()
    duration_ms: int = 0


def severity(summary: RefreshSummary) -> str:
    """The single judgement the entry carries."""
    if summary.unknown or summary.held_back:
        return SEVERITY_WARNING
    if summary.transitions or summary.first_seen or summary.reclassified:
        return SEVERITY_NOTICE
    return SEVERITY_INFO


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _named(items: tuple[str, ...], limit: int = NAMED_LIMIT) -> str:
    if not items:
        return "(none)"
    shown = ", ".join(items[:limit])
    remaining = len(items) - limit
    return shown if remaining <= 0 else f"{shown} +{remaining} more"


def message(summary: RefreshSummary) -> str:
    """The sentence read in the log list, worst news first."""
    clauses: list[str] = []
    if summary.unknown:
        clauses.append(
            f"{len(summary.unknown)} of {summary.checked} could not be checked "
            f"({_named(summary.unknown)}), so their liveness is unchanged"
        )
    if summary.held_back:
        clauses.append(
            f"{_plural(len(summary.held_back), 'announcement')} did not publish "
            f"({_named(summary.held_back)}), retried next poll"
        )
    if summary.transitions:
        moves = tuple(
            f"{change.get('identifier', '?')} {change.get('transition', 'moved')}"
            for change in summary.transitions
        )
        clauses.append(f"{_named(moves)}, announced {len(summary.announced)}")
    if summary.first_seen:
        clauses.append(
            f"{_plural(len(summary.first_seen), 'identifier')} new to the watchlist "
            f"({_named(summary.first_seen)})"
        )
    if summary.reclassified:
        clauses.append(
            f"{_plural(summary.notices, 'new notice')}, reclassified "
            f"{_plural(len(summary.reclassified), 'project')}"
        )
    if not clauses:
        clauses.append(f"{_plural(summary.checked, 'identifier')} checked, nothing changed")
    return f"{summary.provider}: " + "; ".join(clauses)


def labels(env: dict[str, str] | None = None) -> dict[str, str]:
    """Which execution produced the entry, when Cloud Run says so."""
    environ = os.environ if env is None else env
    found: dict[str, str] = {}
    for key, name in (("execution", EXECUTION_VAR), ("attempt", ATTEMPT_VAR)):
        if value := environ.get(name, "").strip():
            found[key] = value
    return found


def entry(summary: RefreshSummary, *, env: dict[str, str] | None = None) -> dict[str, Any]:
    """The whole refresh as one Cloud Logging entry."""
    payload: dict[str, Any] = {
        SEVERITY_KEY: severity(summary),
        MESSAGE_KEY: message(summary),
        "provider": summary.provider,
        # Counts rather than names. This fleet's resting state is five retired
        # identifiers, and enumerating them hourly is what made the old output
        # unreadable; `provider_liveness` holds the census.
        "checked": summary.checked,
        "resolves": len(summary.resolves),
        "not_found": len(summary.not_found),
        "unknown": len(summary.unknown),
        "transitions": len(summary.transitions),
        "announced": len(summary.announced),
        "duration_ms": summary.duration_ms,
    }
    # Named only where the set moved, which is what the entry exists to report.
    if summary.unknown:
        payload["unknown_identifiers"] = list(summary.unknown)
    if summary.transitions:
        payload["transition_detail"] = [dict(change) for change in summary.transitions]
    if summary.announced:
        payload["event_ids"] = list(summary.announced)
    if summary.first_seen:
        payload["first_seen"] = list(summary.first_seen)
    if summary.held_back:
        payload["held_back"] = list(summary.held_back)
    if summary.reclassified:
        payload["reclassified"] = list(summary.reclassified)
        payload["notices"] = summary.notices
    if found := labels(env):
        payload[LABELS_KEY] = found
    return payload


def failure(
    provider: str,
    exc: BaseException,
    *,
    duration_ms: int = 0,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The entry for a refresh that did not finish.

    Carries no counts. A refresh that raised has concluded nothing, and a zero
    beside `not_found` would read as an observation rather than an absence.
    """
    payload: dict[str, Any] = {
        SEVERITY_KEY: SEVERITY_ERROR,
        MESSAGE_KEY: f"{provider}: refresh failed: {type(exc).__name__}: {exc}",
        "provider": provider,
        "error": type(exc).__name__,
        "duration_ms": duration_ms,
    }
    if found := labels(env):
        payload[LABELS_KEY] = found
    return payload


def emit(payload: dict[str, Any], *, stream: TextIO | None = None) -> None:
    """Write one entry, on one line, to the stream Cloud Run reads."""
    target = stream
    if target is None:
        target = sys.stderr if payload.get(SEVERITY_KEY) in STDERR_SEVERITIES else sys.stdout
    # One line, or Cloud Logging treats each line as a separate entry and parses
    # none of them. `default=str` so an unexpected value degrades the field
    # rather than losing the entry to a TypeError.
    print(json.dumps(payload, separators=(",", ":"), default=str), file=target, flush=True)


class _BelowLevel(logging.Filter):
    """Keeps a handler from repeating what a louder handler already carries."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.limit


def configure_logging(level: int = logging.INFO) -> None:
    """Diagnostics on stdout, trouble on stderr.

    Cloud Run infers severity from the stream, so a library's `log.error` on
    stdout is recorded as DEFAULT and nothing can alert on it. One handler per
    stream, split at WARNING, is the smallest thing that makes the inference
    right for the output this job does not format itself.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    plain = logging.Formatter("%(message)s")

    quiet = logging.StreamHandler(sys.stdout)
    quiet.setFormatter(plain)
    quiet.addFilter(_BelowLevel(logging.WARNING))

    loud = logging.StreamHandler(sys.stderr)
    loud.setFormatter(plain)
    loud.setLevel(logging.WARNING)

    root.setLevel(level)
    root.addHandler(quiet)
    root.addHandler(loud)


__all__ = [
    "NAMED_LIMIT",
    "SEVERITY_ERROR",
    "SEVERITY_INFO",
    "SEVERITY_NOTICE",
    "SEVERITY_WARNING",
    "RefreshSummary",
    "configure_logging",
    "emit",
    "entry",
    "failure",
    "labels",
    "message",
    "severity",
]
