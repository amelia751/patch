"""What one repository, at one commit, does about a change.

The corpus says what a notice means and is shared by everyone. This is the
other scope: a verdict that is only true of `repository` at `base_sha`, which
is why the commit is part of the key. A push produces a new sha and therefore a
new assessment, and the previous one stays as history rather than becoming a
quietly stale claim about code that no longer exists.

Prose about somebody's tree belongs here and nowhere else. "Three references,
all string literals in generate.py" is a true and useful sentence about one
repository, and a false one the moment it is shown beside another project's
inventory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from packages.schemas.config import MAX_FINDING_EXCERPT_CHARS
from packages.schemas.impact_report import ImpactReport

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

MAX_NOTES_CHARS: Final[int] = 1000
MAX_EXCERPT_CHARS: Final[int] = MAX_FINDING_EXCERPT_CHARS

_EVENT_ID_SQL: Final[str] = """
SELECT id FROM change_events WHERE provider = $1 AND external_id = $2
"""

_UPSERT_IMPACT_SQL: Final[str] = """
INSERT INTO change_impacts (
    change_event_id, project_id, repository, base_sha,
    affected, confidence, migration_character, required_checks, owners, notes,
    run_id, contract_version, assessed_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8::text[], $9::text[], $10, $11, $12, now())
ON CONFLICT (change_event_id, project_id, repository, base_sha) DO UPDATE
SET affected            = EXCLUDED.affected,
    confidence          = EXCLUDED.confidence,
    migration_character = EXCLUDED.migration_character,
    required_checks     = EXCLUDED.required_checks,
    owners              = EXCLUDED.owners,
    notes               = EXCLUDED.notes,
    run_id              = EXCLUDED.run_id,
    contract_version    = EXCLUDED.contract_version,
    assessed_at         = now()
RETURNING id
"""

# Findings are replaced wholesale rather than merged. A reassessment of the same
# commit supersedes the previous one, and half of an old reading mixed into a
# new one would be a report nobody wrote.
_CLEAR_FINDINGS_SQL: Final[str] = """
DELETE FROM change_impact_findings WHERE impact_id = $1
"""

_INSERT_FINDING_SQL: Final[str] = """
INSERT INTO change_impact_findings (
    impact_id, identifier, path, usage_kind, line, symbol, excerpt
)
VALUES ($1, $2, $3, $4::usage_kind, $5, $6, $7)
"""

_LATEST_SQL: Final[str] = """
SELECT i.id, i.repository, i.base_sha, i.affected, i.confidence,
       i.migration_character, i.notes, i.assessed_at,
       e.external_id
