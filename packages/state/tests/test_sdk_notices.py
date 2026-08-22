"""Registry facts that are not disappearances, turned into releases."""

from packages.providers.sdk import PackageRelease
from packages.state.sdk_notices import deprecation_note, major_note

CHECKED = "2026-08-22T12:00:00+00:00"


def _release(
    *, name: str = "@google/genai", latest: str = "1.4.0", deprecated: str = ""
) -> PackageRelease:
    return PackageRelease(
        ecosystem="npm",
        name=name,
        exists=True,
        latest=latest,
        deprecated=deprecated,
        checked_at=CHECKED,
        source_url=f"https://registry.npmjs.org/{name}",
    )


def test_a_healthy_package_produces_no_deprecation_note() -> None:
    assert deprecation_note("npm:@google/genai", _release()) is None


def test_a_deprecated_package_quotes_the_author() -> None:
    """A liveness probe reports a deprecated package as healthy forever, so the
    registry's own message is the only evidence there is."""
    note = deprecation_note(
        "npm:@google/generative-ai",
        _release(name="@google/generative-ai", deprecated="Use @google/genai instead."),
    )

    assert note is not None
    assert note["change_kind"] == "deprecation"
    assert "Use @google/genai instead." in note["summary"]
    assert note["identifiers"] == ["npm:@google/generative-ai"]


def test_a_deprecated_package_does_not_fail_closed() -> None:
    """It still installs. Naming the successor is reading a sentence, which is
    Change Intelligence's job rather than a parse's."""
    note = deprecation_note(
        "npm:@google/generative-ai",
        _release(name="@google/generative-ai", deprecated="Superseded."),
    )

    assert note is not None
    assert note["fail_closed"] is False
    assert note["replacements"] == []


def test_a_new_major_nobody_pins_is_worth_a_card() -> None:
    note = major_note("npm:@google/genai", _release(latest="2.0.1"), {1})

    assert note is not None
    assert note["change_kind"] == "new_identifier"
    assert note["external_id"] == "sdk:major:npm:@google/genai:2"


def test_a_major_somebody_already_adopted_is_not_news() -> None:
    """Somebody knows. A card for the stragglers is noise on a migration that
    is already under way."""
    assert major_note("npm:@google/genai", _release(latest="2.0.1"), {1, 2}) is None


def test_the_current_major_produces_nothing() -> None:
    assert major_note("npm:@google/genai", _release(latest="1.9.0"), {1}) is None


def test_an_unparseable_constraint_yields_no_major_claim() -> None:
    assert major_note("npm:@google/genai", _release(latest="2.0.0"), set()) is None
