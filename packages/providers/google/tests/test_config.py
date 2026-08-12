"""Model pins, the generation guard, and endpoint construction."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.providers.google.config import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_REASONING_MODEL,
    DEFAULT_VERTEX_LOCATION,
    ENV_CREDENTIALS,
    ENV_LOCATION,
    ENV_PROJECT,
    ENV_REASONING_MODEL,
    SEVERITY_BY_CHANGE_TYPE,
    GoogleProviderConfig,
    load_config,
    parse_gemini_generation,
    require_supported_image_model,
    require_supported_reasoning_model,
    severity_for,
)
from packages.providers.google.errors import ProviderConfigurationError, UnsupportedModelError
from packages.schemas.enums import ChangeType


def test_default_pins_match_the_hackathon_configuration():
    assert DEFAULT_REASONING_MODEL == "gemini-3.5-flash"
    assert DEFAULT_IMAGE_MODEL == "gemini-3.1-flash-image"
    assert DEFAULT_VERTEX_LOCATION == "global"


def test_severity_table_covers_every_change_type():
    assert set(SEVERITY_BY_CHANGE_TYPE) == set(ChangeType)
    assert severity_for(ChangeType.MODEL_RETIREMENT).value == "critical"
    assert severity_for(ChangeType.BEHAVIOR_CHANGE).value == "low"


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("gemini-3.5-flash", (3, 5)),
        ("gemini-3.1-flash-image", (3, 1)),
        ("gemini-10.0-pro", (10, 0)),
    ],
)
def test_parse_gemini_generation(model_id, expected):
    assert parse_gemini_generation(model_id) == expected


@pytest.mark.parametrize(
    "model_id",
    [
        "imagen-4.0-generate-001",
        "claude-opus-5",
        "gpt-5",
        "gemini-flash",
        "vertex/gemini-3.5-flash",
    ],
)
def test_non_gemini_pins_are_refused(model_id):
    with pytest.raises(UnsupportedModelError):
        parse_gemini_generation(model_id)


@pytest.mark.parametrize("model_id", ["gemini-2.5-flash", "gemini-3.1-flash", "gemini-1.5-pro"])
def test_reasoning_pin_below_the_minimum_generation_is_refused(model_id):
    with pytest.raises(UnsupportedModelError, match=r"3\.5 or newer"):
        require_supported_reasoning_model(model_id)


def test_reasoning_pin_at_the_minimum_is_accepted():
    assert require_supported_reasoning_model("gemini-3.5-flash") == "gemini-3.5-flash"


def test_image_pin_must_be_a_gemini_native_image_model():
    assert require_supported_image_model("gemini-3.1-flash-image") == "gemini-3.1-flash-image"
    with pytest.raises(UnsupportedModelError, match="native image model"):
        require_supported_image_model("gemini-3.5-flash")


def test_config_rejects_an_out_of_generation_reasoning_pin():
    """The compliance error surfaces as itself, not buried in a ValidationError."""
    with pytest.raises(UnsupportedModelError):
        GoogleProviderConfig(reasoning_model="gemini-2.5-flash")


def test_config_rejects_an_imagen_image_pin():
    with pytest.raises(UnsupportedModelError):
        GoogleProviderConfig(image_model="imagen-4.0-generate-001")


def test_config_is_frozen():
    config = GoogleProviderConfig(project="patch-505223")
    with pytest.raises(ValidationError):
        config.reasoning_model = "gemini-2.5-flash"


def test_global_location_uses_the_unprefixed_host():
    config = GoogleProviderConfig(project="patch-505223")
    assert config.vertex_host == "https://aiplatform.googleapis.com"
    assert config.generate_content_url("gemini-3.5-flash") == (
        "https://aiplatform.googleapis.com/v1/projects/patch-505223"
        "/locations/global/publishers/google/models/gemini-3.5-flash:generateContent"
    )


def test_regional_location_uses_the_prefixed_host():
    config = GoogleProviderConfig(project="patch-505223", location="us-central1")
    assert config.vertex_host == "https://us-central1-aiplatform.googleapis.com"


def test_url_construction_without_a_project_fails_closed():
    with pytest.raises(ProviderConfigurationError, match=ENV_PROJECT):
        GoogleProviderConfig().generate_content_url("gemini-3.5-flash")


def test_load_config_reads_the_pinned_environment_names(tmp_path):
    config = load_config(
        {
            ENV_PROJECT: "patch-505223",
            ENV_LOCATION: "global",
            ENV_REASONING_MODEL: "gemini-3.5-flash",
            ENV_CREDENTIALS: ".secrets/gcp-service-account.json",
        },
        base_dir=tmp_path,
    )
    assert config.project == "patch-505223"
    assert config.credentials_path == tmp_path / ".secrets" / "gcp-service-account.json"


def test_load_config_keeps_an_absolute_credentials_path(tmp_path):
    absolute = tmp_path / "key.json"
    config = load_config({ENV_CREDENTIALS: str(absolute)}, base_dir=Path("/elsewhere"))
    assert config.credentials_path == absolute


def test_load_config_falls_back_to_the_pinned_defaults():
    config = load_config({})
    assert config.project is None
    assert config.location == DEFAULT_VERTEX_LOCATION
    assert config.reasoning_model == DEFAULT_REASONING_MODEL
    assert config.image_model == DEFAULT_IMAGE_MODEL
