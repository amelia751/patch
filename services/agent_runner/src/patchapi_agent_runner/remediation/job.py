"""One remediation, start to finish, recorded as it happens.

This is the durable half of the patch loop. `scripts/smoke_patch_loop.py` already
proved the loop works: copy a tree into a sandbox, seed a manifest, scan, clear
policy, patch, build, test, verify independently, open a pull request. What it
could not do was be a product — it took a pinned fixture, wrote nothing down, and
lived exactly as long as a terminal.

The differences here are the ones that make it a product rather than a
demonstration:

*The tree is a real repository at a real commit*, fetched by the job and pushed
into the sandbox, never cloned by the sandbox itself.

*The change comes from the corpus*, not a notice feed. The run acts on the
adjudicated record the operator saw on the card.

*Every transition is written down while the run is in progress*, so a console
can follow a run it did not start and a job that dies leaves a truthful record
of how far it got.

*Nothing is invented when the repository is unfamiliar.* A repository whose
build and test commands cannot be established stops with that sentence, which is
a more useful outcome than a green run of a command that tested nothing.
"""

from __future__ import annotations

import difflib
import logging
import os
import shlex
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from agents import live_check
from agents.adk import session_hold_reason
from agents.command_allowlist import CommandNotAllowedError, match_command
from agents.context import RunContext
from agents.journal import RunJournal
from agents.orchestrator import Orchestrator, VerticalSlice
from agents.tools.credentials import RuntimeCredentialsInventory
from agents.trace import ToolTrace
from packages.schemas.run_state import RunState, is_terminal
from packages.state import remediation
from patchapi_agent_runner.config import feed_dir, repo_root
from patchapi_agent_runner.remediation import checkout, manifest, slices
from sandbox.session import SandboxUnavailableError, open_session

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

log = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_FAILED: Final[int] = 1
EXIT_UNKNOWN_RUN: Final[int] = 2

ACTOR: Final[str] = "remediation-job"

# gVisor, no service-account token, deny-all egress. Chosen deliberately over a
# local temp directory: this lane executes code a model wrote, and the isolation
# is the reason it is allowed to run at all. A cluster that cannot be reached
# stops the run rather than quietly downgrading the boundary.
#
# `PATCHAPI_SANDBOX` may name `local` instead, and only a developer's own
# checkout should: it is the same temp-workspace transport the roadmap allows
# for the early phases, and it is what makes the local dispatcher able to run a
# real remediation on a machine with no cluster. Deployments leave it unset, so
# no hosted run can lose the boundary by forgetting a variable.
SANDBOX_ENV_VAR: Final[str] = "PATCHAPI_SANDBOX"


def sandbox_kind() -> str:
    """Which sandbox transport this process runs patches in."""
    requested = os.environ.get(SANDBOX_ENV_VAR, "").strip().lower()
    return requested if requested in {"local", "gke"} else "gke"


# The baseline is a diagnostic, not the run. A repository whose checks take
# longer than this is one whose build the patch loop would time out on anyway.
BASELINE_TIMEOUT: Final[float] = 300.0

# Enough of a build log to see what failed, bounded so a runaway command cannot
# turn one attempt's evidence into the largest row in the database.
MAX_ARTIFACT_CHARS: Final[int] = 20_000

_RUN_SQL: Final[str] = """
SELECT
    r.id, r.state::text AS state, r.repository, r.base_sha, r.project_id,
    r.change_event_id, r.attempt_budget,
    ce.external_id, ce.affected_identifiers
FROM remediation_runs r
JOIN change_events ce ON ce.id = r.change_event_id
WHERE r.id = $1
"""

# Where to patch, and the line that shows how the identifier is bound. Runtime
# files first: a match in a README is a true finding and not a migration.
_ENTRYPOINT_SQL: Final[str] = """
SELECT u.file_path, u.excerpt
FROM provider_usages u
WHERE u.repository = $1
  AND u.retired_at IS NULL
  AND u.identifier = ANY ($2::text[])
ORDER BY (u.usage_kind = 'runtime_source') DESC, u.confidence DESC, u.file_path
LIMIT 1
"""


