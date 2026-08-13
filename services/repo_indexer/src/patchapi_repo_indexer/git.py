"""Git access for the indexer: one bare mirror per repository, cheap checkouts.

Per `repo-indexer.md` §5.5 the indexer keeps a single bare mirror per repository
under `INDEXER_WORKDIR` and fetches it incrementally, so indexing a second
branch of the same repository costs a fetch rather than a clone.

Two constraints shape the code more than anything else:

- Hard constraint #8 — this service never holds a GitHub App private key. It
  reads a short-lived installation token from the environment, and that token is
  only ever passed to git as an argument of a single `fetch`, never written into
  a repository's config where it would outlive the request.
- Every caller-supplied string reaches a filesystem path or a git ref, so
  repository names, branches and revisions are validated before use rather than
  interpolated and hoped for.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Final

from patchapi_repo_indexer import config
from patchapi_repo_indexer.errors import IndexerError, UnsafePathError

__all__ = [
    "GitCommandError",
    "RevisionNotFoundError",
    "changed_paths",
    "checkout_root",
    "clone_url_for",
    "ensure_checkout",
    "mirror_root",
    "prune_checkouts",
    "workdir",
]


class GitCommandError(IndexerError):
    """A git invocation failed, timed out, or could not be started."""


class RevisionNotFoundError(IndexerError):
    """The requested revision is not present after fetching."""


# Network work is bounded so a hung remote fails the run instead of pinning a
# subscriber thread forever; local plumbing is bounded far tighter.
FETCH_TIMEOUT_SECONDS: Final[int] = 600
LOCAL_TIMEOUT_SECONDS: Final[int] = 120

# Only these two are ever legitimate here: https for GitHub, file for the
# fixtures and local development mirrors.
ALLOWED_PROTOCOLS: Final[str] = "https:file"

# Checked in order. The first is the short-lived installation token minted by
# `services/github_tools`; `GITHUB_TOKEN` is the local-development fallback.
TOKEN_ENV_VARS: Final[tuple[str, ...]] = (
    "PATCHAPI_GITHUB_INSTALLATION_TOKEN",
    "GITHUB_INSTALLATION_TOKEN",
    "GITHUB_TOKEN",
)

REMOTE_BASE: Final[str] = os.getenv("PATCHAPI_GIT_REMOTE_BASE", "https://github.com").rstrip("/")

_SEGMENT_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]+$")
_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{7,40}$")
_BRANCH_FORBIDDEN: Final[frozenset[str]] = frozenset(" ~^:?*[\\\x7f")


def workdir() -> Path:
    """Root of every mirror and checkout this process owns."""
    return Path(config.INDEXER_WORKDIR)


def mirror_root() -> Path:
    return workdir() / "mirrors"


def checkout_root() -> Path:
    return workdir() / "checkouts"


def _validate_repository(repository: str) -> tuple[str, str]:
    """Split `owner/name`, refusing anything that could escape the workdir.

    A leading dot is allowed because `owner/.github` is a real repository; `..`
    in any form and a leading dash (which git would read as an option) are not.
    """
    parts = repository.split("/")
    if len(parts) != 2 or not all(_SEGMENT_RE.match(part) for part in parts):
        raise UnsafePathError(f"not a valid repository full name: {repository!r}")
    for part in parts:
        if part in {".", ".."} or ".." in part or part.startswith("-") or part.endswith(".lock"):
            raise UnsafePathError(f"not a valid repository full name: {repository!r}")
    return parts[0], parts[1]


def _validate_branch(branch: str) -> str:
    """Accept a plain branch name only — no refspecs, no option-looking values."""
    if not branch or branch.startswith("-") or branch.startswith("/") or branch.endswith("/"):
        raise UnsafePathError(f"not a valid branch name: {branch!r}")
    if branch.endswith(".lock") or ".." in branch or "@{" in branch or "//" in branch:
        raise UnsafePathError(f"not a valid branch name: {branch!r}")
    if any(char in _BRANCH_FORBIDDEN or ord(char) < 0x20 for char in branch):
        raise UnsafePathError(f"not a valid branch name: {branch!r}")
    if any(segment in {".", ".."} or segment.startswith(".") for segment in branch.split("/")):
        raise UnsafePathError(f"not a valid branch name: {branch!r}")
    return branch


def _validate_sha(sha: str) -> str:
    if not _SHA_RE.match(sha or ""):
        raise UnsafePathError(f"not a valid commit sha: {sha!r}")
    return sha.lower()


def _slug(repository: str) -> str:
    """Stable directory name: readable prefix, hash to keep it collision-free.

    The hash is taken over the lower-cased full name so two spellings of the
    same GitHub repository share one mirror rather than clone it twice.
    """
    owner, name = _validate_repository(repository)
    digest = hashlib.sha256(repository.lower().encode("utf-8")).hexdigest()[:12]
    return f"{owner}__{name}-{digest}"


def clone_url_for(repository: str) -> str:
    """Public clone URL for a repository. No credentials are ever embedded here."""
    _validate_repository(repository)
    return f"{REMOTE_BASE}/{repository}.git"


def _installation_token() -> str | None:
    """Resolve the token at call time; it is short-lived and may rotate mid-process."""
    for name in TOKEN_ENV_VARS:
        token = os.environ.get(name, "").strip()
        if token:
            return token
    return None


def _authenticated_url(url: str, token: str | None) -> str:
    """Attach the token to an https remote for one invocation only."""
    if token is None or not url.startswith("https://"):
        return url
    return f"https://x-access-token:{token}@{url[len('https://') :]}"


def _redact(text: str, secrets: tuple[str | None, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _git_env() -> dict[str, str]:
    """A hermetic git environment: no prompts, no user config, no exotic protocols."""
    env = dict(os.environ)
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ALLOW_PROTOCOL": ALLOWED_PROTOCOLS,
            "GIT_ADVICE": "0",
        }
    )
    return env


def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = LOCAL_TIMEOUT_SECONDS,
    secrets: tuple[str | None, ...] = (),
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        # Fixed executable, no shell: every argument reaching here is either a
        # module constant or a value that passed the validators above.
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            env=_git_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise GitCommandError(
            _redact(f"git {args[0]} timed out after {timeout}s", secrets)
        ) from None
    except OSError as exc:
        raise GitCommandError(_redact(f"could not run git: {exc}", secrets)) from None
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise GitCommandError(
            _redact(
                f"git {' '.join(args)} failed (exit {proc.returncode}): {detail}",
                secrets,
            )
        )
    return proc


def _has_commit(repo: Path, sha: str) -> bool:
    proc = _run_git(["cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo, check=False)
    return proc.returncode == 0


def _ensure_mirror(repository: str, branch: str, remote_url: str | None) -> Path:
    """Create or incrementally update the bare mirror backing `repository`.

    The remote is registered without credentials; the token is supplied as an
    explicit URL on the fetch itself so it never lands in `.git/config`.
    """
    mirror = mirror_root() / f"{_slug(repository)}.git"
    public_url = remote_url or clone_url_for(repository)
    token = _installation_token()
    fetch_url = _authenticated_url(public_url, token)
    secrets = (token,)

    if not (mirror / "HEAD").is_file():
        if mirror.exists():
            shutil.rmtree(mirror, ignore_errors=True)
        mirror.parent.mkdir(parents=True, exist_ok=True)
        _run_git(["init", "--bare", "--quiet", str(mirror)])
        _run_git(["remote", "add", "origin", public_url], cwd=mirror)

    _run_git(
        [
            "fetch",
            "--prune",
            "--no-tags",
            "--quiet",
            fetch_url,
            f"+refs/heads/{branch}:refs/heads/{branch}",
        ],
        cwd=mirror,
        timeout=FETCH_TIMEOUT_SECONDS,
        secrets=secrets,
    )
    return mirror


def _fetch_revision(mirror: Path, repository: str, sha: str, remote_url: str | None) -> None:
    """Fetch a commit that is no longer at the branch tip, e.g. a force-pushed base."""
    token = _installation_token()
    fetch_url = _authenticated_url(remote_url or clone_url_for(repository), token)
    _run_git(
        ["fetch", "--no-tags", "--quiet", fetch_url, sha],
        cwd=mirror,
        timeout=FETCH_TIMEOUT_SECONDS,
        secrets=(token,),
        check=False,
    )


def ensure_checkout(
    repository: str,
    branch: str,
    sha: str,
    *,
    remote_url: str | None = None,
) -> Path:
    """Return a working tree of `sha`, fetching only what the mirror is missing.

    `remote_url` overrides the derived GitHub URL for local fixtures and tests;
    production callers pass the repository full name and nothing else.
    """
    _validate_repository(repository)
    branch = _validate_branch(branch)
    sha = _validate_sha(sha)

    mirror = _ensure_mirror(repository, branch, remote_url)
    if not _has_commit(mirror, sha):
        _fetch_revision(mirror, repository, sha, remote_url)
    if not _has_commit(mirror, sha):
        raise RevisionNotFoundError(
            f"{repository}@{sha} is not reachable from {branch} after fetching"
        )

    target = checkout_root() / _slug(repository) / sha
    if target.exists():
        head = _run_git(["rev-parse", "HEAD"], cwd=target, check=False)
        if head.returncode == 0 and head.stdout.strip().startswith(sha):
            os.utime(target, None)
            return target
        _remove_worktree(mirror, target)

    target.parent.mkdir(parents=True, exist_ok=True)
    _run_git(
        ["worktree", "add", "--detach", "--force", "--quiet", str(target), sha],
        cwd=mirror,
    )
    os.utime(target, None)
    return target


def _remove_worktree(mirror: Path, target: Path) -> None:
    """Drop a checkout and the mirror's bookkeeping entry for it."""
    shutil.rmtree(target, ignore_errors=True)
    if (mirror / "HEAD").is_file():
        _run_git(["worktree", "prune"], cwd=mirror, check=False)


