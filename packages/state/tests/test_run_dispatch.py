"""The console starts a remediator only when this deployment named one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.state.run_dispatch import (
    CloudRunRemediationDispatcher,
    LocalProcessDispatcher,
    build_dispatcher,
    provisioning_note,
)


def test_no_dispatcher_until_a_job_is_named() -> None:
    assert build_dispatcher({}) is None
    assert build_dispatcher({"GCP_PROJECT": "patch-505223"}) is None
    assert build_dispatcher({"PATCHAPI_REMEDIATION_JOB": "patchapi-remediate"}) is None


def test_cloud_run_wins_when_the_job_and_project_are_set() -> None:
    built = build_dispatcher(
        {
            "PATCHAPI_REMEDIATION_JOB": "patchapi-remediate",
            "GCP_PROJECT": "patch-505223",
            "PATCHAPI_REMEDIATION_LOCAL": "1",
        }
    )
    assert isinstance(built, CloudRunRemediationDispatcher)
    assert built.job == "patchapi-remediate"


def test_local_process_when_asked_and_no_job() -> None:
    built = build_dispatcher({"PATCHAPI_REMEDIATION_LOCAL": "1"})
    assert isinstance(built, LocalProcessDispatcher)


def test_provisioning_note_stays_quiet_until_the_job_is_late() -> None:
    started = datetime(2026, 8, 27, 22, 45, tzinfo=UTC)
    traces = [{"body": "Dispatched to cloud-run-job:patchapi-remediate"}]
    assert (
        provisioning_note(
            state="RECEIVED", traces=traces, started_at=started, now=started + timedelta(seconds=5)
        )
        is None
    )
    note = provisioning_note(
        state="RECEIVED", traces=traces, started_at=started, now=started + timedelta(seconds=20)
    )
    assert note is not None
    assert "20s" in note
    assert "job scheduling" in note


def test_provisioning_note_stops_once_the_remediator_claims() -> None:
    started = datetime(2026, 8, 27, 22, 45, tzinfo=UTC)
    traces = [
        {"body": "Dispatched to cloud-run-job:patchapi-remediate"},
        {"body": "Remediator claimed amelia751/storygen at e41d775ec28a."},
    ]
    assert (
        provisioning_note(
            state="RECEIVED", traces=traces, started_at=started, now=started + timedelta(seconds=90)
        )
        is None
    )
