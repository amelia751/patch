"""Read-only index tools shared by Change Intelligence and Impact.

The repo indexer is the Cursor-like corpus: paths, identifiers, and excerpts
already extracted from every imported tree. These tools page that inventory
into a prompt. They do not walk the checkout and they do not write.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.context import RunContext
from agents.tools.results import ok

MAX_HITS_RETURNED: Final[int] = 200


def build_index_lookup_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Bind index readers to this run's preloaded `project_provider_usages`."""

    def lookup_index_usages(identifiers: list[str] | None = None) -> dict[str, Any]:
        """Read the project's indexed inventory for these identifiers.

        Rows come from `project_provider_usages` (the repo indexer), not from
        a live walk. Empty means this run was not bound to a project inventory,
        or the index has no rows for those ids. Use this to see which imported
        repos name a model before you open a file.
        """
        wanted = {item.strip() for item in (identifiers or []) if item and item.strip()}
        rows = list(context.index_usages)
        if wanted:
            rows = [row for row in rows if str(row.get("identifier") or "") in wanted]
        return ok(
            project_id=context.project_id,
            count=len(rows),
            usages=rows[:MAX_HITS_RETURNED],
            truncated=len(rows) > MAX_HITS_RETURNED,
            source="project_provider_usages",
        )

    def search_index(query: str) -> dict[str, Any]:
        """Filter the project index by a substring of identifier, path, or excerpt.

        This is how you traverse an imported tree quickly: the indexer already
        ran. A miss is not proof the repository is clean — only that this
        shard has no row containing `query`.
        """
        needle = (query or "").strip().lower()
        rows = list(context.index_usages)
        if needle:
            rows = [
                row
                for row in rows
                if needle
                in " ".join(
                    str(row.get(key) or "")
                    for key in ("identifier", "file_path", "repository", "excerpt", "usage_kind")
                ).lower()
            ]
        return ok(
            project_id=context.project_id,
            query=needle,
            count=len(rows),
            usages=rows[:MAX_HITS_RETURNED],
            truncated=len(rows) > MAX_HITS_RETURNED,
            source="project_provider_usages",
        )

    return [lookup_index_usages, search_index]


__all__ = ["MAX_HITS_RETURNED", "build_index_lookup_tools"]
