"""Provider change notices — untrusted provider input in, `ChangeManifest` out.

One schema for every provider. The document is data, never instructions, and
this module's whole job is to refuse a notice PatchAPI cannot safely reason
about: an unknown notice version, a change class outside the closed vocabulary,
an uncaptured snapshot dressed up as evidence, or an extra key that smuggles a
decision ("remediation", "auto_merge") into what is supposed to be a
description.

The mapping to a manifest is deterministic and total: no model call, no
heuristics, no opinion about any repository. Two rules shape it.

*Severity* comes from a pinned table keyed on the provider's own change class.
It describes how disruptive that class of change is in general, never how
exposed a particular customer is — that is `ImpactReport` and `PolicyDecision`.

*Semantic migration* fails closed. Unless the notice explicitly declares the
change mechanical, the manifest says a semantic migration is required, because
a wrong "mechanical" produces an identifier string rewrite across a customer's
repository.

Capability notes are the one place a provider's own vocabulary survives. A
notice groups them under names the provider uses — `gemini_image_family`,
`replacement_surface` — and the provider's descriptor names which of those
groups describe the *replacement*. Only those become migration constraints:
what the retired surface used to support is already implied by the affected
identifiers, whereas what the replacement does not support is what constrains a
migration.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Self
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from packages.providers import registry
from packages.providers.errors import ProviderEvidenceError, ProviderRegistryError
from packages.providers.snapshot import sha256_file
from packages.schemas.base import StrictModel
from packages.schemas.change_manifest import ChangeManifest
from packages.schemas.config import ALLOWED_EVIDENCE_URI_SCHEMES
from packages.schemas.enums import (
    ChangeType,
    MigrationCharacter,
    Severity,
    TrustClassification,
)
from packages.schemas.evidence import SourceSnapshot
from packages.schemas.fields import ChangeId, Identifier, NonEmptyLine, ProviderId, Sha256Hex

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    from collections.abc import Mapping

    from packages.providers.descriptor import ProviderDescriptor

# Notice document versions this build knows how to read. An unknown version is
# refused: a notice written by a newer producer may mean something different by
# the same keys.
#
# 1.1.0 replaced the Google-shaped `capability_notes.imagen_family` /
# `gemini_image_family` keys with a provider-neutral `families` map, so a notice
# from any provider has somewhere to put its own vocabulary.
SUPPORTED_NOTICE_VERSIONS: Final[frozenset[str]] = frozenset({"1.1.0"})

# Provider-stated change class → manifest severity. A fixed table, not a
# judgement: how bad the change is *for a given repository* is Impact and Policy
# work, and this only records how disruptive the provider's own class of change
# is in general.
SEVERITY_BY_CHANGE_TYPE: Final[MappingProxyType[ChangeType, Severity]] = MappingProxyType(
    {
        ChangeType.MODEL_RETIREMENT: Severity.CRITICAL,
        ChangeType.ENDPOINT_REMOVAL: Severity.CRITICAL,
        ChangeType.AUTH_CHANGE: Severity.HIGH,
        ChangeType.BREAKING_CHANGE: Severity.HIGH,
        ChangeType.API_DEPRECATION: Severity.MEDIUM,
        ChangeType.PARAMETER_CHANGE: Severity.MEDIUM,
        ChangeType.BEHAVIOR_CHANGE: Severity.LOW,
    }
)

# Schemes a captured page may already live under. Anything else is treated as a
# filesystem path and hashed locally.
_REMOTE_URI_SCHEMES: Final[tuple[str, ...]] = tuple(
    scheme for scheme in ALLOWED_EVIDENCE_URI_SCHEMES if scheme != "file"
)


def severity_for(change_type: ChangeType) -> Severity:
    """Return the pinned severity for a provider change class."""
    try:
        return SEVERITY_BY_CHANGE_TYPE[change_type]
    except KeyError as exc:  # pragma: no cover - unreachable while the table is total
        raise ProviderRegistryError(f"no pinned severity for change type {change_type!r}") from exc


class SnapshotStatus(StrEnum):
    """Whether the official page behind this notice was captured and hashed."""

    CAPTURED = "CAPTURED"
    NOT_CAPTURED = "NOT_CAPTURED"


class FeedSourceSnapshot(StrictModel):
    """The notice's claim about a captured source page.

    A `CAPTURED` claim must carry all three of path, hash and capture time. A
    partially filled capture is worse than none, because it looks like evidence
    in a pull request while being unverifiable.
    """

    status: SnapshotStatus
    reason: NonEmptyLine | None = None
    path: str | None = None
    sha256: Sha256Hex | None = None
    captured_at: datetime | None = None
    source_url: AnyHttpUrl | None = None
    media_type: str = "text/html"

    @model_validator(mode="after")
    def _check_complete(self) -> Self:
        if self.status is not SnapshotStatus.CAPTURED:
            return self
        missing = [
            name for name in ("path", "sha256", "captured_at") if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(
                f"a CAPTURED source snapshot must carry {', '.join(missing)}; "
                "an unverifiable capture is not evidence"
            )
        return self


class FeedTrust(StrictModel):
    """The notice's self-declared trust label."""

    classification: TrustClassification
    note: NonEmptyLine | None = None

    @field_validator("classification")
    @classmethod
    def _must_be_untrusted(cls, value: TrustClassification) -> TrustClassification:
        if value is not TrustClassification.UNTRUSTED_PROVIDER_INPUT:
            raise ValueError(
                "a provider notice is untrusted input; it cannot label itself internal analysis"
            )
        return value