@dataclass(frozen=True, slots=True)
class RunRow:
    run_id: str
    state: RunState
    repository: str
    base_sha: str
    project_id: UUID
    change_event_id: UUID
    external_id: str
    identifiers: list[str]


async def _load(connection: asyncpg.Connection, run_id: str) -> RunRow | None:
    row = await connection.fetchrow(_RUN_SQL, UUID(run_id))
    if row is None:
        return None
    return RunRow(
        run_id=str(row["id"]),
        state=RunState(row["state"]),
        repository=row["repository"],
        base_sha=row["base_sha"],
        project_id=row["project_id"],
        change_event_id=row["change_event_id"],
        external_id=row["external_id"],
        identifiers=list(row["affected_identifiers"] or []),
    )


async def _stop(pool: asyncpg.Pool, run_id: str, reason: str) -> int:
    """End a run that never reached the patch loop, saying why in one sentence."""
    log.error("run %s stopped: %s", run_id, reason)
    async with pool.acquire() as connection:
        await remediation.append_trace(
            connection, run_id, state=RunState.RECEIVED, kind="narration", body=reason
        )
        await remediation.advance(connection, run_id, RunState.FAILED, actor=ACTOR, reason=reason)
    return EXIT_FAILED


async def abandon(pool: asyncpg.Pool, run_id: str, exc: BaseException) -> None:
    """Record that the remediator died before this run reached a terminal state.

    Without this the row keeps whatever state it had when the process went, and
    a crash during setup leaves it on RECEIVED — where the console reads
    "waiting for the remediator to claim this run" and waits for good. A run
    nobody is performing has to say so.
    """
    reason = (
        f"The remediator stopped on an unexpected {type(exc).__name__} and this run did "
        f"not finish: {exc}"
    )
    try:
        await _stop(pool, run_id, reason)
    except Exception:  # pragma: no cover - the original error is what matters
        log.exception("run %s could not be marked failed", run_id)


async def execute(pool: asyncpg.Pool, run_id: str) -> int:
    """Run one remediation to a terminal state."""
    async with pool.acquire() as connection:
        row = await _load(connection, run_id)
        if row is None:
            log.error("no run %s", run_id)
            return EXIT_UNKNOWN_RUN
        if is_terminal(row.state):
            # A restart resets the row to RECEIVED first, so a terminal state
            # here means this execution is a duplicate of one that finished.
            log.info("run %s already ended at %s", run_id, row.state)
            return EXIT_OK
        hint = await connection.fetchrow(_ENTRYPOINT_SQL, row.repository, row.identifiers)
        try:
            change = await manifest.load(connection, row.change_event_id)
        except manifest.ManifestUnavailableError as exc:
            return await _stop(pool, run_id, str(exc))

    if not row.base_sha:
        return await _stop(
            pool,
            run_id,
            f"{row.repository} has no indexed commit, so there is no tree to patch. "
            "Index the repository, then start the run again.",
        )

    scratch = Path(tempfile.mkdtemp(prefix=f"patchapi-run-{run_id[:8]}-"))
    try:
        return await _run(pool, row, change, scratch, hint)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


