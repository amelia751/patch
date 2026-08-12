"""PatchAPI's authoritative Postgres schema: migrations, seeds, and their runner."""

from patchapi_db.migrate import MigrationDriftError, MigrationReport, migrate
from patchapi_db.psql import PsqlError, PsqlTarget, resolve_target
from patchapi_db.scripts import ScriptError, SqlScript, load_scripts, migrations_dir, seeds_dir
from patchapi_db.seed import SeedReport, seed

__all__ = [
    "MigrationDriftError",
    "MigrationReport",
    "PsqlError",
    "PsqlTarget",
    "ScriptError",
    "SeedReport",
    "SqlScript",
    "load_scripts",
    "migrate",
    "migrations_dir",
    "resolve_target",
    "seed",
    "seeds_dir",
]
