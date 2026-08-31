"""Structural guarantee: this service does not write to logs or stdout.

A token that is never logged cannot leak through a log. Rather than auditing
every future call site, the tree simply has no logging or printing in it — the
one operator-facing line lives in the process entry point, which never sees a
credential. Adding a logger here is a deliberate change that fails this test
first and has to be argued for.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "patchapi_github_tools"
ENTRY_POINT = "__main__.py"

SOURCE_FILES = sorted(path for path in SRC.rglob("*.py"))


def test_the_tree_has_source_to_audit():
    assert len(SOURCE_FILES) >= 10


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: path.name)
def test_no_logging_or_printing_outside_the_entry_point(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    if path.name != ENTRY_POINT:
        assert "print" not in called, f"{path.name} prints"
    assert not {"debug", "info", "warning", "error", "exception"} & attributes, f"{path.name} logs"
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "logging" not in imported, f"{path.name} imports logging"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: path.name)
def test_reveal_is_only_called_where_a_credential_is_used(path):
    """`reveal()` is the single greppable exit from `Secret`.

    It may appear only where a credential is genuinely handed to GitHub or to
    the signing primitive: nowhere else in the tree.
    """
    permitted = {"auth.py", "credentials.py"}
    source = path.read_text(encoding="utf-8")
    if path.name in permitted:
        return
    assert ".reveal()" not in source, f"{path.name} unwraps a credential"


def test_error_payloads_never_include_upstream_bodies(client, fake_github, impact_headers):
    response = client.post(
        "/v1/capabilities/get_file",
        json={"repo": "amelia751/storygen", "path": "README.md", "ref": "c" * 40},
        headers=impact_headers,
    )
    assert response.status_code == 502
    body = response.text
    assert "Authorization" not in body
    assert "ghs_" not in body
