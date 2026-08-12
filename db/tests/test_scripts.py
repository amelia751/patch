"""Checks on the SQL corpus itself. These need no database."""

from __future__ import annotations

import re

import pytest
from patchapi_db.psql import PsqlError, compose_target, dsn_target, resolve_target
from patchapi_db.scripts import ScriptError, load_scripts, migrations_dir, seeds_dir

MIGRATIONS = load_scripts(migrations_dir())
SEEDS = load_scripts(seeds_dir())

# The runner wraps every script in `--single-transaction`; a script that opens
# its own transaction would either nest or commit early.
TRANSACTION_CONTROL = re.compile(r"^\s*(BEGIN|COMMIT|ROLLBACK|END)\b", re.IGNORECASE | re.MULTILINE)


def test_migrations_exist():
    assert MIGRATIONS, "no migrations found"


def test_migration_versions_are_contiguous_from_one():
    versions = [int(script.version) for script in MIGRATIONS]
    assert versions == list(range(1, len(versions) + 1))


@pytest.mark.parametrize("script", MIGRATIONS + SEEDS, ids=lambda s: s.name)
def test_script_does_not_manage_its_own_transaction(script):
    assert TRANSACTION_CONTROL.search(script.sql) is None


@pytest.mark.parametrize("script", MIGRATIONS, ids=lambda s: s.name)
def test_migration_is_not_destructive(script):
    lowered = script.sql.lower()
    for forbidden in ("drop table", "drop type", "truncate"):
        assert forbidden not in lowered, f"migrations are forward-only: found {forbidden!r}"


@pytest.mark.parametrize("script", SEEDS, ids=lambda s: s.name)
def test_seed_is_re_runnable(script):
    # Either it upserts, or it removes the rows it previously wrote.
    assert "on conflict" in script.sql.lower() or "delete from" in script.sql.lower()


def test_checksum_changes_with_content():
    first, second = MIGRATIONS[0], MIGRATIONS[1]
    assert first.checksum != second.checksum
    assert len(first.checksum) == 64


def test_load_scripts_rejects_a_malformed_filename(tmp_path):
    (tmp_path / "not-a-migration.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(ScriptError):
        load_scripts(tmp_path)


def test_load_scripts_rejects_duplicate_versions(tmp_path):
    (tmp_path / "0001_alpha.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "0001_beta.sql").write_text("SELECT 2;", encoding="utf-8")
    with pytest.raises(ScriptError):
        load_scripts(tmp_path)


def test_load_scripts_rejects_a_missing_directory(tmp_path):
    with pytest.raises(ScriptError):
        load_scripts(tmp_path / "absent")


def test_database_url_takes_precedence_over_compose():
    try:
        target = resolve_target({"DATABASE_URL": "postgresql://u@h/db"})
    except PsqlError:
        pytest.skip("psql client is not installed on this machine")
    assert target.argv[0] == "psql"


def test_dsn_is_not_echoed_in_the_target_label():
    try:
        target = dsn_target("postgresql://user:hunter2@host/db")
    except PsqlError:
        pytest.skip("psql client is not installed on this machine")
    assert "hunter2" not in target.label


def test_compose_target_runs_psql_inside_the_container():
    try:
        target = compose_target()
    except PsqlError:
        pytest.skip("docker is not installed on this machine")
    assert target.argv[:2] == ("docker", "compose")
    assert "exec" in target.argv
    assert target.argv[-4:] == ("-U", "patchapi", "-d", "patchapi")
