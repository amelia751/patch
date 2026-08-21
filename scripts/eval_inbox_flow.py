"""Import a GitHub repo into Amelia's live project and print the inbox join.

    uv run --all-packages python scripts/eval_inbox_flow.py --repo amelia751/mcp-image-gen

Uses the local control API (Cloud SQL via the Auth Proxy) and a session cookie
issued for amelia.anh.lam@gmail.com. The GitHub App must already see the repo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Final
from uuid import UUID

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.state.session import COOKIE_NAME, issue, load_session_secret  # noqa: E402

API_URL: Final[str] = os.environ.get("PATCHAPI_API_URL", "http://127.0.0.1:8080")
OWNER_EMAIL: Final[str] = "amelia.anh.lam@gmail.com"
STORYGEN_PROJECT: Final[str] = "7b8d0954-58ed-4df3-9290-76fb34a32b13"


def _database_url() -> str:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw:
        return raw
    path = REPO_ROOT / ".secrets" / "database-url-proxy.txt"
    return path.read_text(encoding="utf-8").strip()


async def _owner_id() -> UUID:
    import asyncpg

    conn = await asyncpg.connect(_database_url())
    try:
        value = await conn.fetchval("SELECT id FROM users WHERE email = $1", OWNER_EMAIL)
    finally:
        await conn.close()
    if value is None:
        raise SystemExit(f"no console user for {OWNER_EMAIL}")
    return UUID(str(value))


def _request(method: str, path: str, token: str, body: dict[str, Any] | None = None) -> Any:
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API_URL}{path}",
        data=payload,
        method=method,
        headers={
            "Cookie": f"{COOKIE_NAME}={token}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if payload else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise SystemExit(f"{method} {path} -> {exc.code}: {detail}") from exc


def _print_inbox(payload: dict[str, Any]) -> None:
    print(f"subscribed={payload.get('subscribed')} scan={payload.get('scan')}")
    for change in payload.get("changes") or []:
        print(
            f"  {change.get('status'):<12} {change.get('statusReason') or '-':<18} "
            f"{change.get('id')} hits={change.get('fileHits')} repos={change.get('repos')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="owner/repo to add, if not already imported")
    parser.add_argument("--project-id", default=STORYGEN_PROJECT)
    parser.add_argument("--wait-seconds", type=int, default=180)
    args = parser.parse_args()

    token = issue(asyncio.run(_owner_id()), load_session_secret(REPO_ROOT))
    me = _request("GET", "/api/auth/me", token)
    print(f"session {me.get('email')} {me.get('id')}")

    project = _request("GET", f"/api/projects/{args.project_id}", token)
    names = [row.get("full_name") for row in project.get("repositories") or []]
    print(f"project {project.get('name')} repos={names}")

    if args.repo and args.repo not in names:
        print(f"importing {args.repo}")
        project = _request(
            "POST",
            f"/api/projects/{args.project_id}/repositories",
            token,
            {"github_repo_full_name": args.repo},
        )
        names = [row.get("full_name") for row in project.get("repositories") or []]
        print(f"repos now {names}")

    deadline = time.time() + args.wait_seconds
    while time.time() < deadline:
        indexing = _request("GET", f"/api/projects/{args.project_id}/indexing", token)
        print(
            f"indexing status={indexing.get('status')} "
            f"{indexing.get('progress_percent')}% {indexing.get('repositories')}"
        )
        if indexing.get("status") in {"ready", "error"}:
            break
        time.sleep(5)

    inbox = _request("GET", f"/api/projects/{args.project_id}/changes", token)
    _print_inbox(inbox)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
