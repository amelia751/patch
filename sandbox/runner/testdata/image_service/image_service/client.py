"""The fixture's application code — the thing a migration would edit."""

from __future__ import annotations

from . import provider

MODEL_ID = "imagen-4.0-generate-001"


def render(prompt: str) -> dict[str, str]:
    """Render a prompt with the configured image model."""

    return provider.generate(MODEL_ID, prompt)
