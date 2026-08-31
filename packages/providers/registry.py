"""Which providers this build can detect, and where that answer comes from.

Three sources, in increasing order of precedence:

1. Descriptor documents shipped under `packages/providers/descriptors/`.
2. Extra directories named by `PATCHAPI_PROVIDER_DESCRIPTOR_DIR` (colon
   separated), for an operator adding a provider without a release.
3. `register()`, used by the loader that materialises descriptors stored in
   Postgres, so onboarding a provider is a row rather than a deploy.

Reads fail closed. `descriptor_for` on an unregistered slug raises rather than
returning an empty descriptor, because a provider with no patterns finds
nothing and a caller cannot tell that from a clean repository.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Final

from packages.providers.descriptor import (
    DESCRIPTOR_SUFFIX,
    ProviderDescriptor,
    load_descriptor_file,
)
from packages.providers.errors import UnknownProviderError

log = logging.getLogger(__name__)

BUILTIN_DESCRIPTOR_DIR: Final[Path] = Path(__file__).resolve().parent / "descriptors"

ENV_DESCRIPTOR_DIRS: Final[str] = "PATCHAPI_PROVIDER_DESCRIPTOR_DIR"

# Registry mutation happens at import, at worker startup when descriptors are
# loaded from Postgres, and in tests. A lock keeps a concurrent read from seeing
# a half-replaced mapping.
_LOCK: Final[threading.Lock] = threading.Lock()
_DESCRIPTORS: dict[str, ProviderDescriptor] = {}
_LOADED: bool = False


def register(descriptor: ProviderDescriptor) -> ProviderDescriptor:
    """Add or replace one provider's descriptor. Returns what was registered.

    Replacement is deliberate: a descriptor loaded from Postgres supersedes the
    one shipped in the image, which is what lets an operator widen a watchlist
    without waiting for a release.
    """
    with _LOCK:
        _DESCRIPTORS[descriptor.provider_id] = descriptor
    return descriptor


def unregister(provider: str) -> None:
    """Drop one descriptor. Used by tests to restore a known registry."""
    with _LOCK:
        _DESCRIPTORS.pop(provider, None)


def load_directory(directory: Path) -> tuple[ProviderDescriptor, ...]:
    """Register every descriptor document in `directory`, sorted by filename.

    A missing directory registers nothing and is not an error: the extra-dir
    hook is optional, and an operator who set no override should not get a
    crash. A malformed document *is* an error — a descriptor that silently
    failed to load would narrow a scan without saying so.
    """
    if not directory.is_dir():
        return ()
    loaded: list[ProviderDescriptor] = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() != DESCRIPTOR_SUFFIX:
            continue
        loaded.append(register(load_descriptor_file(path)))
    return tuple(loaded)


def _extra_dirs() -> tuple[Path, ...]:
    raw = os.environ.get(ENV_DESCRIPTOR_DIRS, "").strip()
    return tuple(Path(part) for part in raw.split(os.pathsep) if part.strip())


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    with _LOCK:
        if _LOADED:
            return
        _LOADED = True
    load_directory(BUILTIN_DESCRIPTOR_DIR)
    for directory in _extra_dirs():
        load_directory(directory)


def reload_builtin() -> None:
    """Re-read the shipped descriptors. Used by tests after mutating the registry."""
    global _LOADED
    with _LOCK:
        _DESCRIPTORS.clear()
        _LOADED = False
    _ensure_loaded()


def descriptor_for(provider: str) -> ProviderDescriptor:
    """The descriptor for `provider`, or raise `UnknownProviderError`."""
    _ensure_loaded()
    slug = provider.strip()
    try:
        return _DESCRIPTORS[slug]
    except KeyError as exc:
        known = ", ".join(known_providers()) or "none"
        raise UnknownProviderError(
            f"no provider descriptor registered for {provider!r}; registered providers: {known}"
        ) from exc


def has_provider(provider: str) -> bool:
    """Whether a descriptor is registered, without raising."""
    _ensure_loaded()
    return provider.strip() in _DESCRIPTORS


def known_providers() -> tuple[str, ...]:
    """Every registered provider slug, sorted."""
    _ensure_loaded()
    return tuple(sorted(_DESCRIPTORS))


def descriptors() -> tuple[ProviderDescriptor, ...]:
    """Every registered descriptor, ordered by slug."""
    _ensure_loaded()
    return tuple(_DESCRIPTORS[slug] for slug in known_providers())


def provider_for_identifier(identifier: str) -> str | None:
    """Which provider owns this identifier, or `None` when no descriptor claims it.

    Checked against pinned literals first, then family patterns. A pin is an
    exact statement about one identifier and a pattern is a guess about a shape,
    so the exact answer wins where both could apply.

    `None` rather than a default: guessing an owner would send an identifier to
    a provider's live surface that has never heard of it, and read the resulting
    404 as a retirement.
    """
    wanted = identifier.strip()
    if not wanted:
        return None
    for descriptor in descriptors():
        if wanted in descriptor.all_watched_identifiers():
            return descriptor.provider_id
    for descriptor in descriptors():
        if any(re.search(pattern, wanted) for pattern in descriptor.patterns()):
            return descriptor.provider_id
    return None


__all__ = [
    "BUILTIN_DESCRIPTOR_DIR",
    "ENV_DESCRIPTOR_DIRS",
    "descriptor_for",
    "descriptors",
    "has_provider",
    "known_providers",
    "load_directory",
    "provider_for_identifier",
    "register",
    "reload_builtin",
    "unregister",
]
