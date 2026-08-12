"""Discovery and checksumming of the SQL scripts that define the schema.

Ordering and identity live here rather than in the shell so that both the
migration runner and its tests agree on what "migration 0007" means.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent

# In the workspace checkout the SQL sits two levels up at `db/migrations`; in an
# installed wheel it is force-included next to the module. Both layouts are
# supported so a deployed control plane can apply migrations without the repo.
_CHECKOUT_ROOT = _MODULE_DIR.parents[1]
_INSTALLED_ROOT = _MODULE_DIR / "_sql"

_FILENAME = re.compile(r"^(?P<version>\d{4})_(?P<slug>[a-z0-9_]+)\.sql$")


class ScriptError(RuntimeError):
    """A SQL script directory does not satisfy the naming contract."""


@dataclass(frozen=True)
class SqlScript:
    """One `NNNN_slug.sql` file, its content, and its content hash."""

    version: str
    name: str
    path: Path
    sql: str
    checksum: str


def _root() -> Path:
    return _INSTALLED_ROOT if _INSTALLED_ROOT.is_dir() else _CHECKOUT_ROOT


def checkout_root() -> Path:
    """The `db/` directory in the repository checkout.

    Only meaningful in a working tree; an installed wheel carries the SQL but
    not the compose file that lives alongside it.
    """
    return _CHECKOUT_ROOT


def migrations_dir() -> Path:
    """Directory holding the forward-only migrations."""
    return _root() / "migrations"


def seeds_dir() -> Path:
    """Directory holding the re-runnable demo seeds."""
    return _root() / "seeds"


def checksum(sql: str) -> str:
    """SHA-256 of a script's text, used to detect edits to applied migrations."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def load_scripts(directory: Path) -> tuple[SqlScript, ...]:
    """Return every `NNNN_slug.sql` in `directory`, ordered by version.

    Raises `ScriptError` on a malformed filename or a duplicated version, which
    would otherwise make the apply order depend on filesystem iteration.
    """
    if not directory.is_dir():
        raise ScriptError(f"not a directory: {directory}")

    scripts: dict[str, SqlScript] = {}
    for path in sorted(directory.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue
        if path.suffix != ".sql":
            continue
        match = _FILENAME.match(path.name)
        if match is None:
            raise ScriptError(
                f"{path.name}: expected a NNNN_lower_snake_case.sql name in {directory}"
            )
        version = match.group("version")
        if version in scripts:
            raise ScriptError(
                f"duplicate version {version}: {scripts[version].path.name} and {path.name}"
            )
        sql = path.read_text(encoding="utf-8")
        scripts[version] = SqlScript(
            version=version,
            name=path.name,
            path=path,
            sql=sql,
            checksum=checksum(sql),
        )

    return tuple(scripts[version] for version in sorted(scripts))
