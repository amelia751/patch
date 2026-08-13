"""Codebase tree shaping, without contacting GitHub."""

from packages.state.codebase import (
    build_file_tree,
    codebase_payload,
    imported_repo,
    safe_repo_path,
)


def test_safe_repo_path_rejects_traversal() -> None:
    assert safe_repo_path("../secrets") is None
    assert safe_repo_path("src/../../etc/passwd") is None
    assert safe_repo_path("") is None


def test_safe_repo_path_accepts_a_nested_file() -> None:
    assert safe_repo_path("src/index.ts") == "src/index.ts"
    assert safe_repo_path("/README.md") == "README.md"


def test_imported_repo_prefers_project_repositories() -> None:
    source = imported_repo(
        {
            "repositories": [
                {"full_name": "amelia751/egaki", "default_branch": "main"},
            ],
            "workspaces": [
                {
                    "repo_url": "https://github.com/amelia751/egaki",
                    "repo_branch": "main",
                }
            ],
        }
    )
    assert source == ("amelia751", "egaki", "main")


def test_imported_repo_falls_back_to_workspace_url() -> None:
    source = imported_repo(
        {
            "repositories": [],
            "workspaces": [
                {
                    "repo_url": "https://github.com/amelia751/egaki.git",
                    "repo_branch": "develop",
                }
            ],
        }
    )
    assert source == ("amelia751", "egaki", "develop")


def test_imported_repo_is_absent_without_a_github_url() -> None:
    assert imported_repo({"repositories": [], "workspaces": []}) is None


def test_build_file_tree_nests_blobs_under_folders() -> None:
    tree = build_file_tree(
        [
            {"path": "src", "type": "tree"},
            {"path": "src/index.ts", "type": "blob", "size": 12},
            {"path": "README.md", "type": "blob", "size": 80},
        ]
    )
    names = [node["name"] for node in tree]
    assert names == ["src", "README.md"]
    assert tree[0]["type"] == "folder"
    assert tree[0]["children"][0]["path"] == "src/index.ts"
    assert tree[1]["type"] == "file"


def test_build_file_tree_skips_vendor_directories() -> None:
    tree = build_file_tree(
        [
            {"path": "package.json", "type": "blob"},
            {"path": "node_modules/left-pad/index.js", "type": "blob"},
            {"path": ".next/cache", "type": "tree"},
        ]
    )
    assert [node["path"] for node in tree] == ["package.json"]


def test_codebase_payload_matches_the_dashboard_shape() -> None:
    payload = codebase_payload(
        {
            "sha": "abcdef1234567890",
            "ref": "main",
            "default_branch": "main",
            "committed_at": "2026-08-12T00:00:00Z",
            "created_by": "amelia751",
            "truncated": False,
            "entries": [
                {"path": "README.md", "type": "blob", "size": 10},
            ],
        }
    )
    assert payload["branch"] == "main"
    assert payload["current_version"] == "abcdef1"
    assert payload["source"] == "github"
    assert payload["stats"]["total_files"] == 1
    assert payload["file_tree"][0]["path"] == "README.md"
    assert payload["versions"][0]["commit_sha"] == "abcdef1"
