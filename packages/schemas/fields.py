"""Constrained scalar types reused across the contracts.

Defining these once means a repository name, a commit SHA or a repo-relative
path is validated identically wherever it appears, instead of each contract
re-deriving its own idea of what those look like.
"""

from pathlib import PurePosixPath
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

# Lowercase hex digests. Git object names are 40 characters; content hashes are
# sha256 and 64.
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
HexDigest = Annotated[str, StringConstraints(pattern=r"^([0-9a-f]{40}|[0-9a-f]{64})$")]

RepoFullName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")]

ProviderId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{1,31}$")]

ChangeId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")]

RunId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")]

# A provider identifier such as a model ID. Free-form because providers choose
# their own naming, but never blank and never unbounded.
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200)]

AgentId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9._-]{2,63}$")]

NonEmptyLine = Annotated[str, StringConstraints(min_length=1, max_length=500)]


def _reject_escaping_path(value: str) -> str:
    """Reject anything that can address a file outside the repository.

    An agent-authored path is untrusted structure: absolute paths, Windows
    drive letters, `..` segments and backslash separators are all refused
    before the value can reach a filesystem or a GitHub write.
    """
    if value.startswith(("/", "~")):
        raise ValueError(f"path must be repository-relative, got {value!r}")
    if "\\" in value:
        raise ValueError(f"path must use forward slashes, got {value!r}")
    if len(value) > 1 and value[1] == ":":
        raise ValueError(f"path must be repository-relative, got {value!r}")
    parts = PurePosixPath(value).parts
    if ".." in parts:
        raise ValueError(f"path must not traverse upwards, got {value!r}")
    return value


RepoRelativePath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=1024),
    AfterValidator(_reject_escaping_path),
]

GlobPattern = Annotated[str, StringConstraints(min_length=1, max_length=256)]
