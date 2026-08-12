"""Pinned Google provider configuration.

Every model ID, endpoint and environment-variable name the adapter depends on is
declared here. Call sites take a `GoogleProviderConfig`; none of them names a
model. Changing a pin means editing this file.
"""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final, Self

from pydantic import Field, model_validator

from packages.providers.google.errors import ProviderConfigurationError, UnsupportedModelError
from packages.schemas.base import StrictModel
from packages.schemas.enums import ChangeType, Severity

PROVIDER_ID: Final[str] = "google"

# Bumped when the feed→manifest mapping below changes shape. Recorded alongside
# manifests so a stored manifest can be traced to the adapter that produced it.
ADAPTER_VERSION: Final[str] = "1.0.0"

# Deprecation-feed document versions this build knows how to read. An unknown
# version is refused: a feed written by a newer producer may mean something
# different by the same keys.
SUPPORTED_FEED_VERSIONS: Final[frozenset[str]] = frozenset({"1.0.0"})

DEFAULT_REASONING_MODEL: Final[str] = "gemini-3.5-flash"
DEFAULT_IMAGE_MODEL: Final[str] = "gemini-3.1-flash-image"

# Hackathon rule: PatchAPI reasoning runs on Gemini 3.5 Flash or newer.
MINIMUM_REASONING_GENERATION: Final[tuple[int, int]] = (3, 5)

# The Gemini native image surface starts at 3.1; Imagen 4 is the family being
# retired and is never an acceptable image pin.
MINIMUM_IMAGE_GENERATION: Final[tuple[int, int]] = (3, 1)

# Probed 2026-08-11 on project patch-505223: gemini-3.5-flash and
# gemini-3.1-flash-image answer on `locations/global` and 404 on us-central1.
DEFAULT_VERTEX_LOCATION: Final[str] = "global"
VERTEX_API_VERSION: Final[str] = "v1"
VERTEX_SCOPES: Final[tuple[str, ...]] = ("https://www.googleapis.com/auth/cloud-platform",)
DEFAULT_VERTEX_TIMEOUT_SECONDS: Final[float] = 90.0

# Gemini 3.x spends output tokens on thinking before it emits text, so a small
# cap returns an empty candidate rather than a short answer.
DEFAULT_MAX_OUTPUT_TOKENS: Final[int] = 512

ENV_PROJECT: Final[str] = "GCP_PROJECT"
ENV_LOCATION: Final[str] = "GCP_VERTEX_LOCATION"
ENV_CREDENTIALS: Final[str] = "GOOGLE_APPLICATION_CREDENTIALS"
ENV_REASONING_MODEL: Final[str] = "PATCHAPI_REASONING_MODEL"
ENV_IMAGE_MODEL: Final[str] = "PATCHAPI_IMAGE_MODEL"

# Provider-stated change class → manifest severity. A fixed table, not a
# judgement: how bad the change is *for a given repository* is Impact and Policy
# work, and this only records how disruptive the provider's own class of change
# is in general.
SEVERITY_BY_CHANGE_TYPE: Final[MappingProxyType[ChangeType, Severity]] = MappingProxyType(
    {
        ChangeType.MODEL_RETIREMENT: Severity.CRITICAL,
        ChangeType.ENDPOINT_REMOVAL: Severity.CRITICAL,
        ChangeType.AUTH_CHANGE: Severity.HIGH,
        ChangeType.BREAKING_CHANGE: Severity.HIGH,
        ChangeType.API_DEPRECATION: Severity.MEDIUM,
        ChangeType.PARAMETER_CHANGE: Severity.MEDIUM,
        ChangeType.BEHAVIOR_CHANGE: Severity.LOW,
    }
)

_GEMINI_MODEL_RE: Final[re.Pattern[str]] = re.compile(r"^gemini-(\d+)\.(\d+)-[a-z0-9-]+$")


def severity_for(change_type: ChangeType) -> Severity:
    """Return the pinned severity for a provider change class."""
    try:
        return SEVERITY_BY_CHANGE_TYPE[change_type]
    except KeyError as exc:  # pragma: no cover - unreachable while the table is total
        raise ProviderConfigurationError(
            f"no pinned severity for change type {change_type!r}"
        ) from exc


