"""What PatchAPI watches for on behalf of one provider, as data.

Every provider-specific detail the detection lanes need — which identifier
families to query an index for, which literals are pinned, which client
libraries belong to the provider, which hosts those libraries call, which
ast-grep rules apply, which migration skills to offer — is declared in a
`ProviderDescriptor` and nowhere else. Onboarding a provider is a descriptor,
not an edit to a call site.

Two properties make that safe to rely on.

*Patterns are validated at load.* A descriptor whose regex does not compile is
refused when it is registered, not when a repository is scanned, because a
pattern that fails mid-query would degrade one repository's answer to "clean".

*`search_intent` is the identity of a search.* It hashes what a scan would look
for — descriptor version, queried patterns, pinned literals — so an inventory
can record the question it answered. Adding an identifier to a descriptor
changes the intent, which is what tells an already-indexed repository it needs
re-scanning for that provider rather than skipping as current.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Final, Self

from pydantic import Field, field_validator, model_validator

from packages.providers.errors import DescriptorError
from packages.schemas.base import StrictModel
from packages.schemas.fields import NonEmptyLine, ProviderId

# Registries a client library can be published to. Mirrors `sdk.SDK_ECOSYSTEMS`;
# duplicated as a literal rather than imported so loading a descriptor does not
# pull in httpx.
ECOSYSTEMS: Final[frozenset[str]] = frozenset({"npm", "pypi", "go"})

DESCRIPTOR_SUFFIX: Final[str] = ".json"

# Descriptor document versions this build knows how to read. An unknown version
# is refused for the same reason an unknown feed version is: a newer producer
# may mean something different by the same keys.
SUPPORTED_DESCRIPTOR_VERSIONS: Final[frozenset[str]] = frozenset({"1.0.0"})


class IdentifierFamily(StrictModel):
    """One RE2 pattern naming a family of the provider's identifiers.

    `queried` is what separates a pattern the index is asked for from one kept
    only so a stored finding can name the regex that produced it. A retired
    family stays declared and stops being searched, rather than vanishing and
    leaving old rows unattributable.
    """

    name: NonEmptyLine
    pattern: NonEmptyLine
    queried: bool = True
    note: str = ""

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"identifier family pattern does not compile: {exc}") from exc
        return value


class PackageRef(StrictModel):
    """One client library that belongs to the provider, and the hosts it calls.

    `service_hosts` is how a whole-service shutdown reaches a repository that
    depends on the SDK without naming the hostname anywhere in its source.
    """

    ecosystem: NonEmptyLine
    name: NonEmptyLine
    service_hosts: list[NonEmptyLine] = Field(default_factory=list)

    @field_validator("ecosystem")
    @classmethod
    def _known_ecosystem(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ECOSYSTEMS:
            known = ", ".join(sorted(ECOSYSTEMS))
            raise ValueError(f"unknown package ecosystem {value!r}; known ecosystems: {known}")
        return normalized

    @property
    def identifier(self) -> str:
        """`npm` + `@google/genai` -> `npm:@google/genai`."""
        return f"{self.ecosystem}:{self.name}"


class ProviderDescriptor(StrictModel):
    """Everything provider-specific about detecting one provider's surface."""

    descriptor_version: NonEmptyLine
    provider_id: ProviderId
    display_name: NonEmptyLine
    identifier_families: list[IdentifierFamily] = Field(default_factory=list)
    watched_identifiers: dict[str, list[NonEmptyLine]] = Field(default_factory=dict)
    packages: list[PackageRef] = Field(default_factory=list)

    # Which `capability_notes.families` groups in a notice describe the
    # *replacement* surface. Only those become `migration_constraints`: what the
    # retired family used to support is already implied by the affected
    # identifiers, whereas what the replacement does not support is what
    # constrains a migration.
    replacement_surfaces: list[NonEmptyLine] = Field(default_factory=list)

    # Subdirectory of the indexer's rule root holding this provider's ast-grep
    # rules. Empty means the provider ships none, which costs Layer B precision
    # and never costs Layer A recall.
    rule_namespace: str = ""

    # Skill packages under `skills/` that apply to this provider, most general
    # first. Advisory: ADK exposes every skill and the model chooses.
    skill_packages: list[NonEmptyLine] = Field(default_factory=list)

    @field_validator("descriptor_version")
    @classmethod
    def _known_version(cls, value: str) -> str:
        if value not in SUPPORTED_DESCRIPTOR_VERSIONS:
            known = ", ".join(sorted(SUPPORTED_DESCRIPTOR_VERSIONS))
            raise ValueError(f"unsupported descriptor version {value!r}; this build reads: {known}")
        return value

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        names = [family.name for family in self.identifier_families]
        if len(names) != len(set(names)):
            raise ValueError("identifier family names must be unique within a descriptor")
        identifiers = [pkg.identifier for pkg in self.packages]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("a package may not be declared twice in one descriptor")
        if not self.identifier_families and not self.watched_identifiers:
            raise ValueError(
                f"descriptor for {self.provider_id!r} declares neither a family pattern nor a "
                "pinned identifier; it would search for nothing and report every repository clean"
            )
        return self

    @property
    def namespace(self) -> str:
        """Rule subdirectory for this provider, defaulting to its slug."""
        return self.rule_namespace or self.provider_id

    def patterns(self) -> tuple[str, ...]:
        """The family regexes to query an index with, in declaration order.

        Order is preserved because it is documented behaviour at the call site:
        a longer routed identifier is declared before the bare one it contains.
        """
        return tuple(family.pattern for family in self.identifier_families if family.queried)

    def pattern_named(self, name: str) -> str:
        """One family's regex by name. Raises `KeyError` when it is not declared."""
        for family in self.identifier_families:
            if family.name == name:
                return family.pattern
        raise KeyError(f"{self.provider_id} declares no identifier family named {name!r}")

    def identifier_group(self, name: str) -> tuple[str, ...]:
        """One pinned literal group by name, or empty when it is not declared."""
        return tuple(self.watched_identifiers.get(name, ()))

    def all_watched_identifiers(self) -> tuple[str, ...]:
        """Every pinned literal, deduplicated, in declaration order."""
        found: dict[str, None] = {}
        for group in self.watched_identifiers.values():
            for identifier in group:
                found[identifier] = None
        return tuple(found)

    def package_refs(self) -> tuple[tuple[str, str], ...]:
        """`(ecosystem, name)` for every client library this provider publishes."""
        return tuple((pkg.ecosystem, pkg.name) for pkg in self.packages)

    def service_hosts(self) -> dict[str, tuple[str, ...]]:
        """SDK identifier -> the API hosts that library talks to."""
        return {pkg.identifier: tuple(pkg.service_hosts) for pkg in self.packages}

    def search_intent(self, identifiers: tuple[str, ...] | None = None) -> str:
        """A stable hash of what a scan for this provider would look for.

        Recorded on a per-provider index row so that widening a descriptor
        invalidates exactly the scans whose question changed, instead of forcing
        a global re-index or — worse — leaving an imported repository skipped as
        already-current for a provider it was never searched for.
        """
        wanted = self.all_watched_identifiers() if identifiers is None else identifiers
        material = json.dumps(
            {
                "descriptor_version": self.descriptor_version,
                "provider": self.provider_id,
                "patterns": list(self.patterns()),
                "identifiers": sorted(set(wanted)),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def load_descriptor(payload: dict[str, Any]) -> ProviderDescriptor:
    """Validate one decoded descriptor document."""
    return ProviderDescriptor.model_validate(payload)


def load_descriptor_file(path: Path) -> ProviderDescriptor:
    """Read and validate a descriptor document from disk."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DescriptorError(f"cannot read provider descriptor {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DescriptorError(f"provider descriptor {path} is not a JSON object")
    try:
        return load_descriptor(payload)
    except ValueError as exc:
        raise DescriptorError(f"provider descriptor {path} is invalid: {exc}") from exc


__all__ = [
    "DESCRIPTOR_SUFFIX",
    "ECOSYSTEMS",
    "SUPPORTED_DESCRIPTOR_VERSIONS",
    "IdentifierFamily",
    "PackageRef",
    "ProviderDescriptor",
    "load_descriptor",
    "load_descriptor_file",
]
