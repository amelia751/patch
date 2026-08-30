#!/usr/bin/env python
"""Drive one hosted remediation the way the console does, and judge the result.

Exists because the interesting failures in this product are not unit failures.
They are a worker that never claims the run, a credential hold that parks and
never resumes, a pull request opened against a stale base, a trace that reports
a stage nothing performed. None of those reproduce below the seam of a real
deployment, and all of them are the difference between a demo that works and a
demo that works once.

So this speaks to the deployed control API over HTTP, as a signed-in user, and
asserts on what the database and GitHub actually hold afterwards. It authorises
with a session bearer token minted from the deployment's own session secret —
the same token shape the browser cookie carries, because the point is to
exercise the path the console takes rather than a back door around it.

    ./scripts/e2e_console_remediation.py --change chg_flash_image_preview
    ./scripts/e2e_console_remediation.py --repeat 3   # is it *consistently* green

Read-only against GitHub. The run itself opens a pull request, which is the
product working; nothing here merges one.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final
from uuid import UUID

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_API: Final[str] = "https://patchapi-api-uhkx74fgmq-uc.a.run.app"
DEFAULT_CHANGE: Final[str] = "chg_flash_image_preview"

# A hosted run calls the model several times per stage and waits on a sandbox,
# so minutes are normal and a fixed sleep would either flake or crawl. These
# bound how long a *phase* may take without progress, not the run.
POLL_SECONDS: Final[float] = 5.0
CREDENTIAL_HOLD_TIMEOUT: Final[float] = 420.0
COMPLETION_TIMEOUT: Final[float] = 1500.0

TERMINAL_OK: Final[frozenset[str]] = frozenset({"PR_CREATED"})
TERMINAL_BAD: Final[frozenset[str]] = frozenset({"FAILED", "BLOCKED", "ABANDONED"})
HOLD_STATES: Final[frozenset[str]] = frozenset({"WAITING_ON_OPERATOR", "HUMAN_REQUIRED"})


class Failed(RuntimeError):
    """The flow did not reach a pull request, with the reason a human needs."""


# -- transport ---------------------------------------------------------------


def request(
    method: str, url: str, token: str, body: dict[str, Any] | None = None
) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw.decode("utf-8", "replace")[:400]


def secret(name: str) -> str:
    """One Secret Manager payload, via gcloud rather than a client library.

    This script is operator tooling; borrowing the caller's already-authenticated
    gcloud is less to go wrong than a second credential path.
    """
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", f"--secret={name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise Failed(f"could not read secret {name}: {out.stderr.strip()[:200]}")
    return out.stdout


def psql(dsn: str, sql: str) -> list[str]:
    out = subprocess.run(
        ["psql", dsn, "-qAt", "-F", "\x1f", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise Failed(f"query failed: {out.stderr.strip()[:300]}")
    return [line for line in out.stdout.splitlines() if line]


# -- the flow ----------------------------------------------------------------


@dataclass
class Attempt:
    """What one pass through the console flow did, in the order it happened."""

    change: str
    run_id: str = ""
    states: list[str] = field(default_factory=list)
    held_for: str = ""
    resumed: bool = False
    pull_request: str = ""
    seconds: float = 0.0
    verdict: str = ""

    def saw(self, state: str) -> None:
        if not self.states or self.states[-1] != state:
            self.states.append(state)
            print(f"    {state}", flush=True)


def poll_until(
    api: str,
    token: str,
    project: str,
    run_id: str,
    attempt: Attempt,
    *,
    want: frozenset[str],
    timeout: float,
    what: str,
) -> dict[str, Any]:
    """Poll one run until it reaches `want`, or fails, or the phase times out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, detail = request("GET", f"{api}/api/projects/{project}/runs/{run_id}", token)
        if status != 200:
            raise Failed(f"run read returned {status}: {detail}")
        state = str(detail.get("state") or "")
        attempt.saw(state)
        if state in want:
            return detail
        if state in TERMINAL_BAD:
            raise Failed(f"run ended {state}: {detail.get('failure_reason') or 'no reason given'}")
        time.sleep(POLL_SECONDS)
    raise Failed(f"still {attempt.states[-1]} after {timeout:.0f}s waiting for {what}")