def changed_paths(repo_path: Path, base_sha: str, head_sha: str) -> list[str]:
    """Repository-relative posix paths touched between two commits, sorted and unique.

    Renames are reported as a delete plus an add (`--no-renames`) because the
    inventory has to retire the old path, not just learn the new one. Deletions
    are included for the same reason.
    """
    base = _validate_sha(base_sha)
    head = _validate_sha(head_sha)
    repo = Path(repo_path)
    if not repo.is_dir():
        raise GitCommandError(f"not a directory: {repo}")

    for revision in (base, head):
        if not _has_commit(repo, revision):
            raise RevisionNotFoundError(f"{revision} is not present in {repo}")

    proc = _run_git(
        ["diff", "--name-only", "--no-renames", "-z", base, head],
        cwd=repo,
    )
    paths = {_safe_relative(entry) for entry in proc.stdout.split("\0") if entry}
    return sorted(paths)


def _safe_relative(entry: str) -> str:
    """Reject anything git reports that would resolve outside the repository."""
    candidate = PurePosixPath(entry.replace("\\", "/"))
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise UnsafePathError(f"path escapes the repository: {entry!r}")
    return candidate.as_posix()


def _directory_size(path: Path) -> int:
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
    return total


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def prune_checkouts(max_bytes: int) -> None:
    """Evict least-recently-used working state until the workdir fits `max_bytes`.

    Checkouts go first: they are a `worktree add` away from being recreated,
    while a mirror costs a full clone. Dropping a mirror also drops its
    checkouts, since they cannot be recreated without it.
    """
    if max_bytes < 0:
        raise ValueError("max_bytes must not be negative")

    checkouts: list[tuple[float, Path, int]] = []
    mirrors: list[tuple[float, Path, int]] = []

    if checkout_root().is_dir():
        for slug_dir in checkout_root().iterdir():
            if not slug_dir.is_dir():
                continue
            for checkout in slug_dir.iterdir():
                if checkout.is_dir():
                    checkouts.append((_mtime(checkout), checkout, _directory_size(checkout)))
    if mirror_root().is_dir():
        for mirror in mirror_root().iterdir():
            if mirror.is_dir():
                mirrors.append((_mtime(mirror), mirror, _directory_size(mirror)))

    total = sum(size for _, _, size in checkouts) + sum(size for _, _, size in mirrors)
    if total <= max_bytes:
        return

    removed: set[Path] = set()
    for _, checkout, size in sorted(checkouts):
        if total <= max_bytes:
            return
        mirror = mirror_root() / f"{checkout.parent.name}.git"
        _remove_worktree(mirror, checkout)
        removed.add(checkout)
        total -= size

    for _, mirror, size in sorted(mirrors):
        if total <= max_bytes:
            return
        slug_dir = checkout_root() / mirror.name.removesuffix(".git")
        for _, checkout, checkout_size in checkouts:
            if checkout.parent == slug_dir and checkout not in removed:
                shutil.rmtree(checkout, ignore_errors=True)
                removed.add(checkout)
                total -= checkout_size
        shutil.rmtree(slug_dir, ignore_errors=True)
        shutil.rmtree(mirror, ignore_errors=True)
        total -= size
