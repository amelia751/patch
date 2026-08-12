"""Impact tools: deterministic repository inventory, then a judged report.

Roadmap §11.3 layers detection. Layer A — literal identifier search with a
path-derived usage classification — is `packages.repo_scan`, and it is the only
thing here that decides *where* an identifier appears. The agent's contribution
is the part a grep cannot do: whether those hits mean the repository is actually
affected, how confident that is, and whether the migration is mechanical or
semantic.

`record_impact_report` therefore takes judgement fields only. The findings it
commits are the scan's findings, so a report cannot name a file the scanner
never saw.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.tools.results import ReasonCode, ok, refusal
from packages.repo_scan.classify import classify_path
from packages.repo_scan.scan import IdentifierHit, scan_tree
from packages.schemas.impact_report import ImpactFinding, ImpactReport

CONTRACT: Final[str] = "impact_report"
AGENT: Final[AgentId] = AgentId.IMPACT

# Hits handed back to the model in one call. A repository with thousands of
# matches is a policy question, not something to page into a prompt.
MAX_HITS_RETURNED: Final[int] = 200


def _finding(hit: IdentifierHit) -> ImpactFinding:
    return ImpactFinding(
        identifier=hit.identifier,
        file=hit.path,
        kind=hit.usage_kind,
        line=hit.line_number,
        excerpt=hit.excerpt,
    )


def build_repo_inventory_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Build the Impact tool set bound to `context`."""

    # The most recent scan, so `record_impact_report` commits findings that were
    # actually produced rather than findings that were described.
    scanned: dict[str, list[IdentifierHit]] = {}

    def _workspace() -> Path | None:
        return context.workspace_root

    def scan_repository(identifiers: list[str]) -> dict[str, Any]:
        """Find every literal occurrence of `identifiers` in the checkout.

        Returns one entry per hit with its path, line, usage kind and a short
        excerpt. This is the authoritative inventory: record_impact_report
        commits these findings, so scan before you report.
        """
        root = _workspace()
        if root is None:
            return refusal(
                ReasonCode.STAGE_NOT_READY,
                "this run has no repository workspace; nothing can be scanned",
            )
        cleaned = [value.strip() for value in identifiers if value.strip()]
        if not cleaned:
            return refusal(
                ReasonCode.INVALID_CONTRACT,
                "scan_repository needs at least one non-empty identifier",
            )

        result = scan_tree(root, cleaned)
        scanned["hits"] = list(result.hits)
        hits = [
            {
                "path": hit.path,
                "line": hit.line_number,
                "identifier": hit.identifier,
                "usage_kind": str(hit.usage_kind),
                "excerpt": hit.excerpt,
            }
            for hit in result.hits[:MAX_HITS_RETURNED]
        ]
        return ok(
            scanner_version=result.scanner_version,
            files_scanned=result.files_scanned,
            total_hits=len(result.hits),
            returned_hits=len(hits),
            truncated=len(result.hits) > MAX_HITS_RETURNED,
            hits=hits,
        )

    def classify_repository_path(path: str) -> dict[str, Any]:
        """Say how a repository path is used: runtime, test, docs, config.

        Path-derived and deterministic. Use it to check a single file without
        re-running a scan.
        """
        return ok(path=path, usage_kind=str(classify_path(path)))

    def record_impact_report(
        change_id: str,
        repo: str,
        base_sha: str,
        affected: bool,
        confidence: float,
        migration_character: str,
        required_checks: list[str],
        notes: str,
    ) -> dict[str, Any]:
        """Commit this run's ImpactReport.

        The findings come from the last scan_repository call, not from you.
        Supply the judgement: whether the repository is affected, how confident
        you are between 0 and 1, whether the migration is "mechanical",
        "semantic" or "unsupported", which checks must pass, and a short note.
        """
        if "hits" not in scanned:
            return refusal(
                ReasonCode.STAGE_NOT_READY,
                "call scan_repository before recording an impact report",
            )
        hits = scanned["hits"]
        if affected and not hits:
            return refusal(
                ReasonCode.CONTRADICTS_SOURCE,
                "the scan found no occurrence of the retired identifiers, so this "
                "repository cannot be reported as affected",
            )
        try:
            report = ImpactReport(
                run_id=context.run_id,
                change_id=change_id,
                repo=repo,
                base_sha=base_sha,
                affected=affected,
                confidence=confidence,
                findings=[_finding(hit) for hit in hits],
                migration_character=migration_character or None,
                required_checks=[check for check in required_checks if check.strip()],
                notes=notes or None,
            )
        except ValueError as exc:
            return refusal(ReasonCode.INVALID_CONTRACT, str(exc))

        context.record(CONTRACT, AGENT, report)
        return ok(
            recorded=CONTRACT,
            schema_version=report.schema_version,
            affected=report.affected,
            finding_count=len(report.findings),
        )

    return [scan_repository, classify_repository_path, record_impact_report]


__all__ = ["AGENT", "CONTRACT", "MAX_HITS_RETURNED", "build_repo_inventory_tools"]
