"""Fixtures and the recorded GitHub the capability surface is exercised against.

The App key is generated per session and written only under `tmp_path`, so
these tests exercise the real PEM-loading and RS256-signing code paths without
any credential existing in the repository.

`FakeGitHub` is the recorded stand-in for a live App installation: it speaks the
same URLs, methods, and payload shapes as api.github.com for the endpoints the
capability surface uses, and it records every request. Anything it is not asked
to know about — notably merge, branch-protection, and secret endpoints — answers
599 `unexpected endpoint`, so a boundary crossing surfaces as a loud failure
rather than a passing test. These doubles are never importable from the service
package: nothing in `src/` may fall back to them at runtime.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from patchapi_github_tools.app import create_app
from patchapi_github_tools.config import (
    ENV_API_BASE,
    ENV_APP_ID,
    ENV_INSTALLATION_ID,
    ENV_PRIVATE_KEY_PATH,
)
from patchapi_github_tools.wiring import build_github_client

APP_ID = "123456"
INSTALLATION_ID = "78901234"
REPO = "amelia751/storygen"


# Shaped like a real installation token so the auth path is exercised, but
# deliberately too short to match a credential scanner's `ghs_` pattern.
INSTALLATION_TOKEN: Final[str] = "ghs_EXAMPLE_not_a_token"

_REPO: Final[str] = r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)"


def _sha(*parts: str) -> str:
    # Content addressing for the fake object store; not a security control.
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()


@dataclass
class FakeGitHub:
    """In-memory GitHub with just enough behaviour for the capability surface."""

    default_branch: str = "main"
    branches: dict[str, str] = field(default_factory=dict)
    commits: dict[str, dict[str, Any]] = field(default_factory=dict)
    trees: dict[str, dict[str, Any]] = field(default_factory=dict)
    blobs: dict[str, str] = field(default_factory=dict)
    pulls: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    token_mints: int = 0

    def seed_commit(self, branch: str, *, message: str = "baseline") -> str:
        """Create a commit with an empty tree and point `branch` at it."""
        tree_sha = _sha("tree", branch, message)
        self.trees[tree_sha] = {"sha": tree_sha, "tree": []}
        commit_sha = _sha("commit", branch, message)
        self.commits[commit_sha] = {
            "sha": commit_sha,
            "message": message,
            "tree": {"sha": tree_sha},
            "parents": [],
            "date": "2026-08-01T00:00:00Z",
        }
        self.branches[branch] = commit_sha
        return commit_sha

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    # --- request handling -------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        self.calls.append((method, path))

        if method == "POST" and re.fullmatch(r"/app/installations/\d+/access_tokens", path):
            self.token_mints += 1
            expires = datetime.now(UTC) + timedelta(hours=1)
            return _json(
                201,
                {
                    "token": INSTALLATION_TOKEN,
                    "expires_at": expires.isoformat().replace("+00:00", "Z"),
                },
            )

        if not str(request.headers.get("Authorization", "")).startswith("Bearer "):
            return _json(401, {"message": "Requires authentication"})

        for pattern, methods, handler in self._routes():
            match = re.fullmatch(pattern, path)
            if match and method in methods:
                return handler(request, match)

        return _json(599, {"message": f"unexpected endpoint {method} {path}"})

    def _routes(self) -> list[tuple[str, set[str], Any]]:
        return [
            (_REPO, {"GET"}, self._repo_metadata),
            (_REPO + r"/contents/(?P<path>.+)", {"GET"}, self._contents),
            (_REPO + r"/git/trees/(?P<sha>[^/]+)", {"GET"}, self._get_tree),
            (_REPO + r"/git/trees", {"POST"}, self._create_tree),
            (_REPO + r"/git/blobs", {"POST"}, self._create_blob),
            (_REPO + r"/git/commits/(?P<sha>[^/]+)", {"GET"}, self._get_git_commit),
            (_REPO + r"/git/commits", {"POST"}, self._create_git_commit),
            (_REPO + r"/git/ref/heads/(?P<branch>.+)", {"GET"}, self._get_ref),
            (_REPO + r"/git/refs/heads/(?P<branch>.+)", {"PATCH"}, self._update_ref),
            (_REPO + r"/git/refs", {"POST"}, self._create_ref),
            (_REPO + r"/commits/(?P<sha>[^/]+)/check-runs", {"GET"}, self._check_runs),
            (_REPO + r"/commits/(?P<sha>[^/]+)", {"GET"}, self._get_commit),
            (_REPO + r"/pulls/(?P<number>\d+)", {"GET", "PATCH"}, self._one_pull),
            (_REPO + r"/pulls", {"GET", "POST"}, self._pulls),
            (_REPO + r"/issues/(?P<number>\d+)/comments", {"POST"}, self._comment),
        ]

    # --- endpoints --------------------------------------------------------

    def _repo_metadata(self, _request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        full_name = f"{match['owner']}/{match['repo']}"
        return _json(
            200,
            {
                "full_name": full_name,
                "default_branch": self.default_branch,
                "private": False,
                "archived": False,
                "html_url": f"https://github.com/{full_name}",
            },
        )

    def _contents(self, request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        ref = request.url.params.get("ref")
        if ref not in self.commits:
            return _json(404, {"message": "No commit found for the ref"})
        content = self.blobs.get(match["path"])
        if content is None:
            return _json(404, {"message": "Not Found"})
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        return _json(
            200,
            {
                "path": match["path"],
                "sha": _sha("blob", content),
                "size": len(content),
                "encoding": "base64",
                "content": encoded,
            },
        )

    def _get_tree(self, _request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        tree = self.trees.get(match["sha"])
        if tree is None:
            return _json(404, {"message": "Not Found"})
        return _json(200, {**tree, "truncated": False})

    def _create_tree(self, request: httpx.Request, _match: re.Match[str]) -> httpx.Response:
        body = json.loads(request.content)
        base = self.trees.get(body["base_tree"], {"tree": []})
        merged = {entry["path"]: entry for entry in base["tree"]}
        for entry in body["tree"]:
            merged[entry["path"]] = entry
        sha = _sha("tree", json.dumps(sorted(merged), sort_keys=True), body["base_tree"])
        self.trees[sha] = {"sha": sha, "tree": list(merged.values())}
        return _json(201, {"sha": sha})

    def _create_blob(self, request: httpx.Request, _match: re.Match[str]) -> httpx.Response:
        body = json.loads(request.content)
        sha = _sha("blob", body["content"])
        self.blobs[sha] = body["content"]
        return _json(201, {"sha": sha})

    def _get_git_commit(self, _request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        commit = self.commits.get(match["sha"])
        if commit is None:
            return _json(404, {"message": "Not Found"})
        return _json(200, commit)

    def _create_git_commit(self, request: httpx.Request, _match: re.Match[str]) -> httpx.Response:
        body = json.loads(request.content)
        sha = _sha("commit", body["message"], body["tree"], *body["parents"])
        self.commits[sha] = {
            "sha": sha,
            "message": body["message"],
            "tree": {"sha": body["tree"]},
            "parents": [{"sha": parent} for parent in body["parents"]],
            "date": "2026-08-11T00:00:00Z",
        }
        return _json(201, {"sha": sha})

    def _get_ref(self, _request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        sha = self.branches.get(match["branch"])
        if sha is None:
            return _json(404, {"message": "Not Found"})
        return _json(200, {"ref": f"refs/heads/{match['branch']}", "object": {"sha": sha}})

    def _create_ref(self, request: httpx.Request, _match: re.Match[str]) -> httpx.Response:
        body = json.loads(request.content)
        branch = body["ref"].removeprefix("refs/heads/")
        if branch in self.branches:
            return _json(422, {"message": "Reference already exists"})
        if body["sha"] not in self.commits:
            return _json(422, {"message": "Object does not exist"})
        self.branches[branch] = body["sha"]
        return _json(201, {"ref": body["ref"], "object": {"sha": body["sha"]}})

    def _update_ref(self, request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        body = json.loads(request.content)
        if match["branch"] not in self.branches:
            return _json(422, {"message": "Reference does not exist"})
        self.branches[match["branch"]] = body["sha"]
        return _json(200, {"ref": f"refs/heads/{match['branch']}", "object": {"sha": body["sha"]}})

    def _get_commit(self, _request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        commit = self.commits.get(match["sha"])
        if commit is None:
            return _json(404, {"message": "Not Found"})
        return _json(
            200,
            {
                "sha": commit["sha"],
                "commit": {
                    "message": commit["message"],
                    "committer": {"date": commit["date"]},
                },
                "parents": commit["parents"],
            },
        )

    def _check_runs(self, _request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        return _json(
            200,
            {
                "total_count": 1,
                "check_runs": [{"name": "build", "status": "completed", "conclusion": "success"}],
            },
        )

    def _pulls(self, request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        if request.method == "GET":
            head = request.url.params.get("head")
            state = request.url.params.get("state", "open")
            matched = [
                pull
                for pull in self.pulls
                if (head is None or f"{match['owner']}:{pull['head']['ref']}" == head)
                and (state == "all" or pull["state"] == state)
            ]
            return _json(200, matched)

        body = json.loads(request.content)
        if body["head"] not in self.branches:
            return _json(422, {"message": "Head ref does not exist"})
        number = len(self.pulls) + 1
        pull = {
            "number": number,
            "state": "open",
            "title": body["title"],
            "body": body["body"],
            "draft": body.get("draft", False),
            "merged": False,
            "head": {"ref": body["head"]},
            "base": {"ref": body["base"]},
            "html_url": (f"https://github.com/{match['owner']}/{match['repo']}/pull/{number}"),
        }
        self.pulls.append(pull)
        return _json(201, pull)

    def _one_pull(self, request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        number = int(match["number"])
        for pull in self.pulls:
            if pull["number"] != number:
                continue
            if request.method == "PATCH":
                pull.update(json.loads(request.content))
            return _json(200, pull)
        return _json(404, {"message": "Not Found"})

    def _comment(self, request: httpx.Request, match: re.Match[str]) -> httpx.Response:
        body = json.loads(request.content)
        comment_id = len(self.comments) + 1
        self.comments.append({"number": int(match["number"]), "body": body["body"]})
        return _json(
            201,
            {
                "id": comment_id,
                "html_url": (
                    f"https://github.com/{match['owner']}/{match['repo']}"
                    f"/pull/{match['number']}#issuecomment-{comment_id}"
                ),
            },
        )


def _json(status_code: int, payload: Any) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


@pytest.fixture(scope="session")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def private_key_pem(private_key: rsa.RSAPrivateKey) -> str:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


@pytest.fixture
def key_file(tmp_path, private_key_pem):
    path = tmp_path / "github-app.pem"
    path.write_text(private_key_pem, encoding="utf-8")
    return path


@pytest.fixture
def app_env(key_file) -> dict[str, str]:
    return {
        ENV_APP_ID: APP_ID,
        ENV_INSTALLATION_ID: INSTALLATION_ID,
        ENV_PRIVATE_KEY_PATH: str(key_file),
        ENV_API_BASE: "https://api.github.test",
    }


@pytest.fixture
def fake_github() -> FakeGitHub:
    github = FakeGitHub()
    github.seed_commit("main")
    return github


@pytest.fixture
def github_client(app_env, fake_github):
    """A real `GitHubRest` whose transport is the recorded GitHub."""
    http = httpx.AsyncClient(transport=fake_github.transport())
    client = build_github_client(app_env, http=http)
    assert client is not None
    return client


@pytest.fixture
def client(github_client) -> TestClient:
    """The service with credentials wired."""
    with TestClient(create_app(github=github_client)) as test_client:
        yield test_client


@pytest.fixture
def unwired_client() -> TestClient:
    """The service started with no GitHub App configured."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def run_id() -> str:
    return "run-000000000001"


@pytest.fixture
def pr_headers(run_id) -> dict[str, str]:
    """Identity of the only agent granted write capabilities (roadmap §8.6)."""
    return {"X-PatchAPI-Agent": "patchapi.pr", "X-PatchAPI-Run-Id": run_id}


@pytest.fixture
def impact_headers() -> dict[str, str]:
    """Identity of a read-only agent."""
    return {"X-PatchAPI-Agent": "patchapi.impact"}


@pytest.fixture
def evidence() -> dict[str, object]:
    """The §8.6 evidence payload for the pinned Storygen migration."""
    return {
        "why": "Google retires Imagen 4 on 2026-08-17.",
        "affected_usage": ["cli/src/image.ts uses imagen-4.0-generate-001"],
        "migration": ["Call gemini-3.1-flash-image through the same client"],
        "verification": [
            {"name": "TypeScript build", "passed": True},
            {"name": "Vitest", "passed": True},
            {"name": "independent verification", "passed": True},
        ],
        "risk_level": "medium",
        "risk_rationale": "Semantic image-model migration.",
        "evidence_links": ["gs://patchapi-evidence/run-1/build.txt"],
        "trace_id": "trace-abc123",
    }
