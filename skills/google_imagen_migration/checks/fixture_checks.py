"""Deterministic checks that a change fixture matches what this skill is pinned to.

Drift between the provider notice and the skill's pinned knowledge is a finding,
not something to reconcile silently: a skill that quietly accepts new identifiers
would let unreviewed provider claims drive a code change.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlparse

from check_results import CheckResult, Status

REQUIRED_FIXTURE_KEYS = (
    "fixture_version",
    "provider",
    "change_id",
    "change_type",
    "effective_at",
    "affected_identifiers",
    "recommended_replacement",
    "source_urls",
    "source_snapshot",
    "trust",
    "capability_notes",
    "verification_requirements",
)


def _result(check_id: str, title: str, ok: bool, detail_ok: str, detail_bad: str) -> CheckResult:
    return CheckResult(
        id=check_id,
        title=title,
        status=Status.PASS if ok else Status.FAIL,
        detail=detail_ok if ok else detail_bad,
    )


def check_required_keys(fixture: dict[str, Any]) -> CheckResult:
    missing = [key for key in REQUIRED_FIXTURE_KEYS if key not in fixture]
    return _result(
        "FX-01",
        "fixture carries every required field",
        not missing,
        f"all {len(REQUIRED_FIXTURE_KEYS)} required fields present",
        f"missing fields: {', '.join(missing)}",
    )


def check_provider(fixture: dict[str, Any], manifest: dict[str, Any]) -> CheckResult:
    expected = manifest["skill"]["provider"]
    actual = fixture.get("provider")
    return _result(
        "FX-02",
        "fixture provider matches the skill provider",
        actual == expected,
        f"provider is {expected!r}",
        f"skill handles {expected!r} but fixture declares {actual!r}",
    )


def check_change_type(fixture: dict[str, Any], manifest: dict[str, Any]) -> CheckResult:
    allowed = manifest["applies_to"]["change_types"]
    actual = fixture.get("change_type")
    return _result(
        "FX-03",
        "change type is one this skill applies to",
        actual in allowed,
        f"change_type {actual!r} is in {allowed}",
        f"change_type {actual!r} is not in {allowed}",
    )


def check_effective_date(fixture: dict[str, Any], identifiers: dict[str, Any]) -> CheckResult:
    raw = fixture.get("effective_at")
    try:
        parsed = date.fromisoformat(str(raw))
    except ValueError:
        return CheckResult(
            "FX-04",
            "effective date parses and matches the pin",
            Status.FAIL,
            f"effective_at {raw!r} is not an ISO-8601 date",
        )
    pinned = date.fromisoformat(identifiers["effective_at"])
    return _result(
        "FX-04",
        "effective date parses and matches the pin",
        parsed == pinned,
        f"effective_at is {parsed.isoformat()}",
        f"effective_at {parsed.isoformat()} differs from the pinned {pinned.isoformat()}",
    )


def check_identifiers(fixture: dict[str, Any], identifiers: dict[str, Any]) -> CheckResult:
    pinned = set(identifiers["affected_identifiers"])
    actual = set(fixture.get("affected_identifiers") or [])
    added = sorted(actual - pinned)
    removed = sorted(pinned - actual)
    detail_bad = "; ".join(
        part
        for part in (
            f"fixture adds {added}" if added else "",
            f"fixture drops {removed}" if removed else "",
        )
        if part
    )
    return _result(
        "FX-05",
        "affected identifiers match the skill's pinned set",
        not added and not removed,
        f"{len(pinned)} pinned identifiers match exactly",
        f"identifier drift — the skill must be re-pinned by a human: {detail_bad}",
    )


def check_replacement(fixture: dict[str, Any], identifiers: dict[str, Any]) -> CheckResult:
    expected = identifiers["recommended_replacement"]
    actual = fixture.get("recommended_replacement")
    return _result(
        "FX-06",
        "recommended replacement matches the skill's pin",
        actual == expected,
        f"replacement is {expected!r} (resolve against the target catalog before use)",
        f"fixture recommends {actual!r} but the skill is pinned to {expected!r}",
    )


def check_source_urls(fixture: dict[str, Any], identifiers: dict[str, Any]) -> CheckResult:
    allowed = set(identifiers["allowed_source_hosts"])
    urls = fixture.get("source_urls") or []
    if not urls:
        return CheckResult(
            "FX-07",
            "sources are official provider URLs over https",
            Status.FAIL,
            "no source_urls — a change with no cited source is not evidence",
        )
    bad: list[str] = []
    for url in urls:
        parsed = urlparse(str(url))
        if parsed.scheme != "https" or parsed.hostname not in allowed:
            bad.append(str(url))
    return _result(
        "FX-07",
        "sources are official provider URLs over https",
        not bad,
        f"{len(urls)} source URL(s) on {sorted(allowed)}",
        f"off-allowlist or non-https source(s): {bad}",
    )


def check_trust_classification(fixture: dict[str, Any]) -> CheckResult:
    actual = (fixture.get("trust") or {}).get("classification")
    return _result(
        "FX-08",
        "fixture is labelled untrusted provider input",
        actual == "untrusted_provider_input",
        "classification is untrusted_provider_input",
        f"trust.classification is {actual!r}, expected 'untrusted_provider_input'",
    )


def check_capability_notes(fixture: dict[str, Any]) -> CheckResult:
    notes = fixture.get("capability_notes") or {}
    statement = str(notes.get("statement", ""))
    families_documented = bool(notes.get("imagen_family")) and bool(
        notes.get("gemini_image_family")
    )
    declares_difference = "not interchangeable" in statement.lower()
    ok = families_documented and declares_difference
    return _result(
        "FX-09",
        "fixture states the two model families are not interchangeable",
        ok,
        "both request surfaces are documented and declared non-interchangeable",
        "capability_notes must document both families and state that they are "
        "not interchangeable; a string-swap migration is otherwise implied",
    )


def check_verification_requirements(
    fixture: dict[str, Any], verification: dict[str, Any]
) -> CheckResult:
    required = verification["required_fixture_gates"]
    actual = fixture.get("verification_requirements") or {}
    unmet = [gate for gate in required if actual.get(gate) is not True]
    return _result(
        "FX-10",
        "fixture demands every verification gate the skill requires",
        not unmet,
        f"all {len(required)} gates required: {required}",
        f"gate(s) missing or not required: {unmet}",
    )


def check_source_snapshot(fixture: dict[str, Any], require_snapshot: bool) -> CheckResult:
    snapshot = fixture.get("source_snapshot") or {}
    captured = snapshot.get("status") == "CAPTURED" and bool(snapshot.get("sha256"))
    if captured:
        return CheckResult(
            "FX-11",
            "provider evidence is captured and hashed",
            Status.PASS,
            f"snapshot {snapshot.get('path')} sha256={snapshot.get('sha256')}",
        )
    reason = snapshot.get("reason") or "no reason recorded"
    if require_snapshot:
        return CheckResult(
            "FX-11",
            "provider evidence is captured and hashed",
            Status.FAIL,
            f"no hashed snapshot and --require-snapshot was set: {reason}",
        )
    return CheckResult(
        "FX-11",
        "provider evidence is captured and hashed",
        Status.WARN,
        "evidence gap: provider claim is uncorroborated by a hashed snapshot "
        f"({snapshot.get('status')!r}). Automation downgrades to HUMAN_REQUIRED. {reason}",
    )


def run_fixture_checks(
    fixture: dict[str, Any],
    manifest: dict[str, Any],
    identifiers: dict[str, Any],
    verification: dict[str, Any],
    require_snapshot: bool = False,
) -> list[CheckResult]:
    return [
        check_required_keys(fixture),
        check_provider(fixture, manifest),
        check_change_type(fixture, manifest),
        check_effective_date(fixture, identifiers),
        check_identifiers(fixture, identifiers),
        check_replacement(fixture, identifiers),
        check_source_urls(fixture, identifiers),
        check_trust_classification(fixture),
        check_capability_notes(fixture),
        check_verification_requirements(fixture, verification),
        check_source_snapshot(fixture, require_snapshot),
    ]
