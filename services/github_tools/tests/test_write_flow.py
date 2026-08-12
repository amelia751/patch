"""The write path end to end against the recorded GitHub.

This is the evidence that branch-from-SHA, commit, and pull request work
together: the same sequence the PR Agent performs (roadmap §8.6, §14), driven
through the HTTP surface with the PR Agent's identity.
"""

BRANCH = "patchapi/google-imagen4-shutdown-2026-08-17"
REPO = "amelia751/egaki"


def invoke(client, capability, payload, headers):
    return client.post(f"/v1/capabilities/{capability}", json=payload, headers=headers)


def test_branch_from_sha_then_commit_then_pull_request(
    client, fake_github, pr_headers, evidence, run_id
):
    base_sha = fake_github.branches["main"]

    created = invoke(
        client,
        "create_patch_branch",
        {"repo": REPO, "branch": BRANCH, "base_sha": base_sha},
        pr_headers,
    )
    assert created.status_code == 200, created.text
    branch_result = created.json()["result"]
    assert branch_result == {"branch": BRANCH, "sha": base_sha, "created": True}
    assert fake_github.branches[BRANCH] == base_sha

    committed = invoke(
        client,
        "commit_verified_patch",
        {
            "repo": REPO,
            "branch": BRANCH,
            "message": "Migrate image generation from Imagen 4 to Gemini 3.1 Flash Image",
            "expected_head_sha": base_sha,
            "files": [
                {
                    "path": "cli/src/image.ts",
                    "content": "const MODEL = 'gemini-3.1-flash-image'\n",
                }
            ],
        },
        pr_headers,
    )
    assert committed.status_code == 200, committed.text
    commit_result = committed.json()["result"]
    assert commit_result["parent_sha"] == base_sha
    assert commit_result["files"] == ["cli/src/image.ts"]
    # The branch moved to the new commit; the base branch did not move at all.
    assert fake_github.branches[BRANCH] == commit_result["commit_sha"]
    assert fake_github.branches["main"] == base_sha

    opened = invoke(
        client,
        "open_pull_request",
        {
            "repo": REPO,
            "head_branch": BRANCH,
            "base_branch": "main",
            "title": "Migrate Imagen 4 usage to Gemini 3.1 Flash Image",
            "base_sha": base_sha,
            "run_id": run_id,
            "evidence": evidence,
        },
        pr_headers,
    )
    assert opened.status_code == 200, opened.text
    pull = opened.json()["result"]
    assert pull["created"] is True
    assert pull["number"] == 1
    assert pull["head_ref"] == BRANCH
    assert pull["base_ref"] == "main"
    assert pull["merged"] is False

    body = fake_github.pulls[0]["body"]
    assert "### Automation boundary" in body
    assert "did not merge" in body
    assert pull["idempotency_key"] in body

    # Nothing in the whole flow touched a merge, admin, or secret endpoint.
    assert not any(
        marker in path
        for _method, path in fake_github.calls
        for marker in ("/merge", "/protection", "/secrets", "/collaborators")
    )


def test_reopening_the_same_run_updates_instead_of_duplicating(
    client, fake_github, pr_headers, evidence, run_id
):
    base_sha = fake_github.branches["main"]
    invoke(
        client,
        "create_patch_branch",
        {"repo": REPO, "branch": BRANCH, "base_sha": base_sha},
        pr_headers,
    )
    payload = {
        "repo": REPO,
        "head_branch": BRANCH,
        "base_branch": "main",
        "title": "Migrate Imagen 4 usage to Gemini 3.1 Flash Image",
        "base_sha": base_sha,
        "run_id": run_id,
        "evidence": evidence,
    }
    first = invoke(client, "open_pull_request", payload, pr_headers).json()["result"]
    second = invoke(client, "open_pull_request", payload, pr_headers).json()["result"]

    assert first["created"] is True
    assert second["created"] is False
    assert second["number"] == first["number"]
    assert second["idempotency_key"] == first["idempotency_key"]
    assert len(fake_github.pulls) == 1


def test_recreating_the_branch_at_the_same_base_converges(client, fake_github, pr_headers):
    base_sha = fake_github.branches["main"]
    payload = {"repo": REPO, "branch": BRANCH, "base_sha": base_sha}
    first = invoke(client, "create_patch_branch", payload, pr_headers).json()["result"]
    second = invoke(client, "create_patch_branch", payload, pr_headers).json()["result"]
    assert first["created"] is True
    assert second == {"branch": BRANCH, "sha": base_sha, "created": False}


def test_branch_at_another_commit_is_a_409(client, fake_github, pr_headers):
    base_sha = fake_github.branches["main"]
    other_sha = fake_github.seed_commit(BRANCH, message="someone else's work")
    response = invoke(
        client,
        "create_patch_branch",
        {"repo": REPO, "branch": BRANCH, "base_sha": base_sha},
        pr_headers,
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "repository_state_conflict"
    assert detail["conflict"] == "branch_exists_at_other_commit"
    assert detail["actual_sha"] == other_sha


def test_commit_refuses_a_branch_that_moved_after_verification(client, fake_github, pr_headers):
    base_sha = fake_github.branches["main"]
    invoke(
        client,
        "create_patch_branch",
        {"repo": REPO, "branch": BRANCH, "base_sha": base_sha},
        pr_headers,
    )
    moved_sha = fake_github.seed_commit("scratch", message="concurrent push")
    fake_github.branches[BRANCH] = moved_sha

    response = invoke(
        client,
        "commit_verified_patch",
        {
            "repo": REPO,
            "branch": BRANCH,
            "message": "Migrate image generation",
            "expected_head_sha": base_sha,
            "files": [{"path": "cli/src/image.ts", "content": "x\n"}],
        },
        pr_headers,
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["conflict"] == "branch_moved"
    assert detail["actual_head_sha"] == moved_sha
    # The branch was left exactly as the concurrent push left it.
    assert fake_github.branches[BRANCH] == moved_sha


def test_read_capabilities_work_for_a_read_only_agent(client, fake_github, impact_headers):
    metadata = invoke(client, "get_repository_metadata", {"repo": REPO}, impact_headers).json()[
        "result"
    ]
    assert metadata["full_name"] == REPO
    assert metadata["default_branch"] == "main"

    checks = invoke(
        client,
        "get_checks",
        {"repo": REPO, "ref": fake_github.branches["main"]},
        impact_headers,
    ).json()["result"]
    assert checks["check_runs"][0]["conclusion"] == "success"


def test_upstream_failure_is_a_structured_502(client, impact_headers):
    response = invoke(client, "get_commit", {"repo": REPO, "sha": "b" * 40}, impact_headers)
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error"] == "upstream_error"
    assert detail["upstream_status"] == 404
