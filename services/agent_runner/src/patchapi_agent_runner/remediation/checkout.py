"""Getting the repository into the sandbox, at the commit the run is about.

Two rules decide the shape of this module.

*The fetch happens on the job side, never in the sandbox.* The sandbox runs
generated code under a deny-all egress policy; handing it a network path to
GitHub would undo that, and handing it a credential would break the rule that
agents receive capabilities and never tokens. So the job clones, and the files
go into the session over the session's own write path — the one channel a
sandbox has.

*The commit is pinned, not resolved.* An impact report is only true of the tree
it read. Fetching `main` because it is convenient would have the patch applied
to a tree nobody assessed, and the sha recorded on the evidence would be a
claim about a different set of files.

`.git` is deliberately not staged. Nothing downstream needs it — the patch is
applied with `git apply`, which does not require a repository, and the proposed
diff is read back file by file — and leaving it out means a sandbox cannot fetch,
push, or read a remote URL even if something in it tried.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

log = logging.getLogger(__name__)

GIT_TIMEOUT_SECONDS: Final[int] = 240

# A tree this size is a signal something is wrong — a committed `node_modules`,
# a vendored SDK, a monorepo nobody scoped. Staging it file by file into a pod
# would take longer than the run, so it fails closed and says why.
MAX_STAGED_FILES: Final[int] = 4000
MAX_STAGED_BYTES: Final[int] = 64 * 1024 * 1024

# Never staged: build output and dependency trees that the sandbox either does
# not need or must install itself, plus anything that could carry a credential.
EXCLUDED: Final[tuple[str, ...]] = (
    ".git",
    ".github/workflows",
    "node_modules",
    ".next",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".secrets",
    ".env",
)


class CheckoutError(RuntimeError):
    """The repository could not be placed in the sandbox at the pinned commit."""


@dataclass(frozen=True, slots=True)
class Checkout:
    """A tree on the job's disk, at a known commit."""

    tree: Path
    repository: str
    base_sha: str
    files: int


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=GIT_TIMEOUT_SECONDS,
    )


def fetch(repository: str, base_sha: str, into: Path) -> Checkout:
    """Place `repository` at `base_sha` under `into`.

    Only public repositories are reachable this way. A private one fails here
    rather than being fetched with a token the job would then be holding, and
    the caller turns that into HUMAN_REQUIRED.
    """
    if "/" not in repository:
        raise CheckoutError(f"{repository!r} is not an owner/name repository")
    into.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{repository}.git"

    init = _git("init", "--quiet", cwd=into)
    if init.returncode != 0:
        raise CheckoutError(f"git init failed: {init.stderr.strip()}")
    _git("remote", "add", "origin", url, cwd=into)

    # Asking for the exact object avoids downloading history the run will never
    # read. GitHub serves reachable commits this way; when it does not, the
    # fallback fetches the default branch and checks the commit out of it.
    fetched = _git("fetch", "--depth", "1", "--quiet", "origin", base_sha, cwd=into)
    if fetched.returncode != 0:
        fetched = _git("fetch", "--quiet", "--tags", "origin", cwd=into)
        if fetched.returncode != 0:
            raise CheckoutError(
                f"could not fetch {repository}: {fetched.stderr.strip() or 'unreachable'}"
            )

    checked_out = _git("checkout", "--quiet", "--detach", base_sha, cwd=into)
    if checked_out.returncode != 0:
        raise CheckoutError(
            f"{repository} has no commit {base_sha[:12]}: {checked_out.stderr.strip()}"
        )

    head = _git("rev-parse", "HEAD", cwd=into).stdout.strip()
    if head != base_sha:
        # A checkout that silently landed elsewhere would make every piece of
        # evidence below it describe the wrong tree.
        raise CheckoutError(f"expected {base_sha[:12]} but the tree is at {head[:12]}")

    files = sum(1 for path in _stageable(into))
    log.info("checked out %s at %s (%d files)", repository, base_sha[:12], files)
    return Checkout(tree=into, repository=repository, base_sha=base_sha, files=files)


def _excluded(relative: Path) -> bool:
    if any(part in EXCLUDED for part in relative.parts):
        return True
    posix = relative.as_posix()
    return any(posix.startswith(f"{prefix}/") for prefix in EXCLUDED if "/" in prefix)


def _stageable(tree: Path) -> Iterator[Path]:
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if _excluded(path.relative_to(tree)):
            continue
        yield path


def stage(session: Any, checkout: Checkout) -> int:
    """Copy the tree into the sandbox workspace. Never the reverse.

    A local session exposes a real directory and takes a `copytree`. A pod does
    not, and the whole tree goes over `write_tree` in one transfer.

    It used to go a file at a time over `write_file`, which is one `kubectl exec`
    each: 20 small files measured 9s, the largest wait left before the agent's
    first action once the run stopped waiting for a container. It also could not
    carry a binary file and skipped it, so the sandbox held a tree that was not
    the commit.
    """
    paths = list(_stageable(checkout.tree))
    total = sum(path.stat().st_size for path in paths)
    if len(paths) > MAX_STAGED_FILES or total > MAX_STAGED_BYTES:
        raise CheckoutError(
            f"{checkout.repository} stages {len(paths)} files / {total // 1024}KiB, "
            f"over the sandbox limit of {MAX_STAGED_FILES} files / "
            f"{MAX_STAGED_BYTES // 1024 // 1024}MiB"
        )

    working = session.working_dir
    if isinstance(working, Path):
        shutil.copytree(
            checkout.tree,
            working,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*EXCLUDED),
        )
        return len(paths)

    session.write_tree(
        checkout.tree,
        [path.relative_to(checkout.tree).as_posix() for path in paths],
    )
    return len(paths)


__all__ = [
    "EXCLUDED",
    "MAX_STAGED_FILES",
    "Checkout",
    "CheckoutError",
    "fetch",
    "stage",
]
