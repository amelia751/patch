"""The pinned policy rule set.

Every pattern, rule id, and outcome PatchAPI enforces lives in this file. Rules
are data, not code at a call site, so a reviewer can read the whole enforced
surface in one place and a change to it is a visible diff.

Ordering inside each table is significant: `first_match` reports the first
pattern that fires, and that pattern is what the audit record names.
"""

from typing import Final

from packages.policy.decision import PolicyOutcome, Rule, RuleTier

# Bumped whenever a rule is added, removed, or changes outcome. Recorded on
# every evaluation so an old decision can be explained by the rules that were
# actually in force when it was made.
POLICY_VERSION: Final[str] = "1.1.0"


# --- Hard blocks -----------------------------------------------------------
#
# A path in this table is never edited by a PatchAPI patch, at any risk tier,
# for any provider change, regardless of what a model concludes. These are the
# controls that would otherwise be able to grade PatchAPI's own work.

FORBIDDEN_PATH_RULES: Final[tuple[Rule, ...]] = (
    Rule(
        rule_id="policy.path.ci_definition",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason=(
            "CI definitions decide which checks grade a patch; a patch that may edit them "
            "can approve itself."
        ),
        patterns=(
            ".github/workflows/**",
            ".github/actions/**",
            ".circleci/**",
            ".gitlab-ci.yml",
            "Jenkinsfile",
            "azure-pipelines.yml",
            "**/*.buildkite.yml",
            "cloudbuild.yaml",
            "cloudbuild.yml",
        ),
    ),
    Rule(
        rule_id="policy.path.review_control",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Review ownership and branch protection are the human control PatchAPI stops at.",
        patterns=(
            "**/CODEOWNERS",
            ".github/settings.yml",
            ".github/branch-protection*",
            ".github/ruleset*",
            ".github/rulesets/**",
        ),
    ),
    Rule(
        rule_id="policy.path.secret_material",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Credential material is never read, written, or rotated by an agent.",
        patterns=(
            "**/.env",
            "**/.env.*",
            ".secrets/**",
            "**/*.pem",
            "**/*.key",
            "**/*.p12",
            "**/*.pfx",
            "**/*.jks",
            "**/id_rsa*",
            "**/id_ed25519*",
            "**/*credentials*.json",
            "**/*service-account*.json",
            "**/secrets.*",
        ),
    ),
    Rule(
        rule_id="policy.path.infrastructure",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Infrastructure definitions change the blast radius of a deploy, not an API call.",
        patterns=(
            "infra/**",
            "terraform/**",
            "**/*.tf",
            "**/*.tfvars",
            "**/*.tfstate",
            "deploy/**",
            "helm/**",
            "charts/**",
            "k8s/**",
            "kubernetes/**",
            "**/kustomization.yaml",
        ),
    ),
    Rule(
        rule_id="policy.path.identity_and_access",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="IAM and RBAC grants are privilege; an API migration never needs more of it.",
        patterns=(
            "**/iam/**",
            "**/rbac/**",
            "**/*iam*.json",
            "**/*iam*.yaml",
            "**/*iam*.yml",
            "**/*rbac*.yaml",
            "**/*rbac*.yml",
            "**/policy-bindings*",
        ),
    ),
    Rule(
        rule_id="policy.path.vcs_internals",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Version-control internals and hooks execute outside the sandbox boundary.",
        patterns=(".git/**", ".githooks/**", "**/pre-commit", "**/pre-push"),
    ),
    Rule(
        rule_id="policy.path.policy_self_edit",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="PatchAPI does not edit the rules that constrain PatchAPI.",
        patterns=("packages/policy/**", "**/patchapi-policy/**"),
    ),
)


# --- Organization policy ---------------------------------------------------
#
# Legitimately part of some migrations, but a human signs off. These escalate
# to HUMAN_REQUIRED rather than blocking, because refusing them outright would
# make ordinary dependency-bearing migrations impossible.

