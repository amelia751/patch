"""Codebase tree shaping, without contacting GitHub."""

from packages.state.codebase import (
    build_file_tree,
    codebase_payload,
    codebase_payload_from_repos,
    imported_repo,
    imported_repos,
    resolve_codebase_file,
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
                {"full_name": "amelia751/webapp", "default_branch": "main"},
            ],
            "workspaces": [
                {
                    "repo_url": "https://github.com/amelia751/webapp",
                    "repo_branch": "main",
                }
            ],
        }
    )
    assert source == ("amelia751", "webapp", "main")


def test_imported_repo_falls_back_to_workspace_url() -> None:
    source = imported_repo(
        {
            "repositories": [],
            "workspaces": [
                {
                    "repo_url": "https://github.com/amelia751/webapp.git",
                    "repo_branch": "develop",
                }
            ],
        }
    )
    assert source == ("amelia751", "webapp", "develop")


def test_imported_repo_is_absent_without_a_github_url() -> None:
    assert imported_repo({"repositories": [], "workspaces": []}) is None


def test_imported_repo_selects_a_named_second_import() -> None:
    source = imported_repo(
        {
            "repositories": [
                {"full_name": "amelia751/webapp", "default_branch": "main"},
                {"full_name": "amelia751/storygen", "default_branch": "main"},
            ],
            "workspaces": [
                {
                    "repo_url": "https://github.com/amelia751/webapp.git",
                    "repo_branch": "develop",
                },
                {
                    "repo_url": "https://github.com/amelia751/storygen.git",
                    "repo_branch": "main",
                },
            ],
        },
        full_name="amelia751/storygen",
    )
    assert source == ("amelia751", "storygen", "main")


def test_imported_repo_does_not_borrow_another_repo_workspace_branch() -> None:
    source = imported_repo(
        {
            "repositories": [
                {"full_name": "amelia751/webapp", "default_branch": "main"},
                {"full_name": "amelia751/storygen", "default_branch": "main"},
            ],
            "workspaces": [
                {
                    "repo_url": "https://github.com/amelia751/webapp.git",
                    "repo_branch": "develop",
                }
            ],
        },
        full_name="amelia751/storygen",
    )
    assert source == ("amelia751", "storygen", "main")


def test_imported_repo_rejects_a_repo_the_project_did_not_import() -> None:
    assert (
        imported_repo(
            {
                "repositories": [
                    {"full_name": "amelia751/webapp", "default_branch": "main"},
                ],
                "workspaces": [],
            },
            full_name="amelia751/storygen",
        )
        is None
    )


def test_build_file_tree_prefixes_paths_for_a_second_repo() -> None:
    tree = build_file_tree(
        [{"path": "generate.py", "type": "blob"}],
        path_prefix="storygen",
    )
    assert tree[0]["path"] == "storygen/generate.py"
    assert tree[0]["id"] == "storygen/generate.py"


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


def test_imported_repos_lists_every_import_in_order() -> None:
    found = imported_repos(
        {
            "repositories": [
                {"name": "webapp", "full_name": "amelia751/webapp", "default_branch": "main"},
                {
                    "name": "storygen",
                    "full_name": "amelia751/storygen",
                    "default_branch": "main",
                },
            ],
            "workspaces": [],
        }
    )
    assert [item[0] for item in found] == ["amelia751/webapp", "amelia751/storygen"]


def test_resolve_codebase_file_strips_the_repo_prefix_when_there_are_two() -> None:
    project = {
        "repositories": [
            {"name": "webapp", "full_name": "amelia751/webapp", "default_branch": "main"},
            {
                "name": "storygen",
                "full_name": "amelia751/storygen",
                "default_branch": "main",
            },
        ],
        "workspaces": [],
    }
    assert resolve_codebase_file(project, "amelia751/storygen/generate.py") == (
        "amelia751",
        "storygen",
        "main",
        "generate.py",
    )
    assert resolve_codebase_file(project, "generate.py") is None
    assert resolve_codebase_file(project, "storygen/generate.py") is None


def test_resolve_codebase_file_is_flat_for_a_single_import() -> None:
    project = {
        "repositories": [
            {"name": "webapp", "full_name": "amelia751/webapp", "default_branch": "main"},
        ],
        "workspaces": [],
    }
    assert resolve_codebase_file(project, "src/index.ts") == (
        "amelia751",
        "webapp",
        "main",
        "src/index.ts",
    )


def test_combined_payload_wraps_each_repo_as_a_directory_root() -> None:
    payload = codebase_payload_from_repos(
        [
            (
                "amelia751/webapp",
                {"entries": [{"path": "README.md", "type": "blob"}], "ref": "main", "sha": "aaa"},
            ),
            (
                "amelia751/storygen",
                {
                    "entries": [{"path": "generate.py", "type": "blob"}],
                    "ref": "main",
                    "sha": "bbb",
                },
            ),
        ]
    )
    assert [node["type"] for node in payload["file_tree"]] == ["directory", "directory"]
    assert [node["name"] for node in payload["file_tree"]] == [
        "amelia751/webapp",
        "amelia751/storygen",
    ]
    assert payload["file_tree"][1]["children"][0]["path"] == "amelia751/storygen/generate.py"
    assert payload["stats"]["total_files"] == 2


def test_combined_payload_keeps_an_empty_second_repo_as_a_directory() -> None:
    payload = codebase_payload_from_repos(
        [
            (
                "amelia751/webapp",
                {"entries": [{"path": "README.md", "type": "blob"}], "ref": "main"},
            ),
            ("amelia751/storygen", {"entries": [], "ref": "main"}),
        ]
    )
    assert [node["name"] for node in payload["file_tree"]] == [
        "amelia751/webapp",
        "amelia751/storygen",
    ]
    assert payload["file_tree"][1]["type"] == "directory"
    assert payload["file_tree"][1]["children"] == []


def test_combined_payload_wraps_a_single_import_as_a_directory() -> None:
    payload = codebase_payload_from_repos(
        [
            (
                "amelia751/webapp",
                {"entries": [{"path": "README.md", "type": "blob"}], "ref": "main", "sha": "aaa"},
            ),
        ]
    )
    assert [node["name"] for node in payload["file_tree"]] == ["amelia751/webapp"]
    assert payload["file_tree"][0]["type"] == "directory"
    assert payload["file_tree"][0]["children"][0]["path"] == "amelia751/webapp/README.md"


def test_codebase_payload_matches_the_dashboard_shape() -> None:
    payload = codebase_payload(
        {
            "full_name": "amelia751/webapp",
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
    assert payload["repository"] == "amelia751/webapp"
    assert payload["current_version"] == "abcdef1"
    assert payload["source"] == "github"
    assert payload["stats"]["total_files"] == 1
    assert payload["file_tree"][0]["path"] == "README.md"
    assert payload["versions"][0]["commit_sha"] == "abcdef1"
