"""Console projects and the GitHub repos they import.

Writes belong here because the dashboard creates the tenancy row the rest of
the console hangs off. GitHub tokens never land in these queries.

Importing a repository also announces it: `repo-indexer.md` §6 — without the
`project-repo-added` event the row exists and nothing ever indexes it, so the
Codebase tab sits at `idle` forever. The event is published after the
transaction commits and never inside it, because an event announcing a row that
a rollback removed is a claim about state that does not exist. Publication
failure is logged and does not fail the write: Postgres is authoritative, and
Pub/Sub is how a worker is told to look at what Postgres already records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from packages.events.publisher import publish_async
from packages.events.repo_events import project_repo_added_event, project_repo_removed_event
from packages.state.indexing import mark_import_queued
from packages.state.pool import StateUnavailableError

if TYPE_CHECKING:
    import asyncpg

# What a repository is assumed to track until GitHub tells the console otherwise.
DEFAULT_BRANCH: Final[str] = "main"


def full_name_from_repo_url(repo_url: str) -> str | None:
    """Parse `owner/repo` out of a github.com URL. None if the URL is not that."""
    raw = repo_url.strip().rstrip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]
    marker = "github.com/"
    index = raw.lower().find(marker)
    if index < 0:
        if raw.count("/") == 1 and not raw.startswith("http"):
            owner, repo = raw.split("/", 1)
            if owner and repo:
                return f"{owner}/{repo}"
        return None
    owner_repo = raw[index + len(marker) :].strip("/")
    if owner_repo.count("/") != 1:
        return None
    owner, repo = owner_repo.split("/", 1)
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


async def announce_repository_added(project_id: UUID, repository: str, branch: str) -> bool:
    """Publish `project-repo-added` for a committed import. Never raises.

    Returns whether the event reached the topic, so a caller that wants to tell
    the operator "imported, not yet queued for indexing" can. Replaying an
    import republishes the same idempotency key rather than a second unit of
    work, which is what makes re-importing a repository safe.
    """
    result = await publish_async(
        project_repo_added_event(
            project_id=str(project_id),
            repository=repository,
            branch=branch,
            occurred_at=datetime.now(UTC).isoformat(),
        )
    )
    return result.published


async def _queue_index(
    pool: asyncpg.Pool, project_id: UUID, repository: str, branch: str
) -> None:
    """Publish, then flip the banner so the Code tab does not sit at idle."""
    await mark_import_queued(pool, project_id, repository, branch)


async def announce_repository_removed(project_id: UUID, repository: str, branch: str) -> bool:
    """Publish `project-repo-removed` after the row is gone. Never raises."""
    result = await publish_async(
        project_repo_removed_event(
            project_id=str(project_id),
            repository=repository,
            branch=branch,
            occurred_at=datetime.now(UTC).isoformat(),
        )
    )
    return result.published


def _project(row: Any, *, repositories: list[dict[str, Any]], workspaces: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "owner_id": str(row["owner_id"]),
        "team_id": str(row["team_id"]) if row["team_id"] is not None else None,
        "cloud_provider": row["cloud_provider"],
        "repositories": repositories,
        "workspaces": workspaces,
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _repository(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "name": row["name"],
        "full_name": row["full_name"],
        "default_branch": row["default_branch"],
        "private": row["private"],
        "html_url": row["html_url"],
    }


def _workspace(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "repo_url": row["repo_url"],
        "repo_branch": row["repo_branch"],
        "workspace_path": row["workspace_path"],
        "environment": row["environment"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


_PROJECT_SELECT = """
    SELECT
        id, owner_id, team_id, name, description,
        status::text AS status,
        cloud_provider::text AS cloud_provider,
        created_at, updated_at
    FROM projects
