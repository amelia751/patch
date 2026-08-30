"""Model Armor may add a refusal and may never remove one.

Every test here runs against a fake transport. The live checks against the real
template are in `scripts/verify_policy_model_armor.sh`, which is opt-in: this
suite has to pass in a checkout with no Google credentials, and a safety test
that only runs when a network is reachable is not a safety test.

The asymmetry under test is the whole design. Google documents that Model
Armor's Vertex integration fails open, so the arrangement has to be one where
its absence costs an assurance and never a decision.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from packages.policy.armor import (
    GATE_DETERMINISTIC,
    GATE_MODEL_ARMOR,
    ArmorState,
    ModelArmorClient,
    ModelArmorUnavailableError,
    model_armor_unavailable_reason,
    screen_untrusted_text,
)
from packages.policy.config import (
    ARMOR_INJECTION_FILTER,
    ARMOR_RULE_ID,
    ENV_ARMOR_ENABLED,
    ENV_ARMOR_LOCATION,
    ENV_ARMOR_PROJECT,
    ENV_ARMOR_TEMPLATE,
    ENV_CLOUD_PROJECT,
)
from packages.policy.decision import PolicyOutcome, RuleTier
from packages.policy.injection import normalize_untrusted_text

ADVERSARIAL = Path(__file__).parent / "adversarial"

# The live template's own vocabulary, reproduced exactly. Each entry in
# `filterResults` wraps its payload in one nested key whose name varies by
# filter, and `sdp` nests an `inspectResult` inside that again.
_CLEAN_FILTERS: dict[str, Any] = {
    "csam": {"csamFilterFilterResult": {"matchState": "NO_MATCH_FOUND"}},
    "malicious_uris": {"maliciousUriFilterResult": {"matchState": "NO_MATCH_FOUND"}},
    "pi_and_jailbreak": {"piAndJailbreakFilterResult": {"matchState": "NO_MATCH_FOUND"}},
    "sdp": {"sdpFilterResult": {"inspectResult": {"matchState": "NO_MATCH_FOUND"}}},
}


def _response(*, match: bool, confidence: str = "HIGH") -> dict[str, Any]:
    filters = json.loads(json.dumps(_CLEAN_FILTERS))
    if match:
        filters["pi_and_jailbreak"]["piAndJailbreakFilterResult"] = {
            "matchState": "MATCH_FOUND",
            "confidenceLevel": confidence,
        }
    return {
        "sanitizationResult": {
            "filterMatchState": "MATCH_FOUND" if match else "NO_MATCH_FOUND",
            "filterResults": filters,
        }
    }


class _Transport:
    """A fake Model Armor endpoint that records what it was asked."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def request(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((url, body))
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _client(payload: Any, **kwargs: Any) -> tuple[ModelArmorClient, _Transport]:
    transport = _Transport(payload)
    return (
        ModelArmorClient(
            template=kwargs.get("template", "projects/p/locations/us-central1/templates/t"),
            location=kwargs.get("location", "us-central1"),
            transport=transport,
        ),
        transport,
    )


def _hostile() -> str:
    return normalize_untrusted_text(
        (ADVERSARIAL / "prompt-injection-release-note.md").read_text(encoding="utf-8")
    )


def _benign() -> str:
    return normalize_untrusted_text(
        (ADVERSARIAL / "benign-release-note.md").read_text(encoding="utf-8")
    )


# -- the composition --------------------------------------------------------


def test_a_deterministic_refusal_never_reaches_model_armor():
    """No second opinion is sought on a document the rules already refused.

    Not an optimisation. A match cannot change a BLOCKED, and text the gate has
    read as an attack is not worth forwarding to a third-party service.
    """
    client, transport = _client(_response(match=False))
    screening = screen_untrusted_text(_hostile(), source="hostile.md", client=client)

    assert screening.outcome is PolicyOutcome.BLOCKED
    assert not screening.allowed
    assert transport.calls == []
    assert screening.armor.state is ArmorState.NOT_CONSULTED
    assert screening.screened_by == (GATE_DETERMINISTIC,)


