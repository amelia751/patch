""""Check now" — the same poll the scheduler drives, started by hand.

The console button and Cloud Scheduler must not be two implementations of the
same idea. Scheduler runs the `patchapi-refresh-releases` Cloud Run job; this
starts that identical job, so an impatient operator and the six-hourly tick
exercise one code path and produce one kind of evidence.

Not run inside the request. Cloud Run may reclaim an instance the moment a
response is written, so work started in a background task can vanish after the
API has already told the caller it was accepted. A job execution outlives the
request that asked for it, which is what "durable transport" has to mean here.

Deduplication asks Cloud Run rather than a table. A second trigger while a poll
is in flight is not a second unit of work — the poll already covers the whole
fleet — so an execution that is already running is reported back as the
existing one, and the caller sees `created: false`.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Final

import httpx
from patchapi_control_api.ports import ProviderCheckCommand, ProviderCheckDispatch

JOB_VAR: Final[str] = "PATCHAPI_REFRESH_JOB"
PROJECT_VARS: Final[tuple[str, ...]] = ("GCP_PROJECT", "GOOGLE_CLOUD_PROJECT")
REGION_VAR: Final[str] = "GCP_REGION"

DEFAULT_REGION: Final[str] = "us-central1"
RUN_API: Final[str] = "https://run.googleapis.com/v2"
SCOPE: Final[str] = "https://www.googleapis.com/auth/cloud-platform"

REQUEST_TIMEOUT_SECONDS: Final[float] = 20.0

# Cloud Run reports a finished execution with a completion time. Anything
# without one is still doing the work this request would have asked for.
_RUNNING_STATES: Final[frozenset[str]] = frozenset({"ACTIVE", "STATE_UNSPECIFIED"})


class RefreshJobUnavailableError(RuntimeError):
    """The job could not be reached or refused the request."""


def refresh_job(env: dict[str, str] | None = None) -> str:
    """The configured job name, or empty when this deployment has none."""
    environ = os.environ if env is None else env
    return environ.get(JOB_VAR, "").strip()


def gcp_project(env: dict[str, str] | None = None) -> str:
    environ = os.environ if env is None else env
    for name in PROJECT_VARS:
        value = environ.get(name, "").strip()
        if value:
            return value
    return ""


def gcp_region(env: dict[str, str] | None = None) -> str:
    environ = os.environ if env is None else env
    return environ.get(REGION_VAR, "").strip() or DEFAULT_REGION


def job_path(project: str, region: str, job: str) -> str:
    return f"projects/{project}/locations/{region}/jobs/{job}"


def execution_id(name: str) -> str:
    """The short execution name from a full resource path."""
    return name.rsplit("/", 1)[-1] if name else ""


def _is_running(execution: dict[str, Any]) -> bool:
    if execution.get("completionTime"):
        return False
    reconciling = bool(execution.get("reconciling"))
    state = str(execution.get("state") or "")
    return reconciling or state in _RUNNING_STATES


@dataclass(frozen=True, slots=True)
class CloudRunJobDispatcher:
    """Starts the refresh job, or reports the one already running.

    Holds no credentials of its own: the token comes from the runtime service
    account, which is granted `run.jobs.run` on this one job and nothing else.
    """

    project: str
    region: str
    job: str

    @property
    def resource(self) -> str:
        return job_path(self.project, self.region, self.job)

    async def _token(self) -> str:
        # google-auth is synchronous and refresh does network I/O, so it runs
        # off the loop rather than stalling every other request on this worker.
        def mint() -> str:
            import google.auth
            import google.auth.transport.requests

            credentials, _ = google.auth.default(scopes=[SCOPE])
            credentials.refresh(google.auth.transport.requests.Request())
            return str(credentials.token or "")

        try:
            return await asyncio.to_thread(mint)
        except Exception as exc:
            raise RefreshJobUnavailableError(f"no credentials to run {self.job}: {exc}") from exc

    async def _call(self, client: httpx.AsyncClient, method: str, url: str) -> dict[str, Any]:
        try:
            response = await client.request(method, url)
        except (httpx.HTTPError, OSError) as exc:
            raise RefreshJobUnavailableError(f"Cloud Run did not answer: {exc}") from exc
        if response.status_code >= 400:
            raise RefreshJobUnavailableError(
                f"Cloud Run returned {response.status_code} for {method} {url.rsplit('/', 1)[-1]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RefreshJobUnavailableError("Cloud Run returned a non-JSON body") from exc
        return payload if isinstance(payload, dict) else {}

    async def _running_execution(self, client: httpx.AsyncClient) -> str:
        listed = await self._call(client, "GET", f"{RUN_API}/{self.resource}/executions")
        executions = listed.get("executions")
        if not isinstance(executions, list):
            return ""
        for execution in executions:
            if isinstance(execution, dict) and _is_running(execution):
                return execution_id(str(execution.get("name") or ""))
        return ""

    async def dispatch(self, command: ProviderCheckCommand) -> ProviderCheckDispatch:
        """Start a poll, or acknowledge the one already in flight."""
        token = await self._token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS, headers=headers
        ) as client:
            running = await self._running_execution(client)
            if running:
                return ProviderCheckDispatch(
                    idempotency_key=command.idempotency_key,
                    created=False,
                    run_id=running,
                )
            started = await self._call(client, "POST", f"{RUN_API}/{self.resource}:run")

        # `:run` returns a long-running operation whose response carries the
        # execution. Either shape is accepted because the field that matters is
        # the same in both, and a missing one is reported as no run id rather
        # than as a failure: the job did start.
        response = started.get("response")
        name = str(started.get("name") or "")
        if isinstance(response, dict) and response.get("name"):
            name = str(response["name"])
        return ProviderCheckDispatch(
            idempotency_key=command.idempotency_key,
            created=True,
            run_id=execution_id(name) or None,
        )


def build_dispatcher(env: dict[str, str] | None = None) -> CloudRunJobDispatcher | None:
    """The dispatcher for this deployment, or None when no job is configured.

    Returning None is deliberate. A local checkout has no Cloud Run job, and
    `/readyz` reporting the transport as unwired is the truth; a stub that
    accepted triggers and dropped them would make the button claim success for
    work nobody started.
    """
    job = refresh_job(env)
    project = gcp_project(env)
    if not job or not project:
        return None
    return CloudRunJobDispatcher(project=project, region=gcp_region(env), job=job)


__all__ = [
    "JOB_VAR",
    "CloudRunJobDispatcher",
    "RefreshJobUnavailableError",
    "build_dispatcher",
    "execution_id",
    "gcp_project",
    "gcp_region",
    "job_path",
    "refresh_job",
]
