"""Strict model for the Google deprecation feed — untrusted provider input.

The feed is data, never instructions. This module's whole job is to refuse a
document that PatchAPI cannot safely reason about: an unknown feed version, a
change class outside the closed vocabulary, an uncaptured snapshot dressed up as
evidence, or an extra key that smuggles a decision ("remediation",
"auto_merge") into what is supposed to be a description.

Nothing here decides anything. `normalize` turns an accepted notice into a
`ChangeManifest`; Impact and Policy decide what it means.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from packages.providers.google.config import PROVIDER_ID, SUPPORTED_FEED_VERSIONS
from packages.schemas.base import StrictModel
from packages.schemas.enums import ChangeType, MigrationCharacter, TrustClassification
from packages.schemas.fields import ChangeId, Identifier, NonEmptyLine, ProviderId, Sha256Hex


class SnapshotStatus(StrEnum):
    """Whether the official page behind this notice was captured and hashed."""

    CAPTURED = "CAPTURED"
    NOT_CAPTURED = "NOT_CAPTURED"


class FeedSourceSnapshot(StrictModel):
    """The feed's claim about a captured source page.

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
    """The feed's self-declared trust label."""

    classification: TrustClassification
    note: NonEmptyLine | None = None

    @field_validator("classification")
    @classmethod
    def _must_be_untrusted(cls, value: TrustClassification) -> TrustClassification:
        if value is not TrustClassification.UNTRUSTED_PROVIDER_INPUT:
            raise ValueError(
                "a provider feed is untrusted input; it cannot label itself internal analysis"
            )
        return value


class FeedCapabilityNotes(StrictModel):
    """Provider-stated differences between the retired and replacement surfaces.

    Field names follow the Google Imagen-4 feed literally. They are descriptive
    bullets copied from provider documentation, not migration instructions.
    """

    statement: NonEmptyLine
    imagen_family: list[NonEmptyLine] = Field(default_factory=list)
    gemini_image_family: list[NonEmptyLine] = Field(default_factory=list)
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


class GoogleDeprecationNotice(StrictModel):
    """One accepted, well-formed entry from the Google deprecation feed."""

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
        if value not in SUPPORTED_FEED_VERSIONS:
            known = ", ".join(sorted(SUPPORTED_FEED_VERSIONS))
            raise ValueError(
                f"unsupported deprecation feed version {value!r}; this build reads: {known}"
            )
        return value

    @field_validator("provider")
    @classmethod
    def _is_google(cls, value: str) -> str:
        if value != PROVIDER_ID:
            raise ValueError(f"the Google adapter cannot read a {value!r} feed")
        return value

    @property
    def has_captured_snapshot(self) -> bool:
        """Whether a hashed capture of the official page backs this notice."""
        return (
            self.source_snapshot is not None
            and self.source_snapshot.status is SnapshotStatus.CAPTURED
        )
