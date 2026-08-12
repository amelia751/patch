"""How the runner reaches Postgres.

Two targets are supported and the choice is explicit, never guessed from a
partial connection: a `DATABASE_URL` DSN (Cloud SQL, CI, a proxy shell) or the
local compose container from `db/docker-compose.yml`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from patchapi_db.scripts import checkout_root

COMPOSE_FILE = checkout_root() / "docker-compose.yml"
COMPOSE_SERVICE = "postgres"

DEFAULT_USER = "patchapi"
DEFAULT_DATABASE = "patchapi"

# ON_ERROR_STOP turns a mid-script SQL error into a non-zero exit instead of a
# partially applied migration reported as success.
_BASE_FLAGS = ("--no-psqlrc", "--quiet", "-v", "ON_ERROR_STOP=1")


class PsqlError(RuntimeError):
    """A `psql` invocation exited non-zero."""


@dataclass(frozen=True)
class PsqlTarget:
    """A command prefix that runs `psql` against one database."""

    argv: tuple[str, ...]
    label: str


def dsn_target(dsn: str) -> PsqlTarget:
    """Target an external database through a local `psql` binary."""
    if shutil.which("psql") is None:
        raise PsqlError("DATABASE_URL is set but `psql` is not on PATH")
    # The DSN may carry a password, so the label shows only the target shape.
    return PsqlTarget(argv=("psql", dsn), label="psql via DATABASE_URL")


def compose_target(
    *,
    compose_file: Path = COMPOSE_FILE,
    service: str = COMPOSE_SERVICE,
    user: str = DEFAULT_USER,
    database: str = DEFAULT_DATABASE,
) -> PsqlTarget:
    """Target the local compose Postgres, running `psql` inside the container.

    Executing in-container means a developer needs Docker but not a matching
    client install, and the connection uses the container's local socket.
    """
    if shutil.which("docker") is None:
        raise PsqlError("docker is not on PATH; start Docker or set DATABASE_URL")
    return PsqlTarget(
        argv=(
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "exec",
            "-T",
            service,
            "psql",
            "-U",
            user,
            "-d",
            database,
        ),
        label=f"docker compose service '{service}'",
    )


def resolve_target(env: Mapping[str, str] | None = None) -> PsqlTarget:
    """Pick a target: an explicit `DATABASE_URL` wins over local compose."""
    environ = os.environ if env is None else env
    dsn = environ.get("DATABASE_URL", "").strip()
    if dsn:
        return dsn_target(dsn)
    return compose_target(
        user=environ.get("PATCHAPI_DB_USER", DEFAULT_USER),
        database=environ.get("PATCHAPI_DB_NAME", DEFAULT_DATABASE),
    )


def _run(target: PsqlTarget, extra: Sequence[str], stdin: str | None) -> str:
    # Fixed argv, never a shell string: SQL travels on stdin or as one argv slot.
    completed = subprocess.run(
        [*target.argv, *_BASE_FLAGS, *extra],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise PsqlError(
            f"psql failed against {target.label} (exit {completed.returncode}):\n{detail}"
        )
    return completed.stdout


def run_script(target: PsqlTarget, sql: str) -> str:
    """Execute a script as one transaction; nothing lands if any statement fails."""
    return _run(target, ("--single-transaction", "-f", "-"), sql)


def run_query_script(target: PsqlTarget, sql: str) -> str:
    """Execute a multi-statement script and return its unaligned output.

    Unlike `run_script` this is not wrapped in one transaction, so a script can
    exercise a constraint violation and recover from it.
    """
    return _run(target, ("-At", "-F", "\t", "-f", "-"), sql)


def query(target: PsqlTarget, sql: str) -> list[list[str]]:
    """Run a query and return unaligned, tuples-only rows split on the field separator."""
    out = _run(target, ("-At", "-F", "\x1f", "-c", sql), None)
    return [line.split("\x1f") for line in out.splitlines() if line != ""]


def scalar(target: PsqlTarget, sql: str) -> str:
    """Run a query expected to return exactly one row and one column."""
    rows = query(target, sql)
    if len(rows) != 1 or len(rows[0]) != 1:
        raise PsqlError(f"expected a single scalar from: {sql}")
    return rows[0][0]


def is_reachable(target: PsqlTarget) -> bool:
    """True when the database answers a trivial query."""
    try:
        return scalar(target, "SELECT 1") == "1"
    except PsqlError:
        return False
