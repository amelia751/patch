"""Read the checked-in environment pins without shadowing the real environment.

`.env.example` carries the non-secret pins the fleet agreed on — GCP project,
Vertex location, model IDs, the path of the gitignored service-account key.
Scripts apply those as *defaults* so a verifier run in a bare shell resolves the
same pins the demo uses, while an operator export or a local `.env` always wins.

Deliberately not a general dotenv implementation: no interpolation, no `export`
prefixes, no multi-line values. A pin file that needs those is a pin file that
has stopped being readable evidence.
"""

import os
from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path


def parse_env_text(text: str) -> dict[str, str]:
    """Parse `KEY=value` lines, ignoring blanks and `#` comments."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def read_env_files(paths: Iterable[Path]) -> dict[str, str]:
    """Merge readable files in order; the first file to define a key wins.

    Missing files are skipped, so callers can list `.env` ahead of
    `.env.example` and get the operator's overrides layered over the pins.
    """
    merged: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        for key, value in parse_env_text(path.read_text(encoding="utf-8")).items():
            merged.setdefault(key, value)
    return merged


def apply_defaults(
    values: Mapping[str, str],
    environ: MutableMapping[str, str] | None = None,
) -> list[str]:
    """Set every key that is not already present. Returns the keys that were set."""
    target = os.environ if environ is None else environ
    applied: list[str] = []
    for key, value in values.items():
        if target.get(key):
            continue
        target[key] = value
        applied.append(key)
    return sorted(applied)
