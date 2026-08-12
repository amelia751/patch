"""The package's public surface resolves lazily and stays complete."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import packages.schemas as schemas

PACKAGE_DIR = Path(__file__).parents[1]


def test_every_exported_name_resolves():
    unresolved = [name for name in schemas.__all__ if not hasattr(schemas, name)]

    assert unresolved == []


def test_the_export_map_matches_the_declared_surface():
    assert sorted(schemas._EXPORTS) == sorted(schemas.__all__)


def test_unknown_names_raise_attribute_error():
    with pytest.raises(AttributeError, match="NotAContract"):
        schemas.NotAContract  # noqa: B018 - attribute access is the behaviour under test


def test_dir_matches_all():
    assert dir(schemas) == sorted(schemas.__all__)


def test_every_module_is_shipped_in_the_wheel():
    """The wheel re-adds the `packages/schemas/` prefix file by file.

    A new module that nobody adds to `force-include` would import in-tree and
    vanish for anyone installing the package, so the two lists must match.
    """
    config = tomllib.loads((PACKAGE_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    shipped = set(config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"])
    on_disk = {path.name for path in PACKAGE_DIR.glob("*.py")}

    assert on_disk == shipped


def test_importing_the_package_does_not_pull_in_pydantic(repo_root):
    """Collection in an environment without the dependency must not explode.

    Run out of process: Pydantic is already imported in this one.
    """
    probe = (
        "import sys; import packages.schemas; "
        "assert 'pydantic' not in sys.modules, 'pydantic imported eagerly'"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
