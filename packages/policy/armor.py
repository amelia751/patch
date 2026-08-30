"""Google Model Armor, layered behind the deterministic injection gate.

`scan_untrusted_text` stays the authoritative reading of an untrusted document.
This module adds a second, probabilistic reading on top of it and composes the
two in `screen_untrusted_text`, which is the function intake code should call.

The composition is one-directional on purpose. Model Armor runs only after the
regex gate has already allowed, so it can add a refusal and can never withdraw
one; `packages/policy/config.py` records why that asymmetry is forced rather
than cautious. The reverse arrangement would be worse than not calling Model
Armor at all: Google's Vertex integration fails open, so a gate that deferred to
it would quietly stop screening the moment the service had a bad minute.

Three outcomes have to stay distinguishable, and the whole result type exists to
keep them apart:

*Both gates cleared the document.* The strongest thing this code can say.
*Only the deterministic gate ran, by configuration.* A weaker assurance, and the
run trace has to show that it is weaker.
*Only the deterministic gate ran, because Model Armor could not be reached.* The
run proceeds on the verdict it has — refusing every migration whenever a
telemetry service is down would be its own outage — but it proceeds having said
so out loud. A screening that could not obtain a verdict never reports a clean
one.

Deliberately not `google-cloud-modelarmor`: this module is imported by the gate
that has to keep working when nothing is installed, and the REST surface it needs
is one call. `google-auth` is imported inside the transport so that
`packages.policy` stays standard-library-only to import, which is the property
that lets the hard blocks run anywhere.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Self

from packages.policy.config import (
    ARMOR_ENABLED_DEFAULT,
    ARMOR_ENDPOINT_HOST,
    ARMOR_INJECTION_FILTER,
    ARMOR_LOCATION,
    ARMOR_REQUEST_TIMEOUT_SECONDS,
    ARMOR_RULE_ID,
    ARMOR_SANITIZE_METHOD,
    ARMOR_TEMPLATE_ID,
    ENV_ARMOR_ENABLED,
    ENV_ARMOR_LOCATION,
    ENV_ARMOR_PROJECT,
    ENV_ARMOR_TEMPLATE,
    ENV_CLOUD_PROJECT,
    POLICY_VERSION,
)
from packages.policy.decision import (
    PolicyEvaluation,
    PolicyFinding,
    PolicyOutcome,
    RuleTier,
    combine,
)
from packages.policy.injection import scan_untrusted_text

log = logging.getLogger(__name__)

_SCOPES: Final[tuple[str, ...]] = ("https://www.googleapis.com/auth/cloud-platform",)

_MATCH_FOUND: Final[str] = "MATCH_FOUND"

# Gate names as they appear in an audit record and in the run trace.
GATE_DETERMINISTIC: Final[str] = "deterministic_injection_rules"
GATE_MODEL_ARMOR: Final[str] = "model_armor"

_TRUE: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


class ModelArmorUnavailableError(RuntimeError):
    """A Model Armor verdict was wanted and could not be obtained.

    Raised rather than returned as a clean result, for the same reason
    `MemoryUnavailableError` exists: "the screener said nothing was wrong" and
    "the screener could not be asked" must not collapse into one answer.
    """


class ArmorState(StrEnum):
    """Whether Model Armor spoke, and what it said.

    `NOT_CONSULTED` and `UNAVAILABLE` are both "no verdict", kept apart because
    only one of them is a fault. Not consulting is a choice — the deployment did
    not enable a second opinion, or the deterministic gate had already refused
    and nothing was left to ask about. `UNAVAILABLE` is a second opinion that was
    expected and did not arrive, which is worth an operator's attention. Which of
    the two reasons applies is in `ArmorScreening.detail`, always.
    """

    CLEAN = "clean"
    MATCH = "match"
    NOT_CONSULTED = "not_consulted"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ArmorFilterMatch:
    """One named Model Armor filter that fired, with the confidence it reported."""

    filter_name: str
    confidence: str = ""

    def __str__(self) -> str:
        return f"{self.filter_name}({self.confidence})" if self.confidence else self.filter_name


@dataclass(frozen=True, slots=True)
class ArmorScreening:
    """What Model Armor made of one document.

    `detail` is populated on every state, including the clean one, because this
    object is read straight into a run trace and "why is there no verdict here"
    is the question it exists to answer.
    """

    state: ArmorState
    matched_filters: tuple[ArmorFilterMatch, ...] = ()
    template: str = ""
    detail: str = ""

    @property
    def consulted(self) -> bool:
        """Whether a verdict was actually obtained from the service."""
        return self.state in {ArmorState.CLEAN, ArmorState.MATCH}

    @property
    def matched(self) -> bool:
        return self.state is ArmorState.MATCH

    @property
    def confidence(self) -> str:
        """The confidence reported for the injection filter, or the first match."""
        for match in self.matched_filters:
            if match.filter_name == ARMOR_INJECTION_FILTER:
                return match.confidence
        return self.matched_filters[0].confidence if self.matched_filters else ""

    def as_finding(self, subject: str) -> PolicyFinding | None:
        """This screening as a policy finding, or `None` when it refuses nothing.

        Tiered `SEMANTIC_GOVERNANCE`, which `combine` treats as a ratchet: the
        finding can escalate an ALLOW to BLOCKED and is structurally incapable of
        relaxing anything a hard block already decided.
        """
        if not self.matched:
            return None
        named = ", ".join(str(match) for match in self.matched_filters)
        return PolicyFinding(
            rule_id=ARMOR_RULE_ID,
            tier=RuleTier.SEMANTIC_GOVERNANCE,
            outcome=PolicyOutcome.BLOCKED,
            reason=(
                "Google Model Armor read this document as a prompt-injection or jailbreak "
                f"attempt ({named}). The deterministic rules did not match it, so this is "
                "the only gate that stopped it."
            ),
            subject=subject,
            matched=named,
        )

    def to_audit_record(self) -> dict[str, Any]:
        """A flat, JSON-safe record for the run trace and the audit log."""
        return {
            "gate": GATE_MODEL_ARMOR,
            "state": self.state.value,
            "consulted": self.consulted,
            "matched": self.matched,
            "confidence": self.confidence,
            "matched_filters": [str(match) for match in self.matched_filters],
            "template": self.template,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class UntrustedTextScreening:
    """The composed verdict on one untrusted document, and who reached it.

    `outcome` is what a caller enforces. `screened_by` is what a caller reports:
    a run must be able to tell an intake screened by both gates from one screened
    by a single gate, and a state or a PR body that cannot make that distinction
    is claiming an assurance it does not have.
    """

    source: str
    deterministic: PolicyEvaluation
    armor: ArmorScreening
    outcome: PolicyOutcome
    findings: tuple[PolicyFinding, ...]

    @property
    def allowed(self) -> bool:
        return self.outcome is PolicyOutcome.ALLOW

    @property
    def screened_by(self) -> tuple[str, ...]:
        """The gates that actually returned a verdict on this document."""
        gates = [GATE_DETERMINISTIC]
        if self.armor.consulted:
            gates.append(GATE_MODEL_ARMOR)
        return tuple(gates)

    @property
    def degraded(self) -> bool:
        """Whether a second opinion was expected here and did not arrive."""
        return self.armor.state is ArmorState.UNAVAILABLE

    @property
    def evaluation(self) -> PolicyEvaluation:
        """The composed verdict in the shape the rest of the policy gate speaks."""
        return PolicyEvaluation(
            policy_version=POLICY_VERSION,
            outcome=self.outcome,
            findings=self.findings,
        )

    def to_audit_record(self) -> dict[str, Any]:
        """What the run trace stores. Never the document's own words."""
        return {
            "source": self.source,
            "outcome": self.outcome.value,
            "screened_by": list(self.screened_by),
            "degraded": self.degraded,
            "policy_version": POLICY_VERSION,
            "findings": [finding.to_audit_record() for finding in self.findings],
            "model_armor": self.armor.to_audit_record(),
        }


