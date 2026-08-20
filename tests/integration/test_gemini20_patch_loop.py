"""The two halves of the Gemini 2.0 slice that must agree, checked without a model.

The vertical slice is only meaningful if the pinned deprecation fixture and the
pinned migration target describe the same change. `scripts/smoke_patch_loop.py`
proves the loop converges, but it needs credentials and a live model to say so.
This test covers the seam underneath: the fixture names exactly the four retired
identifiers Google published, the recommended replacement is the one the June 1
changelog names, and the deterministic scanner really finds the retired binding
in the target the agents are pointed at.

Nothing here calls a model, opens a sandbox, or touches the network, so a broken
pin surfaces in the ordinary suite rather than only in the smoke run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from packages.repo_scan import scan_tree

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
FIXTURE: Final[Path] = REPO_ROOT / "demo" / "fixtures" / "google-gemini20-deprecation.json"
TARGET: Final[Path] = REPO_ROOT / "demo" / "storygen"
ENTRYPOINT: Final[str] = "lib/gemini.ts"

# Restated here rather than read from the fixture: a test that derives its
# expectation from the file under test cannot detect the file changing.
RETIRED_IDENTIFIERS: Final[frozenset[str]] = frozenset(
    {
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-lite-001",
    }
)
REPLACEMENT: Final[str] = "gemini-3.5-flash"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_names_only_the_four_official_retired_identifiers() -> None:
    affected = load_fixture()["affected_identifiers"]
    assert isinstance(affected, list)
    # Set equality in both directions: a missing identifier leaves a real usage
    # unmigrated, and an extra one is an invented deprecation.
    assert set(affected) == RETIRED_IDENTIFIERS
    assert len(affected) == len(RETIRED_IDENTIFIERS), "the fixture lists a duplicate"


def test_fixture_pins_the_changelog_replacement() -> None:
    fixture = load_fixture()
    assert fixture["recommended_replacement"] == REPLACEMENT
    assert fixture["recommended_replacement"] not in RETIRED_IDENTIFIERS
    assert fixture["migration_character"] == "mechanical"


def test_fixture_carries_provider_evidence_and_marks_it_untrusted() -> None:
    """Fail-closed inputs: evidence that is captured, and labelled as data."""
    fixture = load_fixture()
    snapshot = fixture["source_snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["status"] == "CAPTURED"

    captured = REPO_ROOT / str(snapshot["path"])
    assert captured.is_file(), f"the fixture cites evidence that is not in the tree: {captured}"
    # A declared hash over an absent or edited excerpt is a fabricated citation,
    # which is the one failure mode the evidence field exists to rule out.
    digest = hashlib.sha256(captured.read_bytes()).hexdigest()
    assert digest == snapshot["sha256"]

    assert fixture["trust"]["classification"] == "untrusted_provider_input"  # type: ignore[index]


def test_scanner_finds_the_retired_binding_in_the_migration_target() -> None:
    result = scan_tree(TARGET, sorted(RETIRED_IDENTIFIERS))

    entrypoint_hits = [
        hit
        for hit in result.hits
        if hit.path == ENTRYPOINT and hit.identifier == "gemini-2.0-flash"
    ]
    assert entrypoint_hits, (
        f"the scanner found no gemini-2.0-flash in {ENTRYPOINT}; "
        f"scanned {result.files_scanned} file(s) under {TARGET}"
    )
    assert any("MODEL" in hit.excerpt for hit in entrypoint_hits), (
        "the scanner found the identifier but not the MODEL binding the patch must rewrite"
    )


def test_the_target_is_unpatched_and_the_replacement_is_absent() -> None:
    """The slice starts red. A target already naming the replacement proves nothing."""
    source = (TARGET / ENTRYPOINT).read_text(encoding="utf-8")
    assert 'MODEL = "gemini-2.0-flash"' in source
    assert REPLACEMENT not in source

    replacement_hits = scan_tree(TARGET, [REPLACEMENT]).hits
    assert [hit.path for hit in replacement_hits if hit.path == ENTRYPOINT] == []