FROM change_impacts i
JOIN change_events e ON e.id = i.change_event_id
WHERE i.project_id = $1 AND e.external_id = $2
ORDER BY i.assessed_at DESC
"""

_FINDINGS_SQL: Final[str] = """
SELECT identifier, path, usage_kind::text AS usage_kind, line, symbol, excerpt
FROM change_impact_findings
WHERE impact_id = $1
ORDER BY path, line NULLS FIRST, identifier
"""


@dataclass(frozen=True, slots=True)
class ImpactWrite:
    """What one assessment recorded."""

    impact_id: str
    repository: str
    base_sha: str
    affected: bool
    findings: int


async def event_id_for(
    connection: asyncpg.Connection, *, provider: str, external_id: str
) -> str | None:
    """The corpus row this assessment is about, if it exists."""
    row = await connection.fetchrow(_EVENT_ID_SQL, provider, external_id)
    return None if row is None else str(row["id"])


async def write_report(
    connection: asyncpg.Connection,
    report: ImpactReport,
    *,
    project_id: str,
    provider: str = "google",
) -> ImpactWrite | None:
    """Persist one repository's verdict on one change.

    Returns None when no corpus row matches. That is not an error: Impact must
    not conjure a release nobody detected, and an assessment with nothing to
    attach to is dropped rather than inventing the change it refers to.
    """
    event_id = await event_id_for(connection, provider=provider, external_id=report.change_id)
    if event_id is None:
        log.info("no change event named %s; impact for %s dropped", report.change_id, report.repo)
        return None

    row = await connection.fetchrow(
        _UPSERT_IMPACT_SQL,
        event_id,
        project_id,
        report.repo,
        report.base_sha,
        report.affected,
        report.confidence,
        str(report.migration_character) if report.migration_character else None,
        list(report.required_checks),
        list(report.owners),
        (report.notes or "").strip()[:MAX_NOTES_CHARS],
        report.run_id,
        report.schema_version,
    )
    if row is None:  # pragma: no cover - upsert always returns
        raise RuntimeError(f"could not write impact for {report.repo}")
    impact_id = row["id"]

    await connection.execute(_CLEAR_FINDINGS_SQL, impact_id)
    for finding in report.findings:
        await connection.execute(
            _INSERT_FINDING_SQL,
            impact_id,
            finding.identifier,
            finding.file,
            str(finding.kind),
            finding.line,
            finding.symbol,
            finding.excerpt or "",
        )

    log.info(
        "recorded impact of %s on %s@%s (%d findings)",
        report.change_id,
        report.repo,
        report.base_sha[:8],
        len(report.findings),
    )
    return ImpactWrite(
        impact_id=str(impact_id),
        repository=report.repo,
        base_sha=report.base_sha,
        affected=report.affected,
        findings=len(report.findings),
    )


async def write_report_payload(
    connection: asyncpg.Connection, payload: dict[str, Any], **kwargs: Any
) -> ImpactWrite | None:
    """Validate a recorded report, then persist it."""
    return await write_report(connection, ImpactReport.model_validate(payload), **kwargs)


def reports_from_index(
    rows: list[dict[str, Any]],
    *,
    change_id: str,
    run_id: str,
    identifiers: set[str],
    semantic: bool,
    notes: str = "",
) -> list[ImpactReport]:
    """One report per repository, built from what the indexer already stored.

    The index carries the path, line, usage kind and excerpt of every hit, which
    is the whole of an `ImpactFinding`. Assessing from it costs no clone and no
    sandbox: the tree was already walked once, when it was pushed.

    That makes this the deterministic half. An agent may replace `notes` with a
    better sentence, but it cannot add a finding for a file the indexer never
    saw.
    """
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("identifier") not in identifiers:
            continue
        by_repo.setdefault(str(row.get("repository") or ""), []).append(row)

    reports: list[ImpactReport] = []
    for repository, hits in sorted(by_repo.items()):
        if not repository or not hits:
            continue
        findings = [
            {
                "identifier": hit["identifier"],
                "file": hit["file_path"],
                "kind": hit["usage_kind"],
                "line": hit.get("line_start"),
                "excerpt": (hit.get("excerpt") or "")[:MAX_EXCERPT_CHARS] or None,
            }
            for hit in hits
        ]
        reports.append(
            ImpactReport.model_validate(
                {
                    "run_id": run_id,
                    "change_id": change_id,
                    "repo": repository,
                    "base_sha": str(hits[0].get("observed_sha") or ""),
                    "affected": True,
                    "confidence": _confidence(hits),
                    "migration_character": "semantic" if semantic else "mechanical",
                    # The indexer knows where a call site is, not which suite
                    # covers it. Naming a check nobody runs would be worse than
                    # leaving the choice to the patch lane.
                    "required_checks": ["verify-migration"],
                    "findings": findings,
                    "notes": notes or _default_notes(hits),
                }
            )
        )
    return reports


def _confidence(hits: list[dict[str, Any]]) -> float:
    """The weakest detection among the hits, since one report covers them all."""
    values = [float(hit.get("confidence") or 0.0) for hit in hits]
    return min(values) if values else 0.0


def _default_notes(hits: list[dict[str, Any]]) -> str:
    """A factual sentence about this repository, until an agent writes a better one."""
    files = len({hit["file_path"] for hit in hits})
    runtime = sum(1 for hit in hits if str(hit.get("usage_kind")) == "runtime_source")
    return (
        f"{len(hits)} reference{'s' if len(hits) != 1 else ''} "
        f"across {files} file{'s' if files != 1 else ''}, "
        f"{runtime} in code that runs."
    )


async def impacts_for(
    connection: asyncpg.Connection, *, project_id: str, external_id: str
) -> list[dict[str, Any]]:
    """Every repository's assessment of one change, newest first."""
    rows = await connection.fetch(_LATEST_SQL, project_id, external_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        findings = await connection.fetch(_FINDINGS_SQL, row["id"])
        out.append(
            {
                "repository": row["repository"],
                "base_sha": row["base_sha"],
                "affected": row["affected"],
                "confidence": row["confidence"],
                "migration_character": row["migration_character"],
                "notes": row["notes"],
                "assessed_at": row["assessed_at"].isoformat() if row["assessed_at"] else None,
                "findings": [dict(finding) for finding in findings],
            }
        )
    return out


__all__ = [
    "MAX_EXCERPT_CHARS",
    "MAX_NOTES_CHARS",
    "ImpactWrite",
    "event_id_for",
    "impacts_for",
    "reports_from_index",
    "write_report",
    "write_report_payload",
]
