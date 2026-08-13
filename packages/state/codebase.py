"""Dashboard codebase tree built from a GitHub git tree.

The Codebase tab asks for a nested `file_tree`. GitHub returns a flat recursive
list. This module only rearranges what GitHub sent; it never invents paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from packages.state.projects import full_name_from_repo_url

# Generated and vendor trees drown the tab and are not the imported product.
_SKIP_SEGMENTS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".next",
        ".venv",
        "__pycache__",
        "dist",
        "node_modules",
        "vendor",
    }
)


def safe_repo_path(raw: str) -> str | None:
    """Return a repository-relative path, or None if it could escape the repo."""
    path = raw.strip().lstrip("/")
    if not path or "\\" in path:
        return None
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return "/".join(parts)


def imported_repo(project: Mapping[str, Any]) -> tuple[str, str, str] | None:
    """`(owner, repo, branch)` from the project's first GitHub import, or None."""
    repos = project.get("repositories") or []
    workspaces = project.get("workspaces") or []
    full_name = ""
    branch = "main"
    if repos:
        first = repos[0]
        full_name = str(first.get("full_name") or "")
        branch = str(first.get("default_branch") or branch) or branch
    elif workspaces:
        parsed = full_name_from_repo_url(str(workspaces[0].get("repo_url") or ""))
        full_name = parsed or ""
    if workspaces:
        branch = str(workspaces[0].get("repo_branch") or branch) or branch
    if full_name.count("/") != 1:
        return None
    owner, repo = full_name.split("/", 1)
    if not owner or not repo:
        return None
    return owner, repo, branch


def _skipped(path: str) -> bool:
    return any(part in _SKIP_SEGMENTS for part in path.split("/"))


def build_file_tree(entries: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Nest GitHub git-tree entries into the dashboard's `file_tree` shape."""
    root: dict[str, Any] = {"children": {}}
    for entry in entries:
        path = str(entry.get("path") or "")
        kind = entry.get("type")
        if not path or _skipped(path) or kind not in {"blob", "tree"}:
            continue
        parts = path.split("/")
        cursor = root
        for index, part in enumerate(parts):
            children: dict[str, Any] = cursor.setdefault("children", {})
            is_last = index == len(parts) - 1
            if part not in children:
                node_path = "/".join(parts[: index + 1])
                is_file = is_last and kind == "blob"
                children[part] = {
                    "id": node_path,
                    "name": part,
                    "path": node_path,
                    "type": "file" if is_file else "folder",
                    "children": None if is_file else {},
                }
            cursor = children[part]
    return _children_list(root)


def _children_list(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    kids = node.get("children") or {}
    out: list[dict[str, Any]] = []
    for name in sorted(kids, key=lambda item: (kids[item]["type"] == "file", item.lower())):
        child = kids[name]
        item: dict[str, Any] = {
            "id": child["id"],
            "name": child["name"],
            "path": child["path"],
            "type": child["type"],
        }
        if child["type"] == "folder":
            item["children"] = _children_list(child)
        out.append(item)
    return out


def _count(nodes: list[Mapping[str, Any]]) -> tuple[int, int]:
    files = 0
    folders = 0
    for node in nodes:
        if node.get("type") == "file":
            files += 1
            continue
        folders += 1
        nested_files, nested_folders = _count(list(node.get("children") or []))
        files += nested_files
        folders += nested_folders
    return files, folders


def codebase_payload(tree: Mapping[str, Any]) -> dict[str, Any]:
    """Shape GitHub tree metadata into the Codebase tab's `CodebaseResponse`."""
    file_tree = build_file_tree(list(tree.get("entries") or []))
    files, folders = _count(file_tree)
    sha = str(tree.get("sha") or "")
    short = sha[:7] if sha else ""
    branch = str(tree.get("ref") or tree.get("default_branch") or "main") or "main"
    return {
        "current_version": short or branch,
        "branch": branch,
        "versions": [
            {
                "id": short or branch,
                "created_at": str(tree.get("committed_at") or ""),
                "created_by": str(tree.get("created_by") or ""),
                "label": branch,
                "status": "imported",
                "commit_sha": short or sha,
            }
        ],
        "file_tree": file_tree,
        "services": [],
        "stats": {
            "total_files": files,
            "total_lines": 0,
            "total_folders": folders,
        },
        "source": "github",
        "truncated": bool(tree.get("truncated")),
    }