"""


async def _repos(connection: asyncpg.Connection, project_id: UUID) -> list[dict[str, Any]]:
    rows = await connection.fetch(
        """
        SELECT
            id, name, full_name, default_branch, private, html_url,
            kind::text AS type
        FROM project_repositories
        WHERE project_id = $1
        ORDER BY created_at
        """,
        project_id,
    )
    return [_repository(row) for row in rows]


async def _workspaces(connection: asyncpg.Connection, project_id: UUID) -> list[dict[str, Any]]:
    rows = await connection.fetch(
        """
        SELECT id, name, repo_url, repo_branch, workspace_path, environment,
               created_at, updated_at
        FROM workspaces
        WHERE project_id = $1
        ORDER BY created_at
        """,
        project_id,
    )
    return [_workspace(row) for row in rows]


async def _assemble(connection: asyncpg.Connection, row: Any) -> dict[str, Any]:
    project_id = row["id"]
    return _project(
        row,
        repositories=await _repos(connection, project_id),
        workspaces=await _workspaces(connection, project_id),
    )


async def create_project(pool: asyncpg.Pool, owner_id: UUID, name: str) -> dict[str, Any]:
    """Insert a draft project owned by the signed-in user."""
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("Project name cannot be empty")
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO projects (owner_id, name, status)
                VALUES ($1, $2, 'draft')
                RETURNING id, owner_id, team_id, name, description,
                          status::text AS status,
                          cloud_provider::text AS cloud_provider,
                          created_at, updated_at
                """,
                owner_id,
                trimmed,
            )
            return await _assemble(connection, row)
    except ValueError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not create project: {type(exc).__name__}") from exc


async def list_projects(pool: asyncpg.Pool, owner_id: UUID) -> list[dict[str, Any]]:
    """Return the signed-in user's projects, newest first."""
    try:
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                {_PROJECT_SELECT}
                WHERE owner_id = $1
                ORDER BY created_at DESC
                """,
                owner_id,
            )
            return [await _assemble(connection, row) for row in rows]
    except Exception as exc:
        raise StateUnavailableError(f"could not list projects: {type(exc).__name__}") from exc


async def read_project(
    pool: asyncpg.Pool, project_id: UUID, owner_id: UUID
) -> dict[str, Any] | None:
    """Return one project the user owns, or None."""
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                f"{_PROJECT_SELECT} WHERE id = $1 AND owner_id = $2",
                project_id,
                owner_id,
            )
            if row is None:
                return None
            return await _assemble(connection, row)
    except Exception as exc:
        raise StateUnavailableError(f"could not read project: {type(exc).__name__}") from exc


async def update_project_cloud_provider(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    *,
    cloud_provider: str | None,
) -> dict[str, Any] | None:
    """Set or clear the project's hosting provider. Does not connect a cloud account."""
    if cloud_provider is not None and cloud_provider not in {"aws", "gcp"}:
        raise ValueError("Invalid cloud provider. Must be 'aws', 'gcp', or null to clear")
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE projects
                SET cloud_provider = $3::cloud_provider, updated_at = now()
                WHERE id = $1 AND owner_id = $2
                RETURNING id, owner_id, team_id, name, description,
                          status::text AS status,
                          cloud_provider::text AS cloud_provider,
                          created_at, updated_at
                """,
                project_id,
                owner_id,
                cloud_provider,
            )
            if row is None:
                return None
            return await _assemble(connection, row)
    except ValueError:
        raise
    except Exception as exc:
        raise StateUnavailableError(
            f"could not update cloud provider: {type(exc).__name__}"
        ) from exc


async def update_project_name(
    pool: asyncpg.Pool, project_id: UUID, owner_id: UUID, name: str
) -> dict[str, Any] | None:
    """Rename a project the user owns."""
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("Project name cannot be empty")
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE projects
                SET name = $3, updated_at = now()
                WHERE id = $1 AND owner_id = $2
                RETURNING id, owner_id, team_id, name, description,
                          status::text AS status,
                          cloud_provider::text AS cloud_provider,
                          created_at, updated_at
                """,
                project_id,
                owner_id,
                trimmed,
            )
            if row is None:
                return None
            return await _assemble(connection, row)
    except ValueError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not update project: {type(exc).__name__}") from exc


