"""The installed wheel must carry every module the indexer imports."""

import tomllib
from pathlib import Path

PACKAGE_DIR = Path(__file__).parents[1]


def test_every_module_is_shipped_in_the_wheel() -> None:
    """A module missing from `force-include` imports in-tree and crashes the
    deployed service, which installs the wheel rather than the checkout."""
    config = tomllib.loads((PACKAGE_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    shipped = set(config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"])
    on_disk = {path.name for path in PACKAGE_DIR.glob("*.py")}

    assert on_disk == shipped
