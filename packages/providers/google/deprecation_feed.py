"""Google's view of the provider notice schema.

There is nothing Google-specific left in the shape of a deprecation notice, so
the model lives in `packages.providers.notice` and every provider shares it.
What used to be Google-specific here was two things, and both moved:

* The `provider == "google"` validator, which refused any other provider's
  document outright. A notice is now checked against the *registry* — it must
  name a provider this build has a descriptor for — so onboarding a provider
  makes its notices readable without touching this module.
* `capability_notes.imagen_family` / `gemini_image_family`, which named Google's
  model families in the schema itself. Notices now group capability bullets
  under `families`, keyed by whatever the provider calls its own surfaces, and
  `descriptors/google.json` names which of those groups describe the
  replacement.

The names below are re-exported because the Google verifier and its golden
suite import them.
"""

from packages.providers.notice import (
    FeedCapabilityNotes,
    FeedSourceSnapshot,
    FeedTrust,
    FeedVerificationRequirements,
    ProviderNotice,
    SnapshotStatus,
)

# The Google adapter reads the shared notice model. Kept as an alias rather than
# a subclass so `isinstance` holds for a notice parsed by any other lane.
GoogleDeprecationNotice = ProviderNotice

__all__ = [
    "FeedCapabilityNotes",
    "FeedSourceSnapshot",
    "FeedTrust",
    "FeedVerificationRequirements",
    "GoogleDeprecationNotice",
    "ProviderNotice",
    "SnapshotStatus",
]
