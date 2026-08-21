"""One handler per capability, and the registry that binds them.

`REGISTRY` is keyed by `packages.github.Capability`, so the set of operations
this service can perform is exactly the shared allowlist — a test asserts the
two are equal. There is no default handler and no dynamic dispatch by string:
a capability that is not a member of the enum has nowhere to land.

Results are projected field by field rather than forwarded. GitHub payloads are
large and change over time; an agent should receive the facts the contract
promises, not whatever the API happened to include.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

from packages.github import Capability
from patchapi_github_tools.github_rest import (
    GitHubRest,
    UpstreamError,
    file_path_segments,
    path_segment,
)
from patchapi_github_tools.models import (
    AddPrCommentArgs,
    CapabilityArgs,
    CommitVerifiedPatchArgs,
    CreatePatchBranchArgs,
    GetChecksArgs,
    GetCommitArgs,
    GetFileArgs,
    GetPullRequestArgs,
    GetRepositoryMetadataArgs,
    ListTreeArgs,
    OpenPullRequestArgs,
)
from patchapi_github_tools.pr_body import (
    BOT_COMMITTER,
    pull_request_idempotency_key,
    render_pull_request_body,
)


class ConflictError(RuntimeError):
    """The repository is not in the state the caller verified against."""

    def __init__(self, code: str, detail: dict[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _repo_path(args: CapabilityArgs) -> str:
    repo = args.repository
    return f"/repos/{path_segment(repo.owner)}/{path_segment(repo.name)}"


async def get_repository_metadata(client: GitHubRest, args: GetRepositoryMetadataArgs) -> dict:
    body = await client.request("GET", _repo_path(args), expected=(200,))
    return {
        "full_name": body["full_name"],
        "default_branch": body["default_branch"],
        "private": body["private"],
        "archived": body["archived"],
        "html_url": body["html_url"],
    }


async def get_file(client: GitHubRest, args: GetFileArgs) -> dict:
    body = await client.request(
        "GET",
        f"{_repo_path(args)}/contents/{file_path_segments(args.path)}",
        params={"ref": args.ref},
        expected=(200,),
    )
    if isinstance(body, list):
        raise ConflictError("path_is_directory", {"path": args.path})
    return {
        "path": body["path"],
        "sha": body["sha"],
        "size": body["size"],
        "encoding": body.get("encoding", "base64"),
        "content": body.get("content", ""),
    }


async def list_tree(client: GitHubRest, args: ListTreeArgs) -> dict:
    params = {"recursive": "1"} if args.recursive else None
    body = await client.request(
        "GET",
        f"{_repo_path(args)}/git/trees/{path_segment(args.sha)}",
        params=params,
        expected=(200,),
    )
    return {
        "sha": body["sha"],
        "truncated": body.get("truncated", False),
        "entries": [
            {
                "path": entry["path"],
                "type": entry["type"],
                "sha": entry["sha"],
                "size": entry.get("size"),
            }
            for entry in body.get("tree", [])
        ],
    }


async def get_commit(client: GitHubRest, args: GetCommitArgs) -> dict:
    body = await client.request(
        "GET",
        f"{_repo_path(args)}/commits/{path_segment(args.sha)}",
        expected=(200,),
    )
    return {
        "sha": body["sha"],
        "message": body["commit"]["message"],
        "committed_at": body["commit"]["committer"]["date"],
        "parents": [parent["sha"] for parent in body.get("parents", [])],
    }


async def get_pull_request(client: GitHubRest, args: GetPullRequestArgs) -> dict:
    body = await client.request(
        "GET",
        f"{_repo_path(args)}/pulls/{args.number}",
        expected=(200,),
    )
    return _project_pull_request(body)


async def get_checks(client: GitHubRest, args: GetChecksArgs) -> dict:
    body = await client.request(
        "GET",
        f"{_repo_path(args)}/commits/{path_segment(args.ref)}/check-runs",
        expected=(200,),
    )
    return {
        "ref": args.ref,
        "total": body.get("total_count", 0),
        "check_runs": [
            {
                "name": run["name"],
                "status": run["status"],
                "conclusion": run.get("conclusion"),
            }
            for run in body.get("check_runs", [])
        ],
    }


async def create_patch_branch(client: GitHubRest, args: CreatePatchBranchArgs) -> dict:
    """Create `branch` at `base_sha`, or accept it if it is already there.

    Re-running a migration must converge. A branch that already points at the
    requested base is success with `created: false`; a branch pointing anywhere
    else is a conflict, because silently moving it would discard whatever is on
    it today.
    """
    ref_path = f"{_repo_path(args)}/git/ref/heads/{file_path_segments(args.branch)}"
    try:
        created = await client.request(
            "POST",
            f"{_repo_path(args)}/git/refs",
            json={"ref": f"refs/heads/{args.branch}", "sha": args.base_sha},
            expected=(201,),
        )
    except UpstreamError as exc:
        if exc.status_code != 422:
            raise
        existing = await client.request("GET", ref_path, expected=(200,))
        existing_sha = existing["object"]["sha"]
        if existing_sha != args.base_sha:
            raise ConflictError(
                "branch_exists_at_other_commit",
                {
                    "branch": args.branch,
                    "expected_sha": args.base_sha,
                    "actual_sha": existing_sha,
                },
            ) from exc
        return {"branch": args.branch, "sha": existing_sha, "created": False}
    return {"branch": args.branch, "sha": created["object"]["sha"], "created": True}


async def commit_verified_patch(client: GitHubRest, args: CommitVerifiedPatchArgs) -> dict:
    """Commit the verified files onto the patch branch via the Git data API.

    The branch head is checked against `expected_head_sha` first and the commit
    is parented on it, so a branch that moved after verification produces a
    refusal instead of a commit built on an unverified tree.
    """
    base = _repo_path(args)
    ref_path = f"{base}/git/ref/heads/{file_path_segments(args.branch)}"
    ref = await client.request("GET", ref_path, expected=(200,))
    head_sha = ref["object"]["sha"]
    if head_sha != args.expected_head_sha:
        raise ConflictError(
            "branch_moved",
            {
                "branch": args.branch,
                "expected_head_sha": args.expected_head_sha,
                "actual_head_sha": head_sha,
            },
        )

    head_commit = await client.request(
        "GET", f"{base}/git/commits/{path_segment(head_sha)}", expected=(200,)
    )

    tree_entries = []
    for patch_file in args.files:
        blob = await client.request(
            "POST",
            f"{base}/git/blobs",
            json={"content": patch_file.content, "encoding": "utf-8"},
            expected=(201,),
        )
        tree_entries.append(
            {"path": patch_file.path, "mode": "100644", "type": "blob", "sha": blob["sha"]}
        )

    tree = await client.request(
        "POST",
        f"{base}/git/trees",
        json={"base_tree": head_commit["tree"]["sha"], "tree": tree_entries},
        expected=(201,),
    )
    commit = await client.request(
        "POST",
        f"{base}/git/commits",
        json={
            "message": args.message,
            "tree": tree["sha"],
            "parents": [head_sha],
            "author": BOT_COMMITTER,
            "committer": BOT_COMMITTER,
        },
        expected=(201,),
    )
    # `force` stays false: this service only ever fast-forwards a branch it
    # created, and never rewrites history.
    updated = await client.request(
        "PATCH",
        f"{base}/git/refs/heads/{file_path_segments(args.branch)}",
        json={"sha": commit["sha"], "force": False},
        expected=(200,),
    )
    return {
        "branch": args.branch,
        "commit_sha": commit["sha"],
        "parent_sha": head_sha,
        "ref_sha": updated["object"]["sha"],
        "files": [patch_file.path for patch_file in args.files],
    }


async def open_pull_request(client: GitHubRest, args: OpenPullRequestArgs) -> dict:
    """Open the pull request, or update the one this run already opened.

    Idempotency is keyed on run, base commit, and title, and the head branch is
    the lookup: a replay finds its own pull request and refreshes the evidence
    rather than opening a duplicate for a human to triage.
    """
    key = pull_request_idempotency_key(run_id=args.run_id, base_sha=args.base_sha, title=args.title)
    body = render_pull_request_body(
        args.evidence, idempotency_key=key, base_sha=args.base_sha, run_id=args.run_id
    )
    base = _repo_path(args)
    existing = await client.request(
        "GET",
        f"{base}/pulls",
        params={"head": f"{args.repository.owner}:{args.head_branch}", "state": "open"},
        expected=(200,),
    )
    if existing:
        current = existing[0]
        updated = await client.request(
            "PATCH",
            f"{base}/pulls/{current['number']}",
            json={"title": args.title, "body": body},
            expected=(200,),
        )
        return {
            **_project_pull_request(updated),
            "created": False,
            "idempotency_key": key,
        }

    created = await client.request(
        "POST",
        f"{base}/pulls",
        json={
            "title": args.title,
            "body": body,
            "head": args.head_branch,
            "base": args.base_branch,
            "draft": args.draft,
        },
        expected=(201,),
    )
    return {**_project_pull_request(created), "created": True, "idempotency_key": key}


async def add_pr_comment(client: GitHubRest, args: AddPrCommentArgs) -> dict:
    body = await client.request(
        "POST",
        f"{_repo_path(args)}/issues/{args.number}/comments",
        json={"body": args.body},
        expected=(201,),
    )
    return {"comment_id": body["id"], "html_url": body["html_url"]}


def _project_pull_request(body: dict) -> dict:
    return {
        "number": body["number"],
        "state": body["state"],
        "title": body["title"],
        "draft": body.get("draft", False),
        "merged": body.get("merged", False),
        "head_ref": body["head"]["ref"],
        "base_ref": body["base"]["ref"],
        "html_url": body["html_url"],
    }


@dataclass(frozen=True, slots=True)
class Operation:
    args_model: type[CapabilityArgs]
    handler: Callable[[GitHubRest, Any], Awaitable[dict]]
    summary: str


REGISTRY: Final[dict[Capability, Operation]] = {
    Capability.GET_REPOSITORY_METADATA: Operation(
        GetRepositoryMetadataArgs, get_repository_metadata, "Read repository metadata"
    ),
    Capability.GET_FILE: Operation(GetFileArgs, get_file, "Read one file at a pinned commit"),
    Capability.LIST_TREE: Operation(ListTreeArgs, list_tree, "List the tree at a pinned commit"),
    Capability.GET_COMMIT: Operation(GetCommitArgs, get_commit, "Read one commit"),
    Capability.GET_PULL_REQUEST: Operation(
        GetPullRequestArgs, get_pull_request, "Read one pull request"
    ),
    Capability.GET_CHECKS: Operation(GetChecksArgs, get_checks, "Read check runs for a commit"),
    Capability.CREATE_PATCH_BRANCH: Operation(
        CreatePatchBranchArgs, create_patch_branch, "Create a patch branch from a pinned commit"
    ),
    Capability.COMMIT_VERIFIED_PATCH: Operation(
        CommitVerifiedPatchArgs, commit_verified_patch, "Commit a verified patch to a patch branch"
    ),
    Capability.OPEN_PULL_REQUEST: Operation(
        OpenPullRequestArgs, open_pull_request, "Open or update the migration pull request"
    ),
    Capability.ADD_PR_COMMENT: Operation(
        AddPrCommentArgs, add_pr_comment, "Comment on a pull request"
    ),
}
