"""HTTP handlers never echo a secret value, even when the vault has one."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.state.project_routes import router as project_router
from packages.state.session import COOKIE_NAME, issue

OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")
PROJECT_ID = UUID("33333333-3333-4333-8333-333333333333")
SESSION_SECRET = "test-session-secret"
PAYLOAD = "AIza-this-must-never-appear-in-a-response"


class MemoryVault:
    def __init__(self) -> None:
        self.payloads: dict[str, str] = {}

    def create(self, secret_id: str, payload: str) -> str:
        name = f"projects/test/secrets/{secret_id}"
        self.payloads[name] = payload
        return name

    def add_version(self, resource_name: str, payload: str) -> None:
        self.payloads[resource_name] = payload

    def delete(self, resource_name: str) -> None:
        self.payloads.pop(resource_name, None)

    def reveal(self, resource_name: str) -> str:
        return self.payloads[resource_name]


class FakeConnection:
    def __init__(self, *, owner_id: UUID) -> None:
        self._owner_id = owner_id
        self.rows: list[dict[str, Any]] = []

    async def fetchval(self, query: str, *args: Any) -> Any:
        if "FROM projects" in query:
            return 1 if args[1] == self._owner_id else None
        return None

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        if "SELECT id, secret_arn FROM project_secrets" in query:
            name = args[1]
            for row in self.rows:
                if row["secret_name"] == name:
                    return {"id": UUID(row["id"]), "secret_arn": row["secret_arn"]}
            return None
        if query.strip().startswith("UPDATE"):
            return {"id": args[0]}
        return None

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return list(self.rows)

    async def execute(self, query: str, *args: Any) -> str:
        if query.strip().startswith("INSERT"):
            self.rows.append(
                {
                    "id": str(args[0]),
                    "secret_name": args[3],
                    "secret_arn": args[4],
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
            )
        if query.strip().startswith("DELETE"):
            self.rows = [row for row in self.rows if row["id"] != str(args[0])]
        return "OK"


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def acquire(self) -> Any:
        connection = self._connection

        class _Acquire:
            async def __aenter__(self) -> FakeConnection:
                return connection

            async def __aexit__(self, *_: Any) -> bool:
                return False

        return _Acquire()


def _client(
    connection: FakeConnection, monkeypatch: pytest.MonkeyPatch, *, user: UUID = OWNER_ID
) -> TestClient:
    vault = MemoryVault()
    monkeypatch.setenv("PATCHAPI_SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setattr("packages.state.project_routes.GoogleSecretVault", lambda _project: vault)
    monkeypatch.setattr("packages.state.project_routes.gcp_project", lambda: "test")
    app = FastAPI()
    app.include_router(project_router)
    app.state.postgres_pool = FakePool(connection)
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(COOKIE_NAME, issue(user, SESSION_SECRET))
    client._vault = vault  # type: ignore[attr-defined]
    return client


def test_list_requires_a_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATCHAPI_SESSION_SECRET", SESSION_SECRET)
    app = FastAPI()
    app.include_router(project_router)
    app.state.postgres_pool = FakePool(FakeConnection(owner_id=OWNER_ID))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(f"/api/projects/{PROJECT_ID}/secrets")
    assert response.status_code == 401


def test_list_is_empty_and_has_no_value_field(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(FakeConnection(owner_id=OWNER_ID), monkeypatch).get(
        f"/api/projects/{PROJECT_ID}/secrets"
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"secrets": []}
    assert "secret_value" not in response.text


def test_post_stores_the_value_in_the_vault_only(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection(owner_id=OWNER_ID)
    client = _client(connection, monkeypatch)
    response = client.post(
        f"/api/projects/{PROJECT_ID}/secrets",
        json={"secret_name": "GOOGLE_GENERATIVE_AI_API_KEY", "secret_value": PAYLOAD},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["secret_name"] == "GOOGLE_GENERATIVE_AI_API_KEY"
    assert body["secret_arn"].startswith("projects/test/secrets/patchapi-ps-")
    assert PAYLOAD not in response.text
    assert "secret_value" not in body
    listed = client.get(f"/api/projects/{PROJECT_ID}/secrets")
    assert listed.status_code == 200
    assert PAYLOAD not in listed.text
    vault = client._vault  # type: ignore[attr-defined]
    assert PAYLOAD in vault.payloads.values()


def test_post_to_someone_elses_project_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(FakeConnection(owner_id=OWNER_ID), monkeypatch, user=OTHER_ID).post(
        f"/api/projects/{PROJECT_ID}/secrets",
        json={"secret_name": "GOOGLE_GENERATIVE_AI_API_KEY", "secret_value": PAYLOAD},
    )
    assert response.status_code == 404
    assert PAYLOAD not in response.text


def test_delete_removes_the_row(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection(owner_id=OWNER_ID)
    client = _client(connection, monkeypatch)
    created = client.post(
        f"/api/projects/{PROJECT_ID}/secrets",
        json={"secret_name": "GOOGLE_GENERATIVE_AI_API_KEY", "secret_value": PAYLOAD},
    )
    assert created.status_code == 201
    deleted = client.delete(f"/api/projects/{PROJECT_ID}/secrets/GOOGLE_GENERATIVE_AI_API_KEY")
    assert deleted.status_code == 200
    listed = client.get(f"/api/projects/{PROJECT_ID}/secrets")
    assert listed.json() == {"secrets": []}
