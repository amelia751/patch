"""Google provider adapter.

Reads the untrusted Google deprecation feed, normalizes it into a
`ChangeManifest`, and calls the pinned Gemini reasoning model on Vertex.

Names resolve on first access. Importing this package must not require Pydantic
or google-auth: a bare `pytest` at the repo root collects every tree in the
workspace-root environment, which installs neither, and an eager import here
would abort collection for all of them.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - resolved statically, never at runtime
    from packages.providers.google.config import (
        ADAPTER_VERSION,
        DEFAULT_IMAGE_MODEL,
        DEFAULT_REASONING_MODEL,
        DEFAULT_VERTEX_LOCATION,
        MINIMUM_IMAGE_GENERATION,
        MINIMUM_REASONING_GENERATION,
        PROVIDER_ID,
        SEVERITY_BY_CHANGE_TYPE,
        SUPPORTED_FEED_VERSIONS,
        GoogleProviderConfig,
        load_config,
        parse_gemini_generation,
        require_supported_image_model,
        require_supported_reasoning_model,
        severity_for,
    )
    from packages.providers.google.deprecation_feed import (
        FeedCapabilityNotes,
        FeedSourceSnapshot,
        FeedTrust,
        FeedVerificationRequirements,
        GoogleDeprecationNotice,
        SnapshotStatus,
    )
    from packages.providers.google.errors import (
        GoogleProviderError,
        MissingCredentialsError,
        ProviderConfigurationError,
        ProviderEvidenceError,
        UnsupportedModelError,
        VertexCallError,
    )
    from packages.providers.google.normalize import (
        load_notice,
        load_notice_file,
        manifest_from_feed_file,
        notice_to_manifest,
    )
    from packages.providers.google.snapshot import (
        sha256_file,
        sha256_hex,
        snapshot_from_file,
        snapshot_matches_file,
    )
    from packages.providers.google.vertex import (
        VertexClient,
        VertexTextResponse,
        credentials_available,
    )

_EXPORTS: dict[str, str] = {
    "ADAPTER_VERSION": "config",
    "DEFAULT_IMAGE_MODEL": "config",
    "DEFAULT_REASONING_MODEL": "config",
    "DEFAULT_VERTEX_LOCATION": "config",
    "MINIMUM_IMAGE_GENERATION": "config",
    "MINIMUM_REASONING_GENERATION": "config",
    "PROVIDER_ID": "config",
    "SEVERITY_BY_CHANGE_TYPE": "config",
    "SUPPORTED_FEED_VERSIONS": "config",
    "FeedCapabilityNotes": "deprecation_feed",
    "FeedSourceSnapshot": "deprecation_feed",
    "FeedTrust": "deprecation_feed",
    "FeedVerificationRequirements": "deprecation_feed",
    "GoogleDeprecationNotice": "deprecation_feed",
    "GoogleProviderConfig": "config",
    "GoogleProviderError": "errors",
    "MissingCredentialsError": "errors",
    "ProviderConfigurationError": "errors",
    "ProviderEvidenceError": "errors",
    "SnapshotStatus": "deprecation_feed",
    "UnsupportedModelError": "errors",
    "VertexCallError": "errors",
    "VertexClient": "vertex",
    "VertexTextResponse": "vertex",
    "credentials_available": "vertex",
    "load_config": "config",
    "load_notice": "normalize",
    "load_notice_file": "normalize",
    "manifest_from_feed_file": "normalize",
    "notice_to_manifest": "normalize",
    "parse_gemini_generation": "config",
    "require_supported_image_model": "config",
    "require_supported_reasoning_model": "config",
    "severity_for": "config",
    "sha256_file": "snapshot",
    "sha256_hex": "snapshot",
    "snapshot_from_file": "snapshot",
    "snapshot_matches_file": "snapshot",
}

# Spelled out rather than derived from `_EXPORTS` so the public surface is
# readable statically. A test asserts the two stay in step.
__all__ = [
    "ADAPTER_VERSION",
    "DEFAULT_IMAGE_MODEL",
    "DEFAULT_REASONING_MODEL",
    "DEFAULT_VERTEX_LOCATION",
    "MINIMUM_IMAGE_GENERATION",
    "MINIMUM_REASONING_GENERATION",
    "PROVIDER_ID",
    "SEVERITY_BY_CHANGE_TYPE",
    "SUPPORTED_FEED_VERSIONS",
    "FeedCapabilityNotes",
    "FeedSourceSnapshot",
    "FeedTrust",
    "FeedVerificationRequirements",
    "GoogleDeprecationNotice",
    "GoogleProviderConfig",
    "GoogleProviderError",
    "MissingCredentialsError",
    "ProviderConfigurationError",
    "ProviderEvidenceError",
    "SnapshotStatus",
    "UnsupportedModelError",
    "VertexCallError",
    "VertexClient",
    "VertexTextResponse",
    "credentials_available",
    "load_config",
    "load_notice",
    "load_notice_file",
    "manifest_from_feed_file",
    "notice_to_manifest",
    "parse_gemini_generation",
    "require_supported_image_model",
    "require_supported_reasoning_model",
    "severity_for",
    "sha256_file",
    "sha256_hex",
    "snapshot_from_file",
    "snapshot_matches_file",
]


def __getattr__(name: str) -> Any:
    """Load the submodule that owns `name`, then cache the binding."""
    try:
        submodule = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(f"{__name__}.{submodule}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
