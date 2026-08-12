"""Forward-only migration application.

Rules the runner enforces, because review alone cannot:

* a migration is applied at most once, tracked in `schema_migrations`;
* an already-applied migration whose text changed is a hard error — the fix is
  a new migration, never an edit to history;
* each migration and its ledger row land in the same transaction, so a failure
  leaves neither behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from patchapi_db.psql import PsqlTarget, query, run_script
from patchapi_db.scripts import SqlScript, load_scripts, migrations_dir

LEDGER_TABLE = "schema_migrations"

_LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    version text PRIMARY KEY,
    name text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
"""


class MigrationDriftError(RuntimeError):
    """An applied migration's text no longer matches what was recorded."""


@dataclass(frozen=True)
class MigrationReport:
    """Outcome of one `migrate` invocation."""

    applied: tuple[str, ...] = field(default_factory=tuple)
    skipped: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        """Number of migrations known to the checkout."""
        return len(self.applied) + len(self.skipped)


def ensure_ledger(target: PsqlTarget) -> None:
    """Create the migration ledger if this is a fresh database."""
    run_script(target, _LEDGER_DDL)


def applied_versions(target: PsqlTarget) -> dict[str, str]:
    """Map of applied version to the checksum recorded when it was applied."""
    rows = query(target, f"SELECT version, checksum FROM {LEDGER_TABLE} ORDER BY version")
    return {version: checksum for version, checksum in rows}


def _record_sql(script: SqlScript) -> str:
    # Safe to interpolate: the version and name come from a filename that
    # matched `\d{4}_[a-z0-9_]+\.sql`, and the checksum is hex from hashlib.
    return (
        f"INSERT INTO {LEDGER_TABLE} (version, name, checksum) "
        f"VALUES ('{script.version}', '{script.name}', '{script.checksum}');"
    )


def apply_migration(target: PsqlTarget, script: SqlScript) -> None:
    """Apply one migration and record it, atomically."""
    run_script(target, f"{script.sql}\n{_record_sql(script)}\n")


def migrate(target: PsqlTarget) -> MigrationReport:
    """Apply every pending migration in version order."""
    ensure_ledger(target)
    already = applied_versions(target)

    applied: list[str] = []
    skipped: list[str] = []
    for script in load_scripts(migrations_dir()):
        recorded = already.get(script.version)
        if recorded is None:
            apply_migration(target, script)
            applied.append(script.name)
            continue
        if recorded != script.checksum:
            raise MigrationDriftError(
                f"{script.name} was modified after it was applied "
                f"(recorded {recorded[:12]}, found {script.checksum[:12]}). "
                "Migrations are forward-only: add a new migration instead."
            )
        skipped.append(script.name)

    return MigrationReport(applied=tuple(applied), skipped=tuple(skipped))
