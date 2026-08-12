"""Fail-closed scan for directive language inside untrusted provider documents.

A provider changelog describes a change. A provider changelog that tells the
automation to merge, to skip verification, or to read credentials is tampered
input, and the correct response is to stop rather than to sanitise and continue:
if the injection cannot be cleanly separated from the factual content, nothing
in the document can be trusted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from check_results import CheckResult, Status

_MAX_EXCERPT = 120


def _compile(patterns: list[dict[str, Any]]) -> list[tuple[dict[str, Any], re.Pattern[str]]]:
    return [(spec, re.compile(spec["pattern"], re.IGNORECASE)) for spec in patterns]


def _excerpt(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 20)
    end = min(len(text), match.end() + 20)
    return " ".join(text[start:end].split())[:_MAX_EXCERPT]


def scan_text(label: str, text: str, rules: dict[str, Any]) -> CheckResult:
    """Scan one untrusted document; a single match fails the whole run closed."""
    hits: list[str] = []
    for spec, pattern in _compile(rules["patterns"]):
        match = pattern.search(text)
        if match:
            hits.append(f"{spec['id']}/{spec['category']}: …{_excerpt(text, match)}…")
    check_id = f"UL:{label}"
    if hits:
        return CheckResult(
            id=check_id,
            title=f"untrusted document {label} contains no directive language",
            status=Status.FAIL,
            detail=(
                f"{len(hits)} directive pattern(s) matched — treating the document as "
                f"tampered and failing closed: " + " | ".join(hits)
            ),
            fail_closed=True,
        )
    return CheckResult(
        id=check_id,
        title=f"untrusted document {label} contains no directive language",
        status=Status.PASS,
        detail=f"{len(rules['patterns'])} directive patterns checked, none matched",
    )


def scan_path(path: Path, text: str, rules: dict[str, Any]) -> CheckResult:
    return scan_text(path.name, text, rules)
