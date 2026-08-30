"""The Vertex Memory Bank adapter, against a recorded transport.

No network: the point of these is the encoding contract between a write and the
recall that has to match it, plus the guarantee that an unreachable engine is
distinguishable from an empty one.
"""

from typing import Any

import pytest

from packages.memory import MemoryUnavailableError, PreviousMigration, RepositoryProfile
from packages.memory.config import (
    ENV_CLOUD_PROJECT,
    ENV_MEMORY_BANK_ENGINE,
    KIND_MIGRATION,
    KIND_PROFILE,
    PROFILE_MARKER,
    SCOPE_KIND,
    SCOPE_REPO,
)
from packages.memory.vertex import VertexMemoryBank, memory_bank_unavailable_reason

REPO = "amelia751/egaki"
ENGINE = "projects/p/locations/us-central1/reasoningEngines/123"


class FakeTransport:
    """An in-memory stand-in for the Agent Engine memories surface."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.memories: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str]] = []
        self._next_id = 0

    def request(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, url))
        if self.fail:
            raise MemoryUnavailableError("503 from Memory Bank: unavailable")
        if method == "POST" and url.endswith(":retrieve"):
            assert body is not None
            wanted = body["scope"]
            return {
                "retrievedMemories": [
                    {"memory": memory} for memory in self.memories if memory["scope"] == wanted
                ]
            }
        if method == "POST" and url.endswith("/memories"):
            assert body is not None
            self._next_id += 1
            self.memories.append(
                {
                    "name": f"{ENGINE}/memories/{self._next_id}",
                    "fact": body["fact"],
                    "scope": body["scope"],
                }
            )
            return {"done": True}
        if method == "GET" and url.endswith("/memories"):
            return {"memories": list(self.memories)}
        if method == "DELETE":
            name = url.split("/v1/", 1)[1]
            self.memories = [m for m in self.memories if m["name"] != name]
            return {}
        raise AssertionError(f"unexpected call {method} {url}")


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def bank(transport):
    return VertexMemoryBank(engine=ENGINE, transport=transport)


@pytest.fixture
def profile():
    return RepositoryProfile(
        repo=REPO,
        owner_team="media-platform",
        criticality="medium",
        approval_rules=("human_review_required",),
        prohibited_paths=(".github/workflows/**",),
    )


def test_profile_round_trips_through_one_json_fact(bank, transport, profile):
    bank.remember(profile)

    stored = [m for m in transport.memories if m["scope"][SCOPE_KIND] == KIND_PROFILE]
    assert len(stored) == 1
    assert stored[0]["fact"].startswith(PROFILE_MARKER)
    assert stored[0]["scope"] == {SCOPE_REPO: REPO, SCOPE_KIND: KIND_PROFILE}
    assert bank.recall(REPO) == profile


def test_recall_returns_none_for_an_unknown_repository(bank):
    assert bank.recall("nobody/nothing") is None


def test_remember_replaces_rather_than_accumulates(bank, transport, profile):
    bank.remember(profile)
    bank.remember(RepositoryProfile(repo=REPO, owner_team="platform"))

    profiles = [m for m in transport.memories if m["scope"][SCOPE_KIND] == KIND_PROFILE]
    assert len(profiles) == 1
    recalled = bank.recall(REPO)
    assert recalled is not None
    assert recalled.owner_team == "platform"
    assert recalled.approval_rules == ()


def test_migration_is_stored_as_prose_under_its_own_kind(bank, transport):
    bank.record_migration(
        REPO,
        PreviousMigration(
            migration_id="google-image-migration-2026-05",
            decision="rejected",
            reason="compatibility issue",
        ),
    )

    stored = [m for m in transport.memories if m["scope"][SCOPE_KIND] == KIND_MIGRATION]
    assert len(stored) == 1
    assert PROFILE_MARKER not in stored[0]["fact"]
    assert "rejected" in stored[0]["fact"]
    assert bank.recall_migrations(REPO) == (stored[0]["fact"],)


def test_a_migration_is_never_mistaken_for_a_profile(bank):
    bank.record_migration(REPO, PreviousMigration(migration_id="m1", decision="merged", reason=""))
    assert bank.recall(REPO) is None


def test_an_unreadable_profile_is_skipped_not_raised(bank, transport):
    transport.memories.append(
        {
            "name": f"{ENGINE}/memories/99",
            "fact": f"{PROFILE_MARKER} {{not json",
            "scope": {SCOPE_REPO: REPO, SCOPE_KIND: KIND_PROFILE},
        }
    )
    assert bank.recall(REPO) is None


def test_an_unreachable_engine_is_not_an_empty_one():
    """The distinction the policy layer depends on: absent context must not read
    as absent prohibitions."""
    bank = VertexMemoryBank(engine=ENGINE, transport=FakeTransport(fail=True))
    with pytest.raises(MemoryUnavailableError):
        bank.recall(REPO)


def test_from_env_reports_what_is_missing():
    assert memory_bank_unavailable_reason({}) is not None
    assert ENV_MEMORY_BANK_ENGINE in memory_bank_unavailable_reason({})
    bare = {ENV_MEMORY_BANK_ENGINE: "123"}
    assert ENV_CLOUD_PROJECT in memory_bank_unavailable_reason(bare)
    with pytest.raises(MemoryUnavailableError):
        VertexMemoryBank.from_env({})


def test_a_bare_engine_id_resolves_against_the_configured_project():
    bank = VertexMemoryBank.from_env({ENV_MEMORY_BANK_ENGINE: "123", ENV_CLOUD_PROJECT: "p"})
    assert bank._engine == ENGINE