async def _run(
    pool: asyncpg.Pool,
    row: RunRow,
    change: Any,
    scratch: Path,
    hint: Any,
) -> int:
    journal = RunJournal(run_id=row.run_id)
    trace = ToolTrace(run_id=row.run_id)
    recorder = _recorder(pool, row.run_id, journal, trace)
    session: Any = None
    kind = sandbox_kind()

    resume = await _resume_state(pool, row)
    inventory = await _credentials(pool, row.project_id)

    # The pump has to start before the clone. Held until after sandbox +
    # baseline, the console sits on an empty log for the slowest minute of
    # the run — the part the operator is watching.
    async with recorder:
        if resume.resumed:
            # The operator is watching for one thing: that pressing Continue
            # continued. Say so before the re-clone, because everything the
            # setup writes next is a line this run's worklog already has.
            recorder.narrate(
                RunState.RECEIVED,
                f"Continuing this run. {resume.describe(inventory)} "
                f"Re-establishing the sandbox at {row.base_sha[:12]} — the worklog above "
                "is the same run, not a new one. "
                + (
                    f"The {resume.hold.get('agent', 'patch')} agent's turn is resumed at "
                    f"`{resume.hold.get('tool', '')}` rather than restarted."
                    if resume.hold
                    else ""
                ),
            )
        else:
            recorder.narrate(
                RunState.RECEIVED,
                f"Remediator claimed {row.repository} at {row.base_sha[:12]}. "
                "Fetching the pinned tree.",
            )
        await recorder.flush()

        try:
            source = checkout.fetch(row.repository, row.base_sha, scratch / "tree")
        except checkout.CheckoutError as exc:
            return await _stop(pool, row.run_id, f"Could not read the repository: {exc}")

        recorder.narrate(
            RunState.RECEIVED,
            f"Fetched {row.repository} at {row.base_sha[:12]}.",
        )
        await recorder.flush()

        decision = slices.decide(
            repository=row.repository,
            change_id=row.external_id,
            identifiers=row.identifiers,
            tree=source.tree,
            entrypoint="" if hint is None else str(hint["file_path"]),
            excerpt="" if hint is None else str(hint["excerpt"] or ""),
        )
        if decision.slice_ is None:
            return await _stop(pool, row.run_id, decision.reason)
        slice_ = decision.slice_

        manifest_dir = scratch / "manifest"
        manifest_path = manifest.write(change, manifest_dir)

        recorder.narrate(
            RunState.RECEIVED,
            f"Allocating an isolated {kind} sandbox.",
        )
        await recorder.flush()

        try:
            session = open_session(
                kind, run_id=f"run-{row.run_id[:12]}", scratch_root=scratch / "sandbox"
            )
        except (SandboxUnavailableError, ImportError, TypeError) as exc:
            return await _stop(
                pool,
                row.run_id,
                f"The isolated sandbox is unavailable, so no generated code was run: {exc}",
            )

        try:
            staged = checkout.stage(session, source)
            recorder.narrate(
                RunState.RECEIVED,
                f"Staged {staged} files from {row.repository} at {row.base_sha[:12]} into an "
                f"isolated {kind} sandbox. "
                + (
                    (
                        f"Local checks for this change: `{slice_.build_command}`."
                        if slice_.build_command
                        else "This change has no local repository check; proof is a live resolve."
                    )
                    if decision.pinned
                    else f"Detected `{slice_.build_command}` and `{slice_.test_command}`."
                ),
            )
            await recorder.flush()

            baseline = _baseline(session, slice_)
            recorder.narrate(RunState.RECEIVED, baseline.narration)
            await recorder.flush()

            # A hold that already produced a patch keeps it: the tree the
            # operator was shown is the tree the run continues from, and asking
            # the model to derive it a second time would be a new patch, not a
            # continuation. A hold inside an unfinished turn is different — the
            # agent is answered and carries on, so the tree is its to write.
            skip_patch = False
            if resume.resumed and resume.diff and not resume.hold:
                applied = session.apply_unified_diff(resume.diff)
                if getattr(applied, "exit_code", 1) == 0:
                    skip_patch = True
                    recorder.narrate(
                        RunState.RECEIVED,
                        "Restored the patched tree from before the hold. The patch loop "
                        "does not start over; the run picks up at its checks.",
                    )
                    await recorder.flush()

            context = RunContext(
                run_id=row.run_id,
                repo_root=repo_root(),
                feed_dir=feed_dir(),
                workspace_root=(
                    Path(session.working_dir) if isinstance(session.working_dir, Path) else None
                ),
                sandbox=session,
                project_id=row.project_id,
                credentials_inventory=inventory,
                live_credentials=await _live_credentials(pool, row.project_id),
                agent_hold=resume.hold,
            )
            async with pool.acquire() as connection:
                attempt_id, attempt_number = await remediation.begin_attempt(
                    connection,
                    row.run_id,
                    patch_agent="patch",
                    prompt_version=slice_.skill_id,
                    sandbox_ref=f"{kind}:{getattr(session, 'name', row.run_id)}",
                )

            # Opened before the orchestrator so the trace can say which try at
            # this run it is recording. Two executions of one run are otherwise
            # indistinguishable in the backend.
            orchestrator = Orchestrator(context, trace, journal, attempt=attempt_number)

            # Impact and policy stay deterministic: whether a repository is
            # affected, and which files, is the scanner's answer, and a status
            # a model can talk itself out of is not a status. The model's work
            # here is the patch, which is graded independently afterwards.
            result = await orchestrator.run_vertical_slice(
                slice_,
                base_sha=row.base_sha,
                static_manifest=manifest_path,
                deterministic=False,
                setup_deterministic=True,
                skip_patch=skip_patch,
            )
            await _persist(
                pool, row, slice_, context, result, source, session, attempt_id, baseline=baseline
            )
            await _remember_hold(pool, row, result, recorder)
            log.info("run %s ended %s: %s", row.run_id, result.state, result.detail)
            if result.state in {RunState.PR_CREATED, RunState.WAITING_ON_OPERATOR}:
                return EXIT_OK
            if not is_terminal(result.state):
                # The orchestrator owes every run an ending. If one gets away
                # without it, the row is the only thing left holding a state
                # nothing will move, so it is closed here rather than left to
                # read as in-flight for good.
                return await _stop(
                    pool,
                    row.run_id,
                    f"The run stopped in {result.state} without reaching an ending. "
                    f"{result.detail}".strip(),
                )
            return EXIT_FAILED
        finally:
            session.close()