async def delete_project(pool: asyncpg.Pool, project_id: UUID, owner_id: UUID) -> bool:
    """Delete a project the user owns. False if it was not theirs.

    The cascade takes every row keyed by `project_id`, but the index is not one
    of those: `repo_index_state` is keyed by repository and shared with whoever
    else imported it, so it is released by reference count rather than by
    deletion. Nothing decrements that count except a `project-repo-removed`
    event, so a project that vanishes without announcing its repositories
    leaves the shard held forever and the inventory attributed to nobody.

    Announced after the delete commits, for the same reason `remove_repository`
    does it: a project the indexer is told to release must actually be gone.
    """
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                owned = await connection.fetchval(
                    "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
                    project_id,
                    owner_id,
                )
                if owned is None:
                    return False
                imported = await connection.fetch(
                    "SELECT full_name, default_branch FROM project_repositories "
                    "WHERE project_id = $1",
                    project_id,
                )
                await connection.execute("DELETE FROM projects WHERE id = $1", project_id)
    except Exception as exc:
        raise StateUnavailableError(f"could not delete project: {type(exc).__name__}") from exc

    for row in imported:
        await announce_repository_removed(
            project_id,
            str(row["full_name"]),
            str(row["default_branch"] or DEFAULT_BRANCH) or DEFAULT_BRANCH,
        )
    return True


