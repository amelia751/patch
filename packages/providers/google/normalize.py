"""Google deprecation feed → `ChangeManifest`.

The mapping is deterministic and total: no model call, no heuristics, no
opinion about any repository. Two rules shape it.

*Severity* comes from a pinned table keyed on the provider's own change class.
It describes how disruptive that class of change is in general, never how
exposed a particular customer is — that is `ImpactReport` and `PolicyDecision`.

*Semantic migration* fails closed. Unless the feed explicitly declares the
change mechanical, the manifest says a semantic migration is required, because
a wrong "mechanical" produces a model-ID string rewrite across a customer's
repository.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from packages.providers.google.config import ADAPTER_VERSION, severity_for
from packages.providers.google.deprecation_feed import (
    FeedCapabilityNotes,
    FeedSourceSnapshot,
    GoogleDeprecationNotice,
    SnapshotStatus,
)
from packages.providers.google.errors import ProviderEvidenceError
from packages.providers.google.snapshot import sha256_file
from packages.schemas.change_manifest import ChangeManifest
from packages.schemas.config import ALLOWED_EVIDENCE_URI_SCHEMES
from packages.schemas.enums import MigrationCharacter, TrustClassification
from packages.schemas.evidence import SourceSnapshot

__all__ = [
    "ADAPTER_VERSION",
    "load_notice",
    "load_notice_file",
    "manifest_from_feed_file",
    "notice_to_manifest",
]

# Schemes a captured page may already live under. Anything else is treated as a
# filesystem path and hashed locally.
_REMOTE_URI_SCHEMES = tuple(scheme for scheme in ALLOWED_EVIDENCE_URI_SCHEMES if scheme != "file")


def load_notice(payload: Mapping[str, Any]) -> GoogleDeprecationNotice:
    """Validate one decoded feed document. Raises `ValidationError` if unusable."""
    return GoogleDeprecationNotice.model_validate(dict(payload))


def load_notice_file(path: Path) -> GoogleDeprecationNotice:
    """Read and validate a feed document from disk."""
    return load_notice(json.loads(path.read_text(encoding="utf-8")))


def _migration_constraints(notes: FeedCapabilityNotes | None) -> list[str]:
    """Provider-stated constraints, in reading order, deduplicated.

    Only the replacement-surface bullets are carried: what the retired family
    used to support is already implied by `affected_identifiers`, whereas what
    the replacement does *not* support is what constrains a migration.
    """
    if notes is None:
        return []
    ordered = [notes.statement, *notes.gemini_image_family]
    if notes.consequence is not None:
        ordered.append(notes.consequence)
    seen: set[str] = set()
    constraints: list[str] = []
    for line in ordered:
        if line not in seen:
            seen.add(line)
            constraints.append(line)
    return constraints


def _snapshot_evidence(
    snapshot: FeedSourceSnapshot | None,
    *,
    fallback_url: str,
    base_dir: Path,
) -> list[SourceSnapshot]:
    """Turn a `CAPTURED` feed snapshot into verified evidence, or return none.

    An uncaptured snapshot yields an empty list, which leaves
    `ChangeManifest.has_verifiable_evidence` false so Policy fails closed. A
    capture that claims bytes the adapter cannot re-hash raises instead of
    quietly downgrading to that same empty list — a broken claim is a different
    situation from an honest absence.
    """
    if snapshot is None or snapshot.status is not SnapshotStatus.CAPTURED:
        return []

    claimed_path, digest, captured_at = snapshot.path, snapshot.sha256, snapshot.captured_at
    if claimed_path is None or digest is None or captured_at is None:  # pragma: no cover
        # FeedSourceSnapshot's completeness validator rejects this shape first.
        raise ProviderEvidenceError("captured snapshot is missing path, hash or capture time")

    source_url = str(snapshot.source_url) if snapshot.source_url is not None else fallback_url

    if urlsplit(claimed_path).scheme in _REMOTE_URI_SCHEMES:
        content_uri = claimed_path
    else:
        candidate = Path(claimed_path).expanduser()
        resolved = (candidate if candidate.is_absolute() else base_dir / candidate).resolve()
        if not resolved.is_file():
            raise ProviderEvidenceError(
                f"feed claims a captured snapshot at {claimed_path!r} but no file is there "
                f"(looked in {resolved}); an unverifiable capture is not evidence"
            )
        actual = sha256_file(resolved)
        if actual != digest:
            raise ProviderEvidenceError(
                f"captured snapshot {resolved} hashes to {actual}, but the feed recorded {digest}"
            )
        content_uri = resolved.as_uri()

    return [
        SourceSnapshot(
            source_url=source_url,
            retrieved_at=captured_at,
            content_uri=content_uri,
            content_sha256=digest,
            media_type=snapshot.media_type,
        )
    ]


def notice_to_manifest(
    notice: GoogleDeprecationNotice,
    *,
    base_dir: Path | None = None,
) -> ChangeManifest:
    """Normalize an accepted feed notice into the versioned agent contract.

    `base_dir` is what a relative captured-snapshot path is resolved against;
    it defaults to the working directory.
    """
    root = Path.cwd() if base_dir is None else base_dir
    snapshots = _snapshot_evidence(
        notice.source_snapshot,
        fallback_url=str(notice.source_urls[0]),
        base_dir=root,
    )
    return ChangeManifest(
        provider=notice.provider,
        change_id=notice.change_id,
        change_type=notice.change_type,
        severity=severity_for(notice.change_type),
        announced_at=notice.announced_at,
        effective_at=notice.effective_at,
        affected_identifiers=list(notice.affected_identifiers),
        recommended_replacement=notice.recommended_replacement,
        semantic_migration_required=notice.migration_character is not MigrationCharacter.MECHANICAL,
        migration_constraints=_migration_constraints(notice.capability_notes),
        source_urls=[str(url) for url in notice.source_urls],
        source_snapshots=snapshots,
        trust=TrustClassification.UNTRUSTED_PROVIDER_INPUT,
    )


def manifest_from_feed_file(path: Path, *, base_dir: Path | None = None) -> ChangeManifest:
    """Read a feed document and normalize it in one step.

    Relative snapshot paths resolve against the document's own directory unless
    `base_dir` says otherwise, so a fixture stays portable.
    """
    notice = load_notice_file(path)
    return notice_to_manifest(notice, base_dir=base_dir or path.parent)
