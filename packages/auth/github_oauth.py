"""GitHub App user-to-server OAuth and installation-scoped repository lists.

One GitHub App covers login and repo import (README). User-to-server tokens
never leave the exchange; installation tokens are minted per request and
never stored.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import quote, urlencode

import httpx

from packages.auth.config import IdentityPlatformConfig
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError

GITHUB_AUTH_ENDPOINT: Final[str] = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_ENDPOINT: Final[str] = "https://github.com/login/oauth/access_token"
GITHUB_API: Final[str] = "https://api.github.com"
GITHUB_ACCEPT: Final[str] = "application/vnd.github+json"
GITHUB_API_VERSION: Final[str] = "2022-11-28"
USER_AGENT: Final[str] = "patchapi-auth/0.1.0"
APP_JWT_LIFETIME_SECONDS: Final[int] = 9 * 60
# GitHub's contents API caps at 1 MiB; stay under that rather than inventing a blob fetch.
MAX_FILE_BYTES: Final[int] = 512_000
TREE_TIMEOUT_SECONDS: Final[float] = 30.0


class GitHubResourceError(RuntimeError):
    """GitHub answered, but this installation cannot see the repo, ref, or file.

    Distinct from AuthUnavailableError: the outcome is known. Callers map this
    to 404 rather than inventing a tree.
    """

    def __init__(self, status_code: int, message: str = "not found") -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubProfile:
    """What GitHub returns for the signed-in App user. No tokens."""

    subject: str
    login: str
    email: str
    email_verified: bool
    name: str | None
    avatar_url: str | None
    installation_id: str | None = None
    account_login: str | None = None
    account_type: str | None = None


def authorization_url(config: IdentityPlatformConfig, state: str) -> str:
    """Build the GitHub authorize URL the browser should navigate to."""
    if not config.github_oauth_configured():
        raise AuthConfigurationError(
            "GitHub OAuth client is not configured; write .secrets/github-app.json"
        )
    query = urlencode(
        {
            "client_id": config.github_client_id,
            "redirect_uri": config.github_redirect_uri,
            "state": state,
            "allow_signup": "true",
        }
    )
    return f"{GITHUB_AUTH_ENDPOINT}?{query}"


def install_url(config: IdentityPlatformConfig) -> str | None:
    """URL that starts App installation, or None when the slug is unknown."""
    slug = (config.github_app_slug or "").strip()
    if not slug:
        return None
    return f"https://github.com/apps/{slug}/installations/new"


async def exchange_code(
    config: IdentityPlatformConfig,
    code: str,
    *,
    installation_id: str | None = None,
) -> GitHubProfile:
    """Trade an authorization code for the GitHub profile of the signed-in user."""
    if not config.github_oauth_configured():
        raise AuthConfigurationError(
            "GitHub OAuth client is not configured; write .secrets/github-app.json"
        )
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            token_response = await client.post(
                GITHUB_TOKEN_ENDPOINT,
                headers=headers,
                data={
                    "client_id": config.github_client_id,
                    "client_secret": config.github_client_secret,
                    "code": code,
                    "redirect_uri": config.github_redirect_uri,
                },
            )
            token_response.raise_for_status()
            token_body = token_response.json()
            if token_body.get("error"):
                raise AuthUnavailableError("GitHub rejected the authorization code")
            access_token = (token_body.get("access_token") or "").strip()
            if not access_token:
                raise AuthUnavailableError("GitHub did not return an access token")
            api_headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": GITHUB_ACCEPT,
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": USER_AGENT,
            }
            userinfo = await client.get(f"{GITHUB_API}/user", headers=api_headers)
            userinfo.raise_for_status()
            email, verified = await _email(client, api_headers, userinfo.json())
            installation = await _installation(
                client, api_headers, installation_id, userinfo.json()
            )
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not reach GitHub OAuth: {exc}") from exc

    body: dict[str, Any] = userinfo.json()
    login = (body.get("login") or "").strip()
    subject = str(body.get("id") or "").strip()
    if not login or not subject:
        raise AuthUnavailableError("GitHub did not return a login and id")
    name = (body.get("name") or "").strip() or None
    avatar = (body.get("avatar_url") or "").strip() or None
    return GitHubProfile(
        subject=subject,
        login=login,
        email=email,
        email_verified=verified,
        name=name,
        avatar_url=avatar,
        installation_id=installation[0] if installation else None,
        account_login=installation[1] if installation else None,
        account_type=installation[2] if installation else None,
    )


async def _email(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    user: dict[str, Any],
) -> tuple[str, bool]:
    """Pick a real email when GitHub exposes one; otherwise the noreply address."""
    login = (user.get("login") or "user").strip() or "user"
    subject = str(user.get("id") or "0").strip() or "0"
    fallback = f"{subject}+{login}@users.noreply.github.com"
    public = (user.get("email") or "").strip()
    try:
        response = await client.get(f"{GITHUB_API}/user/emails", headers=headers)
        response.raise_for_status()
        entries = response.json()
    except httpx.HTTPError:
        if public:
            return public, False
        return fallback, False
    if not isinstance(entries, list):
        if public:
            return public, False
        return fallback, False
    primary_verified = None
    any_verified = None
    any_email = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        address = (entry.get("email") or "").strip()
        if not address or address.endswith("@users.noreply.github.com"):
            continue
        verified = bool(entry.get("verified"))
        if entry.get("primary") and verified:
            primary_verified = address
        elif verified and any_verified is None:
            any_verified = address
        elif any_email is None:
            any_email = address
    chosen = primary_verified or any_verified or public or any_email or fallback
    return chosen, chosen in {primary_verified, any_verified}


async def _installation(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    requested_id: str | None,
    user: dict[str, Any],
) -> tuple[str, str, str] | None:
    """Resolve the App installation that this OAuth, if any, was issued for."""
    wanted = (requested_id or "").strip() or None
    try:
        response = await client.get(f"{GITHUB_API}/user/installations", headers=headers)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError:
        if wanted:
            login = (user.get("login") or "").strip() or "unknown"
            return wanted, login, "User"
        return None
    installations = payload.get("installations") if isinstance(payload, dict) else None
    if not isinstance(installations, list) or not installations:
        if wanted:
            login = (user.get("login") or "").strip() or "unknown"
            return wanted, login, "User"
        return None
    chosen = None
    for entry in installations:
        if not isinstance(entry, dict):
            continue
        ident = str(entry.get("id") or "").strip()
        if wanted and ident != wanted:
            continue
        account = entry.get("account") if isinstance(entry.get("account"), dict) else {}
        login = (account.get("login") or "").strip() or (user.get("login") or "").strip()
        account_type = (account.get("type") or "User").strip() or "User"
        if account_type not in {"User", "Organization"}:
            account_type = "User"
        candidate = (ident, login, account_type)
        if wanted and ident == wanted:
            return candidate
        if chosen is None:
            chosen = candidate
    return chosen


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _app_jwt(config: IdentityPlatformConfig) -> str:
    """Mint a short-lived App JWT. Callers must not log the return value."""
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    if not config.github_app_jwt_configured() or config.github_private_key_path is None:
        raise AuthConfigurationError("GitHub App private key is not configured")
    pem = config.github_private_key_path.read_text(encoding="utf-8")
    key = load_pem_private_key(pem.encode("utf-8"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise AuthConfigurationError("the GitHub App private key must be an RSA key")
    issued_at = int(datetime.now(UTC).timestamp()) - 60
    payload = {"iat": issued_at, "exp": issued_at + APP_JWT_LIFETIME_SECONDS, "iss": int(config.github_app_id or 0)}
    header = {"alg": "RS256", "typ": "JWT"}
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        for part in (header, payload)
    ).encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), SHA256())
    return f"{signing_input.decode('ascii')}.{_b64url(signature)}"


def _app_headers(config: IdentityPlatformConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_app_jwt(config)}",
        "Accept": GITHUB_ACCEPT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": USER_AGENT,
    }


def _account(entry: dict[str, Any], fallback_login: str = "") -> tuple[str, str, str] | None:
    ident = str(entry.get("id") or "").strip()
    if not ident:
        return None
    account = entry.get("account") if isinstance(entry.get("account"), dict) else {}
    login = (account.get("login") or "").strip() or fallback_login
    account_type = (account.get("type") or "User").strip() or "User"
    if account_type not in {"User", "Organization"}:
        account_type = "User"
    if not login:
        return None
    return ident, login, account_type


async def fetch_installation(
    config: IdentityPlatformConfig, installation_id: str
) -> tuple[str, str, str] | None:
    """Look up one App installation by id. Returns (id, account_login, account_type)."""
    ident = installation_id.strip()
    if not ident or not config.github_app_jwt_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.get(
                f"{GITHUB_API}/app/installations/{ident}",
                headers=_app_headers(config),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not reach GitHub App API: {exc}") from exc
    parsed = response.json()
    if not isinstance(parsed, dict):
        return None
    return _account(parsed)


async def find_installation_for_login(
    config: IdentityPlatformConfig, login: str
) -> tuple[str, str, str] | None:
    """Find this App's installation whose account login matches `login`."""
    wanted = login.strip()
    if not wanted or not config.github_app_jwt_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.get(
                f"{GITHUB_API}/app/installations",
                headers=_app_headers(config),
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not reach GitHub App API: {exc}") from exc
    payload = response.json()
    entries = payload if isinstance(payload, list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        found = _account(entry)
        if found is not None and found[1].lower() == wanted.lower():
            return found
    return None


async def mint_installation_token(config: IdentityPlatformConfig, installation_id: str) -> str:
    """Mint a user-installation token. Callers must not log the return value."""
    ident = installation_id.strip()
    if not ident or not config.github_app_jwt_configured():
        raise AuthConfigurationError("GitHub App private key is not configured")
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.post(
                f"{GITHUB_API}/app/installations/{ident}/access_tokens",
                headers=_app_headers(config),
            )
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not reach GitHub App API: {exc}") from exc
    if response.status_code != 201:
        raise AuthUnavailableError("GitHub refused the installation token request")
    token = (response.json().get("token") or "").strip()
    if not token:
        raise AuthUnavailableError("GitHub did not return an installation token")
    return token


def public_repository(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Project a GitHub repository onto the dashboard import list."""
    return {
        "id": int(entry.get("id") or 0),
        "name": str(entry.get("name") or ""),
        "full_name": str(entry.get("full_name") or ""),
        "private": bool(entry.get("private")),
        "language": entry.get("language"),
        "stargazers_count": int(entry.get("stargazers_count") or 0),
        "updated_at": str(entry.get("updated_at") or ""),
        "html_url": str(entry.get("html_url") or ""),
    }


def public_contents_entry(entry: Mapping[str, Any]) -> dict[str, str] | None:
    """Project a GitHub contents item onto the folder picker (`name` + `type`)."""
    name = str(entry.get("name") or "")
    kind = str(entry.get("type") or "")
    if not name or kind not in {"file", "dir", "symlink", "submodule"}:
        return None
    return {"name": name, "type": "dir" if kind == "dir" else "file"}


async def list_installation_repositories(
    config: IdentityPlatformConfig, installation_id: str
) -> list[dict[str, Any]]:
    """List repositories the App installation can see. Tokens never leave this call."""
    token = await mint_installation_token(config, installation_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": GITHUB_ACCEPT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": USER_AGENT,
    }
    repos: list[dict[str, Any]] = []
    url: str | None = f"{GITHUB_API}/installation/repositories?per_page=100"
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            while url:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                entries = payload.get("repositories") if isinstance(payload, dict) else None
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict) and entry.get("full_name"):
                            repos.append(public_repository(entry))
                next_link = response.links.get("next") if hasattr(response, "links") else None
                url = next_link.get("url") if isinstance(next_link, dict) else None
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not list GitHub repositories: {exc}") from exc
    repos.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return repos


def _installation_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": GITHUB_ACCEPT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": USER_AGENT,
    }


def _repo_path(owner: str, repo: str) -> str:
    return f"{quote(owner, safe='')}/{quote(repo, safe='')}"


def _file_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.split("/"))


def _raise_for_github(response: httpx.Response, *, what: str) -> None:
    if response.status_code == 401:
        raise AuthUnavailableError("GitHub rejected the installation token")
    if response.status_code in {403, 404}:
        raise GitHubResourceError(response.status_code, f"{what} is not visible to this installation")
    if response.status_code >= 400:
        raise AuthUnavailableError(f"GitHub refused {what}")


async def fetch_repository_tree(
    config: IdentityPlatformConfig,
    installation_id: str,
    *,
    owner: str,
    repo: str,
    ref: str | None,
) -> dict[str, Any]:
    """Recursive git tree for one repo the installation can see. Token is not stored."""
    token = await mint_installation_token(config, installation_id)
    headers = _installation_headers(token)
    repo_path = _repo_path(owner, repo)
    timeout = max(config.timeout_seconds, TREE_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            repo_response = await client.get(f"{GITHUB_API}/repos/{repo_path}", headers=headers)
            _raise_for_github(repo_response, what="repository")
            repo_body = repo_response.json()
            default_branch = str(repo_body.get("default_branch") or "main") or "main"
            resolved = (ref or "").strip() or default_branch
            commit_response = await client.get(
                f"{GITHUB_API}/repos/{repo_path}/commits/{quote(resolved, safe='')}",
                headers=headers,
            )
            _raise_for_github(commit_response, what="ref")
            commit_body = commit_response.json()
            commit_sha = str(commit_body.get("sha") or "")
            if not commit_sha:
                raise GitHubResourceError(404, "ref has no commit")
            tree_response = await client.get(
                f"{GITHUB_API}/repos/{repo_path}/git/trees/{quote(commit_sha, safe='')}",
                headers=headers,
                params={"recursive": "1"},
            )
            _raise_for_github(tree_response, what="tree")
            tree_body = tree_response.json()
    except GitHubResourceError:
        raise
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not read GitHub tree: {exc}") from exc
    commit = commit_body.get("commit") if isinstance(commit_body, dict) else None
    committer = commit.get("committer") if isinstance(commit, dict) else None
    author = commit.get("author") if isinstance(commit, dict) else None
    gh_author = commit_body.get("author") if isinstance(commit_body, dict) else None
    created_by = ""
    if isinstance(author, dict) and author.get("name"):
        created_by = str(author["name"])
    elif isinstance(gh_author, dict) and gh_author.get("login"):
        created_by = str(gh_author["login"])
    committed_at = ""
    if isinstance(committer, dict) and committer.get("date"):
        committed_at = str(committer["date"])
    entries = []
    for entry in tree_body.get("tree") or []:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        kind = entry.get("type")
        if kind not in {"blob", "tree"}:
            continue
        item: dict[str, Any] = {
            "path": str(entry["path"]),
            "type": kind,
            "sha": str(entry.get("sha") or ""),
        }
        if entry.get("size") is not None:
            item["size"] = int(entry["size"])
        entries.append(item)
    return {
        "full_name": str(repo_body.get("full_name") or f"{owner}/{repo}"),
        "default_branch": default_branch,
        "ref": resolved,
        "sha": commit_sha,
        "committed_at": committed_at,
        "created_by": created_by,
        "truncated": bool(tree_body.get("truncated")),
        "entries": entries,
    }


async def list_repository_contents(
    config: IdentityPlatformConfig,
    installation_id: str,
    *,
    owner: str,
    repo: str,
    path: str | None,
    ref: str | None,
) -> list[dict[str, str]]:
    """Immediate children of a path the installation can see. Token is not stored."""
    token = await mint_installation_token(config, installation_id)
    headers = _installation_headers(token)
    repo_path = _repo_path(owner, repo)
    relative = (path or "").strip().lstrip("/")
    params: dict[str, str] = {}
    if (ref or "").strip():
        params["ref"] = ref.strip()
    url = f"{GITHUB_API}/repos/{repo_path}/contents"
    if relative:
        url = f"{url}/{_file_path(relative)}"
    try:
        async with httpx.AsyncClient(timeout=max(config.timeout_seconds, TREE_TIMEOUT_SECONDS)) as client:
            response = await client.get(url, headers=headers, params=params or None)
            _raise_for_github(response, what="directory")
            body = response.json()
    except GitHubResourceError:
        raise
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not list GitHub directory: {exc}") from exc
    if not isinstance(body, list):
        return []
    entries: list[dict[str, str]] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        projected = public_contents_entry(item)
        if projected is not None:
            entries.append(projected)
    return entries


async def fetch_repository_file(
    config: IdentityPlatformConfig,
    installation_id: str,
    *,
    owner: str,
    repo: str,
    path: str,
    ref: str | None,
) -> dict[str, Any]:
    """Decoded file body for a path the installation can see. Token is not stored."""
    token = await mint_installation_token(config, installation_id)
    headers = _installation_headers(token)
    repo_path = _repo_path(owner, repo)
    params: dict[str, str] = {}
    if (ref or "").strip():
        params["ref"] = ref.strip()
    try:
        async with httpx.AsyncClient(timeout=max(config.timeout_seconds, TREE_TIMEOUT_SECONDS)) as client:
            response = await client.get(
                f"{GITHUB_API}/repos/{repo_path}/contents/{_file_path(path)}",
                headers=headers,
                params=params or None,
            )
            _raise_for_github(response, what="file")
            body = response.json()
    except GitHubResourceError:
        raise
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not read GitHub file: {exc}") from exc
    if isinstance(body, list):
        raise GitHubResourceError(404, "path is a directory")
    size = int(body.get("size") or 0)
    encoding = str(body.get("encoding") or "")
    raw = body.get("content") or ""
    if size > MAX_FILE_BYTES or (not raw and size > 0):
        content = f"// File is too large to display ({size} bytes)"
    elif encoding == "base64" and isinstance(raw, str):
        try:
            decoded = base64.b64decode(raw)
        except (ValueError, TypeError) as exc:
            raise AuthUnavailableError("GitHub returned undecodable file content") from exc
        try:
            content = decoded.decode("utf-8")
        except UnicodeDecodeError:
            content = f"// Binary file ({size} bytes) cannot be displayed as text"
    elif isinstance(raw, str):
        content = raw
    else:
        content = ""
    return {
        "path": str(body.get("path") or path),
        "sha": str(body.get("sha") or ""),
        "size": size,
        "content": content,
    }
