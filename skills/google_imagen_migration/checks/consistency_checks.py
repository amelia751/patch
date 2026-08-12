"""Checks that the skill package is internally consistent.

SKILL.md is what an agent reads; the JSON references are what the checks read.
Letting the two drift would mean the documented migration and the enforced one
are different migrations, so the prose is machine-checked against the data.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from check_results import CheckResult, Status

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_SKILL_VERSION_LINE = re.compile(r"^\*\*Skill version:\*\*\s*(\S+)", re.MULTILINE)


def _result(check_id: str, title: str, ok: bool, detail_ok: str, detail_bad: str) -> CheckResult:
    return CheckResult(
        id=check_id,
        title=title,
        status=Status.PASS if ok else Status.FAIL,
        detail=detail_ok if ok else detail_bad,
    )


def check_version_declared(manifest: dict[str, Any], skill_md: str) -> CheckResult:
    version = manifest["skill"]["version"]
    if not _SEMVER.match(str(version)):
        return CheckResult(
            "CS-01",
            "skill version is semver and declared in SKILL.md",
            Status.FAIL,
            f"skill.json version {version!r} is not semver",
        )
    match = _SKILL_VERSION_LINE.search(skill_md)
    declared = match.group(1) if match else None
    return _result(
        "CS-01",
        "skill version is semver and declared in SKILL.md",
        declared == version,
        f"SKILL.md and skill.json both declare version {version}",
        f"SKILL.md declares {declared!r} but skill.json declares {version!r}",
    )


def check_identifiers_documented(identifiers: dict[str, Any], skill_md: str) -> CheckResult:
    missing = [i for i in identifiers["affected_identifiers"] if i not in skill_md]
    if identifiers["recommended_replacement"] not in skill_md:
        missing.append(identifiers["recommended_replacement"])
    return _result(
        "CS-02",
        "every pinned identifier appears in SKILL.md",
        not missing,
        f"{len(identifiers['affected_identifiers'])} identifiers and the replacement documented",
        f"not documented in SKILL.md: {missing}",
    )


def check_reference_files_exist(manifest: dict[str, Any], skill_root: Path) -> CheckResult:
    declared = list(manifest.get("references", {}).values())
    declared.append(manifest["checks"]["entry_point"])
    missing = [rel for rel in declared if not (skill_root / rel).is_file()]
    return _result(
        "CS-03",
        "every file the manifest declares exists",
        not missing,
        f"{len(declared)} declared file(s) present",
        f"declared but missing: {missing}",
    )


def check_capability_dispositions(capabilities: dict[str, Any]) -> CheckResult:
    allowed = set(capabilities["allowed_dispositions"])
    problems: list[str] = []
    for option in capabilities["options"]:
        name = option["option"]
        disposition = option.get("disposition")
        if disposition not in allowed:
            problems.append(f"{name}: disposition {disposition!r} not in {sorted(allowed)}")
            continue
        if option.get("gemini") is False and disposition != "HUMAN_REQUIRED":
            problems.append(f"{name}: no Gemini equivalent but disposition is {disposition}")
        if option.get("gemini") is True:
            if disposition != "MAP":
                problems.append(f"{name}: has a Gemini equivalent but disposition is {disposition}")
            elif not option.get("gemini_option"):
                problems.append(f"{name}: mapped without naming the Gemini option")
    return _result(
        "CS-04",
        "capability map escalates every option with no Gemini equivalent",
        not problems,
        f"{len(capabilities['options'])} options mapped; every gap is HUMAN_REQUIRED",
        "; ".join(problems),
    )


def check_string_replace_rejected(capabilities: dict[str, Any]) -> CheckResult:
    ok = capabilities.get("string_replace_is_sufficient") is False
    return _result(
        "CS-05",
        "skill rejects an identifier-only migration",
        ok,
        "string_replace_is_sufficient is false",
        "capability map does not declare string_replace_is_sufficient=false, which "
        "would license a model-ID swap as a complete migration",
    )


def check_invariants_documented(verification: dict[str, Any], skill_md: str) -> CheckResult:
    missing = [text for text in verification["required_skill_invariants"] if text not in skill_md]
    return _result(
        "CS-06",
        "SKILL.md states every required invariant verbatim",
        not missing,
        f"{len(verification['required_skill_invariants'])} invariants present",
        f"missing from SKILL.md: {missing}",
    )


def check_review_date(manifest: dict[str, Any], today: date) -> CheckResult:
    skill = manifest["skill"]
    pinned = date.fromisoformat(skill["pinned_at"])
    review_by = date.fromisoformat(skill["review_by"])
    if review_by <= pinned:
        return CheckResult(
            "CS-07",
            "skill carries a future review date",
            Status.FAIL,
            f"review_by {review_by} is not after pinned_at {pinned}",
        )
    if today > review_by:
        return CheckResult(
            "CS-07",
            "skill carries a future review date",
            Status.WARN,
            f"skill knowledge expired on {review_by}; re-pin against current provider "
            "documentation before relying on it",
        )
    return CheckResult(
        "CS-07",
        "skill carries a future review date",
        Status.PASS,
        f"pinned {pinned}, review by {review_by}",
    )


def run_consistency_checks(
    manifest: dict[str, Any],
    identifiers: dict[str, Any],
    capabilities: dict[str, Any],
    verification: dict[str, Any],
    skill_md: str,
    skill_root: Path,
    today: date,
) -> list[CheckResult]:
    return [
        check_version_declared(manifest, skill_md),
        check_identifiers_documented(identifiers, skill_md),
        check_reference_files_exist(manifest, skill_root),
        check_capability_dispositions(capabilities),
        check_string_replace_rejected(capabilities),
        check_invariants_documented(verification, skill_md),
        check_review_date(manifest, today),
    ]