def model_armor_unavailable_reason(env: dict[str, str] | None = None) -> str | None:
    """Return `None` when Model Armor is configured and callable in principle.

    Checked before the call so that a deployment which never enabled a second
    opinion is reported as such, rather than as a service that failed.
    """
    environ = env if env is not None else dict(os.environ)
    if not _enabled(environ):
        return f"{ENV_ARMOR_ENABLED} is not set"
    if not _project(environ):
        return f"{ENV_ARMOR_PROJECT} or {ENV_CLOUD_PROJECT} is required to resolve a template"
    try:
        import google.auth  # noqa: F401
    except ImportError as exc:
        return f"google-auth is not installed ({exc})"
    return None


class ModelArmorClient:
    """One Model Armor template's `sanitizeUserPrompt` surface.

    Construct with `from_env()` in production. The explicit constructor exists so
    a test can point at a fake transport without credentials or a project.
    """

    __slots__ = ("_location", "_template", "_transport")

    def __init__(
        self,
        *,
        template: str,
        location: str = ARMOR_LOCATION,
        transport: Any | None = None,
    ) -> None:
        self._template = template
        self._location = location
        self._transport = transport if transport is not None else _AuthorizedTransport()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Self:
        """Build from configuration, or raise if no template is configured."""
        environ = env if env is not None else dict(os.environ)
        reason = model_armor_unavailable_reason(environ)
        if reason is not None:
            raise ModelArmorUnavailableError(reason)
        return cls(template=_resolve_template(environ), location=_location(environ))

    @property
    def template(self) -> str:
        return self._template

    def sanitize_user_prompt(self, text: str) -> ArmorScreening:
        """Screen one document, or raise `ModelArmorUnavailableError`.

        Never returns a clean verdict it did not receive. A response this code
        cannot parse is an unavailable service, not an empty match list: a
        schema change at Google's end must not read here as "nothing was found".
        """
        host = ARMOR_ENDPOINT_HOST.format(location=self._location)
        url = f"https://{host}/v1/{self._template}:{ARMOR_SANITIZE_METHOD}"
        payload = self._transport.request(url, {"userPromptData": {"text": text}})
        result = payload.get("sanitizationResult")
        if not isinstance(result, dict) or "filterMatchState" not in result:
            raise ModelArmorUnavailableError(
                f"Model Armor returned no sanitizationResult for template {self._template}"
            )
        matches = _matched_filters(result.get("filterResults"))
        if str(result.get("filterMatchState")) == _MATCH_FOUND:
            return ArmorScreening(
                state=ArmorState.MATCH,
                matched_filters=matches,
                template=self._template,
                detail=(
                    "Model Armor reported "
                    + (", ".join(str(match) for match in matches) or _MATCH_FOUND)
                ),
            )
        return ArmorScreening(
            state=ArmorState.CLEAN,
            template=self._template,
            detail="Model Armor screened this document and matched no filter",
        )