def test_a_clean_model_armor_verdict_cannot_lift_a_deterministic_refusal():
    """The one-directional property, stated as its own test."""
    client, _ = _client(_response(match=False))
    hostile = _hostile()

    assert screen_untrusted_text(hostile, source="hostile.md", client=client).outcome is (
        PolicyOutcome.BLOCKED
    )
    # And with the service explicitly clean and consulted, via a document the
    # rules refuse for a different reason: an oversized one.
    oversized = "a" * 200_001
    screening = screen_untrusted_text(oversized, source="huge.md", client=client)
    assert screening.outcome is PolicyOutcome.BLOCKED
    assert "policy.injection.document_too_large" in {f.rule_id for f in screening.findings}


def test_model_armor_adds_a_refusal_the_rules_missed():
    """The reason to consult it at all, in the shape the live fixture shows."""
    client, transport = _client(_response(match=True, confidence="MEDIUM_AND_ABOVE"))
    screening = screen_untrusted_text(_benign(), source="notice.md", client=client)

    assert screening.outcome is PolicyOutcome.BLOCKED
    assert screening.armor.state is ArmorState.MATCH
    assert screening.armor.confidence == "MEDIUM_AND_ABOVE"
    assert screening.screened_by == (GATE_DETERMINISTIC, GATE_MODEL_ARMOR)
    assert not screening.degraded
    assert len(transport.calls) == 1

    finding = next(f for f in screening.findings if f.rule_id == ARMOR_RULE_ID)
    # Below a hard block, so `combine` can only ever let it escalate.
    assert finding.tier is RuleTier.SEMANTIC_GOVERNANCE
    assert finding.outcome is PolicyOutcome.BLOCKED
    assert ARMOR_INJECTION_FILTER in finding.matched
    assert "MEDIUM_AND_ABOVE" in finding.matched
    assert "Model Armor" in finding.reason


def test_both_gates_clearing_a_document_is_recorded_as_two():
    client, transport = _client(_response(match=False))
    screening = screen_untrusted_text(_benign(), source="notice.md", client=client)

    assert screening.allowed
    assert screening.screened_by == (GATE_DETERMINISTIC, GATE_MODEL_ARMOR)
    assert screening.armor.state is ArmorState.CLEAN
    assert not screening.degraded
    assert transport.calls[0][1] == {"userPromptData": {"text": _benign()}}


def test_an_unreachable_model_armor_degrades_visibly_and_does_not_end_the_run():
    """Fail soft on the additive gate, but never silently."""
    client, _ = _client(ModelArmorUnavailableError("503 from Model Armor"))
    screening = screen_untrusted_text(_benign(), source="notice.md", client=client)

    assert screening.allowed, "a telemetry outage must not refuse every migration"
    assert screening.degraded
    assert screening.armor.state is ArmorState.UNAVAILABLE
    assert not screening.armor.consulted
    assert screening.screened_by == (GATE_DETERMINISTIC,)
    record = screening.to_audit_record()
    assert record["degraded"] is True
    assert record["model_armor"]["consulted"] is False
    assert "503" in record["model_armor"]["detail"]


def test_an_unexpected_transport_failure_is_also_a_missing_verdict():
    """A credential error is not a clean document."""
    client, _ = _client(RuntimeError("could not refresh the access token"))
    screening = screen_untrusted_text(_benign(), source="notice.md", client=client)

    assert screening.allowed
    assert screening.degraded
    assert screening.armor.state is ArmorState.UNAVAILABLE


def test_a_response_that_does_not_parse_is_unavailable_not_clean():
    """A schema change at Google's end must not read here as 'nothing found'."""
    client, _ = _client({"unexpected": "shape"})
    with pytest.raises(ModelArmorUnavailableError, match="no sanitizationResult"):
        client.sanitize_user_prompt("some provider text")

    screening = screen_untrusted_text(_benign(), source="notice.md", client=client)
    assert screening.armor.state is ArmorState.UNAVAILABLE
    assert not screening.armor.consulted