HUMAN_REVIEW_PATH_RULES: Final[tuple[Rule, ...]] = (
    Rule(
        rule_id="policy.path.dependency_lockfile",
        tier=RuleTier.ORG_POLICY,
        outcome=PolicyOutcome.HUMAN_REQUIRED,
        reason="Lockfile changes are a supply-chain surface and get a human reviewer.",
        patterns=(
            "**/package-lock.json",
            "**/pnpm-lock.yaml",
            "**/yarn.lock",
            "**/uv.lock",
            "**/poetry.lock",
            "**/Cargo.lock",
            "**/go.sum",
        ),
    ),
    Rule(
        rule_id="policy.path.dependency_manifest",
        tier=RuleTier.ORG_POLICY,
        outcome=PolicyOutcome.HUMAN_REQUIRED,
        reason="Adding or bumping a dependency is a procurement decision, not a code fix.",
        patterns=(
            "**/package.json",
            "**/pyproject.toml",
            "**/requirements*.txt",
            "**/go.mod",
            "**/Cargo.toml",
            "**/Gemfile",
        ),
    ),
    Rule(
        rule_id="policy.path.container_definition",
        tier=RuleTier.ORG_POLICY,
        outcome=PolicyOutcome.HUMAN_REQUIRED,
        reason="Container and compose definitions change the runtime a service executes in.",
        patterns=("**/Dockerfile", "**/Dockerfile.*", "**/docker-compose*.yml"),
    ),
)


ALL_PATH_RULES: Final[tuple[Rule, ...]] = FORBIDDEN_PATH_RULES + HUMAN_REVIEW_PATH_RULES

# Flattened for the `forbidden_globs` field of a `PolicyDecision` (roadmap §8.3).
FORBIDDEN_GLOBS: Final[tuple[str, ...]] = tuple(
    pattern for rule in FORBIDDEN_PATH_RULES for pattern in rule.patterns
)


# --- Untrusted-text rules --------------------------------------------------
#
# Provider release notes, changelogs, migration guides, and issue comments are
# data. These patterns detect text that is trying to be an instruction instead.
# Every one is a hard block: there is no benign reason for a changelog to
# address the agent reading it.

INJECTION_RULES: Final[tuple[Rule, ...]] = (
    Rule(
        rule_id="policy.injection.instruction_override",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Provider text attempted to override PatchAPI's own instructions.",
        patterns=(
            r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|preceding)\s+"
            r"(?:instructions?|prompts?|rules?|directions?)",
            r"disregard\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|system)",
            r"forget\s+(?:everything|all)\b",
            r"new\s+(?:system\s+)?instructions?\s*:",
            r"(?:override|replace)\s+(?:your|the)\s+system\s+prompt",
            r"<\|im_(?:start|end)\|>",
            r"\[/?INST\]",
        ),
    ),
    Rule(
        rule_id="policy.injection.role_hijack",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Provider text attempted to reassign the agent's role or identity.",
        patterns=(
            r"you\s+are\s+now\s+(?:a|an|the)\b",
            r"act\s+as\s+(?:a|an|the)\s+(?:admin|administrator|root|owner|maintainer)",
            r"developer\s+mode",
            r"enable\s+(?:god|admin|unrestricted)\s+mode",
            r"as\s+the\s+system\s+administrator,?\s+(?:you|i)\b",
        ),
    ),
    Rule(
        rule_id="policy.injection.privilege_escalation",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Provider text requested a privilege or credential change.",
        patterns=(
            r"(?:edit|update|modify|change|patch)\s+(?:the\s+)?iam\b",
            r"\bgrant\s+(?:me\s+|the\s+)?(?:\w+\s+){0,3}?(?:admin|owner|write|editor)\b",
            r"add\s+(?:me|yourself)\s+as\s+(?:an?\s+)?(?:admin|collaborator|owner)",
            r"(?:disable|remove|turn\s+off|bypass)\s+(?:the\s+)?branch\s+protection",
            r"(?:rotate|replace|print|reveal|exfiltrate)\s+(?:the\s+)?(?:secret|credential|api\s*key|token)",
            r"service\s+account\s+key",
        ),
    ),
    Rule(
        rule_id="policy.injection.merge_or_approve",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Provider text asked PatchAPI to go past the pull request.",
        patterns=(
            r"merge\s+(?:this|the|your)\s+(?:pr|pull\s+request|change|branch)",
            r"auto[-\s]?merge",
            r"self[-\s]?approve",
            r"approve\s+(?:this|your\s+own)\s+(?:pr|pull\s+request|change)",
            r"(?:bypass|skip|ignore)\s+(?:ci|the\s+ci|code\s*owners|codeowners|review|tests?)",
            r"\[skip\s+ci\]",
            r"deploy\s+(?:this\s+)?(?:to\s+)?(?:prod|production)",
        ),
    ),
    Rule(
        rule_id="policy.injection.exfiltration",
        tier=RuleTier.HARD_BLOCK,
        outcome=PolicyOutcome.BLOCKED,
        reason="Provider text attempted to move repository or environment data off-host.",
        patterns=(
            r"curl\s+(?:-\w+\s+)*(?:https?://|\$)",
            r"(?:send|post|upload|forward)\s+(?:the\s+)?(?:\w+\s+){0,3}?"
            r"(?:to\s+)?https?://",
            r"(?:os\.environ|process\.env|printenv|env\s*\|)",
            r"base64\s+(?:-d|--decode)",
            r"\bnc\s+-\w*e\b",
        ),
    ),
)


