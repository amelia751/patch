"""The installed wheel must carry every module and descriptor a provider needs."""

import tomllib
from pathlib import Path

PACKAGE_DIR = Path(__file__).parents[1]


def test_every_module_is_shipped_in_the_wheel() -> None:
    """A module missing from `force-include` imports in-tree and crashes the
    deployed service, which installs the wheel rather than the checkout.

    A *descriptor* missing from it fails more quietly and matters more: the
    service starts, finds no patterns for that provider, and reports every
    repository as unaffected by it. So the JSON is compared here too.

    Sub-packages are listed with their directory prefix, so the comparison
    walks one level down as well as across the top.
    """
    config = tomllib.loads((PACKAGE_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    shipped = set(config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"])

    on_disk = {path.name for path in PACKAGE_DIR.glob("*.py")}
    for child in sorted(PACKAGE_DIR.iterdir()):
        if not child.is_dir() or child.name in {"tests", "__pycache__"}:
            continue
        on_disk |= {f"{child.name}/{path.name}" for path in child.glob("*.py")}
        on_disk |= {f"{child.name}/{path.name}" for path in child.glob("*.json")}

    assert on_disk == shipped