async def import_repo_workspace(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    *,
    name: str,
    repo_url: str,
    repo_branch: str,
    workspace_path: str | None,
    environment: str,
) -> dict[str, Any] | None:
    """Attach a GitHub repo and workspace to a project the user owns."""
    full_name = full_name_from_repo_url(repo_url)
    if full_name is None:
        raise ValueError("Repository URL must be a github.com owner/repo URL")
    repo_name = full_name.split("/", 1)[1]
    branch = (repo_branch or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
    path = (workspace_path or "").strip() or None
    env = (environment or "dev").strip() or "dev"
    workspace_name = (name or f"{repo_name} Workspace").strip() or f"{repo_name} Workspace"
    html_url = f"https://github.com/{full_name}"
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                owned = await connection.fetchval(
                    "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
                    project_id,
                    owner_id,
                )
                if owned is None:
                    return None
                repo_row = await connection.fetchrow(
                    """
                    INSERT INTO project_repositories (
                        project_id, kind, name, full_name, default_branch, html_url
                    )
                    VALUES ($1, 'backend', $2, $3, $4, $5)
                    ON CONFLICT (project_id, full_name) DO UPDATE
                    SET default_branch = EXCLUDED.default_branch,
                        html_url = EXCLUDED.html_url
                    RETURNING id
                    """,
                    project_id,
                    repo_name,
                    full_name,
                    branch,
                    html_url,
                )
                await connection.execute(
                    """
                    INSERT INTO workspaces (
                        project_id, repository_id, name, repo_url, repo_branch,
                        workspace_path, environment
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    project_id,
                    repo_row["id"],
                    workspace_name,
                    repo_url.strip(),
                    branch,
                    path,
                    env,
                )
                await connection.execute(
                    "UPDATE projects SET updated_at = now() WHERE id = $1",
                    project_id,
                )
                row = await connection.fetchrow(
                    f"{_PROJECT_SELECT} WHERE id = $1",
                    project_id,
                )
                project = await _assemble(connection, row)
    except ValueError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not import repository: {type(exc).__name__}") from exc
    await announce_repository_added(project_id, full_name, branch)
    await _queue_index(pool, project_id, full_name, branch)
    return project


async def add_repository(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    *,
    github_repo_full_name: str,
) -> dict[str, Any] | None:
    """Attach an additional GitHub repo to a project the user owns.

    Same rows as `import_repo_workspace`: a `project_repositories` row and a
    workspace. Add Repository used to write only the repo, so the Codebase tab
    (first import) and Configure (workspaces) kept showing the original repo
    and looked like the Python add had failed.
    """
    full_name = full_name_from_repo_url(github_repo_full_name)
    if full_name is None:
        raise ValueError("Repository must be owner/repo")
    repo_name = full_name.split("/", 1)[1]
    html_url = f"https://github.com/{full_name}"
    repo_url = f"{html_url}.git"
    workspace_name = f"{repo_name} Workspace"
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                owned = await connection.fetchval(
                    "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
                    project_id,
                    owner_id,
                )
                if owned is None:
                    return None
                repo_row = await connection.fetchrow(
                    """
                    INSERT INTO project_repositories (
                        project_id, kind, name, full_name, default_branch, html_url
                    )
                    VALUES ($1, 'backend', $2, $3, $4, $5)
                    ON CONFLICT (project_id, full_name) DO UPDATE
                    SET html_url = EXCLUDED.html_url
                    RETURNING id, default_branch
                    """,
                    project_id,
                    repo_name,
                    full_name,
                    DEFAULT_BRANCH,
                    html_url,
                )
                # Read the branch back rather than assuming the inserted default:
                # on conflict the existing row kept whatever branch it already
                # had, and announcing the wrong branch would queue a shard the
                # project does not import.
                branch = str(repo_row["default_branch"] or DEFAULT_BRANCH) or DEFAULT_BRANCH
                has_workspace = await connection.fetchval(
                    """
                    SELECT 1 FROM workspaces
                    WHERE project_id = $1 AND repository_id = $2
                    """,
                    project_id,
                    repo_row["id"],
                )
                if has_workspace is None:
                    await connection.execute(
                        """
                        INSERT INTO workspaces (
                            project_id, repository_id, name, repo_url, repo_branch,
                            workspace_path, environment
                        )
                        VALUES ($1, $2, $3, $4, $5, NULL, 'dev')
                        """,
                        project_id,
                        repo_row["id"],
                        workspace_name,
                        repo_url,
                        branch,
                    )
                await connection.execute(
                    "UPDATE projects SET updated_at = now() WHERE id = $1",
                    project_id,
                )
                row = await connection.fetchrow(
                    f"{_PROJECT_SELECT} WHERE id = $1",
                    project_id,
                )
                project = await _assemble(connection, row)
    except ValueError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not add repository: {type(exc).__name__}") from exc
    await announce_repository_added(project_id, full_name, branch or DEFAULT_BRANCH)
    await _queue_index(pool, project_id, full_name, branch or DEFAULT_BRANCH)
    return project


async def remove_repository(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    *,
    repo_name: str,
) -> dict[str, Any] | None:
    """Drop one imported repo from a project. Does not touch GitHub."""
    wanted = repo_name.strip()
    if not wanted:
        raise ValueError("Repository name is required")
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                owned = await connection.fetchval(
                    "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
                    project_id,
                    owner_id,
                )
                if owned is None:
                    return None
                row = await connection.fetchrow(
                    """
                    SELECT id, full_name, default_branch
                    FROM project_repositories
                    WHERE project_id = $1 AND (name = $2 OR full_name = $2)
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    project_id,
                    wanted,
                )
                if row is None:
                    return None
                await connection.execute(
                    "DELETE FROM workspaces WHERE project_id = $1 AND repository_id = $2",
                    project_id,
                    row["id"],
                )
                await connection.execute(
                    "DELETE FROM project_repositories WHERE id = $1",
                    row["id"],
                )
                await connection.execute(
                    "UPDATE projects SET updated_at = now() WHERE id = $1",
                    project_id,
                )
                project_row = await connection.fetchrow(
                    f"{_PROJECT_SELECT} WHERE id = $1",
                    project_id,
                )
                project = await _assemble(connection, project_row)
    except ValueError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not remove repository: {type(exc).__name__}") from exc
    await announce_repository_removed(
        project_id,
        str(row["full_name"]),
        str(row["default_branch"] or DEFAULT_BRANCH) or DEFAULT_BRANCH,
    )
    return project