# Checks a run must pass before a PR may be opened. Named here so a call site
# cannot quietly shorten the list (roadmap §8.3).
REQUIRED_CHECKS: Final[tuple[str, ...]] = ("build", "unit_tests", "live_api_smoke_test")

# Longest untrusted document the gate will scan. Beyond this a document is
# refused rather than truncated: a truncated scan that reports "clean" is worse
# than one that reports "too large to clear".
MAX_UNTRUSTED_TEXT_CHARS: Final[int] = 200_000


# --- Model Armor, as a second opinion only ---------------------------------
#
# `INJECTION_RULES` above is a regex table and misses phrasings nobody wrote a
# pattern for: `demo/adversarial/ci-workflow-edit-request.md` clears every rule
# in it, and Google's Model Armor rates the same document a MEDIUM_AND_ABOVE
# prompt-injection match. That is the case for consulting it.
#
# It is nonetheless never the authoritative gate here, and the reason is not
# modesty about its accuracy. Google documents that Model Armor's Vertex
# integration fails *open* — when the service errors or is unreachable, the
# prompt proceeds unscreened. A control that vanishes when it breaks cannot be
# the control that says no. So it sits at `RuleTier.SEMANTIC_GOVERNANCE`, runs
# only after the deterministic gate has already allowed, and can add a refusal
# but never withdraw one.

ENV_ARMOR_ENABLED: Final[str] = "PATCHAPI_MODEL_ARMOR_ENABLED"
ENV_ARMOR_PROJECT: Final[str] = "PATCHAPI_MODEL_ARMOR_PROJECT"
ENV_ARMOR_LOCATION: Final[str] = "PATCHAPI_MODEL_ARMOR_LOCATION"
ENV_ARMOR_TEMPLATE: Final[str] = "PATCHAPI_MODEL_ARMOR_TEMPLATE"
ENV_CLOUD_PROJECT: Final[str] = "GOOGLE_CLOUD_PROJECT"

# Opt-in rather than on-by-default, so that a checkout with ambient Google
# credentials does not start billing an external call from the unit suite. An
# unconsulted Model Armor is never silent: every screening reports which gates
# actually ran, so "deterministic only" is distinguishable from "both agreed".
ARMOR_ENABLED_DEFAULT: Final[bool] = False

ARMOR_LOCATION: Final[str] = "us-central1"
ARMOR_TEMPLATE_ID: Final[str] = "patchapi-untrusted-intake"

# Templates are served only from the regional endpoint. The global
# `modelarmor.googleapis.com` host carries floor settings and answers a template
# call with a 403 that names permission rather than the wrong host — an hour of
# debugging that is pinned here so no call site has to rediscover it.
ARMOR_ENDPOINT_HOST: Final[str] = "modelarmor.{location}.rep.googleapis.com"
ARMOR_SANITIZE_METHOD: Final[str] = "sanitizeUserPrompt"

# Short by intent. The deterministic verdict is already in hand when this call
# is made, so waiting longer only delays a run that has an answer.
ARMOR_REQUEST_TIMEOUT_SECONDS: Final[float] = 8.0

# The filter that carries prompt-injection and jailbreak verdicts. Named so a
# reader of an audit record can tell an injection match from an SDP or malicious
# URI match without consulting Google's response schema.
ARMOR_INJECTION_FILTER: Final[str] = "pi_and_jailbreak"

# Any `MATCH_FOUND` refuses, at whatever confidence the service reports. The
# sensitivity knob is the template's own confidence threshold, and keeping it
# there means there is one place to reason about how strict screening is rather
# than a second threshold hidden in this repository.
ARMOR_RULE_ID: Final[str] = "policy.injection.model_armor"