def screen_untrusted_text(
    text: str,
    *,
    source: str,
    client: ModelArmorClient | None = None,
    env: dict[str, str] | None = None,
) -> UntrustedTextScreening:
    """Screen one untrusted document through both gates, deterministic first.

    `source` names where the text came from and is carried into the audit record.
    Pass `client` to screen through an already-built client; otherwise one is
    resolved from configuration, and a deployment with no Model Armor configured
    gets the deterministic verdict labelled as the single gate it is.

    The deterministic gate short-circuits: when it refuses, Model Armor is not
    called at all. Nothing about the second opinion could change that answer, and
    a document the gate has already read as an attack is not worth sending to a
    third party.
    """
    deterministic = scan_untrusted_text(text, source=source)
    if deterministic.outcome is not PolicyOutcome.ALLOW:
        return UntrustedTextScreening(
            source=source,
            deterministic=deterministic,
            armor=ArmorScreening(
                state=ArmorState.NOT_CONSULTED,
                detail=("not consulted: the deterministic rules already refused this document"),
            ),
            outcome=deterministic.outcome,
            findings=deterministic.findings,
        )

    armor = _second_opinion(text, client=client, env=env)
    findings = list(deterministic.findings)
    finding = armor.as_finding(source)
    if finding is not None:
        findings.append(finding)
    return UntrustedTextScreening(
        source=source,
        deterministic=deterministic,
        armor=armor,
        outcome=combine(tuple(findings)),
        findings=tuple(findings),
    )


def reset_shared_client() -> None:
    """Drop the cached client so a later call re-reads configuration.

    For tests and for a worker whose environment changed under it. Nothing in a
    run depends on being called.
    """
    global _SHARED
    _SHARED = None


# -- internals --------------------------------------------------------------

# One client per process, because building one resolves application-default
# credentials and an intake path screens many documents.
_SHARED: ModelArmorClient | None = None


