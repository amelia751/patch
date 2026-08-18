"""The installed wheel must carry every module the control plane imports."""

import tomllib
from pathlib import Path

PACKAGE_DIR = Path(__file__).parents[1]


def test_every_module_is_shipped_in_the_wheel() -> None:
    """The wheel re-adds the `packages/state/` prefix file by file.

    A new module that nobody adds to `force-include` would import in-tree and
    crash Cloud Run, which installs the wheel rather than the checkout.
    """
    config = tomllib.loads((PACKAGE_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    shipped = set(config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"])
    on_disk = {path.name for path in PACKAGE_DIR.glob("*.py")}
    data = PACKAGE_DIR / "data"
    if data.is_dir():
        on_disk |= {f"data/{path.name}" for path in data.iterdir() if path.is_file()}

    assert on_disk == shipped
