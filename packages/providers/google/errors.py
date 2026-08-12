"""Failure modes of the Google provider adapter.

Each one is a distinct fail-closed reason a caller may need to distinguish:
misconfiguration is an operator problem, missing credentials is a `SKIP`, and a
rejected model pin is a compliance stop rather than something to retry.
"""


class GoogleProviderError(Exception):
    """Base class for every Google adapter failure."""


class ProviderConfigurationError(GoogleProviderError):
    """The adapter was asked to run without the pins it needs."""


class UnsupportedModelError(ProviderConfigurationError):
    """A model pin is outside the generation PatchAPI is allowed to use.

    Roadmap constraint: reasoning runs on Gemini 3.5 Flash or newer. An older
    pin is refused here rather than silently honoured at a call site.
    """


class ProviderEvidenceError(GoogleProviderError):
    """The feed claims evidence the adapter cannot verify.

    A snapshot whose bytes are absent or no longer hash to the recorded digest
    is not evidence. Downstream agents must not see it as one.
    """


class MissingCredentialsError(GoogleProviderError):
    """No usable Google credentials, so a live call cannot be attempted.

    Callers turn this into an explicit `SKIP`. It never turns into a synthesized
    model response.
    """


class VertexCallError(GoogleProviderError):
    """A live Vertex call failed or returned a body the adapter cannot read."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