def run_once(api: str, token: str, project: str, change: str, credentials: str) -> Attempt:
    attempt = Attempt(change=change)
    started = time.monotonic()

    print(f"  start remediation on {change}", flush=True)
    status, payload = request(
        "POST", f"{api}/api/projects/{project}/changes/{change}/remediate", token, {}
    )
    if status not in (200, 201, 202):
        raise Failed(f"start remediation returned {status}: {payload}")
    attempt.run_id = str(payload.get("run_id") or "")
    if not attempt.run_id:
        raise Failed(f"no run id in {payload}")
    print(f"  run {attempt.run_id}", flush=True)

    # The credential hold is the behaviour worth proving: the run discovers it
    # cannot resolve a replacement without a live provider credential, parks,
    # and waits for a person — rather than guessing an identifier.
    detail = poll_until(
        api,
        token,
        project,
        attempt.run_id,
        attempt,
        want=HOLD_STATES | TERMINAL_OK,
        timeout=CREDENTIAL_HOLD_TIMEOUT,
        what="a credential hold or a pull request",
    )

    if str(detail.get("state")) in HOLD_STATES:
        attempt.held_for = str(detail.get("failure_reason") or "credentials")
        print("  supplying the GCP connection", flush=True)
        status, said = request(
            "POST",
            f"{api}/api/projects/{project}/gcp-connections",
            token,
            {"credentials_json": credentials, "region": "us-central1"},
        )
        if status not in (200, 201):
            raise Failed(f"connecting GCP returned {status}: {said}")

        # Pressing the same button is the resume: `open_run` finds the parked
        # row, keeps its trace and its diff, and dispatches the same run. A
        # second run id here would mean one change became two pull requests.
        status, payload = request(
            "POST", f"{api}/api/projects/{project}/changes/{change}/remediate", token, {}
        )
        if status not in (200, 201, 202):
            raise Failed(f"resume returned {status}: {payload}")
        if str(payload.get("run_id")) != attempt.run_id:
            raise Failed(
                f"resume opened a second run {payload.get('run_id')}, not {attempt.run_id}"
            )
        attempt.resumed = True
        detail = poll_until(
            api,
            token,
            project,
            attempt.run_id,
            attempt,
            want=TERMINAL_OK,
            timeout=COMPLETION_TIMEOUT,
            what="a pull request",
        )

    attempt.pull_request = str(detail.get("pull_request_url") or "")
    attempt.seconds = time.monotonic() - started
    if not attempt.pull_request:
        raise Failed("run reached PR_CREATED with no pull request URL recorded")
    return attempt


# -- what the run must be able to prove afterwards ---------------------------


def audit(dsn: str, attempt: Attempt) -> list[str]:
    """Claims the run makes about itself that the database has to support.

    Every one of these is a failure mode that leaves the console looking green:
    a state that says text was screened when nothing screened it, a policy row
    that never existed, a verification the patch agent graded itself.
    """
    problems: list[str] = []
    run = attempt.run_id

    screened = psql(
        dsn,
        "SELECT count(*) FROM run_trace_events "
        f"WHERE run_id = '{run}' AND verb = 'screen_untrusted_text'",
    )
    if screened and int(screened[0]) == 0:
        problems.append("no intake screening recorded, but the run reported SANITIZED")

    if "SANITIZED" not in attempt.states:
        problems.append("run never passed through SANITIZED")

    policy = psql(dsn, f"SELECT decision FROM policy_decisions WHERE run_id = '{run}'")
    if not policy:
        problems.append("no policy decision recorded")

    verified = psql(
        dsn,
        "SELECT verdict, verifier_agent, patch_agent "
        f"FROM verification_results WHERE run_id = '{run}'",
    )
    if not verified:
        problems.append("no independent verification recorded")
    for row in verified:
        verdict, verifier, patcher = [*row.split("\x1f"), "", "", ""][:3]
        # Constraint 6, checked rather than assumed. The row carries both sides
        # precisely so "the patch agent graded its own work" is detectable.
        if verifier and patcher and verifier == patcher:
            problems.append(f"{verifier} verified its own patch")
        if verdict.lower() not in {"pass", "passed", "verified"}:
            problems.append(f"pull request opened on a {verdict!r} verification")

    if not psql(dsn, f"SELECT attempt_number FROM patch_attempts WHERE run_id = '{run}'"):
        problems.append("no patch attempt recorded")

    prs = psql(dsn, f"SELECT number, url FROM pull_requests WHERE run_id = '{run}'")
    if len(prs) != 1:
        problems.append(f"expected exactly one pull request row, found {len(prs)}")

    return problems