def parse_gemini_generation(model_id: str) -> tuple[int, int]:
    """Return `(major, minor)` for a Gemini model ID.

    Refuses anything that is not a Gemini model ID, which is how an Imagen or
    third-party pin gets caught before it can reach an agent.
    """
    match = _GEMINI_MODEL_RE.match(model_id)
    if match is None:
        raise UnsupportedModelError(
            f"{model_id!r} is not a Gemini model ID of the form 'gemini-<major>.<minor>-<variant>'"
        )
    return int(match.group(1)), int(match.group(2))


def _require_generation(model_id: str, minimum: tuple[int, int], role: str) -> str:
    generation = parse_gemini_generation(model_id)
    if generation < minimum:
        raise UnsupportedModelError(
            f"{role} model {model_id!r} is generation {generation[0]}.{generation[1]}; "
            f"PatchAPI requires {minimum[0]}.{minimum[1]} or newer"
        )
    return model_id


def require_supported_reasoning_model(model_id: str) -> str:
    """Return `model_id` if it may be used for PatchAPI reasoning, else raise."""
    return _require_generation(model_id, MINIMUM_REASONING_GENERATION, "reasoning")


def require_supported_image_model(model_id: str) -> str:
    """Return `model_id` if it may be used for image generation, else raise."""
    checked = _require_generation(model_id, MINIMUM_IMAGE_GENERATION, "image")
    if not checked.endswith("-image"):
        raise UnsupportedModelError(
            f"image model {model_id!r} is not a Gemini native image model "
            "(expected an ID ending in '-image')"
        )
    return checked


class GoogleProviderConfig(StrictModel):
    """Resolved pins for one Google provider session.

    `project` stays optional so offline normalization works with no GCP context
    at all; the Vertex client is what insists on it.
    """

    project: str | None = None
    location: str = DEFAULT_VERTEX_LOCATION
    reasoning_model: str = DEFAULT_REASONING_MODEL
    image_model: str = DEFAULT_IMAGE_MODEL
    credentials_path: Path | None = None
    timeout_seconds: float = Field(default=DEFAULT_VERTEX_TIMEOUT_SECONDS, gt=0)

    @model_validator(mode="after")
    def _check_pins(self) -> Self:
        require_supported_reasoning_model(self.reasoning_model)
        require_supported_image_model(self.image_model)
        if not self.location:
            raise ValueError("location must be set (Gemini 3.x is served from 'global')")
        return self

    @property
    def vertex_host(self) -> str:
        """Host serving `location`.

        The global endpoint has no regional prefix; every other location does.
        """
        if self.location == "global":
            return "https://aiplatform.googleapis.com"
        return f"https://{self.location}-aiplatform.googleapis.com"

    def require_project(self) -> str:
        if not self.project:
            raise ProviderConfigurationError(
                f"no GCP project configured; set {ENV_PROJECT} (see .env.example)"
            )
        return self.project

    def generate_content_url(self, model_id: str) -> str:
        """Full `:generateContent` URL for `model_id` under the pinned location."""
        return (
            f"{self.vertex_host}/{VERTEX_API_VERSION}"
            f"/projects/{self.require_project()}/locations/{self.location}"
            f"/publishers/google/models/{model_id}:generateContent"
        )


def load_config(
    environ: Mapping[str, str] | None = None,
    *,
    base_dir: Path | None = None,
) -> GoogleProviderConfig:
    """Build a config from the environment, resolving relative credential paths.

    `base_dir` is what a relative `GOOGLE_APPLICATION_CREDENTIALS` (the form
    `.env.example` uses) is resolved against, so a verifier can point at the
    repository root regardless of the working directory it was launched from.
    """
    env = os.environ if environ is None else environ
    root = Path.cwd() if base_dir is None else base_dir

    raw_credentials = env.get(ENV_CREDENTIALS, "").strip()
    credentials_path: Path | None = None
    if raw_credentials:
        candidate = Path(raw_credentials).expanduser()
        credentials_path = candidate if candidate.is_absolute() else (root / candidate)

    return GoogleProviderConfig(
        project=env.get(ENV_PROJECT, "").strip() or None,
        location=env.get(ENV_LOCATION, "").strip() or DEFAULT_VERTEX_LOCATION,
        reasoning_model=env.get(ENV_REASONING_MODEL, "").strip() or DEFAULT_REASONING_MODEL,
        image_model=env.get(ENV_IMAGE_MODEL, "").strip() or DEFAULT_IMAGE_MODEL,
        credentials_path=credentials_path,
    )