@dataclass(frozen=True, slots=True)
class ResumeState:
    """Whether this execution is continuing a run that paused for the operator.

    A Cloud Run job cannot survive an operator hold: it exits, and Continue
    starts a new execution of the same run row. That execution has to know it
    is a continuation, because the difference between continuing and restarting
    is not cosmetic — it decides whether the model is asked to patch a second
    time and whether the console tells the operator their click worked.
    """

    resumed: bool
    diff: str = ""
    parked: dict[str, str] | None = None

    @property
    def hold(self) -> dict[str, str]:
        """The parked agent turn, or an empty mapping when nothing is parked."""
        return dict(self.parked or {})

    def describe(self, inventory: Any) -> str:
        """One sentence naming what the operator supplied, from the vault's own view."""
        if not self.resumed:
            return ""
        project = str(getattr(inventory, "gcp_project_id", "") or "")
        names = tuple(getattr(inventory, "secret_names", ()) or ())
        if getattr(inventory, "gcp_connected", False) and project:
            supplied = f"GCP project {project} is connected."
        elif getattr(inventory, "gcp_connected", False):
            supplied = "A GCP connection is stored."
        elif names:
            supplied = f"{len(names)} runtime secret name(s) are configured."
        else:
            # Fail honest: continuing without visible credentials will park
            # again, and saying otherwise would make the next hold look broken.
            supplied = "No new credential is visible to this project yet."
        return supplied


async def _remember_hold(pool: asyncpg.Pool, row: RunRow, result: Any, recorder: Any) -> None:
    """Write down the parked agent turn, or clear a pointer that no longer holds.

    Called after every slice, not only after a park: a run that moved past its
    hold must not leave a pointer behind for the next execution to answer.
    """
    parked = getattr(result, "parked_turn", None)
    hold = (
        {
            "agent": str(parked.agent),
            "session_id": parked.session_id,
            "call_id": parked.pending_call_id,
            "tool": str(parked.long_running_tool or ""),
        }
        if parked is not None
        else None
    )
    try:
        async with pool.acquire() as connection:
            await remediation.record_agent_hold(connection, row.run_id, hold)
    except Exception as exc:
        # The run's state is already written. Losing the pointer costs a replay
        # of the turn on Continue, not correctness, so it is logged and the
        # console is told rather than failing a run that reached its hold.
        log.warning("run %s could not record its agent hold: %s", row.run_id, exc)
        return
    if hold:
        recorder.narrate(
            RunState.WAITING_ON_OPERATOR,
            f"The {hold['agent']} agent's turn is held open at `{hold['tool']}`. "
            "Continue answers that call, so the files it has already read and the "
            "commands it has already run stay in context.",
        )
        await recorder.flush()
        return
    if getattr(result, "parked_mid_turn_without_a_pointer", False):
        recorder.narrate(
            RunState.WAITING_ON_OPERATOR,
            "An agent turn stopped mid-way and could not be held open "
            f"({session_hold_reason() or 'the session was not stored'}). Continue will "
            "start that turn again rather than answering it.",
        )
        await recorder.flush()


