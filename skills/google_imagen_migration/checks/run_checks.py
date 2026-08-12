#!/usr/bin/env python3
"""Entry point for the Google Imagen migration skill's deterministic checks.

    python skills/google_imagen_migration/checks/run_checks.py [options]

Exit codes are part of the contract (mirrored in skill.json):

    0  the skill may be applied; verdict is SKILL_APPLICABLE or HUMAN_REQUIRED
    1  a deterministic check failed; the skill must not be applied
    2  fail closed — a document ingested as provider evidence issued directives

The checks are deterministic on purpose. Nothing here calls a model: this is the
floor a model's judgement is measured against, so it must be reproducible.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_results import CheckReport, Status
from consistency_checks import run_consistency_checks
from fixture_checks import run_fixture_checks
from language_checks import scan_path
from skill_loader import (
    SKILL_ROOT,
    SkillLoadError,
    default_fixture_path,
    load_json,
    load_manifest,
    load_reference,
    read_text,
)

_STATUS_MARK = {Status.PASS: "ok  ", Status.WARN: "warn", Status.FAIL: "FAIL"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_checks.py",
        description="Deterministic checks for the Google Imagen migration skill.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="change fixture to check (default: the one pinned in skill.json)",
    )
    parser.add_argument(
        "--scan",
        type=Path,
        action="append",
        default=[],
        help="additional untrusted provider document to scan for directive language",
    )
    parser.add_argument(
        "--require-snapshot",
        action="store_true",
        help="treat an uncaptured provider snapshot as a failure instead of an evidence gap",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="override today's date for the skill-expiry check (testing)",
    )
    return parser.parse_args(argv)


def build_report(args: argparse.Namespace) -> CheckReport:
    manifest = load_manifest()
    identifiers = load_reference(manifest, "identifiers")
    capabilities = load_reference(manifest, "capabilities")
    verification = load_reference(manifest, "verification")
    untrusted_language = load_reference(manifest, "untrusted_language")
    skill_md = read_text(SKILL_ROOT / "SKILL.md")

    fixture_path = args.fixture or default_fixture_path(manifest)
    fixture = load_json(fixture_path)
    if not isinstance(fixture, dict):
        raise SkillLoadError(f"{fixture_path} must contain a JSON object")

    report = CheckReport()

    # Untrusted input is screened before anything reads its content as fact.
    report.add(scan_path(fixture_path, read_text(fixture_path), untrusted_language))
    for extra in args.scan:
        report.add(scan_path(extra, read_text(extra), untrusted_language))

    report.extend(
        run_consistency_checks(
            manifest=manifest,
            identifiers=identifiers,
            capabilities=capabilities,
            verification=verification,
            skill_md=skill_md,
            skill_root=SKILL_ROOT,
            today=args.today or datetime.now(UTC).date(),
        )
    )
    report.extend(
        run_fixture_checks(
            fixture=fixture,
            manifest=manifest,
            identifiers=identifiers,
            verification=verification,
            require_snapshot=args.require_snapshot,
        )
    )
    return report


def render_text(report: CheckReport, fixture_path: Path) -> str:
    lines = [f"skill: google_imagen_migration   fixture: {fixture_path}"]
    for result in report.results:
        lines.append(f"{_STATUS_MARK[result.status]} {result.id:<24} {result.title}")
        if result.status is not Status.PASS:
            lines.append(f"       {result.detail}")
    counts = report.to_dict()["counts"]
    lines.append(
        f"verdict: {report.verdict().value}   "
        f"pass={counts['pass']} warn={counts['warn']} fail={counts['fail']}"
    )
    if report.fail_closed:
        lines.append("fail closed: untrusted directive language in provider evidence")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args)
    except SkillLoadError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    fixture_path = args.fixture or default_fixture_path(load_manifest())
    if args.json:
        payload = report.to_dict()
        payload["fixture"] = str(fixture_path)
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(report, fixture_path))
    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
