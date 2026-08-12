"""Filesystem access for the skill package.

Reference data is JSON rather than YAML so the checks run against a bare Python
3.12 interpreter with no third-party dependency. The skill has to be runnable
inside the sandbox image, where the dependency set is deliberately small.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent.parent


class SkillLoadError(RuntimeError):
    """The skill package itself is unreadable — an operator error, not a finding."""


def load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillLoadError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkillLoadError(f"{path} is not valid JSON: {exc}") from exc


def load_manifest() -> dict[str, Any]:
    manifest = load_json(SKILL_ROOT / "skill.json")
    if not isinstance(manifest, dict):
        raise SkillLoadError("skill.json must contain an object")
    return manifest


def load_reference(manifest: dict[str, Any], key: str) -> Any:
    references = manifest.get("references", {})
    relative = references.get(key)
    if not isinstance(relative, str):
        raise SkillLoadError(f"skill.json declares no reference named {key!r}")
    return load_json(SKILL_ROOT / relative)


def reference_path(manifest: dict[str, Any], key: str) -> Path:
    references = manifest.get("references", {})
    relative = references.get(key)
    if not isinstance(relative, str):
        raise SkillLoadError(f"skill.json declares no reference named {key!r}")
    return SKILL_ROOT / relative


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillLoadError(f"cannot read {path}: {exc}") from exc


def default_fixture_path(manifest: dict[str, Any]) -> Path:
    relative = manifest.get("checks", {}).get("default_fixture")
    if not isinstance(relative, str):
        raise SkillLoadError("skill.json declares no checks.default_fixture")
    return REPO_ROOT / relative
