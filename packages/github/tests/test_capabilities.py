import pytest

from packages.github import (
    FORBIDDEN_CAPABILITIES,
    READ_CAPABILITIES,
    WRITE_CAPABILITIES,
    Capability,
    CommitRef,
    ForbiddenCapabilityError,
    PullRequestRef,
    RepositoryRef,
    UnknownCapabilityError,
    is_write_capability,
    resolve_capability,
)

STORYGEN = RepositoryRef(owner="amelia751", name="storygen")
PINNED_SHA = "c5428cdcdcd12204e1f4cc47c393dc6e738d88b2"


def test_read_capability_resolves():
    assert resolve_capability("get_file") is Capability.GET_FILE
    assert not is_write_capability(Capability.GET_FILE)


def test_write_capability_resolves_and_is_classified():
    assert is_write_capability(resolve_capability("open_pull_request"))
    assert READ_CAPABILITIES.isdisjoint(WRITE_CAPABILITIES)
    assert READ_CAPABILITIES | WRITE_CAPABILITIES == frozenset(Capability)


@pytest.mark.parametrize("name", sorted(FORBIDDEN_CAPABILITIES))
def test_forbidden_capabilities_are_refused(name):
    with pytest.raises(ForbiddenCapabilityError):
        resolve_capability(name)


def test_forbidden_names_are_not_enum_members():
    assert FORBIDDEN_CAPABILITIES.isdisjoint({c.value for c in Capability})


def test_unknown_capability_fails_closed():
    with pytest.raises(UnknownCapabilityError):
        resolve_capability("get_file_but_also_merge")


def test_commit_ref_requires_a_full_sha():
    assert CommitRef(repo=STORYGEN, sha=PINNED_SHA).sha == PINNED_SHA
    with pytest.raises(ValueError):
        CommitRef(repo=STORYGEN, sha="c09e1a4")
    with pytest.raises(ValueError):
        CommitRef(repo=STORYGEN, sha="main")


def test_repository_ref_round_trip():
    assert RepositoryRef.parse("amelia751/storygen") == STORYGEN
    assert STORYGEN.full_name == "amelia751/storygen"
    with pytest.raises(ValueError):
        RepositoryRef.parse("storygen")


def test_pull_request_url():
    assert (
        PullRequestRef(repo=STORYGEN, number=7).url
        == "https://github.com/amelia751/storygen/pull/7"
    )
    with pytest.raises(ValueError):
        PullRequestRef(repo=STORYGEN, number=0)
