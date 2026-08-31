"""One interface every provider is reached through.

Two questions have provider-shaped answers, and before this module both were
answered by importing the Google adapter directly:

* *What does this notice say?* — now provider-neutral. `packages.providers.notice`
  parses any registered provider's document, so `parse_notice` is inherited by
  every adapter and overridden by none so far.
* *Does this identifier still resolve?* — genuinely provider-specific. Google
  answers it by listing published models on the Gemini and Vertex surfaces.
  Nobody else has that surface, so the default answers what it honestly can:
  package registries for SDK identifiers, `UNKNOWN` for everything else.

`UNKNOWN` is the load-bearing default. It means "the check could not run", never
"the identifier is gone", so a provider with no liveness surface degrades into
"corroborate this from the notice" rather than into a wave of false retirements.

A provider with a descriptor and no bespoke module gets `DescriptorAdapter` and
works. Registering a bespoke one is `register_adapter`, and is only worth doing
for a provider that has a surface worth asking.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from packages.providers import registry
from packages.providers.notice import manifest_from_notice_file

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    from collections.abc import Sequence
    from pathlib import Path

    from packages.providers.live_result import LiveResult
    from packages.schemas.change_manifest import ChangeManifest


@runtime_checkable
class ProviderAdapter(Protocol):
    """What PatchAPI asks of a provider, whoever the provider is."""

    provider_id: str

    def parse_notice(self, path: Path, *, base_dir: Path | None = None) -> ChangeManifest:
        """Normalize one notice document into the versioned agent contract."""
        ...

    async def live_identifiers(
        self, identifiers: Sequence[str], *, base_dir: Path | None = None
    ) -> tuple[LiveResult, ...]:
        """Ask the provider's own surface whether each identifier still resolves."""
        ...


class DescriptorAdapter:
    """The adapter a provider gets from its descriptor alone.

    Enough to onboard a provider with no code: notices parse, and SDK
    identifiers are checked against the registry that publishes them.
    """

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id

    def parse_notice(self, path: Path, *, base_dir: Path | None = None) -> ChangeManifest:
        return manifest_from_notice_file(path, base_dir=base_dir)

    async def live_identifiers(
        self, identifiers: Sequence[str], *, base_dir: Path | None = None
    ) -> tuple[LiveResult, ...]:
        """Package registries for SDK identifiers; `UNKNOWN` for the rest.

        A model ID or an API version has no registry to ask, and inventing an
        answer for it would be worse than admitting the check did not run.
        """
        from packages.providers import sdk
        from packages.providers.live_result import LiveResult, LiveStatus

        checked = await sdk.live_packages(identifiers)
        answered = {result.identifier for result in checked}
        unknown = tuple(
            LiveResult(
                identifier=identifier,
                surface=self.provider_id,
                status=LiveStatus.UNKNOWN,
                checked_at="",
                detail=(
                    f"{self.provider_id} publishes no liveness surface PatchAPI can query for "
                    "this identifier; corroborate from the notice and an official page"
                ),
                source_url="",
            )
            for identifier in identifiers
            if identifier not in answered
        )
        return checked + unknown


class GoogleAdapter(DescriptorAdapter):
    """Adds the Gemini and Vertex model listings to the descriptor default."""

    def __init__(self) -> None:
        super().__init__("google")

    async def live_identifiers(
        self, identifiers: Sequence[str], *, base_dir: Path | None = None
    ) -> tuple[LiveResult, ...]:
        # Imported here rather than at module scope: the listing needs
        # google-auth, and a build that only reads notices must not pay for it.
        from packages.providers.google.live import live_identifiers as google_live

        return await google_live(list(identifiers), base_dir=base_dir)


_LOCK: Final[threading.Lock] = threading.Lock()
_ADAPTERS: dict[str, ProviderAdapter] = {"google": GoogleAdapter()}


def register_adapter(adapter: ProviderAdapter) -> ProviderAdapter:
    """Register a bespoke adapter, replacing any adapter for the same provider."""
    with _LOCK:
        _ADAPTERS[adapter.provider_id] = adapter
    return adapter


def adapter_for(provider: str) -> ProviderAdapter:
    """The adapter for `provider`.

    Raises `UnknownProviderError` when no descriptor is registered: an adapter
    for a provider PatchAPI cannot describe would parse notices it has no
    patterns to act on.
    """
    descriptor = registry.descriptor_for(provider)
    with _LOCK:
        existing = _ADAPTERS.get(descriptor.provider_id)
    if existing is not None:
        return existing
    return register_adapter(DescriptorAdapter(descriptor.provider_id))


__all__ = [
    "DescriptorAdapter",
    "GoogleAdapter",
    "ProviderAdapter",
    "adapter_for",
    "register_adapter",
]
