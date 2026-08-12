import pytest

from packages.memory import (
    LocalMemoryBank,
    MemoryBankClient,
    PreviousMigration,
    RepositoryProfile,
)

EGAKI = "amelia751/egaki"


@pytest.fixture
def profile():
    """The roadmap §10.2 example, as a profile."""
    return RepositoryProfile(
        repo=EGAKI,
        owner_team="media-platform",
        criticality="medium",
        provider_dependencies=("google",),
        approval_rules=("human_review_required",),
        previous_migrations=(
            PreviousMigration(
                migration_id="google-image-migration-2026-05",
                decision="rejected",
                reason="compatibility issue",
            ),
        ),
        canonical_test_commands=("pnpm --dir cli build", "pnpm --dir cli test"),
        prohibited_paths=(".github/workflows/**",),
    )


def test_local_bank_satisfies_the_client_protocol():
    assert isinstance(LocalMemoryBank(), MemoryBankClient)


def test_recall_returns_none_for_an_unknown_repository():
    assert LocalMemoryBank().recall("someone/never-seen") is None


def test_remember_then_recall(profile):
    bank = LocalMemoryBank()
    bank.remember(profile)

    assert bank.recall(EGAKI) == profile
    assert bank.recall(EGAKI).requires_human_review


def test_previous_rejection_is_recalled(profile):
    bank = LocalMemoryBank()
    bank.remember(profile)

    (rejected,) = bank.recall(EGAKI).rejected_migrations()
    assert rejected.migration_id == "google-image-migration-2026-05"
    assert rejected.reason == "compatibility issue"


def test_record_migration_appends_without_losing_history(profile):
    bank = LocalMemoryBank()
    bank.remember(profile)
    bank.record_migration(
        EGAKI,
        PreviousMigration(
            migration_id="google-image-migration-2026-08",
            decision="pr_opened",
            reason="Imagen 4 retirement",
        ),
    )

    history = bank.recall(EGAKI).previous_migrations
    assert [m.migration_id for m in history] == [
        "google-image-migration-2026-05",
        "google-image-migration-2026-08",
    ]
    # The earlier rejection stays visible; that is the part worth recalling.
    assert len(bank.recall(EGAKI).rejected_migrations()) == 1


def test_record_migration_for_an_unknown_repo_creates_a_profile():
    bank = LocalMemoryBank()
    bank.record_migration(
        "new/repo", PreviousMigration(migration_id="m-1", decision="rejected", reason="unclear")
    )

    assert bank.recall("new/repo").repo == "new/repo"


def test_persistence_survives_a_new_client(tmp_path, profile):
    path = tmp_path / "memory.json"
    LocalMemoryBank(path).remember(profile)

    assert LocalMemoryBank(path).recall(EGAKI) == profile


def test_profile_round_trips_through_plain_data(profile):
    assert RepositoryProfile.from_dict(profile.to_dict()) == profile


def test_an_absent_profile_asserts_nothing():
    """A repository we know nothing about must not look pre-approved."""
    blank = RepositoryProfile(repo="new/repo")

    assert not blank.requires_human_review
    assert blank.prohibited_paths == ()
    assert blank.rejected_migrations() == ()
    assert blank.criticality == "unknown"


def test_forget(profile):
    bank = LocalMemoryBank()
    bank.remember(profile)

    assert bank.forget(EGAKI)
    assert not bank.forget(EGAKI)
    assert bank.recall(EGAKI) is None
