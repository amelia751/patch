"""GCP connection JSON goes to the vault; Postgres stores a pointer only."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from packages.state.gcp_connections import (
    GcpConnectionError,
    delete_connection,
    parse_service_account_json,
    reveal_latest_connection,
    upsert_connection,
)
from packages.state.secret_manager import is_managed_resource, secret_id_for_connection

_SA = {
    "type": "service_account",
    "project_id": "artful-journey-486915-a8",
    "client_email": "patchapi-viewer@artful-journey-486915-a8.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n",
}
_SA_JSON = json.dumps(_SA)


def test_parse_accepts_a_service_account_object() -> None:
    project, email = parse_service_account_json(_SA_JSON)
    assert project == "artful-journey-486915-a8"
    assert email.startswith("patchapi-viewer@")


def test_parse_rejects_a_non_service_account() -> None:
    with pytest.raises(GcpConnectionError):
        parse_service_account_json('{"type":"authorized_user","client_email":"x@y"}')


def test_connection_resource_names_use_the_row_id() -> None:
    row_id = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    resource = f"projects/patch-505223/secrets/{secret_id_for_connection(row_id)}"
    assert is_managed_resource(resource)
    assert resource.endswith(f"patchapi-gcp-{row_id.hex}")


class MemoryVault:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.versions: dict[str, list[str]] = {}
        self.deleted: list[str] = []

    def create(self, secret_id: str, payload: str, *, purpose: str = "project-secret") -> str:
        name = f"projects/test/secrets/{secret_id}"
        self.created.append(name)
        self.versions.setdefault(name, []).append(payload)
        assert purpose in {"project-secret", "gcp-connection"}
        return name

    def add_version(self, resource_name: str, payload: str) -> None:
        self.versions.setdefault(resource_name, []).append(payload)

    def delete(self, resource_name: str) -> None:
        self.deleted.append(resource_name)
        self.versions.pop(resource_name, None)

    def reveal(self, resource_name: str) -> str:
        return self.versions[resource_name][-1]


class RecordingConnection:
    def __init__(self, *, owner: bool, existing: dict[str, Any] | None = None) -> None:
        self.owner = owner
        self.existing = existing
        self.inserted: dict[str, Any] | None = None
        self.workspace_ok = True
        self.default_workspace: UUID | None = None
        self.statements: list[str] = []

    async def fetchval(self, query: str, *args: Any) -> Any:
        if "FROM projects" in query:
            return 1 if self.owner else None
        if "SELECT 1 FROM workspaces" in query:
            return 1 if self.workspace_ok else None
        if "SELECT id" in query and "FROM workspaces" in query:
            return self.default_workspace
        return None

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        if "SELECT id, secret_arn FROM gcp_connections" in query:
            return self.existing
        row = self.inserted or self.existing
        if row is None:
            return None
        return {
            "id": row["id"],
            "environment": "development",
            "gcp_project_id": "artful-journey-486915-a8",
            "gcp_project_number": None,
            "service_account_email": _SA["client_email"],
            "default_region": "us-central1",
            "secret_arn": row.get("secret_arn"),
            "workspace_id": row.get("workspace_id"),
            "last_validated_at": None,
            "created_at": None,
            "updated_at": None,
            "workspace_name": None,
            "workspace_path": None,
            "repo_url": "https://github.com/amelia751/storygen.git",
        }

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        row = await self.fetchrow("SELECT listed",)
        return [] if row is None else [row]

    async def execute(self, query: str, *args: Any) -> str:
        self.statements.append(" ".join(query.split()))
        if query.strip().startswith("INSERT"):
            self.inserted = {
                "id": args[0],
                "workspace_id": args[2],
                "secret_arn": args[7],
            }
            return "INSERT 0 1"
        return "OK"


class RecordingPool:
    def __init__(self, connection: RecordingConnection) -> None:
        self._connection = connection

    def acquire(self) -> Any:
        connection = self._connection

        class _Acquire:
            async def __aenter__(self) -> RecordingConnection:
                return connection

            async def __aexit__(self, *_: Any) -> bool:
                return False

        return _Acquire()


@pytest.mark.asyncio
async def test_upsert_writes_the_json_only_to_the_vault() -> None:
    vault = MemoryVault()
    connection = RecordingConnection(owner=True)
    row = await upsert_connection(
        RecordingPool(connection),  # type: ignore[arg-type]
        uuid4(),
        uuid4(),
        credentials_json=_SA_JSON,
        vault=vault,
    )

    assert row is not None
    assert row["gcp_project_id"] == "artful-journey-486915-a8"
    assert _SA_JSON not in str(row)
    assert "BEGIN PRIVATE KEY" not in str(row)
    assert connection.inserted is not None
    assert connection.inserted["secret_arn"].startswith("projects/test/secrets/patchapi-gcp-")
    assert _SA_JSON not in str(connection.inserted)
    assert vault.reveal(connection.inserted["secret_arn"]) == _SA_JSON


@pytest.mark.asyncio
async def test_upsert_refuses_a_project_the_user_does_not_own() -> None:
    row = await upsert_connection(
        RecordingPool(RecordingConnection(owner=False)),  # type: ignore[arg-type]
        uuid4(),
        uuid4(),
        credentials_json=_SA_JSON,
        vault=MemoryVault(),
    )
    assert row is None


@pytest.mark.asyncio
async def test_reveal_latest_returns_the_stored_json() -> None:
    vault = MemoryVault()
    resource = vault.create("patchapi-gcp-latest", _SA_JSON, purpose="gcp-connection")
    connection = RecordingConnection(
        owner=True, existing={"id": uuid4(), "secret_arn": resource}
    )
    loaded = await reveal_latest_connection(RecordingPool(connection), uuid4(), vault)  # type: ignore[arg-type]
    assert loaded is not None
    meta, payload = loaded
    assert payload == _SA_JSON
    assert meta["gcp_project_id"] == "artful-journey-486915-a8"
    assert meta["default_region"] == "us-central1"

@pytest.mark.asyncio
async def test_disconnecting_the_last_connection_un_chooses_gcp() -> None:
    """Connecting sets `projects.cloud_provider`; disconnecting has to clear it.

    Without the mirror the console kept offering a connected GCP account for a
    project whose connection had been deleted.
    """
    row_id = uuid4()
    connection = RecordingConnection(
        owner=True, existing={"id": row_id, "secret_arn": "projects/test/secrets/patchapi-gcp-x"}
    )
    deleted = await delete_connection(
        RecordingPool(connection),  # type: ignore[arg-type]
        uuid4(),
        uuid4(),
        row_id,
        MemoryVault(),
    )

    assert deleted is True
    release = [item for item in connection.statements if "cloud_provider = NULL" in item]
    assert len(release) == 1
    assert "NOT EXISTS ( SELECT 1 FROM gcp_connections" in release[0]
