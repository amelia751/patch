"""The pull request body carries the evidence §8.6 requires, always."""

import pytest
from patchapi_github_tools.models import PullRequestEvidence
from patchapi_github_tools.pr_body import (
    extract_idempotency_key,
    pull_request_idempotency_key,
    render_pull_request_body,
)
from pydantic import ValidationError

BASE_SHA = "c5428cdcdcd12204e1f4cc47c393dc6e738d88b2"


def render(evidence_payload, *, run_id="run-000000000001", title="Migrate Imagen 4"):
    evidence = PullRequestEvidence.model_validate(evidence_payload)
    key = pull_request_idempotency_key(run_id=run_id, base_sha=BASE_SHA, title=title)
    return key, render_pull_request_body(
        evidence, idempotency_key=key, base_sha=BASE_SHA, run_id=run_id
    )


def test_body_contains_every_required_section(evidence):
    _key, body = render(evidence)
    for heading in ("## Changes", "## Files", "## Checks"):
        assert heading in body
    assert "<details>" in body
    assert "Evidence" in body


def test_body_states_the_automation_boundary(evidence):
    _key, body = render(evidence)
    assert "cannot merge" in body
    assert "CODEOWNERS" in body
    assert "branch protection" in body
    assert "patchbot" in body


def test_body_links_the_run_the_commit_and_the_trace(evidence):
    _key, body = render(evidence)
    assert f"Base `{BASE_SHA}`" in body
    assert "Run `run-000000000001`" in body
    assert "Trace `trace-abc123`" in body
    assert "gs://patchapi-evidence/run-1/build.txt" in body


def test_body_drops_local_file_uris_and_collapses_duplicate_files(evidence):
    evidence["why"] = "Deterministic slice: the risk tier follows the manifest."
    evidence["affected_usage"] = [
        "generate.py — runtime_source",
        "generate.py — runtime_source",
        "README.md — documentation_example",
    ]
    evidence["evidence_links"] = [
        "file:///var/folders/tmp/build.log",
        "gs://patchapi-evidence/run-1/build.txt",
    ]
    _key, body = render(evidence)
    assert "file:///var/folders" not in body
    assert body.count("`generate.py`") == 1
    assert "| `README.md` | Docs |" in body
    assert "Deterministic slice" not in body
    assert "Call gemini-3.1-flash-image through the same client" in body


def test_idempotency_key_round_trips_through_the_body(evidence):
    key, body = render(evidence)
    assert extract_idempotency_key(body) == key


def test_idempotency_key_is_stable_and_scoped(evidence):
    first = pull_request_idempotency_key(run_id="r1", base_sha=BASE_SHA, title="Migrate")
    same = pull_request_idempotency_key(run_id="r1", base_sha=BASE_SHA, title=" Migrate ")
    other_base = pull_request_idempotency_key(run_id="r1", base_sha="0" * 40, title="Migrate")
    other_run = pull_request_idempotency_key(run_id="r2", base_sha=BASE_SHA, title="Migrate")
    assert first == same
    assert first != other_base
    assert first != other_run


def test_extract_returns_none_for_a_body_written_by_a_human():
    assert extract_idempotency_key("Looks good to me") is None
    assert extract_idempotency_key(None) is None


def test_evidence_with_a_failed_check_cannot_be_built(evidence):
    evidence["verification"][1]["passed"] = False
    with pytest.raises(ValidationError, match="every verification check must pass"):
        PullRequestEvidence.model_validate(evidence)


def test_evidence_requires_verification_at_all(evidence):
    evidence["verification"] = []
    with pytest.raises(ValidationError):
        PullRequestEvidence.model_validate(evidence)


def test_a_failed_verification_blocks_the_pull_request_route(
    client, fake_github, pr_headers, evidence, run_id
):
    base_sha = fake_github.branches["main"]
    evidence["verification"].append({"name": "Vitest", "passed": False})
    response = client.post(
        "/v1/capabilities/open_pull_request",
        json={
            "repo": "amelia751/storygen",
            "head_branch": "patchapi/migrate",
            "base_branch": "main",
            "title": "Migrate Imagen 4",
            "base_sha": base_sha,
            "run_id": run_id,
            "evidence": evidence,
        },
        headers=pr_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_arguments"
    assert fake_github.pulls == []
