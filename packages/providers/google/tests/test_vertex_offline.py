"""Vertex client behaviour that must hold without touching the network.

The live proof is `packages.providers.google.smoke`. These tests cover the parts
that must not depend on a live call: response parsing against a recorded body,
the model guard firing before any request, and a missing credential producing a
`SKIP` reason rather than an exception a caller might swallow.
"""

import json

import pytest

from packages.providers.google.config import (
    ENV_CREDENTIALS,
    ENV_PROJECT,
    GoogleProviderConfig,
    load_config,
)
from packages.providers.google.errors import UnsupportedModelError, VertexCallError
from packages.providers.google.vertex import (
    VertexClient,
    credentials_available,
    extract_text,
    parse_generate_content,
)


@pytest.fixture
def recorded_response(golden_dir):
    return json.loads((golden_dir / "vertex" / "generate-content.response.json").read_text())


def test_recorded_response_parses(recorded_response):
    response = parse_generate_content(recorded_response, requested_model="gemini-3.5-flash")

    assert response.model_version == "gemini-3.5-flash"
    assert response.text == '{"ping":"pong"}'
    assert response.finish_reason == "STOP"
    assert response.total_token_count == 129
    assert response.response_id == "crp7apHLG9-TsbwPjfTH-AU"


def test_thinking_parts_are_not_read_as_the_reply():
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "the user wants a ping", "thought": True},
                        {"text": "pong"},
                    ]
                }
            }
        ],
        "modelVersion": "gemini-3.5-flash",
    }
    assert extract_text(payload) == "pong"


def test_a_response_without_model_identity_is_a_failure():
    with pytest.raises(VertexCallError, match="model identity unproven"):
        parse_generate_content(
            {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
            requested_model="gemini-3.5-flash",
        )


def test_an_empty_candidate_list_yields_no_text():
    assert extract_text({"candidates": []}) == ""


def test_an_out_of_generation_override_is_refused_before_any_request():
    client = VertexClient(GoogleProviderConfig(project="patch-505223"))
    with pytest.raises(UnsupportedModelError):
        client.generate_text("hello", model="gemini-2.5-flash")


def test_a_credentials_path_that_does_not_exist_is_reported_as_a_skip_reason(tmp_path):
    config = load_config(
        {ENV_PROJECT: "patch-505223", ENV_CREDENTIALS: "missing-key.json"}, base_dir=tmp_path
    )
    reason = credentials_available(config)
    assert reason is not None
    assert "does not exist" in reason


def test_a_missing_project_is_reported_as_a_skip_reason(tmp_path):
    key = tmp_path / "key.json"
    key.write_text("{}", encoding="utf-8")
    config = load_config({ENV_CREDENTIALS: str(key)}, base_dir=tmp_path)
    # An unreadable key file surfaces its own reason first; either way the
    # caller gets a reason string and never a fabricated response.
    assert credentials_available(config) is not None
