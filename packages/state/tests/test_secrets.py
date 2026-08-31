"""Secret name rules and the vault-backed upsert, without Google or Postgres."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from packages.state.secret_manager import is_managed_resource, secret_id_for
from packages.state.secrets import SecretInputError, validate_secret_name, validate_secret_value


def test_secret_name_accepts_the_storygen_key() -> None:
    assert validate_secret_name("GOOGLE_GENERATIVE_AI_API_KEY") == "GOOGLE_GENERATIVE_AI_API_KEY"


def test_secret_name_rejects_paths_and_spaces() -> None:
    with pytest.raises(SecretInputError):
        validate_secret_name("../.env")
    with pytest.raises(SecretInputError):
        validate_secret_name("GOOGLE KEY")
    with pytest.raises(SecretInputError):
        validate_secret_name("")


def test_secret_value_cannot_be_empty() -> None:
    with pytest.raises(SecretInputError):
        validate_secret_value("")


def test_managed_resource_names_use_the_row_id() -> None:
    row_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    resource = f"projects/patch-505223/secrets/{secret_id_for(row_id)}"
    assert is_managed_resource(resource)
    assert not is_managed_resource("projects/customer/secrets/cloud-run-bound")


class MemoryVault:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.versions: dict[str, list[str]] = {}
        self.deleted: list[str] = []

    def create(self, secret_id: str, payload: str) -> str:
        name = f"projects/test/secrets/{secret_id}"
        self.created.append(name)
        self.versions.setdefault(name, []).append(payload)
        return name

    def add_version(self, resource_name: str, payload: str) -> None:
        self.versions.setdefault(resource_name, []).append(payload)

    def delete(self, resource_name: str) -> None:
        self.deleted.append(resource_name)
        self.versions.pop(resource_name, None)

    def reveal(self, resource_name: str) -> str:
        return self.versions[resource_name][-1]


class RecordingConnection:
    """Enough asyncpg surface for upsert / list / delete."""

    def __init__(self, *, owner: bool, existing: dict[str, Any] | None = None) -> None:
        self.owner = owner
        self.existing = existing
        self.inserted: dict[str, Any] | None = None
        self.updated: dict[str, Any] | None = None
        self.deleted_id: UUID | None = None
        self.workspace_ok = True
        self.default_workspace: UUID | None = None

    async def fetchval(self, query: str, *args: Any) -> Any:
        if "FROM projects" in query:
            return 1 if self.owner else None
        if "SELECT 1 FROM workspaces" in query:
            return 1 if self.workspace_ok else None
        if "SELECT id" in query and "FROM workspaces" in query:
            return self.default_workspace
        if "SELECT secret_arn" in query:
            return None if self.existing is None else self.existing.get("secret_arn")
        return None

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        if "SELECT id, secret_arn FROM project_secrets" in query:
            return self.existing
        if query.strip().startswith("UPDATE"):
            self.updated = {"id": args[0], "args": args}
            return {"id": args[0]}
        row = self.inserted or self.existing
        if row is None:
            return None
        return {
            "id": row["id"],
            "secret_name": row.get("secret_name", "GOOGLE_GENERATIVE_AI_API_KEY"),
            "secret_arn": row.get("secret_arn"),
            "type": "api_key",
            "status": "configured",
            "workspace_id": None,
            "referenced_by": [],
            "last_rotated_at": None,
            "created_at": None,
            "updated_at": None,
            "workspace_name": None,
            "workspace_path": None,
        }

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        row = self.inserted or self.existing
        if row is None:
            return []
        return [
            {
                "id": row["id"],
                "secret_name": row.get("secret_name", "GOOGLE_GENERATIVE_AI_API_KEY"),
                "secret_arn": row.get("secret_arn"),
                "type": "api_key",
                "status": "configured",
                "workspace_id": None,
                "referenced_by": [],
                "last_rotated_at": None,
                "created_at": None,
                "updated_at": None,
                "workspace_name": None,
                "workspace_path": None,
            }
        ]

    async def execute(self, query: str, *args: Any) -> str:
        if query.strip().startswith("INSERT"):
            self.inserted = {
                "id": args[0],
                "secret_name": args[3],
                "secret_arn": args[4],
                "workspace_id": args[2],
            }
            return "INSERT 0 1"
        if query.strip().startswith("DELETE"):
            self.deleted_id = args[0]
            return "DELETE 1"
        if query.strip().startswith("UPDATE"):
            self.updated = {"args": args}
            return "UPDATE 1"
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
async def test_upsert_writes_the_payload_only_to_the_vault() -> None:
    from packages.state.secrets import upsert_secret

    vault = MemoryVault()
    connection = RecordingConnection(owner=True)
    owner = uuid4()
    project = uuid4()
    row = await upsert_secret(
        RecordingPool(connection),  # type: ignore[arg-type]
        project,
        owner,
        secret_name="GOOGLE_GENERATIVE_AI_API_KEY",
        secret_value="should-never-reach-postgres",
        vault=vault,
    )

    assert row is not None
    assert row["secret_name"] == "GOOGLE_GENERATIVE_AI_API_KEY"
    assert "should-never-reach-postgres" not in str(row)
    assert connection.inserted is not None
    assert connection.inserted["secret_arn"].startswith("projects/test/secrets/patchapi-ps-")
    assert "should-never-reach-postgres" not in str(connection.inserted)
    assert vault.reveal(connection.inserted["secret_arn"]) == "should-never-reach-postgres"


@pytest.mark.asyncio
async def test_upsert_refuses_a_project_the_user_does_not_own() -> None:
    from packages.state.secrets import upsert_secret

    row = await upsert_secret(
        RecordingPool(RecordingConnection(owner=False)),  # type: ignore[arg-type]
        uuid4(),
        uuid4(),
        secret_name="GOOGLE_GENERATIVE_AI_API_KEY",
        secret_value="x",
        vault=MemoryVault(),
    )
    assert row is None


@pytest.mark.asyncio
async def test_rotate_adds_a_version_on_the_existing_resource() -> None:
    from packages.state.secrets import upsert_secret

    vault = MemoryVault()
    resource = "projects/test/secrets/patchapi-ps-existing"
    vault.versions[resource] = ["old"]
    row_id = uuid4()
    connection = RecordingConnection(
        owner=True,
        existing={
            "id": row_id,
            "secret_arn": resource,
            "secret_name": "GOOGLE_GENERATIVE_AI_API_KEY",
        },
    )
    await upsert_secret(
        RecordingPool(connection),  # type: ignore[arg-type]
        uuid4(),
        uuid4(),
        secret_name="GOOGLE_GENERATIVE_AI_API_KEY",
        secret_value="new-value",
        vault=vault,
    )
    assert vault.versions[resource] == ["old", "new-value"]
    assert vault.created == []


@pytest.mark.asyncio
async def test_upsert_without_workspace_uses_the_project_root() -> None:
    from packages.state.secrets import upsert_secret

    workspace = uuid4()
    vault = MemoryVault()
    connection = RecordingConnection(owner=True)
    connection.default_workspace = workspace
    await upsert_secret(
        RecordingPool(connection),  # type: ignore[arg-type]
        uuid4(),
        uuid4(),
        secret_name="GOOGLE_GENERATIVE_AI_API_KEY",
        secret_value="x",
        vault=vault,
    )
    assert connection.inserted is not None
    assert connection.inserted.get("workspace_id") == workspace
