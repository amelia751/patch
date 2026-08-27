"""Starting the work a run describes, without doing it in the request.

A remediation clones a repository, reasons over it several times, builds it,
tests it, has a second agent grade the result, and opens a pull request. That is
minutes, sometimes many. Three places it must therefore not happen:

*Not in the HTTP request.* Cloud Run may reclaim an instance as soon as a
response is written, so a background task started during a request can be killed
after the console has already been told the run began.

*Not in a Pub/Sub push handler.* A push subscription's ack deadline caps at ten
minutes and cannot be raised. Past it Pub/Sub does not fail the delivery — it
redelivers, so a twelve-minute remediation becomes two remediations racing to
open the same pull request.

*Not on a shared web instance at all.* `patchapi-agents` serves change
intelligence at concurrency one; a remediation parked there stalls the lane that
fills the inbox.

So the API writes the run row and starts a job, which is a unit of work Cloud Run
will let run for hours and which outlives whatever asked for it. Locally there is
no Cloud Run, and a subprocess is the honest equivalent: same entry point, same
arguments, same durability guarantee relative to the thing that spawned it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

import httpx

from packages.state.provider_check import (
    REQUEST_TIMEOUT_SECONDS,
    RUN_API,
    SCOPE,
    execution_id,
    gcp_project,
    gcp_region,
    job_path,
)

log = logging.getLogger(__name__)

JOB_VAR: Final[str] = "PATCHAPI_REMEDIATION_JOB"
LOCAL_VAR: Final[str] = "PATCHAPI_REMEDIATION_LOCAL"

ENTRY_POINT: Final[str] = "patchapi-remediate"

# How long the console sits on the dispatch line before we say Cloud Run is
# still starting the container. Shorter than this and a fast claim looks like
# we invented a stall. Longer and the operator stares at one sentence for a
# minute, which is the complaint this exists to answer.
PROVISION_AFTER_SECONDS: Final[float] = 8.0
PROVISION_EVERY_SECONDS: Final[float] = 15.0


class RemediationUnavailableError(RuntimeError):
    """Nothing could be asked to run this remediation."""


@runtime_checkable
class RemediationDispatcher(Protocol):
    """Starts one remediation and returns a handle to whatever is running it."""

    async def dispatch(self, run_id: str) -> str: ...

    @property
    def transport(self) -> str: ...


@dataclass(frozen=True, slots=True)
class CloudRunRemediationDispatcher:
    """Runs the remediation job, once per run id.

    Holds no credentials: the token comes from the API's runtime service account,
    which is granted `run.jobs.run` on this one job and nothing else.

    Unlike the provider poll, a running execution is not a reason to skip. Two
    remediations are two different pieces of work; what stops a change being
    patched twice is the unique run row, decided before this is ever called.
    """

    project: str
    region: str
    job: str

    @property
    def transport(self) -> str:
        return f"cloud-run-job:{self.job}"

    @property
    def resource(self) -> str:
        return job_path(self.project, self.region, self.job)

    async def dispatch(self, run_id: str) -> str:
        token = await _token(self.job)
        # The job image has no run id baked in; the override is what makes one
        # deployed job able to serve every run.
        body: dict[str, Any] = {
            "overrides": {
                "containerOverrides": [{"args": ["--run-id", run_id]}],
                "taskCount": 1,
            }
        }
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
            try:
                response = await client.post(f"{RUN_API}/{self.resource}:run", json=body)
            except (httpx.HTTPError, OSError) as exc:
                raise RemediationUnavailableError(f"Cloud Run did not answer: {exc}") from exc
            if response.status_code >= 400:
                raise RemediationUnavailableError(
                    f"Cloud Run returned {response.status_code} starting {self.job}: "
                    f"{_why(response)}"
                )
            payload = response.json() if response.content else {}

        name = str(payload.get("name") or "")
        nested = payload.get("response")
        if isinstance(nested, dict) and nested.get("name"):
            name = str(nested["name"])
        started = execution_id(name)
        log.info("dispatched run %s to %s (%s)", run_id, self.job, started or "unnamed")
        return started


@dataclass(frozen=True, slots=True)
class LocalProcessDispatcher:
    """Runs the remediation in a detached child process.

    For a local checkout, where there is no Cloud Run job to trigger. The child
    is detached deliberately: a remediation must not die because the dev server
    reloaded, which is the same property the Cloud Run job has relative to the
    request that started it.
    """

    repo_root: Path
    log_dir: Path

    @property
    def transport(self) -> str:
        return "local-process"

    async def dispatch(self, run_id: str) -> str:
        command = _local_command()
        if command is None:
            raise RemediationUnavailableError(
                f"neither {ENTRY_POINT} nor uv is on PATH; cannot run a remediation locally"
            )
        self.log_dir.mkdir(parents=True, exist_ok=True)
        output = self.log_dir / f"run-{run_id}.log"

        def spawn() -> int:
            with output.open("ab") as sink:
                process = subprocess.Popen(
                    [*command, "--run-id", run_id],
                    cwd=self.repo_root,
                    stdout=sink,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            return process.pid

        pid = await asyncio.to_thread(spawn)
        log.info("dispatched run %s to local pid %d (%s)", run_id, pid, output)
        return f"pid-{pid}"


def _local_command() -> list[str] | None:
    installed = shutil.which(ENTRY_POINT)
    if installed:
        return [installed]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", ENTRY_POINT]
    return [sys.executable, "-m", "patchapi_remediation.entrypoint"]


def _why(response: httpx.Response) -> str:
    """Cloud Run's own explanation, which the status code alone does not give.

    A bare 403 reads as "the job is missing or the deployment is broken" and
    sends whoever is looking at IAM in general. Cloud Run says which permission
    was denied, and that sentence is the difference between a guess and a fix,
    so it is carried through to the console rather than dropped here.
    """
    try:
        error = response.json().get("error", {})
        message = str(error.get("message", "")).strip()
    except (ValueError, AttributeError):
        message = ""
    return message or response.text.strip()[:300] or "no reason given"


async def _token(job: str) -> str:
    def mint() -> str:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(scopes=[SCOPE])
        credentials.refresh(google.auth.transport.requests.Request())
        return str(credentials.token or "")

    try:
        return await asyncio.to_thread(mint)
    except Exception as exc:
        raise RemediationUnavailableError(f"no credentials to run {job}: {exc}") from exc


def build_dispatcher(
    env: dict[str, str] | None = None, *, repo_root: Path | None = None
) -> RemediationDispatcher | None:
    """The dispatcher for this deployment, or None when nothing can run a job.

    None is a legitimate answer and is reported as such. A console that accepted
    "Start remediation" and dropped it would claim a run nobody is performing,
    which is worse than a button that says the lane is not wired.
    """
    environ = os.environ if env is None else env
    job = environ.get(JOB_VAR, "").strip()
    project = gcp_project(env)
    if job and project:
        return CloudRunRemediationDispatcher(project=project, region=gcp_region(env), job=job)

    if environ.get(LOCAL_VAR, "").strip().lower() in {"1", "true", "yes"}:
        root = repo_root or Path(__file__).resolve().parents[2]
        return LocalProcessDispatcher(repo_root=root, log_dir=root / ".runs")
    return None


def provisioning_note(
    *,
    state: str,
    traces: list[dict[str, Any]],
    started_at: datetime | None,
    now: datetime | None = None,
) -> str | None:
    """A worklog line for the Cloud Run wait, or None if one should not be written.

    ADK is not running during this stretch. `run_live` is bidirectional audio
    and is the wrong surface. The gap the console sees after dispatch is job
    scheduling (often a minute-plus on a cold image). Saying that on the poll
    is the honest stream, not a model token.
    """
    if state != "RECEIVED":
        return None
    if any("Remediator claimed" in str(row.get("body") or "") for row in traces):
        return None
    if started_at is None:
        return None
    clock = now or datetime.now(UTC)
    start = started_at if started_at.tzinfo else started_at.replace(tzinfo=UTC)
    elapsed = (clock - start).total_seconds()
    if elapsed < PROVISION_AFTER_SECONDS:
        return None
    last = traces[-1] if traces else None
    if last and "Cloud Run is still starting the remediator" in str(last.get("body") or ""):
        occurred = last.get("occurred_at")
        if isinstance(occurred, datetime):
            when = occurred if occurred.tzinfo else occurred.replace(tzinfo=UTC)
            if (clock - when).total_seconds() < PROVISION_EVERY_SECONDS:
                return None
    return (
        f"Cloud Run is still starting the remediator ({int(elapsed)}s). "
        "The agent has not started. This wait is job scheduling, not ADK."
    )


__all__ = [
    "ENTRY_POINT",
    "JOB_VAR",
    "LOCAL_VAR",
    "CloudRunRemediationDispatcher",
    "LocalProcessDispatcher",
    "RemediationDispatcher",
    "RemediationUnavailableError",
    "build_dispatcher",
    "provisioning_note",
]
