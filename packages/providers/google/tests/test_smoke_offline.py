"""The smoke's fail-closed paths, exercised without calling Vertex.

The PASS path is only ever reached by a real call; that is the point of the
smoke, and `scripts/verify_packages_providers_google.sh` runs it for real.
"""

from pathlib import Path

import pytest

from packages.providers.google import smoke
from packages.providers.google.config import GoogleProviderConfig
from packages.providers.google.errors import VertexCallError
from packages.providers.google.vertex import VertexTextResponse


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """Keep the smoke from reading repository pins or the operator's environment."""
    monkeypatch.setattr(smoke, "_apply_repo_pins", lambda: Path(tmp_path))
    monkeypatch.setattr(
        smoke, "load_config", lambda base_dir=None: GoogleProviderConfig(project="patch-505223")
    )


def _response(**overrides) -> VertexTextResponse:
    fields = {
        "requested_model": "gemini-3.5-flash",
        "model_version": "gemini-3.5-flash",
        "text": '{"ping":"pong"}',
        "finish_reason": "STOP",
    }
    return VertexTextResponse(**{**fields, **overrides})


def test_absent_credentials_skip_rather_than_fail(monkeypatch, capsys):
    monkeypatch.setattr(smoke, "credentials_available", lambda config: "no credentials configured")

    assert smoke.main([]) == smoke.EXIT_SKIP
    assert capsys.readouterr().out.startswith("SKIP: no credentials configured")


def test_a_failed_call_is_never_reported_as_pass(monkeypatch, capsys):
    monkeypatch.setattr(smoke, "credentials_available", lambda config: None)

    class Failing:
        def __init__(self, config):
            pass

        def generate_text(self, prompt, **kwargs):
            raise VertexCallError("Vertex returned 404 for gemini-3.5-flash at us-central1")

    monkeypatch.setattr(smoke, "VertexClient", Failing)

    assert smoke.main([]) == smoke.EXIT_FAIL
    assert "FAIL: Vertex returned 404" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"text": "   "}, "returned no text"),
        ({"model_version": "gemini-2.5-flash"}, "older than the pinned minimum 3.5"),
        ({"model_version": "imagen-4.0-generate-001"}, "not a Gemini model ID"),
    ],
)
def test_an_unacceptable_response_fails(monkeypatch, capsys, overrides, expected):
    monkeypatch.setattr(smoke, "credentials_available", lambda config: None)

    class Canned:
        def __init__(self, config):
            pass

        def generate_text(self, prompt, **kwargs):
            return _response(**overrides)

    monkeypatch.setattr(smoke, "VertexClient", Canned)

    assert smoke.main([]) == smoke.EXIT_FAIL
    assert expected in capsys.readouterr().out


def test_exit_codes_are_distinct():
    assert len({smoke.EXIT_PASS, smoke.EXIT_FAIL, smoke.EXIT_SKIP}) == 3