def test_an_unconfigured_deployment_is_one_gate_but_not_a_degradation():
    """Choosing not to enable a second opinion is not the same as losing one."""
    screening = screen_untrusted_text(_benign(), source="notice.md", env={})

    assert screening.allowed
    assert screening.screened_by == (GATE_DETERMINISTIC,)
    assert screening.armor.state is ArmorState.NOT_CONSULTED
    assert not screening.degraded
    assert ENV_ARMOR_ENABLED in screening.armor.detail


# -- the response surface ---------------------------------------------------


def test_every_matching_filter_is_named_including_the_nested_ones():
    """Unwrapped generically, so a filter added to the template is reported."""
    payload = {
        "sanitizationResult": {
            "filterMatchState": "MATCH_FOUND",
            "filterResults": {
                "malicious_uris": {
                    "maliciousUriFilterResult": {"matchState": "MATCH_FOUND"},
                },
                "sdp": {
                    "sdpFilterResult": {"inspectResult": {"matchState": "MATCH_FOUND"}},
                },
                "some_future_filter": {
                    "someFutureFilterResult": {
                        "matchState": "MATCH_FOUND",
                        "confidenceLevel": "LOW_AND_ABOVE",
                    }
                },
                "pi_and_jailbreak": {
                    "piAndJailbreakFilterResult": {"matchState": "NO_MATCH_FOUND"},
                },
            },
        }
    }
    client, _ = _client(payload)
    screening = client.sanitize_user_prompt("text")

    assert screening.matched
    assert {match.filter_name for match in screening.matched_filters} == {
        "malicious_uris",
        "sdp",
        "some_future_filter",
    }
    # No injection filter fired, so the reported confidence falls back to the
    # first match rather than claiming a level nothing supplied.
    assert screening.confidence == ""


def test_the_call_goes_to_the_regional_endpoint():
    """Templates are served only from `modelarmor.<location>.rep.googleapis.com`.

    The global host answers a template call with a 403 that names permission
    rather than the wrong host, so a regression here would look like an IAM
    problem for as long as someone believed the error message.
    """
    client, transport = _client(_response(match=False), location="europe-west4")
    client.sanitize_user_prompt("text")

    url = transport.calls[0][0]
    assert url.startswith("https://modelarmor.europe-west4.rep.googleapis.com/v1/")
    assert url.endswith(":sanitizeUserPrompt")
    assert "modelarmor.googleapis.com" not in url


# -- configuration ----------------------------------------------------------


def test_model_armor_is_off_until_a_deployment_asks_for_it():
    """So that the default suite needs no credentials and bills no calls."""
    assert model_armor_unavailable_reason({}) == f"{ENV_ARMOR_ENABLED} is not set"
    assert (
        model_armor_unavailable_reason({ENV_ARMOR_ENABLED: "1"})
        == f"{ENV_ARMOR_PROJECT} or {ENV_CLOUD_PROJECT} is required to resolve a template"
    )
    assert model_armor_unavailable_reason({ENV_ARMOR_ENABLED: "0", ENV_CLOUD_PROJECT: "p"})


def test_a_bare_template_id_resolves_against_the_configured_project():
    env = {
        ENV_ARMOR_ENABLED: "true",
        ENV_ARMOR_PROJECT: "patch-505223",
        ENV_ARMOR_LOCATION: "us-central1",
    }
    assert model_armor_unavailable_reason(env) is None
    client = ModelArmorClient.from_env(env)
    assert client.template == (
        "projects/patch-505223/locations/us-central1/templates/patchapi-untrusted-intake"
    )


def test_a_full_resource_name_is_taken_as_given():
    named = "projects/other/locations/europe-west4/templates/strict"
    client = ModelArmorClient.from_env(
        {
            ENV_ARMOR_ENABLED: "1",
            ENV_CLOUD_PROJECT: "patch-505223",
            ENV_ARMOR_TEMPLATE: named,
        }
    )
    assert client.template == named


def test_from_env_refuses_rather_than_guessing_a_project():
    with pytest.raises(ModelArmorUnavailableError, match=ENV_ARMOR_ENABLED):
        ModelArmorClient.from_env({})
