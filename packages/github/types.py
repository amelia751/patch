"""Reference types for the objects the GitHub tool surface points at.

These are references — owner/name, a pinned SHA, a PR number — never repository
content. Passing a `CommitRef` instead of a bare string keeps an unpinned or
mistyped SHA from reaching a sandbox checkout.
"""

import re
from dataclasses import dataclass
from typing import Final, Self

# GitHub's own constraints, applied here so a malformed reference is rejected
# before it can be interpolated into a URL.
_OWNER_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_REF_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    owner: str
    name: str

    def __post_init__(self) -> None:
        if not _OWNER_RE.match(self.owner):
            raise ValueError(f"invalid repository owner: {self.owner!r}")
        if not _REPO_RE.match(self.name):
            raise ValueError(f"invalid repository name: {self.name!r}")

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @classmethod
    def parse(cls, full_name: str) -> Self:
        """Build a reference from `owner/name`."""
        owner, separator, name = full_name.partition("/")
        if not separator:
            raise ValueError(f"expected 'owner/name', got {full_name!r}")
        return cls(owner=owner, name=name)


@dataclass(frozen=True, slots=True)
class CommitRef:
    """A repository pinned to one full commit SHA.

    Short SHAs and branch names are refused: every sandbox run and every piece
    of evidence has to name the exact commit it was produced from.
    """

    repo: RepositoryRef
    sha: str

    def __post_init__(self) -> None:
        if not _SHA_RE.match(self.sha):
            raise ValueError(f"expected a full lowercase 40-character commit SHA, got {self.sha!r}")


@dataclass(frozen=True, slots=True)
class BranchRef:
    repo: RepositoryRef
    name: str

    def __post_init__(self) -> None:
        if not _REF_RE.match(self.name):
            raise ValueError(f"invalid branch name: {self.name!r}")


@dataclass(frozen=True, slots=True)
class PullRequestRef:
    repo: RepositoryRef
    number: int

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"pull request numbers start at 1, got {self.number}")

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo.full_name}/pull/{self.number}"
