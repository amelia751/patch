"""Identity for the PatchAPI control plane, backed by Google Cloud Identity Platform.

Re-exports are lazy. A bare `pytest` at the repository root imports every tree,
and this one reaches httpx and google-auth; importing eagerly would make an
unrelated test run depend on those being installed.
"""

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from packages.auth.config import IdentityPlatformConfig, load_config
    from packages.auth.errors import AuthConfigurationError, AuthUnavailableError
    from packages.auth.identity_platform import (
        AuthTokens,
        AuthUser,
        IdentityPlatformService,
        get_identity_service,
        reset_identity_service,
    )

_EXPORTS: Final[dict[str, str]] = {
    "IdentityPlatformConfig": "config",
    "load_config": "config",
    "AuthConfigurationError": "errors",
    "AuthUnavailableError": "errors",
    "AuthTokens": "identity_platform",
    "AuthUser": "identity_platform",
    "IdentityPlatformService": "identity_platform",
    "get_identity_service": "identity_platform",
    "reset_identity_service": "identity_platform",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f"packages.auth.{module_name}"), name)


# Spelled out rather than derived from `_EXPORTS`: a computed `__all__` is
# invisible to linters, which then read the re-exports above as dead imports.
__all__ = [
    "AuthConfigurationError",
    "AuthTokens",
    "AuthUnavailableError",
    "AuthUser",
    "IdentityPlatformConfig",
    "IdentityPlatformService",
    "get_identity_service",
    "load_config",
    "reset_identity_service",
]
