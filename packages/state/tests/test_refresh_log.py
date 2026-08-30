"""The refresh log has to say what happened, at a severity that can be alerted on.

The defect being pinned: every line this job wrote landed at Cloud Run's default
severity, so a crash, a withheld announcement, and an hour in which nothing
happened were the same colour. These tests hold the ladder in place — and hold
the steady state quiet, because the reason the old output went unread was that
it enumerated five permanently retired identifiers every hour.
"""

from __future__ import annotations

import io
import json
import logging
import sys

from packages.state import refresh_log
from packages.state.refresh_log import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_NOTICE,
    SEVERITY_WARNING,
    RefreshSummary,
)

# The shape of a real resting poll: one live model, five retired ones, nothing
# moved. This is what ran 24 times a day and produced seven lines each time.
RESTING = RefreshSummary(
    provider="google",
    checked=6,
    resolves=("gemini-3.5-flash",),
    not_found=(
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-lite-001",
        "imagen-4.0-generate-001",
    ),
)

RETIREMENT = {
    "identifier": "imagen-4.0-generate-001",
    "surface": "vertex",
    "transition": "retired",
    "from": "resolves",
    "to": "not_found",
}


def test_nothing_changed_is_info() -> None:
    assert refresh_log.severity(RESTING) == SEVERITY_INFO
    assert "nothing changed" in refresh_log.message(RESTING)


def test_the_resting_entry_does_not_enumerate_the_census() -> None:
    """Counts, not names. The names are why nobody read the old output."""
    payload = refresh_log.entry(RESTING, env={})
    assert payload["not_found"] == 5
    assert payload["resolves"] == 1
    assert payload["checked"] == 6
    # No key carries an identifier list, so no retired model is named hourly.
    encoded = json.dumps(payload)
    for identifier in RESTING.not_found:
        assert identifier not in encoded


def test_a_transition_is_notice_and_is_named() -> None:
    summary = RefreshSummary(
        provider="google",
        checked=6,
        transitions=(RETIREMENT,),
        announced=("evt_1",),
    )
    assert refresh_log.severity(summary) == SEVERITY_NOTICE
    assert "imagen-4.0-generate-001 retired" in refresh_log.message(summary)
    payload = refresh_log.entry(summary, env={})
    assert payload["transition_detail"] == [RETIREMENT]
    assert payload["event_ids"] == ["evt_1"]
    assert payload["transitions"] == 1


def test_a_new_identifier_on_the_watchlist_is_notice() -> None:
    """The case the old log called "nothing announced" and left at DEFAULT.

    On 2026-08-29 the watchlist went from 6 identifiers to 8 as a merged pull
    request introduced `gemini-3.1-flash-image`. No provider transition occurred,
    correctly, and both summary lines therefore reported that nothing had
    happened — of a poll that was now watching two things it had never seen.
    """
    summary = RefreshSummary(
        provider="google",
        checked=8,
        first_seen=("gemini-3.1-flash-image", "gemini-3.1-flash-image-preview"),
    )
    assert refresh_log.severity(summary) == SEVERITY_NOTICE
    assert "2 identifiers new to the watchlist" in refresh_log.message(summary)
    assert refresh_log.entry(summary, env={})["first_seen"] == list(summary.first_seen)


def test_reclassification_is_notice_and_reports_its_cause() -> None:
    summary = RefreshSummary(provider="google", checked=6, notices=3, reclassified=("storygen",))
    assert refresh_log.severity(summary) == SEVERITY_NOTICE
    assert "3 new notices, reclassified 1 project" in refresh_log.message(summary)
    payload = refresh_log.entry(summary, env={})
    assert payload["notices"] == 3
    assert payload["reclassified"] == ["storygen"]


def test_an_unreachable_surface_is_a_warning_not_a_clean_bill() -> None:
    """Constraint 10: a poll that could not tell must not report that nothing moved."""
    summary = RefreshSummary(
        provider="google",
        checked=6,
        resolves=("gemini-3.5-flash",),
        unknown=("imagen-4.0-generate-001",),
    )
    assert refresh_log.severity(summary) == SEVERITY_WARNING
    text = refresh_log.message(summary)
    assert "could not be checked" in text
    assert "nothing changed" not in text
    assert refresh_log.entry(summary, env={})["unknown_identifiers"] == ["imagen-4.0-generate-001"]


