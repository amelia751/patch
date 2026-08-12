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

EGAKI = RepositoryRef(owner="amelia751", name="egaki")
PINNED_SHA = "c09e1a44200ff5e951746e013035e68aeb3a14b1"


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
    assert CommitRef(repo=EGAKI, sha=PINNED_SHA).sha == PINNED_SHA
    with pytest.raises(ValueError):
        CommitRef(repo=EGAKI, sha="c09e1a4")
    with pytest.raises(ValueError):
        CommitRef(repo=EGAKI, sha="main")


def test_repository_ref_round_trip():
    assert RepositoryRef.parse("amelia751/egaki") == EGAKI
    assert EGAKI.full_name == "amelia751/egaki"
    with pytest.raises(ValueError):
        RepositoryRef.parse("egaki")


def test_pull_request_url():
    assert PullRequestRef(repo=EGAKI, number=7).url == "https://github.com/amelia751/egaki/pull/7"
    with pytest.raises(ValueError):
        PullRequestRef(repo=EGAKI, number=0)
