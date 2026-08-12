"""Command line entry point: `python -m patchapi_db {migrate,seed,status}`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from patchapi_db.migrate import MigrationDriftError, applied_versions, migrate
from patchapi_db.psql import (
    PsqlError,
    PsqlTarget,
    query,
    resolve_target,
    run_query_script,
    scalar,
)
from patchapi_db.scripts import ScriptError, load_scripts, migrations_dir, seeds_dir
from patchapi_db.seed import LEDGER_TABLE as SEED_LEDGER_TABLE
from patchapi_db.seed import seed


def _cmd_migrate(target: PsqlTarget) -> int:
    report = migrate(target)
    for name in report.applied:
        print(f"applied  {name}")
    for name in report.skipped:
        print(f"skipped  {name} (already applied)")
    print(f"migrate: {len(report.applied)} applied, {len(report.skipped)} already present")
    return 0


def _cmd_seed(target: PsqlTarget) -> int:
    report = seed(target)
    for name in report.applied:
        print(f"seeded   {name}")
    print(f"seed: {len(report.applied)} script(s) applied")
    return 0


def _cmd_status(target: PsqlTarget) -> int:
    known = load_scripts(migrations_dir())
    applied = applied_versions(target)
    for script in known:
        mark = "ok" if script.version in applied else "PENDING"
        print(f"{script.version}  {mark:8} {script.name}")
    pending = [s.name for s in known if s.version not in applied]
    print(f"migrations: {len(known)} known, {len(pending)} pending")

    # `status` reports; it never creates the seed ledger, which may legitimately
    # be absent on a migrated-but-never-seeded database.
    counts: dict[str, str] = {}
    if scalar(target, f"SELECT to_regclass('public.{SEED_LEDGER_TABLE}') IS NOT NULL") == "t":
        rows = query(target, f"SELECT name, apply_count FROM {SEED_LEDGER_TABLE} ORDER BY name")
        counts = {name: count for name, count in rows}
    for script in load_scripts(seeds_dir()):
        print(f"seed      {script.name} applied {counts.get(script.name, '0')}x")
    return 1 if pending else 0


def _cmd_sql(target: PsqlTarget) -> int:
    script = sys.stdin.read()
    if not script.strip():
        print("FAIL: no SQL on stdin", file=sys.stderr)
        return 1
    sys.stdout.write(run_query_script(target, script))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the requested subcommand."""
    parser = argparse.ArgumentParser(
        prog="patchapi-db",
        description=(
            "Apply PatchAPI's forward-only migrations and demo seeds. "
            "Targets DATABASE_URL when set, otherwise db/docker-compose.yml."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply pending migrations")
    sub.add_parser("seed", help="re-apply demo seed data")
    sub.add_parser("status", help="report applied/pending migrations; exit 1 if any pending")
    sub.add_parser("sql", help="run a SQL script read from stdin against the same target")

    args = parser.parse_args(argv)

    try:
        target = resolve_target()
        if args.command == "migrate":
            return _cmd_migrate(target)
        if args.command == "seed":
            return _cmd_seed(target)
        if args.command == "sql":
            return _cmd_sql(target)
        return _cmd_status(target)
    except (PsqlError, ScriptError, MigrationDriftError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
