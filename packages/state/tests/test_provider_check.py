"""The "Check now" button: starts the poll, or points at the running one."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from patchapi_control_api.ports import ProviderCheckCommand

from packages.state.provider_check import (
    CloudRunJobDispatcher,
    RefreshJobUnavailableError,
    build_dispatcher,
    execution_id,
    job_path,
)

KEY = "a" * 64
JOB = "patchapi-refresh-releases"
PROJECT = "patch-505223"
REGION = "us-central1"

RESOURCE = job_path(PROJECT, REGION, JOB)
RUNNING = f"{RESOURCE}/executions/{JOB}-running"
STARTED = f"{RESOURCE}/executions/{JOB}-new"


def command() -> ProviderCheckCommand:
    return ProviderCheckCommand(
        provider_id="google", since=None, requested_by="dashboard", idempotency_key=KEY
    )


def dispatcher(monkeypatch: pytest.MonkeyPatch, handler: Any) -> CloudRunJobDispatcher:
    """A dispatcher whose token is stubbed and whose HTTP is a transport double."""
    subject = CloudRunJobDispatcher(project=PROJECT, region=REGION, job=JOB)

    async def token(self: CloudRunJobDispatcher) -> str:
        return "test-token"

    monkeypatch.setattr(CloudRunJobDispatcher, "_token", token)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def build(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", build)
    return subject


def _executions(payload: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"executions": payload})


async def test_an_idle_job_is_started(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return _executions([{"name": RUNNING, "completionTime": "2026-08-22T00:00:00Z"}])
        return httpx.Response(200, json={"response": {"name": STARTED}})

    result = await dispatcher(monkeypatch, handler).dispatch(command())

    assert (result.created, result.run_id) == (True, f"{JOB}-new")
    assert result.idempotency_key == KEY
    assert calls[-1][0] == "POST"


async def test_a_running_poll_is_not_started_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second click while the fleet-wide poll is in flight is not more work."""
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return _executions([{"name": RUNNING, "state": "ACTIVE"}])

    result = await dispatcher(monkeypatch, handler).dispatch(command())

    assert (result.created, result.run_id) == (False, f"{JOB}-running")
    assert "POST" not in methods


async def test_an_execution_still_reconciling_counts_as_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _executions([{"name": RUNNING, "reconciling": True}])

    result = await dispatcher(monkeypatch, handler).dispatch(command())

    assert result.created is False


async def test_a_refused_run_is_reported_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 403 must not read as "started". The caller has to learn it did not run."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _executions([])
        return httpx.Response(403, json={"error": {"message": "denied"}})

    with pytest.raises(RefreshJobUnavailableError):
        await dispatcher(monkeypatch, handler).dispatch(command())


async def test_an_unreachable_api_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(RefreshJobUnavailableError):
        await dispatcher(monkeypatch, handler).dispatch(command())


async def test_a_started_job_without_an_execution_name_still_reports_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The job ran. A missing name costs the run id, not the acknowledgement."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _executions([])
        return httpx.Response(200, json={})

    result = await dispatcher(monkeypatch, handler).dispatch(command())

    assert (result.created, result.run_id) == (True, None)


def test_no_dispatcher_without_a_job_to_run() -> None:
    """Local checkouts have no Cloud Run job, and must not pretend otherwise."""
    assert build_dispatcher({}) is None
    assert build_dispatcher({"PATCHAPI_REFRESH_JOB": JOB}) is None
    assert build_dispatcher({"GCP_PROJECT": PROJECT}) is None


def test_the_dispatcher_targets_the_configured_job() -> None:
    built = build_dispatcher({"PATCHAPI_REFRESH_JOB": JOB, "GOOGLE_CLOUD_PROJECT": PROJECT})
    assert built is not None
    assert built.resource == RESOURCE
    assert execution_id(RUNNING) == f"{JOB}-running"
