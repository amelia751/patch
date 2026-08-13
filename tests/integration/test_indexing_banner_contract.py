"""The Codebase indexing banner is driven by live state, not by the preview switch.

`repo-indexer.md` §7.6 lists three things that must be true once the indexing
endpoint exists: the force-show flag is off, the sign takes a real `progress`,
and the tab polls `GET /api/projects/{id}/indexing`. A banner still pinned on by
the preview constant would show "Indexing codebase" over a project nobody is
indexing — a demo-visible lie about what the system is doing.

This reads the TypeScript as text on purpose. The assertion is about three
literals in two files, and a Node toolchain in the Python suite would cost far
more than the fact is worth.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CODEBASE_TAB_DIR = (
    REPO_ROOT / "apps" / "web" / "src" / "components" / "interface" / "ops" / "codebase-tab"
)
SIGN_TSX = CODEBASE_TAB_DIR / "codebase-indexing-sign.tsx"
TAB_TSX = CODEBASE_TAB_DIR / "codebase-tab.tsx"

# `export const FORCE_SHOW_CODEBASE_INDEXING = <literal>;` — the literal is what
# the test is about, so it is captured rather than matched.
FORCE_SHOW_RE = re.compile(
    r"export\s+const\s+FORCE_SHOW_CODEBASE_INDEXING\s*(?::[^=]+)?=\s*(\w+)\s*;"
)


@pytest.fixture(scope="module")
def sign_source() -> str:
    assert SIGN_TSX.is_file(), f"indexing sign is missing: {SIGN_TSX}"
    return SIGN_TSX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_source() -> str:
    assert TAB_TSX.is_file(), f"codebase tab is missing: {TAB_TSX}"
    return TAB_TSX.read_text(encoding="utf-8")


def test_force_show_preview_switch_is_off(sign_source: str) -> None:
    match = FORCE_SHOW_RE.search(sign_source)
    assert match is not None, "FORCE_SHOW_CODEBASE_INDEXING is no longer declared as a const"
    assert match.group(1) == "false", (
        "FORCE_SHOW_CODEBASE_INDEXING is on: the banner would render over every "
        "project regardless of whether an index is running (repo-indexer.md §7.6)"
    )


def test_sign_accepts_a_live_progress_value(sign_source: str) -> None:
    assert re.search(r"progress\?\s*:\s*number", sign_source), (
        "CodebaseIndexingSign no longer takes an optional numeric `progress` prop"
    )
    # Without this guard the preview interval keeps ticking over a live value.
    assert re.search(r"if\s*\(\s*progress\s*!=\s*null\s*\)\s*return", sign_source), (
        "the preview animation does not stand down when a live progress arrives"
    )


def test_wrapper_passes_live_progress_and_hides_when_idle(sign_source: str) -> None:
    assert re.search(r"<CodebaseIndexingSign\s+progress=", sign_source), (
        "withCodebaseIndexingSign renders the sign without passing progress"
    )
    assert 'indexing?.status === "indexing"' in sign_source, (
        "the wrapper does not gate on a live `indexing` status"
    )


def test_tab_polls_the_indexing_endpoint(tab_source: str) -> None:
    assert "/api/projects/${projectId}/indexing" in tab_source, (
        "the Codebase tab does not poll GET /api/projects/{id}/indexing"
    )
    assert re.search(r"INDEXING_POLL_MS\s*=\s*(\d+)", tab_source), (
        "the poll interval is not a named constant"
    )


def test_indexing_route_is_served_by_the_control_plane() -> None:
    """The endpoint the tab polls exists on the Python side of the contract."""
    routes = (REPO_ROOT / "packages" / "state" / "project_routes.py").read_text(encoding="utf-8")
    assert '@router.get("/{project_id}/indexing")' in routes, (
        "GET /api/projects/{id}/indexing is not registered; the banner would poll a 404"
    )
    assert "indexing_for_project" in routes, (
        "the indexing route does not read the repo_index_state rollup"
    )
