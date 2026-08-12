"""Loading GitHub App credentials without letting them escape.

The service owns the App private key so that agents and sandboxes never do
(roadmap §14). Two rules follow, and both are enforced by types here rather
than by discipline at call sites:

* a secret is carried in `Secret`, whose `repr` and `str` are redacted, so a
  stray f-string, traceback frame, or structured-log field cannot print it;
* loading failures name the environment variable that was missing, never a
  value that was found.

The private key is read either from a file (local development, `.secrets/`) or
from a Secret Manager resource name (deployed). Secret Manager is reached
through a protocol so the dependency is optional and its absence is a clear
error rather than an import crash at start-up.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from cryptography.hazmat.primitives.serialization import load_pem_private_key

from patchapi_github_tools.config import (
    ENV_APP_ID,
    ENV_INSTALLATION_ID,
    ENV_PRIVATE_KEY_PATH,
    ENV_PRIVATE_KEY_SECRET,
)
from patchapi_github_tools.errors import CredentialsUnavailableError

_REDACTED: Final[str] = "<redacted>"


class Secret:
    """A string that refuses to render itself.

    `reveal()` is the single, greppable way to obtain the value; everything
    else — `repr`, `str`, `format`, JSON encoding via `__str__` — yields
    `<redacted>`.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return _REDACTED

    def __str__(self) -> str:
        return _REDACTED

    def __format__(self, _spec: str) -> str:
        return _REDACTED

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        # Hashing the value would let a dictionary probe recover it; identity
        # semantics are enough for the one place this is used as a key.
        return hash(_REDACTED)


@runtime_checkable
class SecretResolver(Protocol):
    """Resolves a Secret Manager resource name to its payload."""

    def resolve(self, resource_name: str) -> str: ...


class GoogleSecretManagerResolver:
    """Reads a secret version from Google Secret Manager.

    The client library is imported lazily: local development uses the file
    path variant and must not need the dependency installed.
    """

    def resolve(self, resource_name: str) -> str:
        try:
            from google.cloud import secretmanager
        except ImportError as exc:  # pragma: no cover - depends on deploy image
            raise CredentialsUnavailableError(
                f"{ENV_PRIVATE_KEY_SECRET} names a Secret Manager resource but "
                "google-cloud-secret-manager is not installed in this image"
            ) from exc
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(name=resource_name)
        return response.payload.data.decode("utf-8")


@dataclass(frozen=True, slots=True)
class AppCredentials:
    """Everything needed to mint an installation token, and nothing more."""

    app_id: str
    installation_id: str
    private_key_pem: Secret

    def __post_init__(self) -> None:
        if not self.app_id.isdigit():
            raise CredentialsUnavailableError(f"{ENV_APP_ID} must be the numeric GitHub App ID")
        if not self.installation_id.isdigit():
            raise CredentialsUnavailableError(
                f"{ENV_INSTALLATION_ID} must be the numeric installation ID"
            )
        # Parsing here means a malformed key fails at start-up with a named
        # cause instead of at the first signing attempt inside a run.
        try:
            load_pem_private_key(self.private_key_pem.reveal().encode("utf-8"), password=None)
        except Exception as exc:
            raise CredentialsUnavailableError(
                "the GitHub App private key is not a readable unencrypted PEM key"
            ) from exc

    def __repr__(self) -> str:
        return f"AppCredentials(app_id={self.app_id!r}, installation_id={self.installation_id!r})"


def credentials_are_configured(env: Mapping[str, str] | None = None) -> bool:
    """True when the environment names an App ID, installation, and key source."""
    source = env if env is not None else os.environ
    has_key_source = bool(
        source.get(ENV_PRIVATE_KEY_PATH, "").strip()
        or source.get(ENV_PRIVATE_KEY_SECRET, "").strip()
    )
    return (
        bool(source.get(ENV_APP_ID, "").strip())
        and bool(source.get(ENV_INSTALLATION_ID, "").strip())
        and has_key_source
    )


def load_app_credentials(
    env: Mapping[str, str] | None = None,
    *,
    secret_resolver: SecretResolver | None = None,
) -> AppCredentials:
    """Build `AppCredentials` from the environment, or fail closed.

    Raises `CredentialsUnavailableError` naming the missing variable. Callers
    that want "configured or not" without an exception use
    `credentials_are_configured`.
    """
    source = env if env is not None else os.environ

    app_id = source.get(ENV_APP_ID, "").strip()
    if not app_id:
        raise CredentialsUnavailableError(f"{ENV_APP_ID} is not set")

    installation_id = source.get(ENV_INSTALLATION_ID, "").strip()
    if not installation_id:
        raise CredentialsUnavailableError(f"{ENV_INSTALLATION_ID} is not set")

    key_path = source.get(ENV_PRIVATE_KEY_PATH, "").strip()
    secret_name = source.get(ENV_PRIVATE_KEY_SECRET, "").strip()
    if key_path and secret_name:
        raise CredentialsUnavailableError(
            f"set exactly one of {ENV_PRIVATE_KEY_PATH} or {ENV_PRIVATE_KEY_SECRET}, not both"
        )

    if key_path:
        path = Path(key_path)
        if not path.is_file():
            raise CredentialsUnavailableError(
                f"{ENV_PRIVATE_KEY_PATH} points at {key_path!r}, which is not a readable file"
            )
        pem = path.read_text(encoding="utf-8")
    elif secret_name:
        resolver = secret_resolver if secret_resolver is not None else GoogleSecretManagerResolver()
        pem = resolver.resolve(secret_name)
    else:
        raise CredentialsUnavailableError(
            f"neither {ENV_PRIVATE_KEY_PATH} nor {ENV_PRIVATE_KEY_SECRET} is set"
        )

    return AppCredentials(
        app_id=app_id,
        installation_id=installation_id,
        private_key_pem=Secret(pem),
    )
