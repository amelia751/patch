"""Deterministic policy and risk gates (roadmap §8.3).

Rules first, model judgment second. Everything that decides here does so with
pinned data and the standard library, so the answer to "may this run edit this
file" never depends on an inference call succeeding — or on an inference call
being honest about untrusted text it just read.

`screen_untrusted_text` is the one exception, and it is shaped so that it is not
one: Model Armor is consulted only after the deterministic rules have allowed,
and can add a refusal but never remove one. `armor.py` explains why an external
screener that fails open has to be arranged that way.
"""

from packages.policy.armor import (
    GATE_DETERMINISTIC,
    GATE_MODEL_ARMOR,
    ArmorScreening,
    ArmorState,
    ModelArmorClient,
    ModelArmorUnavailableError,
    UntrustedTextScreening,
    model_armor_unavailable_reason,
    screen_untrusted_text,
)
from packages.policy.config import (
    FORBIDDEN_GLOBS,
    FORBIDDEN_PATH_RULES,
    HUMAN_REVIEW_PATH_RULES,
    INJECTION_RULES,
    POLICY_VERSION,
    REQUIRED_CHECKS,
)
from packages.policy.decision import (
    PolicyEvaluation,
    PolicyFinding,
    PolicyOutcome,
    Rule,
    RuleTier,
    combine,
)
from packages.policy.gate import decision_fields, evaluate_change
from packages.policy.globs import glob_match, normalize_path
from packages.policy.injection import (
    contains_injection,
    normalize_untrusted_text,
    scan_untrusted_text,
)
from packages.policy.paths import (
    evaluate_path,
    evaluate_paths,
    forbidden_globs,
    is_forbidden_path,
)

__all__ = [
    "FORBIDDEN_GLOBS",
    "FORBIDDEN_PATH_RULES",
    "GATE_DETERMINISTIC",
    "GATE_MODEL_ARMOR",
    "HUMAN_REVIEW_PATH_RULES",
    "INJECTION_RULES",
    "POLICY_VERSION",
    "REQUIRED_CHECKS",
    "ArmorScreening",
    "ArmorState",
    "ModelArmorClient",
    "ModelArmorUnavailableError",
    "PolicyEvaluation",
    "PolicyFinding",
    "PolicyOutcome",
    "Rule",
    "RuleTier",
    "UntrustedTextScreening",
    "combine",
    "contains_injection",
    "decision_fields",
    "evaluate_change",
    "evaluate_path",
    "evaluate_paths",
    "forbidden_globs",
    "glob_match",
    "is_forbidden_path",
    "model_armor_unavailable_reason",
    "normalize_path",
    "normalize_untrusted_text",
    "scan_untrusted_text",
    "screen_untrusted_text",
]
