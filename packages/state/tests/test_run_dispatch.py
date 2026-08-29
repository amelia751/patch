"""The console starts a remediator only when this deployment named one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from packages.state import run_dispatch
from packages.state.run_dispatch import (
    CloudRunRemediationDispatcher,
    LocalProcessDispatcher,
    WarmPoolDispatcher,
    build_dispatcher,
    provisioning_note,
)
from packages.state.worker_registry import LaneHealth


def test_no_dispatcher_until_a_job_is_named() -> None:
    assert build_dispatcher({}) is None
    assert build_dispatcher({"GCP_PROJECT": "patch-505223"}) is None
    assert build_dispatcher({"PATCHAPI_REMEDIATION_JOB": "patchapi-remediate"}) is None


def test_cloud_run_runs_the_job_when_nothing_asked_for_the_local_lane() -> None:
    built = build_dispatcher(
        {"PATCHAPI_REMEDIATION_JOB": "patchapi-remediate", "GCP_PROJECT": "patch-505223"}
    )
    assert isinstance(built, CloudRunRemediationDispatcher)
    assert built.job == "patchapi-remediate"


def test_an_explicit_local_request_outranks_a_configured_job() -> None:
    """A developer asking for the local lane means it, job name or not.

    A laptop that knows the Cloud Run job name is the normal case, so preferring
    the job sent every run to a container built from a different commit than the
    one being edited.
    """
    built = build_dispatcher(
        {
            "PATCHAPI_REMEDIATION_JOB": "patchapi-remediate",
            "GCP_PROJECT": "patch-505223",
            "PATCHAPI_REMEDIATION_LOCAL": "1",
        }
    )
    assert isinstance(built, LocalProcessDispatcher)


def test_local_process_when_asked_and_no_job() -> None:
    built = build_dispatcher({"PATCHAPI_REMEDIATION_LOCAL": "1"})
    assert isinstance(built, LocalProcessDispatcher)


def test_a_warm_pool_outranks_the_job_it_replaces() -> None:
    """The job stays deployed for replaying a run by hand, and must not be preferred.

    Measured, a job execution waits ~136s for capacity and pays it again when an
    operator hold ends the execution. Choosing the job here would hand that back,
    and would leave two remediators eligible for one row.
    """
    built = build_dispatcher(
        {
            "PATCHAPI_REMEDIATION_JOB": "patchapi-remediate",
            "PATCHAPI_REMEDIATION_WORKER_POOL": "patchapi-remediate-worker",
            "GCP_PROJECT": "patch-505223",
        }
    )
    assert isinstance(built, WarmPoolDispatcher)
    assert built.transport == "cloud-run-worker-pool:patchapi-remediate-worker"


def test_an_explicit_local_request_outranks_a_warm_pool() -> None:
    built = build_dispatcher(
        {
            "PATCHAPI_REMEDIATION_WORKER_POOL": "patchapi-remediate-worker",
            "PATCHAPI_REMEDIATION_LOCAL": "1",
        }
    )
    assert isinstance(built, LocalProcessDispatcher)


async def test_dispatching_to_a_warm_pool_starts_nothing() -> None:
    """The run row is the request. There is no execution to create."""
    assert await WarmPoolDispatcher(pool="p").dispatch("11111111-1111-1111-1111-111111111111") == ""


def test_a_local_worker_is_named_as_one() -> None:
    """Same behaviour as the pool, and the worklog should not call a laptop Cloud Run."""
    built = build_dispatcher({"PATCHAPI_REMEDIATION_WORKER_POOL": "local"})
    assert isinstance(built, WarmPoolDispatcher)
    assert built.transport == "local-worker"


def test_both_warm_lanes_are_recognised_as_warm() -> None:
    assert run_dispatch.warm_transport("local-worker") is True
    assert run_dispatch.warm_transport("cloud-run-worker-pool:patchapi-remediate-worker") is True
    assert run_dispatch.warm_transport("cloud-run-job:patchapi-remediate") is False
    assert run_dispatch.warm_transport("local-process") is False


def test_the_local_command_names_the_workspace_member(monkeypatch) -> None:
    """`uv run patchapi-remediate` resolves against the workspace root.

    The root does not declare the script, so the child exited before writing a
    line and the run sat on "waiting for the remediator" for good.
    """
    monkeypatch.setattr(
        run_dispatch.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )
    assert run_dispatch._local_command() == [
        "/usr/bin/uv",
        "run",
        "--package",
        "patchapi-agent-runner",
        "patchapi-remediate",
    ]


def test_an_installed_entry_point_is_run_directly(monkeypatch) -> None:
    monkeypatch.setattr(
        run_dispatch.shutil,
        "which",
        lambda name: "/venv/bin/patchapi-remediate" if name == "patchapi-remediate" else None,
    )
    assert run_dispatch._local_command() == ["/venv/bin/patchapi-remediate"]


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
    # Claims only what a run row can support, and attributes the wait where the
    # Cloud Run task API puts it: 136s waiting for capacity, 5.6s of container.
    assert "No agent has run yet" in note
    assert "ADK" not in note


def _warm_note(health: LaneHealth | None) -> str:
    started = datetime(2026, 8, 27, 22, 45, tzinfo=UTC)
    note = provisioning_note(
        state="RECEIVED",
        traces=[{"body": "Dispatched to cloud-run-worker-pool:patchapi-remediate-worker"}],
        started_at=started,
        transport="cloud-run-worker-pool:patchapi-remediate-worker",
        now=started + timedelta(seconds=20),
        health=health,
    )
    assert note is not None
    # The one claim every wording shares, and the only one a run row supports.
    assert "No agent has run yet" in note
    assert "waiting for Cloud Run to give" not in note
    return note


def test_a_silent_warm_pool_is_not_described_as_a_starting_container() -> None:
    """Same silence, different cause. A pool has already found its capacity."""
    assert "a remediation worker is running" in _warm_note(None)


def test_an_unattended_lane_is_named_as_the_fault_it_is() -> None:
    """What the four-hour silence should have said, instead of advice."""
    note = _warm_note(LaneHealth(alive=0, idle=0, silent_for=240.0))

    assert "went quiet 240s ago" in note
    assert "nothing is available to claim this run" in note


def test_a_lane_no_worker_ever_reported_into_says_so() -> None:
    """Distinct from having gone quiet: nothing was ever deployed here."""
    assert "has ever reported in" in _warm_note(LaneHealth())


def test_every_worker_being_busy_is_reported_as_queueing_not_as_a_fault() -> None:
    """One run per worker is the design, so being behind one is not a problem."""
    note = _warm_note(LaneHealth(alive=2, idle=0, silent_for=1.0))

    assert "every remediation worker on this lane is busy" in note
    assert "2 of 2" in note
    assert "check" not in note.lower()


def test_a_free_worker_means_the_next_poll_takes_it() -> None:
    note = _warm_note(LaneHealth(alive=3, idle=2, silent_for=1.0))

    assert "3 remediation worker(s) are on the air with 2 free" in note


def test_provisioning_note_does_not_repeat_itself_on_every_poll() -> None:
    """The suppression match and the note itself have to stay one string."""
    started = datetime(2026, 8, 27, 22, 45, tzinfo=UTC)
    first_at = started + timedelta(seconds=20)
    first = provisioning_note(
        state="RECEIVED",
        traces=[{"body": "Dispatched to cloud-run-job:patchapi-remediate"}],
        started_at=started,
        now=first_at,
    )
    assert first is not None
    told = [
        {"body": "Dispatched to cloud-run-job:patchapi-remediate"},
        {"body": first, "occurred_at": first_at},
    ]
    assert (
        provisioning_note(
            state="RECEIVED", traces=told, started_at=started, now=first_at + timedelta(seconds=5)
        )
        is None
    )
    again = provisioning_note(
        state="RECEIVED", traces=told, started_at=started, now=first_at + timedelta(seconds=30)
    )
    assert again is not None
    assert "50s" in again


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
