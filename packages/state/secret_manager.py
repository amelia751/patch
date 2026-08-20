"""Google Secret Manager vault for project secret *payloads*.

Postgres stores the resource name only (`project_secrets.secret_arn`). The
bytes live here. The client library is imported inside methods so unit tests
and a laptop without the deploy extra do not need it installed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final, Protocol, runtime_checkable
from uuid import UUID

ENV_PROJECT: Final[str] = "GCP_PROJECT"
ENV_CREDENTIALS: Final[str] = "GOOGLE_APPLICATION_CREDENTIALS"
DEFAULT_CREDENTIALS_FILE: Final[str] = ".secrets/gcp-service-account.json"
SECRET_ID_PREFIX: Final[str] = "patchapi-ps-"
GCP_CONNECTION_PREFIX: Final[str] = "patchapi-gcp-"
REPLICA_LOCATION: Final[str] = "us-central1"


class SecretStoreError(RuntimeError):
    """Secret Manager could not complete the requested write or read."""


@runtime_checkable
class SecretVault(Protocol):
    """Create, rotate, delete, and reveal secret payloads.

    `reveal` is the only method that returns plaintext. Callers must not log
    or serialize that return value.
    """

    def create(self, secret_id: str, payload: str) -> str: ...

    def add_version(self, resource_name: str, payload: str) -> None: ...

    def delete(self, resource_name: str) -> None: ...

    def reveal(self, resource_name: str) -> str: ...


def secret_id_for(row_id: UUID) -> str:
    """Return a Secret Manager id bound to the Postgres row.

    Hex form stays inside `[A-Za-z0-9_-]`. The row id is the only coupling, so
    rotating the value does not rename the container.
    """
    return f"{SECRET_ID_PREFIX}{row_id.hex}"


def secret_id_for_connection(row_id: UUID) -> str:
    """Secret Manager id for a stored GCP service-account JSON."""
    return f"{GCP_CONNECTION_PREFIX}{row_id.hex}"


def resource_name(project: str, secret_id: str) -> str:
    return f"projects/{project}/secrets/{secret_id}"


def is_managed_resource(resource: str) -> bool:
    """True when this process created the container and may delete it."""
    return (
        f"/secrets/{SECRET_ID_PREFIX}" in resource
        or f"/secrets/{GCP_CONNECTION_PREFIX}" in resource
    )


def gcp_project(*, environ: dict[str, str] | None = None, base_dir: Path | None = None) -> str:
    """Return the GCP project that owns PatchAPI-managed secrets."""
    env = os.environ if environ is None else environ
    from_env = env.get(ENV_PROJECT, "").strip()
    if from_env:
        return from_env
    raw = env.get(ENV_CREDENTIALS, "").strip() or DEFAULT_CREDENTIALS_FILE
    candidate = Path(raw).expanduser()
    path = candidate if candidate.is_absolute() else (base_dir or Path.cwd()) / candidate
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecretStoreError("cannot resolve GCP project for Secret Manager") from exc
    value = payload.get("project_id") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise SecretStoreError("service-account file has no project_id")
    return value.strip()


class GoogleSecretVault:
    """Writes and reads secret versions in the PatchAPI GCP project."""

    def __init__(self, project: str) -> None:
        if not project.strip():
            raise SecretStoreError("Secret Manager project is empty")
        self._project = project.strip()

    def create(self, secret_id: str, payload: str, *, purpose: str = "project-secret") -> str:
        client = _client()
        parent = f"projects/{self._project}"
        name = resource_name(self._project, secret_id)
        try:
            client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {
                        "replication": {
                            "user_managed": {
                                "replicas": [{"location": REPLICA_LOCATION}],
                            }
                        },
                        "labels": {
                            "purpose": purpose,
                            "managed-by": "patchapi",
                        },
                    },
                }
            )
        except Exception as exc:
            raise SecretStoreError(
                f"could not create secret container: {type(exc).__name__}"
            ) from exc
        self.add_version(name, payload)
        return name

    def add_version(self, resource: str, payload: str) -> None:
        client = _client()
        try:
            client.add_secret_version(
                request={
                    "parent": resource,
                    "payload": {"data": payload.encode("utf-8")},
                }
            )
        except Exception as exc:
            raise SecretStoreError(f"could not add secret version: {type(exc).__name__}") from exc

    def delete(self, resource: str) -> None:
        client = _client()
        try:
            client.delete_secret(request={"name": resource})
        except Exception as exc:
            # Already-gone is success: the Postgres row is what the UI lists.
            if _is_not_found(exc):
                return
            raise SecretStoreError(f"could not delete secret: {type(exc).__name__}") from exc

    def reveal(self, resource: str) -> str:
        client = _client()
        version = resource if "/versions/" in resource else f"{resource}/versions/latest"
        try:
            response = client.access_secret_version(request={"name": version})
        except Exception as exc:
            raise SecretStoreError(f"could not read secret: {type(exc).__name__}") from exc
        return response.payload.data.decode("utf-8")


def _client() -> object:
    try:
        from google.cloud import secretmanager
    except ImportError as exc:  # pragma: no cover - deploy extra
        raise SecretStoreError("google-cloud-secret-manager is not installed") from exc
    return secretmanager.SecretManagerServiceClient()


def _is_not_found(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if code == 404 or getattr(code, "value", None) == 404:
        return True
    name = type(exc).__name__
    return name in {"NotFound", "NotFoundError"}
