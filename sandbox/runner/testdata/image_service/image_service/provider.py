"""Stand-in for a vendored image-generation SDK.

The fixture mirrors the property that makes the flagship migration verifiable:
the provider knows which model identifiers exist, so an invented identifier is
rejected by the code under test rather than by a reviewer's memory.
"""

from __future__ import annotations

SUPPORTED_MODEL_IDS: frozenset[str] = frozenset(
    {
        "imagen-4.0-generate-001",
        "gemini-3.1-flash-image",
    }
)


class UnsupportedModelError(ValueError):
    """The requested model identifier is not one this provider serves."""


def generate(model_id: str, prompt: str) -> dict[str, str]:
    """Return a rendering descriptor, or refuse an unknown model identifier."""

    if model_id not in SUPPORTED_MODEL_IDS:
        raise UnsupportedModelError(f"unknown model id: {model_id}")
    return {"model": model_id, "prompt": prompt, "format": "png"}
