"""`ChangeManifest` — the Change Intelligence agent's only output (roadmap §8.1).

The manifest is derived from untrusted provider text, so it stays descriptive:
what changed, when it takes effect, which identifiers go away, what the provider
recommends instead. It never states what a customer repository should do — that
is Impact and Policy work.
"""

from datetime import date
from typing import ClassVar, Self

from pydantic import AnyHttpUrl, Field, model_validator

from packages.schemas.base import VersionedContract
from packages.schemas.enums import ChangeType, Severity, TrustClassification
from packages.schemas.evidence import SourceSnapshot
from packages.schemas.fields import ChangeId, Identifier, NonEmptyLine, ProviderId

# Change types where a missing effective date would leave every downstream
# deadline undefined. Roadmap §8.1: announcement date and effective date are
# distinct, and the effective one drives urgency.
_REQUIRES_EFFECTIVE_DATE: frozenset[ChangeType] = frozenset(
    {ChangeType.MODEL_RETIREMENT, ChangeType.ENDPOINT_REMOVAL}
)


class ChangeManifest(VersionedContract):
    CONTRACT_NAME: ClassVar[str] = "change_manifest"

    provider: ProviderId
    change_id: ChangeId
    change_type: ChangeType
    severity: Severity
    announced_at: date | None = None
    effective_at: date | None = None
    affected_identifiers: list[Identifier] = Field(min_length=1)
    recommended_replacement: Identifier | None = None
    semantic_migration_required: bool
    migration_constraints: list[NonEmptyLine] = Field(default_factory=list)
    source_urls: list[AnyHttpUrl] = Field(min_length=1)
    source_snapshots: list[SourceSnapshot] = Field(default_factory=list)
    trust: TrustClassification = TrustClassification.UNTRUSTED_PROVIDER_INPUT

    @model_validator(mode="after")
    def _check_coherent(self) -> Self:
        if len(set(self.affected_identifiers)) != len(self.affected_identifiers):
            raise ValueError("affected_identifiers must not repeat an identifier")
        if self.recommended_replacement in self.affected_identifiers:
            raise ValueError(
                "recommended_replacement is also listed as retired: "
                f"{self.recommended_replacement!r}"
            )
        if self.change_type in _REQUIRES_EFFECTIVE_DATE and self.effective_at is None:
            raise ValueError(f"{self.change_type} requires an effective_at date")
        if (
            self.announced_at is not None
            and self.effective_at is not None
            and self.announced_at > self.effective_at
        ):
            raise ValueError("announced_at must not be later than effective_at")
        if self.trust is not TrustClassification.UNTRUSTED_PROVIDER_INPUT:
            raise ValueError("a ChangeManifest always describes untrusted provider input")
        return self

    @property
    def has_verifiable_evidence(self) -> bool:
        """Whether at least one hashed source snapshot backs this manifest.

        Policy fails closed when this is false: a manifest with no captured,
        hashed source is an unproven claim about a provider, not grounds for
        touching customer code.
        """
        return bool(self.source_snapshots)

    def retires(self, identifier: str) -> bool:
        """Whether `identifier` is one of the identifiers going away."""
        return identifier in self.affected_identifiers
