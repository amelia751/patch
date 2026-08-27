"""The console starts a remediator only when this deployment named one."""

from __future__ import annotations

from packages.state.run_dispatch import (
    CloudRunRemediationDispatcher,
    LocalProcessDispatcher,
    build_dispatcher,
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
