"""Constructing and running ADK agents against the pinned Vertex model.

Google ADK is the only orchestration framework PatchAPI runs (CLAUDE.md
constraint 1), and there is no fallback: if ADK or Vertex credentials are
absent, the caller reports a skip. Nothing in this module substitutes a canned
answer for a model that was never called.

`configure_vertex_environment` writes the three variables google-genai reads to
route through Vertex. That is genuinely how the SDK is configured, and doing it
in one named function keeps the alternative — every entry point exporting
variables in a slightly different way — from happening. It never overrides a
value an operator already exported.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agents.config import APP_NAME, MAX_OUTPUT_TOKENS, MODEL_TEMPERATURE, REASONING_MODEL
from agents.errors import AdkUnavailableError
from agents.trace import ToolTrace
from packages.providers.google.config import GoogleProviderConfig
from packages.providers.google.vertex import credentials_available

# google-genai reads these to route generateContent through Vertex rather than
# the AI Studio endpoint. Probed 2026-08-11: the pinned models answer on
# `global` and 404 on regional hosts.
ENV_USE_VERTEX: Final[str] = "GOOGLE_GENAI_USE_VERTEXAI"
ENV_CLOUD_PROJECT: Final[str] = "GOOGLE_CLOUD_PROJECT"
ENV_CLOUD_LOCATION: Final[str] = "GOOGLE_CLOUD_LOCATION"
ENV_CREDENTIALS: Final[str] = "GOOGLE_APPLICATION_CREDENTIALS"


def adk_unavailable_reason() -> str | None:
    """Return `None` if google-adk is importable, else why it is not."""
    try:
        import google.adk  # noqa: F401
    except ImportError as exc:
        return f"google-adk is not installed in this environment ({exc})"
    return None


def adk_version() -> str:
    """Version of the installed ADK. Recorded in the smoke output."""
    try:
        from google.adk.version import __version__
    except ImportError as exc:  # pragma: no cover - guarded by the caller
        raise AdkUnavailableError(str(exc)) from exc
    return __version__


def configure_vertex_environment(config: GoogleProviderConfig) -> dict[str, str]:
    """Point google-genai at Vertex using the adapter's pins. Returns what it set.

    These are overwritten, not defaulted. `config` is already the result of
    resolving `GCP_PROJECT` and `GCP_VERTEX_LOCATION`, so it is the run's decided
    target; leaving a pre-existing `GOOGLE_CLOUD_PROJECT` in place would let an
    unrelated variable in an operator's shell silently redirect an agent run to
    another project. An operator changes the target through `GCP_PROJECT`, which
    is one precedence chain instead of two competing ones.
    """
    applied = {
        ENV_USE_VERTEX: "TRUE",
        ENV_CLOUD_PROJECT: config.require_project(),
        ENV_CLOUD_LOCATION: config.location,
    }
    if config.credentials_path is not None:
        applied[ENV_CREDENTIALS] = str(config.credentials_path)
    os.environ.update(applied)
    return applied


def vertex_unavailable_reason(config: GoogleProviderConfig) -> str | None:
    """Return `None` if a live model call can be attempted, else the reason."""
    return credentials_available(config)


def generate_content_config() -> Any:
    """Decoding settings shared by every agent.

    Temperature zero: these agents confirm and record structured facts, and a
    sampled answer would make a stored trace irreproducible.
    """
    from google.genai import types

    return types.GenerateContentConfig(
        temperature=MODEL_TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


@dataclass(slots=True)
class TurnResult:
    """What one agent turn produced.

    `model_versions` is the identity Vertex reported, not the identity that was
    requested — it is what a compliance check should assert on.
    """

    agent: str
    final_text: str
    model_versions: tuple[str, ...]
    event_count: int
    trace: ToolTrace
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def served_model(self) -> str:
        return self.model_versions[0] if self.model_versions else ""


async def run_turn(
    agent: Any,
    prompt: str,
    *,
    trace: ToolTrace,
    user_id: str = "patchapi-orchestrator",
    app_name: str = APP_NAME,
) -> TurnResult:
    """Run one agent turn to completion and return what it produced.

    The trace is the caller's, already wired into the agent's tool callbacks, so
    a turn's tool calls land in the same stream as every other stage of the run.
    """
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=agent, app_name=app_name)
    session = await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, session_id=trace.run_id
    )

    texts: list[str] = []
    models: list[str] = []
    errors: list[str] = []
    events = 0
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        ):
            events += 1
            if event.model_version and event.model_version not in models:
                models.append(event.model_version)
            if event.error_message:
                errors.append(f"{event.error_code}: {event.error_message}")
            if event.partial:
                continue
            content = getattr(event, "content", None)
            for part in getattr(content, "parts", None) or ():
                if getattr(part, "text", None) and not getattr(part, "thought", False):
                    texts.append(part.text)
    finally:
        await runner.close()

    return TurnResult(
        agent=agent.name,
        final_text="".join(texts).strip(),
        model_versions=tuple(models),
        event_count=events,
        trace=trace,
        errors=tuple(errors),
    )


def repo_root() -> Path:
    """The repository root, derived from this file rather than the cwd."""
    return Path(__file__).resolve().parents[1]


__all__ = [
    "ENV_CLOUD_LOCATION",
    "ENV_CLOUD_PROJECT",
    "ENV_CREDENTIALS",
    "ENV_USE_VERTEX",
    "MAX_OUTPUT_TOKENS",
    "MODEL_TEMPERATURE",
    "REASONING_MODEL",
    "TurnResult",
    "adk_unavailable_reason",
    "adk_version",
    "configure_vertex_environment",
    "generate_content_config",
    "repo_root",
    "run_turn",
    "vertex_unavailable_reason",
]
