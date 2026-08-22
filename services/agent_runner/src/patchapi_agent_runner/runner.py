"""Run Change Intelligence for one announced change, and store what it argued.

This is the second lane on `change-normalized`. The first lane already decided
the status from evidence; by the time an event reaches here the finding is
correct whether or not this process ever runs. That ordering is deliberate — a
model that is slow, rate-limited, or wrong must not be able to hold up, or
alter, a correct answer.

So the failure modes are all quiet. No notice for the change, ADK missing,
Vertex unreachable, the agent asking for a human: each returns a skip rather
than raising, because retrying a turn that refused for a good reason only
spends tokens to refuse again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from patchapi_agent_runner.config import ensure_fleet_importable, feed_dir, repo_root

if TYPE_CHECKING:
    import asyncpg

    from packages.events.envelope import EventEnvelope

log = logging.getLogger(__name__)

# Origins this lane must not react to. Enriching our own output would be a loop
# with a per-turn bill attached.
_AGENT_ORIGIN: Final[str] = "change_intelligence"


@dataclass(frozen=True)
class RunOutcome:
    """What one delivery produced. `applied` is the only success."""

    action: str
    external_id: str = ""
    reason: str = ""
    replacement: str = ""
    impacts: int = 0

    @classmethod
    def skipped(cls, external_id: str, reason: str) -> RunOutcome:
        return cls(action="skipped", external_id=external_id, reason=reason)


def notice_available(change_id: str, *, directory: Path | None = None) -> bool:
    """Whether a provider notice exists for this change.

    Change Intelligence reads notices. Without one it can only refuse, and
    constraint 10 says a refusal is the right answer rather than a guess, so
    checking first turns a wasted turn into a cheap skip.
    """
    ensure_fleet_importable()
    from agents.tools.change.feed import _notice_paths

    target = directory or feed_dir()
    try:
        return change_id in _notice_paths(target)
    except OSError as exc:  # a missing or unreadable feed dir is a skip, not a crash
        log.warning("cannot read the notice feed at %s: %s", target, exc)
        return False


def _environment_reason() -> str | None:
    """Why a live turn cannot run here, or None if it can."""
    ensure_fleet_importable()
    from agents.adk import (
        adk_unavailable_reason,
        configure_vertex_environment,
        vertex_unavailable_reason,
    )
    from packages.providers.dotenv import apply_defaults, read_env_files
    from packages.providers.google.config import load_config

    reason = adk_unavailable_reason()
    if reason is not None:
        return reason
    root = repo_root()
    # The container sets these explicitly; a checkout gets them from the pins,
    # so the same code path runs in both without a branch here.
    apply_defaults(read_env_files([root / ".env", root / ".env.example"]))
    config = load_config(base_dir=root)
    reason = vertex_unavailable_reason(config)
    if reason is not None:
        return reason
    configure_vertex_environment(config)
    return None


async def run_change_intelligence(
    connection: asyncpg.Connection, envelope: EventEnvelope
) -> RunOutcome:
    """Normalize one notice into the corpus, then assess the repositories using it."""
    from packages.state.corpus import write_manifest

    payload = envelope.payload
    external_id = str(payload.get("external_id") or "").strip()
    provider = str(payload.get("provider") or "google")
    if not external_id:
        return RunOutcome.skipped("", "event names no change")
    if str(payload.get("origin") or "") == _AGENT_ORIGIN:
        return RunOutcome.skipped(external_id, "this lane wrote it")
    if not notice_available(external_id):
        # The deterministic summary already says what the liveness check proved.
        # Better that than prose invented to fill the space.
        return RunOutcome.skipped(external_id, "no provider notice covers this change")

    reason = _environment_reason()
    if reason is not None:
        return RunOutcome.skipped(external_id, reason)

    manifest, rationale = await _produce_manifest(external_id, run_id=envelope.run_id)
    if manifest is None:
        return RunOutcome.skipped(external_id, "the agent recorded no manifest")

    # One notice, understood once. The row is the same for every subscriber,
    # which is why the rationale may not mention a repository.
    await write_manifest(
        connection,
        manifest,
        title=str(payload.get("title") or ""),
        summary=str(payload.get("summary") or ""),
        rationale=rationale,
    )
    impacts = await assess_projects(connection, manifest, run_id=envelope.run_id, provider=provider)

    replacement = str(getattr(manifest, "recommended_replacement", "") or "")
    log.info("%s: %s normalized, %d repositories assessed", provider, external_id, impacts)
    return RunOutcome(
        action="normalized",
        external_id=external_id,
        replacement=replacement,
        impacts=impacts,
    )


_PROJECTS_USING_SQL: Final[str] = """
SELECT DISTINCT u.project_id
FROM project_provider_usages u
JOIN project_provider_subscriptions s ON s.project_id = u.project_id
JOIN providers p ON p.id = s.provider_id AND p.slug = u.provider
WHERE u.provider = $1 AND u.identifier = ANY($2::text[])
"""


async def assess_projects(
    connection: asyncpg.Connection,
    manifest: Any,
    *,
    run_id: str,
    provider: str = "google",
) -> int:
    """Record what each subscribed project's repositories do about this change.

    Built from the index rather than a checkout. The tree was already walked
    when it was pushed, and the rows carry the path, line, usage kind and
    excerpt an `ImpactFinding` needs, so an assessment costs a query instead of
    a clone.
    """
    from packages.state.impact import reports_from_index, write_report
    from packages.state.index_inventory import load_index_usages

    identifiers = [str(value) for value in getattr(manifest, "affected_identifiers", []) or []]
    if not identifiers:
        return 0

    rows = await connection.fetch(_PROJECTS_USING_SQL, provider, identifiers)
    written = 0
    for row in rows:
        project_id = row["project_id"]
        usages = await load_index_usages(
            connection, project_id, provider=provider, identifiers=identifiers
        )
        reports = reports_from_index(
            usages,
            change_id=str(manifest.change_id),
            run_id=run_id,
            identifiers=set(identifiers),
            semantic=bool(getattr(manifest, "semantic_migration_required", False)),
        )
        for report in reports:
            recorded = await write_report(
                connection, report, project_id=str(project_id), provider=provider
            )
            if recorded:
                written += 1
    return written


async def _produce_manifest(change_id: str, *, run_id: str) -> tuple[Any | None, str]:
    """One Change Intelligence turn, isolated from the caller's failure modes.

    Returns the manifest and the agent's own sentence about it. The manifest is
    the deterministic parse of the notice and is the same every run; the
    rationale is what this lane is here to add.
    """
    ensure_fleet_importable()
    from agents.context import RunContext
    from agents.orchestrator import Orchestrator
    from agents.tools.change.feed import RATIONALE_CONTRACT
    from agents.trace import ToolTrace

    context = RunContext(run_id=run_id, repo_root=repo_root(), feed_dir=feed_dir())
    orchestrator = Orchestrator(context, ToolTrace(run_id=run_id))
    try:
        result = await orchestrator.run_change_intelligence(change_id)
    except Exception as exc:  # a failed turn is a skip; the status already stands
        log.warning("change intelligence failed on %s: %s", change_id, exc)
        return None, ""
    if result.human_required:
        log.info("change intelligence asked for a human on %s", change_id)
        return None, ""
    return result.output, str(context.output(RATIONALE_CONTRACT) or "")


__all__ = ["RunOutcome", "notice_available", "run_change_intelligence"]
