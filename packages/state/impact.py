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

from packages.schemas.impact_report import ImpactReport

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

MAX_NOTES_CHARS: Final[int] = 1000

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
    "MAX_NOTES_CHARS",
    "ImpactWrite",
    "event_id_for",
    "impacts_for",
    "write_report",
    "write_report_payload",
]
