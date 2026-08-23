"""Deciding what "build it and test it" means for one repository.

A `VerticalSlice` tells the patch loop which file holds the binding, what to run
to prove the tree still builds, and what to run to prove it still works. Getting
those wrong is not a degraded run — a wrong test command exits 0 on a repository
it never tested, and the verifier then grades a patch nobody checked.

So this refuses more readily than it guesses. Pinned repositories carry a
profile that was verified by hand. Everything else is detected only where the
repository states the answer itself, in a manifest it maintains, and a detection
that comes up short returns why rather than a plausible default. `HUMAN_REQUIRED`
with "I could not tell how to test this" is a useful thing to tell somebody;
`npm test` guessed at a repository with no test script is not.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agents.orchestrator import VerticalSlice

# Which migration skill applies. Keyed by the identifier family a change
# retires, because a skill encodes how to move off that family — not how one
# repository is laid out.
SKILL_BY_PREFIX: Final[tuple[tuple[str, str], ...]] = (
    ("imagen-", "google_imagen_migration"),
    ("gemini-2.0", "google_gemini20_migration"),
)
DEFAULT_SKILL: Final[str] = "google_gemini20_migration"


@dataclass(frozen=True, slots=True)
class RepoProfile:
    """How to build and test one repository, and where its binding lives."""

    entrypoint: str
    binding: str
    build_command: str
    test_command: str


# The flagship demo target, pinned by `roadmap.md` and verified end to end. The
# commands are the fixture's own: `generate.py` exits non-zero when the bound
# model identifier no longer resolves, which is what makes a green run evidence
# that the patch landed rather than evidence a provider was reachable.
PINNED_PROFILES: Final[dict[str, RepoProfile]] = {
    "amelia751/storygen": RepoProfile(
        entrypoint="lib/gemini.ts",
        binding="MODEL",
        build_command="python3 generate.py",
        test_command="python3 -m unittest test_generate.py",
    ),
}

# An identifier is usually bound to a screaming-snake constant, in any of the
# four syntaxes the indexed languages use. Anchored on the assignment so a
# mention inside a comment or a string list does not read as a binding.
_BINDING = re.compile(
    r"(?:^|\b)(?:export\s+)?(?:const|let|var|final|static)?\s*"
    r"([A-Z][A-Z0-9_]{2,})\s*(?::\s*[\w<>\[\]|\s.]+)?\s*="
)

_JS_BUILD_KEYS: Final[tuple[str, ...]] = ("build", "compile")
_JS_TEST_KEYS: Final[tuple[str, ...]] = ("test", "test:unit", "check")


@dataclass(frozen=True, slots=True)
class SliceDecision:
    """A slice, or the reason there is not one."""

    slice_: VerticalSlice | None
    reason: str = ""
    pinned: bool = False

    @property
    def ok(self) -> bool:
        return self.slice_ is not None


def skill_for(identifiers: list[str]) -> str:
    for identifier in identifiers:
        for prefix, skill in SKILL_BY_PREFIX:
            if identifier.startswith(prefix):
                return skill
    return DEFAULT_SKILL


def binding_name(excerpt: str) -> str:
    """The constant an identifier is assigned to, from the line that assigns it."""
    for line in excerpt.splitlines():
        found = _BINDING.search(line)
        if found:
            return found.group(1)
    return ""


def bound_constant(entrypoint: Path, identifiers: list[str]) -> str:
    """The constant in `entrypoint` that holds one of `identifiers`.

    Answers "which line is this change about" by reading the file rather than by
    trusting a pin, so a repository binding several models in one module gets the
    right one per change.
    """
    try:
        source = entrypoint.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in source.splitlines():
        if not any(identifier and identifier in line for identifier in identifiers):
            continue
        found = _BINDING.search(line)
        if found:
            return found.group(1)
    return ""


def _package_manager(tree: Path) -> str:
    """The manager this repository declares, by the lockfile it committed."""
    if (tree / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (tree / "yarn.lock").is_file():
        return "yarn"
    return "npm"


def _node_commands(tree: Path) -> tuple[str, str]:
    manifest = tree / "package.json"
    if not manifest.is_file():
        return "", ""
    try:
        scripts = json.loads(manifest.read_text(encoding="utf-8")).get("scripts") or {}
    except (ValueError, OSError):
        return "", ""
    if not isinstance(scripts, dict):
        return "", ""

    manager = _package_manager(tree)
    build = next((key for key in _JS_BUILD_KEYS if key in scripts), "")
    test = next((key for key in _JS_TEST_KEYS if key in scripts), "")
    return (
        f"{manager} run {build}" if build else "",
        f"{manager} run {test}" if test else "",
    )


def _python_commands(tree: Path) -> tuple[str, str]:
    """Python has no build step to speak of, so an import check stands in.

    A test command is only claimed when the repository has somewhere for tests
    to live. `pytest` against a tree with no tests exits 5, not 0, so guessing
    would fail the run rather than pass it falsely — but it would fail it for
    the wrong reason, and a reviewer would go looking for a bug in the patch.
    """
    if not any((tree / name).is_file() for name in ("pyproject.toml", "setup.py", "setup.cfg")):
        return "", ""
    has_tests = (tree / "tests").is_dir() or any(tree.glob("test_*.py"))
    return "python3 -m compileall -q .", "python3 -m pytest -q" if has_tests else ""


def detect_profile(tree: Path, *, entrypoint: str, binding: str) -> RepoProfile | None:
    """Read build and test commands out of what the repository already declares."""
    for build, test in (_node_commands(tree), _python_commands(tree)):
        if build and test:
            return RepoProfile(
                entrypoint=entrypoint, binding=binding, build_command=build, test_command=test
            )
    return None


def decide(
    *,
    repository: str,
    change_id: str,
    identifiers: list[str],
    tree: Path,
    entrypoint: str = "",
    excerpt: str = "",
) -> SliceDecision:
    """The slice to run, or why this repository cannot be remediated unattended.

    A pinned profile wins over detection even when detection would succeed: the
    pin is a human's verified answer, and silently preferring an inferred one
    would make the demo depend on whatever `package.json` happens to say.
    """
    skill = skill_for(identifiers)

    profile = PINNED_PROFILES.get(repository)
    if profile is not None:
        # The pin fixes how the repository is built, not which constant this
        # particular change is about. One entrypoint can hold several bound
        # identifiers — a text model and an image model beside it — and patching
        # the pinned name would rewrite the wrong line for every change but one.
        bound = bound_constant(tree / profile.entrypoint, identifiers) or profile.binding
        return SliceDecision(
            slice_=VerticalSlice(
                change_id=change_id,
                repo=repository,
                skill_id=skill,
                entrypoint=profile.entrypoint,
                binding=bound,
                build_command=profile.build_command,
                test_command=profile.test_command,
            ),
            pinned=True,
        )

    if not entrypoint:
        return SliceDecision(
            None,
            "No indexed runtime file names the retired identifier, so there is no "
            "entry point to patch. A human should confirm where the change applies.",
        )
    if not (tree / entrypoint).is_file():
        return SliceDecision(
            None,
            f"The index points at {entrypoint}, which is not in the tree at this "
            "commit. The inventory is stale; re-index before remediating.",
        )

    binding = binding_name(excerpt) or binding_name(
        (tree / entrypoint).read_text(encoding="utf-8", errors="replace")
    )
    if not binding:
        return SliceDecision(
            None,
            f"{entrypoint} uses the retired identifier without assigning it to a "
            "named constant, so a patch cannot be verified by re-reading the binding.",
        )

    detected = detect_profile(tree, entrypoint=entrypoint, binding=binding)
    if detected is None:
        return SliceDecision(
            None,
            f"{repository} declares no build and test commands PatchAPI can run "
            "unattended. Add them, or pin a profile for this repository.",
        )

    return SliceDecision(
        slice_=VerticalSlice(
            change_id=change_id,
            repo=repository,
            skill_id=skill,
            entrypoint=detected.entrypoint,
            binding=detected.binding,
            build_command=detected.build_command,
            test_command=detected.test_command,
        )
    )


__all__ = [
    "DEFAULT_SKILL",
    "PINNED_PROFILES",
    "RepoProfile",
    "SliceDecision",
    "binding_name",
    "bound_constant",
    "decide",
    "detect_profile",
    "skill_for",
]