def test_a_held_back_announcement_is_a_warning() -> None:
    summary = RefreshSummary(
        provider="google",
        checked=6,
        transitions=(RETIREMENT,),
        held_back=("imagen-4.0-generate-001 on vertex",),
    )
    # The retirement alone would be NOTICE; failing to announce it is the more
    # actionable fact, so it wins.
    assert refresh_log.severity(summary) == SEVERITY_WARNING
    assert "did not publish" in refresh_log.message(summary)


def test_degradation_outranks_news() -> None:
    summary = RefreshSummary(
        provider="google",
        checked=6,
        transitions=(RETIREMENT,),
        first_seen=("gemini-3.1-flash-image",),
        unknown=("gemini-2.0-flash",),
    )
    assert refresh_log.severity(summary) == SEVERITY_WARNING


def test_a_long_list_is_counted_rather_than_recited() -> None:
    summary = RefreshSummary(
        provider="google",
        checked=9,
        unknown=tuple(f"model-{index}" for index in range(9)),
    )
    text = refresh_log.message(summary)
    assert "+6 more" in text
    # The entry still carries every one; only the sentence is bounded.
    assert len(refresh_log.entry(summary, env={})["unknown_identifiers"]) == 9


def test_one_entry_is_one_json_line() -> None:
    """Cloud Logging parses a JSON object only when it owns the whole line."""
    stream = io.StringIO()
    refresh_log.emit(refresh_log.entry(RESTING, env={}), stream=stream)
    written = stream.getvalue()
    assert written.count("\n") == 1
    assert json.loads(written)["severity"] == SEVERITY_INFO


def test_a_failed_refresh_is_error_and_claims_no_observations() -> None:
    payload = refresh_log.failure("google", RuntimeError("no route to host"), env={})
    assert payload["severity"] == SEVERITY_ERROR
    assert payload["error"] == "RuntimeError"
    assert "no route to host" in payload["message"]
    # A refresh that raised concluded nothing, so a zero here would be a claim.
    assert "not_found" not in payload
    assert "checked" not in payload


def test_error_goes_to_stderr_so_the_stream_agrees_with_the_severity() -> None:
    out, err = io.StringIO(), io.StringIO()
    refresh_log.emit(refresh_log.entry(RESTING, env={}), stream=out)
    assert out.getvalue()
    # No explicit stream: the severity picks the descriptor, which is the only
    # signal left if the JSON is ever unparseable.
    payload = refresh_log.failure("google", RuntimeError("boom"), env={})
    assert payload["severity"] in refresh_log.STDERR_SEVERITIES
    refresh_log.emit(payload, stream=err)
    assert json.loads(err.getvalue())["severity"] == SEVERITY_ERROR


def test_the_execution_is_labelled_when_cloud_run_says_so() -> None:
    env = {
        refresh_log.EXECUTION_VAR: "patchapi-refresh-releases-n2xqd",
        refresh_log.ATTEMPT_VAR: "0",
    }
    payload = refresh_log.entry(RESTING, env=env)
    assert payload[refresh_log.LABELS_KEY] == {
        "execution": "patchapi-refresh-releases-n2xqd",
        "attempt": "0",
    }
    # Absent outside Cloud Run, and an empty label block is worse than none.
    assert refresh_log.LABELS_KEY not in refresh_log.entry(RESTING, env={})


def test_trouble_is_routed_to_stderr_and_diagnostics_are_not() -> None:
    """Cloud Run infers severity from the stream for anything we do not format.

    A library's `log.error` used to land on stdout and be recorded as DEFAULT.
    """
    refresh_log.configure_logging(logging.DEBUG)
    root = logging.getLogger()
    try:
        # By identity, not by name: pytest substitutes both descriptors, and the
        # handlers hold whichever objects were current when they were built.
        streams = {handler.stream: handler for handler in root.handlers}
        assert set(streams) == {sys.stdout, sys.stderr}

        warning = logging.LogRecord("t", logging.WARNING, __file__, 1, "trouble", None, None)
        info = logging.LogRecord("t", logging.INFO, __file__, 1, "routine", None, None)
        assert streams[sys.stderr].level == logging.WARNING
        # stdout declines what stderr will carry, so nothing is logged twice.
        assert not streams[sys.stdout].filter(warning)
        assert streams[sys.stdout].filter(info)
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
