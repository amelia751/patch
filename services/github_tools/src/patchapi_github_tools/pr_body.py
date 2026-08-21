"""Render the pull request body from the checked-in template.

The body is generated, never supplied. Roadmap §8.6: the automation boundary
is appended because there is no code path that produces a body without it.

Pretty GitHub PRs (Dependabot, Renovate) lead with one sentence, put the
diff facts in tables, and hide logs in `<details>`. Local `file://` paths
never ship — they are sandbox leftovers and do not resolve on GitHub.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from patchapi_github_tools.models import PullRequestEvidence, VerificationCheck

BODY_VERSION: Final[str] = "pr-body/v2"
TEMPLATE_PATH: Final[Path] = Path(__file__).resolve().parent / "templates" / "migration_pr.md"

IDEMPOTENCY_MARKER_PREFIX: Final[str] = "<!-- patchapi:idempotency-key="

# GitHub Apps always display as `{name}[bot]`. The App display name should be
# `patchbot` so comments and reviews read `patchbot[bot]`.
BOT_NAME: Final[str] = "patchbot"
BOT_COMMITTER: Final[dict[str, str]] = {
    "name": BOT_NAME,
    "email": "patchbot@users.noreply.github.com",
}

AUTOMATION_BOUNDARY_HEADING: Final[str] = "## Checks"
AUTOMATION_BOUNDARY_TEXT: Final[str] = (
    f"{BOT_NAME} opened this pull request and cannot merge it. "
    "CODEOWNERS, branch protection, and CI stay in charge."
)

_KIND_LABEL: Final[dict[str, str]] = {
    "runtime_source": "Runtime",
    "documentation_example": "Docs",
    "configuration": "Config",
    "test": "Test",
    "lockfile": "Lockfile",
}

_INTERNAL_WHY: Final[tuple[str, ...]] = (
    "deterministic slice",
    "no model judged",
    "no model graded",
)


def pull_request_idempotency_key(*, run_id: str, base_sha: str, title: str) -> str:
    """Stable key for "the same migration, proposed again"."""
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


def _public_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme in {"http", "https", "gs"}:
        return True
    return bool(parsed.scheme == "" and not uri.startswith("/"))


def _kind_label(kind: str) -> str:
    return _KIND_LABEL.get(kind.strip(), kind.replace("_", " ").title() or "Usage")


def _usage_rows(items: Iterable[str]) -> list[tuple[str, str]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        raw = item.strip()
        if not raw or raw.startswith("("):
            continue
        if " — " in raw:
            path, kind = raw.split(" — ", 1)
        elif " uses " in raw:
            path, kind = raw.split(" uses ", 1)
            kind = "runtime_source"
        else:
            path, kind = raw, ""
        path = path.strip().strip("`")
        label = _kind_label(kind)
        kinds = grouped.setdefault(path, [])
        if label and label not in kinds:
            kinds.append(label)
    return [(path, ", ".join(kinds) or "Usage") for path, kinds in grouped.items()]


def _human_why(evidence: PullRequestEvidence) -> str:
    why = evidence.why.strip()
    if why and not any(token in why.lower() for token in _INTERNAL_WHY):
        return why
    if evidence.migration:
        return evidence.migration[0].strip()
    return "Migrate retired API identifiers."


def _files_table(evidence: PullRequestEvidence) -> str:
    rows = _usage_rows(evidence.affected_usage)
    if not rows:
        return "_No call sites recorded._"
    lines = ["| File | Kind |", "| --- | --- |"]
    lines.extend(f"| `{path}` | {kind} |" for path, kind in rows)
    return "\n".join(lines)


def _checks_table(checks: list[VerificationCheck]) -> str:
    lines = ["| Check | Result |", "| --- | --- |"]
    for check in checks:
        mark = "Pass" if check.passed else "Fail"
        detail = f" — {check.detail}" if check.detail else ""
        lines.append(f"| {check.name} | {mark}{detail} |")
    return "\n".join(lines)


def _evidence_block(evidence: PullRequestEvidence, *, base_sha: str, run_id: str) -> str:
    links = [uri for uri in evidence.evidence_links if _public_uri(uri)]
    lines = [f"- `{uri}`" for uri in links]
    lines.append(f"- Base `{base_sha}`")
    lines.append(f"- Run `{run_id}`")
    if evidence.trace_id and evidence.trace_id != run_id:
        lines.append(f"- Trace `{evidence.trace_id}`")
    return "\n".join(lines)


def render_pull_request_body(
    evidence: PullRequestEvidence,
    *,
    idempotency_key: str,
    base_sha: str,
    run_id: str,
) -> str:
    """Fill the checked-in template from evidence."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    filled = (
        template.replace("{{lead}}", _human_why(evidence))
        .replace("{{changes}}", "\n\n".join(item.strip() for item in evidence.migration) or "_None recorded._")
        .replace("{{files}}", _files_table(evidence))
        .replace("{{checks}}", _checks_table(evidence.verification))
        .replace("{{evidence}}", _evidence_block(evidence, base_sha=base_sha, run_id=run_id))
        .replace("{{boundary}}", AUTOMATION_BOUNDARY_TEXT)
        .replace("{{marker}}", idempotency_marker(idempotency_key))
    )
    return filled if filled.endswith("\n") else f"{filled}\n"
