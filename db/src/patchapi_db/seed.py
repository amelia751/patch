"""Demo seed application.

Seeds differ from migrations in one way that matters: they are re-applied on
every invocation. Each seed script must therefore converge — fixed primary
keys, upserts, and explicit deletion of its own append-only rows. The ledger
here records how many times a seed ran, not whether it may run again.
"""

from __future__ import annotations

from dataclasses import dataclass

from patchapi_db.psql import PsqlTarget, run_script
from patchapi_db.scripts import SqlScript, load_scripts, seeds_dir

LEDGER_TABLE = "seed_applications"

_LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    name text PRIMARY KEY,
    checksum text NOT NULL,
    apply_count integer NOT NULL DEFAULT 0,
    first_applied_at timestamptz NOT NULL DEFAULT now(),
    last_applied_at timestamptz NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True)
class SeedReport:
    """Outcome of one `seed` invocation."""

    applied: tuple[str, ...]


def ensure_ledger(target: PsqlTarget) -> None:
    """Create the seed ledger if this is a fresh database."""
    run_script(target, _LEDGER_DDL)


def _record_sql(script: SqlScript) -> str:
    # Interpolation is safe for the same reason as in `migrate`: the name comes
    # from a filename validated against a strict pattern, the checksum is hex.
    return (
        f"INSERT INTO {LEDGER_TABLE} (name, checksum, apply_count) "
        f"VALUES ('{script.name}', '{script.checksum}', 1) "
        f"ON CONFLICT (name) DO UPDATE SET "
        f"checksum = EXCLUDED.checksum, "
        f"apply_count = {LEDGER_TABLE}.apply_count + 1, "
        f"last_applied_at = now();"
    )


def apply_seed(target: PsqlTarget, script: SqlScript) -> None:
    """Apply one seed script and bump its ledger row, atomically."""
    run_script(target, f"{script.sql}\n{_record_sql(script)}\n")


def seed(target: PsqlTarget) -> SeedReport:
    """Re-apply every seed script in version order."""
    ensure_ledger(target)
    scripts = load_scripts(seeds_dir())
    for script in scripts:
        apply_seed(target, script)
    return SeedReport(applied=tuple(script.name for script in scripts))
