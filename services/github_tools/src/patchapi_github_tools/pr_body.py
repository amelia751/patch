"""Rendering the pull request body from evidence (roadmap §8.6).

The body is generated, never supplied. That is what makes the automation
boundary a property of the service rather than a habit of the agent: the
closing statement that PatchAPI did not merge, and will not, is appended to
every pull request this service opens because there is no code path that
produces a body without it.

The rendered body also carries the idempotency key as an HTML comment, so a
replayed run can recognise its own pull request from the pull request itself
rather than from a database row that may not have been written yet.
"""

from __future__ import annotations

import hashlib
from typing import Final

from patchapi_github_tools.models import PullRequestEvidence

BODY_VERSION: Final[str] = "pr-body/v1"

IDEMPOTENCY_MARKER_PREFIX: Final[str] = "<!-- patchapi:idempotency-key="

AUTOMATION_BOUNDARY_HEADING: Final[str] = "### Automation boundary"
AUTOMATION_BOUNDARY_TEXT: Final[str] = (
    "PatchAPI did not merge this pull request and cannot. Normal CODEOWNERS, "
    "branch protection, and CI review apply. The tool surface that opened this "
    "pull request has no merge, administration, secret, or branch-protection "
    "capability."
)

_RISK_LABEL: Final[dict[str, str]] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}


def pull_request_idempotency_key(*, run_id: str, base_sha: str, title: str) -> str:
    """Stable key for "the same migration, proposed again".

    Derived from the run, the base commit, and the title so that a retried run
    against the same base updates its pull request instead of opening a second
    one. A different base SHA is a different proposal and gets its own PR.
    """
    digest = hashlib.sha256(
        "\x00".join((BODY_VERSION, run_id, base_sha, title.strip())).encode("utf-8")
    )
    return digest.hexdigest()[:32]


def idempotency_marker(key: str) -> str:
    return f"{IDEMPOTENCY_MARKER_PREFIX}{key} -->"


def extract_idempotency_key(body: str | None) -> str | None:
    """Recover the key a previously rendered body was stamped with."""
    if not body:
        return None
    start = body.find(IDEMPOTENCY_MARKER_PREFIX)
    if start < 0:
        return None
    start += len(IDEMPOTENCY_MARKER_PREFIX)
    end = body.find(" -->", start)
    return body[start:end] if end > start else None


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- _none recorded_"


def render_pull_request_body(
    evidence: PullRequestEvidence,
    *,
    idempotency_key: str,
    base_sha: str,
    run_id: str,
) -> str:
    """Render the full evidence-backed body for one migration pull request."""
    checks = "\n".join(
        f"- {'✅' if check.passed else '❌'} {check.name}"
        + (f" — {check.detail}" if check.detail else "")
        for check in evidence.verification
    )
    sections = [
        "## PatchAPI migration",
        "",
        "### Why",
        evidence.why.strip(),
        "",
        "### Affected usage",
        _bullets(evidence.affected_usage),
        "",
        "### Migration",
        _bullets(evidence.migration),
        "",
        "### Verification",
        checks,
        "",
        "### Risk",
        f"{_RISK_LABEL[evidence.risk_level]} — {evidence.risk_rationale.strip()}",
        "",
        "### Evidence",
        _bullets(evidence.evidence_links),
        f"- base commit `{base_sha}`",
        f"- PatchAPI run `{run_id}`",
        f"- PatchAPI trace `{evidence.trace_id}`",
        "",
        AUTOMATION_BOUNDARY_HEADING,
        AUTOMATION_BOUNDARY_TEXT,
        "",
        idempotency_marker(idempotency_key),
    ]
    return "\n".join(sections) + "\n"