async def _resume_state(pool: asyncpg.Pool, row: RunRow) -> ResumeState:
    """Read whether Continue opened this execution, and the tree it left behind."""
    try:
        async with pool.acquire() as connection:
            reason = await connection.fetchval(
                """
                SELECT reason FROM run_state_transitions
                WHERE run_id = $1
                ORDER BY sequence DESC LIMIT 1
                """,
                UUID(row.run_id),
            )
            if str(reason or "") != remediation.RESUMED_REASON:
                return ResumeState(resumed=False)
            diff = await connection.fetchval(
                """
                SELECT body FROM artifacts
                WHERE run_id = $1 AND kind = 'diff' AND COALESCE(body, '') <> ''
                ORDER BY created_at DESC LIMIT 1
                """,
                UUID(row.run_id),
            )
            hold = await remediation.read_agent_hold(connection, row.run_id)
    except Exception as exc:
        # Not knowing means treating this as a fresh execution, which is the
        # safe direction: it patches again rather than skipping the patch.
        log.warning("run %s could not read its resume state: %s", row.run_id, exc)
        return ResumeState(resumed=False)
    return ResumeState(resumed=True, diff=str(diff or ""), parked=hold)


@dataclass(frozen=True, slots=True)
class Baseline:
    """Whether the repository's own checks passed before anything was patched."""

    build_exit_code: int
    test_exit_code: int
    output: str
    command: str

    @property
    def green(self) -> bool:
        return self.build_exit_code == 0 and self.test_exit_code == 0

    @property
    def narration(self) -> str:
        if not self.command:
            return (
                "This change has no local repository check; proof is the binding "
                "rewrite and a live provider resolve."
            )
        if self.green:
            return f"Baseline checks pass at this commit: `{self.command}`."
        return (
            f"Baseline checks already fail at this commit before any patch "
            f"(`{self.command}`). A patch is expected to turn them green; if they "
            f"still fail afterwards the failure is not attributed to the patch."
        )


def _baseline(session: Any, slice_: VerticalSlice) -> Baseline:
    """Run the repository's checks on the unmodified tree.

    Without this a run cannot tell "the patch broke the build" from "the build
    was already broken", and it reports the second as the first. That matters
    most in the case this product exists for: a retirement gate that fails
    precisely because the retired identifier is still in the tree, which is the
    failure the patch is supposed to clear.

    An empty command is not a green check. It means this change has no local
    gate (Imagen on storygen: generate.py reads MODEL, not IMAGE_MODEL).
    """
    if not (slice_.build_command or "").strip():
        return Baseline(0, 0, "no local repository check is pinned for this change\n", "")
    build = _check(session, slice_.build_command)
    test = (
        _check(session, slice_.test_command)
        if slice_.test_command and slice_.test_command != slice_.build_command
        else build
    )
    return Baseline(
        build_exit_code=build[0],
        test_exit_code=test[0],
        output="\n".join(part for part in (build[1], "" if test is build else test[1]) if part)[
            :MAX_ARTIFACT_CHARS
        ],
        command=slice_.build_command,
    )


def _check(session: Any, command: str) -> tuple[int, str]:
    """Run one repository check through the allowlist the patch loop uses.

    Going through `match_command` matters: the baseline must not be able to run
    something the patch stage would have refused. A command this run's own tools
    would reject is reported as unrunnable rather than executed with a wider
    reach than the agents get.
    """
    try:
        allowed = match_command(shlex.split(command))
    except (CommandNotAllowedError, ValueError) as exc:
        return 0, f"$ {command}\n(not run: {exc})"

    result = session.execute(list(allowed.argv), min(allowed.timeout_seconds, BASELINE_TIMEOUT))
    body = "\n".join(
        part
        for part in (
            f"$ {' '.join(allowed.argv)}",
            (result.stdout or "").strip(),
            (result.stderr or "").strip(),
            f"(exit {result.exit_code})",
        )
        if part
    )
    return result.exit_code, body


