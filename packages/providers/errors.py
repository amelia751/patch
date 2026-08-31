"""Failure modes shared by every provider adapter.

Provider-neutral on purpose. `packages/providers/google/errors.py` keeps the
Google adapter's own hierarchy; these are raised by the registry, which has no
provider to belong to.
"""


class ProviderRegistryError(Exception):
    """Base class for every registry failure."""


class UnknownProviderError(ProviderRegistryError):
    """No descriptor is registered for the requested provider.

    Raised rather than answered with an empty descriptor. A provider with no
    patterns and no watchlist finds nothing, which is byte-for-byte the answer
    a genuinely unaffected repository gives.
    """


class DescriptorError(ProviderRegistryError):
    """A descriptor document is malformed, or two descriptors claim one slug."""


class ProviderEvidenceError(ProviderRegistryError):
    """A notice claims evidence the adapter cannot verify.

    A snapshot whose bytes are absent or no longer hash to the recorded digest
    is not evidence. Downstream agents must not see it as one.
    """