class FeedCapabilityNotes(StrictModel):
    """Provider-stated differences between the retired and replacement surfaces.

    `families` is keyed by whatever the provider calls its own surfaces. The
    provider's descriptor decides which of those keys describe the replacement;
    nothing here interprets a key name.
    """

    statement: NonEmptyLine
    families: dict[str, list[NonEmptyLine]] = Field(default_factory=dict)
    consequence: NonEmptyLine | None = None


class FeedVerificationRequirements(StrictModel):
    """What the provider evidence implies a verification run must cover.

    Still evidence rather than decision: the Verification agent owns the plan,
    and reads this as one input to it.
    """

    build: bool = True
    tests: bool = True
    live_replacement_model_call: bool = False
    no_deprecated_identifier_in_exercised_path: bool = True


class ProviderNotice(StrictModel):
    """One accepted, well-formed change notice from any provider."""

    fixture_version: str
    provider: ProviderId
    change_id: ChangeId
    change_type: ChangeType
    announced_at: date | None = None
    effective_at: date | None = None
    affected_identifiers: list[Identifier] = Field(min_length=1)
    recommended_replacement: Identifier | None = None
    migration_character: MigrationCharacter | None = None
    source_urls: list[AnyHttpUrl] = Field(min_length=1)
    source_snapshot: FeedSourceSnapshot | None = None
    trust: FeedTrust | None = None
    capability_notes: FeedCapabilityNotes | None = None
    verification_requirements: FeedVerificationRequirements | None = None

    @field_validator("fixture_version")
    @classmethod
    def _known_version(cls, value: str) -> str:
        if value not in SUPPORTED_NOTICE_VERSIONS:
            known = ", ".join(sorted(SUPPORTED_NOTICE_VERSIONS))
            raise ValueError(
                f"unsupported provider notice version {value!r}; this build reads: {known}"
            )
        return value

    @field_validator("provider")
    @classmethod
    def _is_registered(cls, value: str) -> str:
        """Refuse a notice from a provider this build cannot detect.

        Accepting one would produce a manifest that no indexer has patterns for,
        which reaches the inbox as a change affecting nothing — indistinguishable
        from a fleet that is genuinely clean.
        """
        if not registry.has_provider(value):
            known = ", ".join(registry.known_providers()) or "none"
            raise ValueError(
                f"no provider descriptor is registered for a {value!r} notice; "
                f"registered providers: {known}"
            )
        return value

    @property
    def has_captured_snapshot(self) -> bool:
        """Whether a hashed capture of the official page backs this notice."""
        return (
            self.source_snapshot is not None
            and self.source_snapshot.status is SnapshotStatus.CAPTURED
        )


def load_notice(payload: Mapping[str, Any]) -> ProviderNotice:
    """Validate one decoded notice document. Raises `ValidationError` if unusable."""
    return ProviderNotice.model_validate(dict(payload))


def load_notice_file(path: Path) -> ProviderNotice:
    """Read and validate a notice document from disk."""
    return load_notice(json.loads(path.read_text(encoding="utf-8")))


def _migration_constraints(
    notes: FeedCapabilityNotes | None, descriptor: ProviderDescriptor
) -> list[str]:
    """Provider-stated constraints, in reading order, deduplicated.

    Only the groups the descriptor names as replacement surfaces are carried.
    A notice that names none contributes just its statement and consequence,
    which is the honest floor rather than an empty constraint list.
    """
    if notes is None:
        return []
    ordered: list[str] = [notes.statement]
    for name in descriptor.replacement_surfaces:
        ordered.extend(notes.families.get(name, ()))
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
    """Turn a `CAPTURED` notice snapshot into verified evidence, or return none.

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
                f"notice claims a captured snapshot at {claimed_path!r} but no file is there "
                f"(looked in {resolved}); an unverifiable capture is not evidence"
            )
        actual = sha256_file(resolved)
        if actual != digest:
            raise ProviderEvidenceError(
                f"captured snapshot {resolved} hashes to {actual}, but the notice recorded {digest}"
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
    notice: ProviderNotice,
    *,
    base_dir: Path | None = None,
) -> ChangeManifest:
    """Normalize an accepted notice into the versioned agent contract.

    `base_dir` is what a relative captured-snapshot path is resolved against;
    it defaults to the working directory.
    """
    root = Path.cwd() if base_dir is None else base_dir
    descriptor = registry.descriptor_for(notice.provider)
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
        migration_constraints=_migration_constraints(notice.capability_notes, descriptor),
        source_urls=[str(url) for url in notice.source_urls],
        source_snapshots=snapshots,
        trust=TrustClassification.UNTRUSTED_PROVIDER_INPUT,
    )


def manifest_from_notice_file(path: Path, *, base_dir: Path | None = None) -> ChangeManifest:
    """Read a notice document and normalize it in one step.

    Relative snapshot paths resolve against the document's own directory unless
    `base_dir` says otherwise, so a fixture stays portable.
    """
    notice = load_notice_file(path)
    return notice_to_manifest(notice, base_dir=base_dir or path.parent)


__all__ = [
    "SEVERITY_BY_CHANGE_TYPE",
    "SUPPORTED_NOTICE_VERSIONS",
    "FeedCapabilityNotes",
    "FeedSourceSnapshot",
    "FeedTrust",
    "FeedVerificationRequirements",
    "ProviderNotice",
    "SnapshotStatus",
    "load_notice",
    "load_notice_file",
    "manifest_from_notice_file",
    "notice_to_manifest",
    "severity_for",
]
