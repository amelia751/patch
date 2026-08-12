"""Segment-wise glob matching for repository paths.

`fnmatch` is not usable here: its `*` crosses `/`, so `infra/*` would silently
match `infra/modules/main.tf` and `.env*` would match nothing under a
subdirectory. A denylist that matches by accident is as wrong as one that
misses, because both make the recorded audit reason untrue.

Semantics, matching the glob dialect used in `roadmap.md` §8.3:

- `*`  matches any run of characters inside one path segment
- `?`  matches one character inside one path segment
- `**` matches zero or more whole segments
"""

import re
from functools import lru_cache
from typing import Final

_SEGMENT_TRANSLATION: Final[dict[str, str]] = {"*": "[^/]*", "?": "[^/]"}


def normalize_path(path: str) -> str:
    """Reduce a repository path to the form the rules are written against.

    Backslashes become slashes and redundant separators collapse. A `..`
    segment is refused rather than resolved: traversal is how a generated patch
    would reach outside the checkout, so it is an error, not a formatting quirk.
    """
    segments = [
        segment
        for segment in path.strip().replace("\\", "/").split("/")
        if segment not in ("", ".")
    ]
    if ".." in segments:
        raise ValueError(f"path escapes the repository root: {path!r}")
    if not segments:
        raise ValueError(f"empty repository path: {path!r}")
    return "/".join(segments)


def _translate_segment(segment: str) -> str:
    return "".join(_SEGMENT_TRANSLATION.get(char, re.escape(char)) for char in segment)


def _to_regex(pattern: str) -> str:
    segments = [segment for segment in pattern.split("/") if segment]
    parts: list[str] = []
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        if segment == "**":
            # A trailing `**` also matches the directory itself, so `infra/**`
            # covers a policy written about the whole `infra` subtree.
            if is_last:
                parts.append(r"(?:.+)?" if not parts else r"(?:/.+)?")
            else:
                parts.append(r"(?:[^/]+/)*" if not parts else r"/(?:[^/]+/)*")
            continue
        translated = _translate_segment(segment)
        if not parts or parts[-1].endswith("/)*"):
            parts.append(translated)
        else:
            parts.append(f"/{translated}")
    return "".join(parts)


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(f"^{_to_regex(pattern)}$")


def glob_match(pattern: str, path: str) -> bool:
    """True when `path` matches `pattern` under the semantics above."""
    return _compiled(pattern).match(normalize_path(path)) is not None


def first_match(patterns: tuple[str, ...], path: str) -> str | None:
    """Return the first pattern in `patterns` that matches, or `None`.

    Order is significant and preserved so the pattern that produced a decision
    can be named verbatim in the audit record.
    """
    normalized = normalize_path(path)
    for pattern in patterns:
        if _compiled(pattern).match(normalized):
            return pattern
    return None