_CREDENTIALS_SQL: Final[str] = """
SELECT
    COALESCE(
        (
            SELECT array_agg(DISTINCT s.secret_name ORDER BY s.secret_name)
            FROM project_secrets s
            WHERE s.project_id = $1 AND s.status = 'configured'
        ),
        '{}'
    )                                                       AS secret_names,
    EXISTS (SELECT 1 FROM gcp_connections g WHERE g.project_id = $1) AS gcp_connected,
    (
        SELECT g.gcp_project_id FROM gcp_connections g
        WHERE g.project_id = $1 ORDER BY g.updated_at DESC LIMIT 1
    )                                                       AS gcp_project_id
"""


async def _credentials(pool: asyncpg.Pool, project_id: UUID) -> RuntimeCredentialsInventory:
    """What this project has told PatchAPI it holds — names only, never values.

    Without this the run has no view at all, and `resolve_inventory` is right to
    treat every name as missing: an unbound view means "unknown", and unknown
    has to read as absent. The effect was that a run paused for a key even when
    the operator had already supplied one, so the pause said nothing about the
    project. Reading the vault's *names* here is what makes the pause a fact.
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(_CREDENTIALS_SQL, project_id)
    names = tuple(row["secret_names"] or ())
    gcp_connected = bool(row["gcp_connected"])
    cloud_run_env_names: tuple[str, ...] = ()
    if gcp_connected:
        cloud_run_env_names = await _cloud_run_env_names(pool, project_id)
    return RuntimeCredentialsInventory(
        bound=True,
        secret_names=names,
        gcp_connected=gcp_connected,
        cloud_run_env_names=cloud_run_env_names,
        gcp_project_id=row["gcp_project_id"],
        detail=(
            f"{len(names)} runtime secret name(s) configured for this project"
            if names
            else "no runtime secrets are configured for this project"
        ),
    )


async def _live_credentials(
    pool: asyncpg.Pool, project_id: UUID
) -> Callable[[tuple[str, ...]], dict[str, str]]:
    """A broker for the live-verification step, and only that step.

    Values are read here, before the agents start, so the vault is never called
    from inside an orchestrator turn and the only thing crossing into agent code
    is a closure over names the sandbox allowlist already permits. What it
    returns becomes the environment of one command; it is never recorded, never
    handed to a model, and never written to evidence.

    Missing names are absent from the mapping rather than empty strings, which
    is what lets the live check say "not asked" instead of failing a patch for a
    credential the project never had.
    """
    from packages.state.gcp_connections import reveal_latest_connection
    from packages.state.gcp_viewer import broker_live_env
    from packages.state.secret_manager import GoogleSecretVault
    from packages.state.secrets import reveal_secret

    vault = GoogleSecretVault(os.environ.get("GCP_PROJECT", ""))
    resolved: dict[str, str] = {}
    for name in live_check.CREDENTIAL_NAMES:
        try:
            value = await reveal_secret(pool, project_id, secret_name=name, vault=vault)
        except Exception as exc:
            log.warning("could not read %s for project %s: %s", name, project_id, exc)
            continue
        if value:
            resolved[name] = value

    if not any(name in resolved for name in live_check.CREDENTIAL_NAMES):
        try:
            loaded = await reveal_latest_connection(pool, project_id, vault)
        except Exception as exc:
            log.warning("could not reveal viewer connection for %s: %s", project_id, exc)
            loaded = None
        if loaded is not None:
            meta, payload = loaded
            try:
                env = broker_live_env(
                    payload,
                    gcp_project_id=str(meta["gcp_project_id"]),
                    region=str(meta["default_region"]),
                )
            except Exception as exc:
                log.warning("could not broker Cloud Run live env for %s: %s", project_id, exc)
                env = {}
            for name in live_check.CREDENTIAL_NAMES:
                value = env.get(name)
                if value and name not in resolved:
                    resolved[name] = value

    def broker(requested: tuple[str, ...]) -> dict[str, str]:
        return {name: value for name, value in resolved.items() if name in requested}

    return broker


async def _cloud_run_env_names(pool: asyncpg.Pool, project_id: UUID) -> tuple[str, ...]:
    """Secret *names* Cloud Run already mounts. Never payloads."""
    from packages.state.gcp_connections import reveal_latest_connection
    from packages.state.gcp_viewer import GcpViewerError, list_cloud_run_services
    from packages.state.secret_manager import GoogleSecretVault

    vault = GoogleSecretVault(os.environ.get("GCP_PROJECT", ""))
    try:
        loaded = await reveal_latest_connection(pool, project_id, vault)
    except Exception as exc:
        log.warning("could not reveal viewer connection for names: %s", exc)
        return ()
    if loaded is None:
        return ()
    meta, payload = loaded
    try:
        services = list_cloud_run_services(
            payload,
            gcp_project_id=str(meta["gcp_project_id"]),
            region=str(meta["default_region"]),
        )
    except GcpViewerError as exc:
        log.warning("could not list Cloud Run secret refs: %s", exc)
        return ()
    names: list[str] = []
    for service in services:
        for ref in service.get("secret_refs") or []:
            env_name = str(ref.get("env_name") or "")
            if env_name in live_check.CREDENTIAL_NAMES and env_name not in names:
                names.append(env_name)
    return tuple(names)


def _recorder(pool: asyncpg.Pool, run_id: str, journal: RunJournal, trace: ToolTrace) -> Any:
    from patchapi_agent_runner.remediation.recorder import RunRecorder

    return RunRecorder(pool=pool, run_id=run_id, journal=journal, trace=trace)


async def _persist(
    pool: asyncpg.Pool,
    row: RunRow,
    slice_: VerticalSlice,
    context: RunContext,
    result: Any,
    source: checkout.Checkout,
    session: Any,
    attempt_id: str,
    baseline: Baseline,
) -> None:
    """Write the evidence bundle the console renders and a reviewer reads."""
    policy = context.output("policy_decision")
    report = context.output("verification_report")
    plan = context.output("patch_plan")
    touched = list(getattr(plan, "files_expected", None) or [slice_.entrypoint])

    async with pool.acquire() as connection:
        await remediation.explain(connection, row.run_id, str(result.detail or ""))
        await remediation.record_artifact(
            connection,
            row.run_id,
            kind="build_log",
            body=f"# baseline at {row.base_sha[:12]}, before any patch\n{baseline.output}",
            patch_attempt_id=attempt_id,
        )

        if policy is not None:
            await remediation.record_policy(
                connection,
                row.run_id,
                decision=str(getattr(policy, "outcome", "human_required")),
                risk=str(getattr(policy, "risk_tier", "") or ""),
                auto_patch=bool(getattr(policy, "auto_patch", False)),
                auto_pr=bool(getattr(policy, "auto_pr", False)),
                human_review_required=bool(getattr(policy, "human_review_required", True)),
                forbidden_globs=list(getattr(policy, "forbidden_globs", []) or []),
                required_checks=list(getattr(policy, "required_checks", []) or []),
                rule_ids=list(getattr(policy, "rule_ids", []) or []),
                reason=str(getattr(policy, "reason", "") or ""),
                policy_version=str(getattr(policy, "policy_version", "") or ""),
            )

        diff = _diff(source, session, touched)
        if diff:
            await remediation.record_artifact(
                connection,
                row.run_id,
                kind="diff",
                body=diff,
                media_type="text/x-diff",
                patch_attempt_id=attempt_id,
            )
        for name, kind in (("build.log", "build_log"), ("test.log", "test_log")):
            body = _evidence(context, name)
            if body:
                await remediation.record_artifact(
                    connection, row.run_id, kind=kind, body=body, patch_attempt_id=attempt_id
                )

        if result.state is RunState.WAITING_ON_OPERATOR:
            # The attempt is paused, not finished. A failed status here is what
            # made a Connect-GCP hold look like a broken remediator job.
            pass
        else:
            await remediation.finish_attempt(
                connection,
                attempt_id,
                status="succeeded" if result.reached_testing else "failed",
                files_changed=touched,
                failure_summary=_failure_summary(result, baseline),
            )

        if report is not None:
            await remediation.record_verification(
                connection,
                row.run_id,
                verdict=str(getattr(report, "verdict", "inconclusive")).lower(),
                checks=_checks(report),
                verifier_agent="verification",
                verifier_model=str(getattr(report, "verifier_model", "") or ""),
                patch_agent="patch",
                patch_model=str(getattr(report, "patch_model", "") or ""),
                evidence_summary=str(getattr(report, "notes", "") or ""),
                patch_attempt_id=attempt_id,
            )

        opened = _pull_request(result)
        if opened:
            await remediation.record_pull_request(
                connection,
                row.run_id,
                number=int(opened.get("number") or 0) or 1,
                url=str(opened.get("html_url") or opened.get("url") or ""),
                title=str(opened.get("title") or ""),
                head_branch=f"patchapi/{slice_.change_id}",
                base_branch="main",
                head_sha=str(opened.get("head_sha") or ""),
            )
            await remediation.audit(
                connection,
                actor="patchapi.pr",
                action="open_pull_request",
                outcome="SUCCEEDED",
                target=f"{row.repository}#{opened.get('number', '')}",
                run_id=row.run_id,
                project_id=row.project_id,
                repository=row.repository,
            )


def _failure_summary(result: Any, baseline: Baseline) -> str:
    """Why the attempt ended, said in a way a reviewer can act on.

    "`python3 generate.py` did not exit 0" is true and useless when the command
    did not exit 0 before the patch either. Naming that turns a dead end into a
    next step: fix the repository's checks, or point the run at the change those
    checks are actually about.
    """
    if result.reached_testing:
        return ""
    detail = str(result.detail or "")
    if baseline.green or not detail:
        return detail
    return (
        f"{detail} — note that `{baseline.command}` also failed at "
        f"{'the base commit' if baseline.build_exit_code else 'baseline test'} "
        f"before this patch, so this repository was not green to begin with."
    )


def _checks(report: Any) -> list[dict[str, Any]]:
    """The verifier's per-check outcomes, in the shape the console renders.

    `VerificationReport.checks` is a mapping of check name to outcome, so
    iterating it yields names. Reading an outcome off a string gives False for
    everything, which put four failing checks next to a PASS verdict on the run
    card — the report contradicting itself in the one place a reviewer looks to
    decide whether to trust it.
    """
    checks = getattr(report, "checks", None) or {}
    if isinstance(checks, dict):
        return [{"name": str(name), "passed": _passed(outcome)} for name, outcome in checks.items()]
    return [
        {
            "name": str(getattr(check, "name", check)),
            "passed": _passed(getattr(check, "outcome", check)),
        }
        for check in checks
    ]


def _passed(outcome: Any) -> bool:
    return str(getattr(outcome, "value", outcome)).lower() in {"pass", "passed", "true", "ok"}


def _evidence(context: RunContext, name: str) -> str:
    root = getattr(context, "evidence_root", None)
    if root is None:
        return ""
    path = Path(root) / name
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _diff(source: checkout.Checkout, session: Any, paths: list[str]) -> str:
    """The proposed change, as a unified diff against the commit that was read.

    Built by comparing the sandbox to the tree that was staged into it, rather
    than by asking the sandbox for one. The tree on this side is known to be the
    pinned commit; a diff the sandbox produced would be a diff of whatever it
    says its own history is.
    """
    chunks: list[str] = []
    for relative in sorted(set(paths)):
        before_path = source.tree / relative
        before = (
            before_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            if before_path.is_file()
            else []
        )
        try:
            after = session.read_file(relative).splitlines(keepends=True)
        except Exception:
            continue
        if before == after:
            continue
        chunks.extend(
            difflib.unified_diff(
                before, after, fromfile=f"a/{relative}", tofile=f"b/{relative}", n=3
            )
        )
    return "".join(chunks)


def _pull_request(result: Any) -> dict[str, Any]:
    for stage in reversed(getattr(result, "stages", []) or []):
        output = getattr(stage, "output", None)
        if not isinstance(output, dict):
            continue
        payload = output.get("result") if isinstance(output.get("result"), dict) else output
        if isinstance(payload, dict) and (payload.get("html_url") or payload.get("number")):
            return payload
    return {}


__all__ = [
    "ACTOR",
    "EXIT_FAILED",
    "EXIT_OK",
    "SANDBOX_ENV_VAR",
    "abandon",
    "execute",
    "sandbox_kind",
]
