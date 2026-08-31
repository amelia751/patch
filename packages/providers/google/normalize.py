"""Google notice → `ChangeManifest`.

The mapping is provider-neutral and lives in `packages.providers.notice`. This
module is the Google-named entry point the orchestrator and the Google verifier
already import; it adds nothing to the mapping and decides nothing about it.

Which capability-note groups become `migration_constraints` is the one thing
that used to be hardcoded here — the normalizer read `gemini_image_family` by
name. That choice now comes from `descriptors/google.json`
(`replacement_surfaces`), so a provider states its own vocabulary and the
normalizer reads the descriptor rather than the model family.
"""

from packages.providers.google.config import ADAPTER_VERSION
from packages.providers.notice import (
    load_notice,
    load_notice_file,
    manifest_from_notice_file,
    notice_to_manifest,
)

# The Google-named spelling of `manifest_from_notice_file`, kept because the
# orchestrator, the Change Intelligence tools and the verifier import it.
manifest_from_feed_file = manifest_from_notice_file

__all__ = [
    "ADAPTER_VERSION",
    "load_notice",
    "load_notice_file",
    "manifest_from_feed_file",
    "manifest_from_notice_file",
    "notice_to_manifest",
]