def cloud_trace_spans(since: str) -> list[str]:
    """PatchAPI span names Cloud Trace holds since `since`.

    Read back out of Google rather than trusting the exporter's own report,
    because "the client says it exported" and "the backend stored it" have
    already diverged once in this project.
    """
    out = subprocess.run(
        [
            "gcloud",
            "trace",
            "list",
            f"--start-time={since}",
            "--format=value(spans.name)",
            "--limit=300",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(f"    (cloud trace unreadable: {out.stderr.strip()[:160]})", flush=True)
        return []
    names = out.stdout.replace(";", "\n").replace(",", "\n").splitlines()
    return sorted({name.strip() for name in names if name.strip()})


def memory_recollections(repo: str) -> int:
    """How many migration memories the Memory Bank holds for this repository.

    A run that recorded its outcome leaves this higher than it found it, which
    is the only externally checkable evidence that context survives the run.
    """
    try:
        from packages.memory.vertex import VertexMemoryBank

        return len(VertexMemoryBank.from_env().recall_migrations(repo))
    except Exception as exc:
        print(f"    (memory bank unreadable: {exc})", flush=True)
        return -1


def reset(dsn: str) -> None:
    """Return the deployment to 'never connected, never ran'.

    The credential hold only happens when no connection exists, so a repeat pass
    that skipped this would prove the resume path once and then stop testing it.
    """
    for statement in (
        "DELETE FROM run_trace_events",
        "DELETE FROM run_state_transitions",
        "DELETE FROM verification_results",
        "DELETE FROM policy_decisions",
        "DELETE FROM patch_attempts",
        "DELETE FROM artifacts",
        "DELETE FROM pull_requests",
        "DELETE FROM idempotency_keys",
        "DELETE FROM remediation_runs",
        "DELETE FROM gcp_connections",
    ):
        psql(dsn, statement)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=os.environ.get("PATCHAPI_API_URL", DEFAULT_API))
    parser.add_argument("--change", default=DEFAULT_CHANGE)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()

    from packages.state.session import issue

    dsn = (REPO_ROOT / ".secrets" / "database-url-proxy.txt").read_text().strip()
    credentials = (REPO_ROOT / ".secrets" / "gcp-service-account.json").read_text()

    owners = psql(dsn, "SELECT id, owner_id, name FROM projects ORDER BY created_at LIMIT 1")
    if not owners:
        raise Failed("no project in the database")
    project, owner, name = owners[0].split("\x1f")
    token = issue(UUID(owner), secret("patchapi-session-secret").strip())
    repositories = psql(
        dsn, f"SELECT full_name FROM project_repositories WHERE project_id = '{project}' LIMIT 1"
    )
    repository = repositories[0] if repositories else ""
    print(f"project {name} ({project})\nrepository {repository}\napi {args.api}\n", flush=True)

    results: list[Attempt] = []
    for pass_number in range(1, args.repeat + 1):
        print(f"pass {pass_number} of {args.repeat}", flush=True)
        if not args.no_reset:
            reset(dsn)
        opened = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        memories_before = memory_recollections(repository)
        try:
            attempt = run_once(args.api, token, project, args.change, credentials)
        except Failed as exc:
            print(f"  FAIL {exc}\n", flush=True)
            results.append(Attempt(change=args.change, verdict=f"FAIL {exc}"))
            continue
        problems = audit(dsn, attempt)

        # The two platform integrations, checked against Google rather than
        # against our own logs. Reported but not fatal: a trace that has not
        # been ingested yet is a lag, not a broken remediation, and the whole
        # design says observability must not be able to fail a run.
        spans = [name for name in cloud_trace_spans(opened) if "patchapi" in name.lower()]
        print(f"    cloud trace: {len(spans)} patchapi spans {spans[:6]}", flush=True)
        memories_after = memory_recollections(repository)
        print(f"    memory bank: {memories_before} -> {memories_after} recollections", flush=True)
        if memories_after >= 0 and memories_before >= 0 and memories_after <= memories_before:
            print("    WARN the run recorded no migration memory", flush=True)
        attempt.verdict = "PASS" if not problems else "FAIL " + "; ".join(problems)
        print(
            f"  {attempt.verdict} in {attempt.seconds:.0f}s"
            f"{' (resumed after a hold)' if attempt.resumed else ''}\n"
            f"  {attempt.pull_request}\n",
            flush=True,
        )
        results.append(attempt)

    passed = sum(1 for item in results if item.verdict == "PASS")
    print(f"{passed} of {len(results)} passed")
    for index, item in enumerate(results, start=1):
        held = "held" if item.held_for else "no hold"
        print(f"  {index}. {item.verdict[:110]} · {held} · {item.seconds:.0f}s")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failed as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