def _second_opinion(
    text: str, *, client: ModelArmorClient | None, env: dict[str, str] | None
) -> ArmorScreening:
    """Model Armor's reading of `text`, or a stated reason there is none.

    Every failure mode lands on a screening object rather than an exception:
    this is the second opinion, and a run that already has a deterministic
    verdict must not be ended by the failure of the gate that only adds.
    """
    if client is None:
        reason = model_armor_unavailable_reason(env)
        if reason is not None:
            return ArmorScreening(
                state=ArmorState.NOT_CONSULTED,
                detail=f"not consulted: {reason}",
            )
    try:
        resolved = client if client is not None else _shared_client(env)
        return resolved.sanitize_user_prompt(text)
    except ModelArmorUnavailableError as exc:
        # Loud on purpose. This is the branch where the screening a deployment
        # asked for did not happen, and it must not be inferable only from the
        # absence of a log line.
        log.warning("Model Armor could not screen an untrusted document: %s", exc)
        return ArmorScreening(
            state=ArmorState.UNAVAILABLE,
            detail=(
                f"no Model Armor verdict was obtained ({exc}); this document was cleared "
                "by the deterministic rules alone"
            ),
        )
    except Exception as exc:
        # Broad on purpose. Anything this gate raises — a credential library
        # error, a socket, a JSON surprise — is a missing second opinion, and the
        # gate that only adds refusals must not be able to end a run by failing.
        log.warning("Model Armor screening failed unexpectedly: %s", exc)
        return ArmorScreening(
            state=ArmorState.UNAVAILABLE,
            detail=(
                f"no Model Armor verdict was obtained ({exc!r}); this document was cleared "
                "by the deterministic rules alone"
            ),
        )


def _shared_client(env: dict[str, str] | None) -> ModelArmorClient:
    global _SHARED
    if _SHARED is None:
        _SHARED = ModelArmorClient.from_env(env)
    return _SHARED


def _matched_filters(filter_results: Any) -> tuple[ArmorFilterMatch, ...]:
    """The filters that fired, from Model Armor's per-filter result map.

    Each entry wraps its payload in a single nested key whose name varies with
    the filter (`piAndJailbreakFilterResult`, `csamFilterFilterResult`), and SDP
    nests one level deeper again. Unwrapping generically rather than by name
    means a filter added to the template is reported rather than skipped.
    """
    if not isinstance(filter_results, dict):
        return ()
    matches: list[ArmorFilterMatch] = []
    for name, wrapper in sorted(filter_results.items()):
        payload = _unwrap(wrapper)
        if not isinstance(payload, dict):
            continue
        inner = payload.get("inspectResult")
        payload = inner if isinstance(inner, dict) else payload
        if str(payload.get("matchState")) == _MATCH_FOUND:
            matches.append(
                ArmorFilterMatch(
                    filter_name=str(name),
                    confidence=str(payload.get("confidenceLevel") or ""),
                )
            )
    return tuple(matches)


def _unwrap(wrapper: Any) -> Any:
    if isinstance(wrapper, dict) and len(wrapper) == 1:
        return next(iter(wrapper.values()))
    return wrapper


class _AuthorizedTransport:
    """Google-signed POSTs over the standard library.

    Credentials are resolved once and refreshed on demand; a long-lived worker
    outlives an access token.
    """

    __slots__ = ("_credentials",)

    def __init__(self) -> None:
        self._credentials: Any | None = None

    def request(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=ARMOR_REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise ModelArmorUnavailableError(f"{exc.code} from Model Armor: {detail}") from exc

    def _token(self) -> str:
        import google.auth
        import google.auth.transport.requests

        if self._credentials is None:
            self._credentials, _ = google.auth.default(scopes=_SCOPES)
        if not self._credentials.valid:
            self._credentials.refresh(google.auth.transport.requests.Request())
        return str(self._credentials.token)


def _enabled(env: dict[str, str]) -> bool:
    raw = env.get(ENV_ARMOR_ENABLED, "").strip().lower()
    return raw in _TRUE if raw else ARMOR_ENABLED_DEFAULT


def _project(env: dict[str, str]) -> str:
    return env.get(ENV_ARMOR_PROJECT, "").strip() or env.get(ENV_CLOUD_PROJECT, "").strip()


def _location(env: dict[str, str]) -> str:
    return env.get(ENV_ARMOR_LOCATION, "").strip() or ARMOR_LOCATION


def _resolve_template(env: dict[str, str]) -> str:
    """Full resource name for the configured template."""
    template = env.get(ENV_ARMOR_TEMPLATE, "").strip() or ARMOR_TEMPLATE_ID
    if template.startswith("projects/"):
        return template
    location = _location(env)
    return f"projects/{_project(env)}/locations/{location}/templates/{template}"


__all__ = [
    "GATE_DETERMINISTIC",
    "GATE_MODEL_ARMOR",
    "ArmorFilterMatch",
    "ArmorScreening",
    "ArmorState",
    "ModelArmorClient",
    "ModelArmorUnavailableError",
    "UntrustedTextScreening",
    "model_armor_unavailable_reason",
    "reset_shared_client",
    "screen_untrusted_text",
]
