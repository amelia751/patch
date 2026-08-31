"""Layer B rules: every rule parses, and none of them fires on prose.

The shape tests run without ast-grep installed, so a malformed rule is caught in
CI whether or not the binary is on the runner. The matching tests skip when it
is absent — Layer B is a precision layer, and its absence is covered by
`test_fallback.py`.
"""

import json
import re
from pathlib import Path

import pytest
from patchapi_repo_indexer.astgrep.runner import (
    DEFAULT_RULE_DIR,
    RULE_SUFFIXES,
    available,
    configured_rule_dir,
    rule_files,
    rule_root,
    scan_files,
)
from patchapi_repo_indexer.errors import AstGrepRuleError

from packages.providers import registry

needs_ast_grep = pytest.mark.skipif(not available(), reason="ast-grep is not installed")

GOOGLE_RULE_DIR = DEFAULT_RULE_DIR / "google"
STRIPE_RULE_DIR = DEFAULT_RULE_DIR / "stripe"

# Every rule any provider ships. The shape assertions below apply to all of
# them; the matching assertions name the provider whose rules they exercise.
RULES = tuple(
    sorted(
        (path for path in DEFAULT_RULE_DIR.rglob("*") if path.suffix.lower() in RULE_SUFFIXES),
        key=lambda path: path.as_posix(),
    )
)

CALL_SITE_SOURCE = """\
import { GoogleGenAI } from "@google/genai";

const client = new GoogleGenAI({ apiKey: process.env.GOOGLE_API_KEY });

export async function draw(prompt: string) {
  return client.models.generateImages({
    model: "imagen-4.0-generate-001",
    prompt,
  });
}
"""

PROSE_SOURCE = """\
// Historically this project used imagen-4.0-generate-001 for sketch rendering.
// The note below is documentation, not a call site.
export const NOTES = "imagen-4.0-generate-001 was retired";
"""

CONFIG_SOURCE = '{\n  "imageModel": "imagen-4.0-generate-001"\n}\n'

# Removed in Stripe API version 2026-03-25.dahlia:
# docs.stripe.com/changelog/dahlia/2026-03-25/remove-legacy-stripejs-methods
STRIPE_CALL_SOURCE = """\
import { loadStripe } from "@stripe/stripe-js";

const stripe = await loadStripe(process.env.STRIPE_PUBLISHABLE_KEY!);

export async function pay(clientSecret: string, cardElement: unknown) {
  return stripe.handleCardPayment(clientSecret, cardElement);
}
"""

# The false positive the CLIENT constraint exists to stop: an application helper
# that happens to share a name with a method Stripe retired.
STRIPE_LOOKALIKE_SOURCE = """\
const attachments = { createSource(name: string) { return name; } };

export const made = attachments.createSource("upload");
"""

STRIPE_CONFIG_SOURCE = '{\n  "apiVersion": "2024-09-30.acacia"\n}\n'


def load(path: Path) -> dict:
    """Parse a rule without a YAML dependency.

    The rule files are flat enough that the keys under test are readable with a
    line scan, and the indexer must not grow a parser dependency to assert that
    its own configuration is well formed.
    """
    parsed: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if match:
            parsed[match.group(1)] = match.group(2).strip()
    return parsed


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "image.ts").write_text(CALL_SITE_SOURCE, encoding="utf-8")
    (tmp_path / "src" / "notes.ts").write_text(PROSE_SOURCE, encoding="utf-8")
    (tmp_path / "config.json").write_text(CONFIG_SOURCE, encoding="utf-8")
    return tmp_path


@pytest.fixture
def stripe_tree(tmp_path):
    root = tmp_path / "stripe-checkout"
    (root / "src").mkdir(parents=True)
    (root / "src" / "checkout.ts").write_text(STRIPE_CALL_SOURCE, encoding="utf-8")
    (root / "src" / "uploads.ts").write_text(STRIPE_LOOKALIKE_SOURCE, encoding="utf-8")
    (root / "stripe.json").write_text(STRIPE_CONFIG_SOURCE, encoding="utf-8")
    return root


def test_the_service_ships_its_rules():
    assert {path.name for path in RULES} >= {
        "google-imagen-call-site.yml",
        "google-imagen-config.yml",
        "stripe-legacy-stripejs-call.yml",
    }


def test_rules_live_under_the_provider_that_owns_them():
    """A rule directly in the root would run for every provider."""
    assert not [path for path in DEFAULT_RULE_DIR.glob("*") if path.suffix in RULE_SUFFIXES]
    for path in RULES:
        assert registry.has_provider(path.parent.name)


def test_the_rule_root_defaults_to_the_shipped_one():
    assert rule_root() == DEFAULT_RULE_DIR


@pytest.mark.parametrize(
    ("provider", "directory"), [("google", GOOGLE_RULE_DIR), ("stripe", STRIPE_RULE_DIR)]
)
def test_a_provider_resolves_to_its_own_rule_directory(provider, directory):
    assert configured_rule_dir(provider) == directory


def test_a_provider_that_ships_no_rules_skips_layer_b_rather_than_failing(monkeypatch, tmp_path):
    """Precision missing is not recall missing. Layer A findings still stand."""
    monkeypatch.setattr("patchapi_repo_indexer.astgrep.runner.ASTGREP_RULE_DIR", str(tmp_path))

    assert configured_rule_dir("google") is None


def test_a_missing_rule_dir_is_a_configuration_error(tmp_path):
    # Running zero rules would report every candidate as unconfirmed, which is
    # not the same answer as "no rule matched".
    with pytest.raises(AstGrepRuleError):
        rule_files(tmp_path / "nope")


def test_an_empty_rule_dir_is_a_configuration_error(tmp_path):
    with pytest.raises(AstGrepRuleError):
        rule_files(tmp_path)


@pytest.mark.parametrize("rule", RULES, ids=lambda path: path.name)
def test_every_rule_declares_the_required_keys(rule):
    parsed = load(rule)

    assert parsed["id"] == rule.stem
    assert parsed["language"]
    # `error` severity changes ast-grep's exit code, which this runner reads as
    # a broken rule rather than as a finding.
    assert parsed["severity"] == "info"
    assert rule.suffix in RULE_SUFFIXES


@pytest.mark.parametrize("rule", RULES, ids=lambda path: path.name)
def test_every_rule_constrains_what_it_matches(rule):
    """An unconstrained rule confirms every call it can parse.

    A confirmation ranks a finding higher, so a rule that matches on shape
    alone would promote unrelated code into a migration PR.
    """
    body = rule.read_text(encoding="utf-8")
    patterns = re.findall(r"regex:\s*'([^']+)'", body)

    assert patterns, "a rule with no regex constraint matches every call it parses"
    for pattern in patterns:
        re.compile(pattern)


def test_rule_ids_are_unique():
    ids = [load(rule)["id"] for rule in RULES]

    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("rule", RULES, ids=lambda path: path.name)
def test_pattern_and_regex_values_are_quoted(rule):
    """An ast-grep pattern must be a quoted YAML scalar.

    A pattern carries `: `, `{` and `$`, so unquoted YAML parses
    `pattern: $C.generateImages({ model: $MODEL })` as a nested mapping and the
    file stops being a rule. ast-grep then rejects the whole rule, Layer B
    reports nothing, and — because a failed rule degrades to Layer A rather than
    raising — the only symptom is silently unconfirmed findings.

    This runs without the binary on purpose: the tests that would otherwise
    catch it need ast-grep installed, which is exactly what CI may not have.
    """
    unquoted = [
        line.strip()
        for line in rule.read_text(encoding="utf-8").splitlines()
        if (value := re.match(r"^\s*-?\s*(?:pattern|regex):\s*(\S.*)$", line))
        and not value.group(1).startswith(("'", '"'))
    ]

    assert not unquoted, f"quote these values or the rule stops parsing: {unquoted}"


@pytest.mark.parametrize("rule", RULES, ids=lambda path: path.name)
def test_every_rule_parses_as_yaml(rule):
    # Depth where the parser is available. `test_pattern_and_regex_values_are_
    # quoted` is the stdlib-only guard that always runs; PyYAML reaches this
    # workspace only as a transitive dependency of another member.
    yaml = pytest.importorskip("yaml")

    document = yaml.safe_load(rule.read_text(encoding="utf-8"))

    assert isinstance(document, dict), "a rule file must parse to a mapping"
    assert document["id"] == rule.stem
    assert document["language"]
    assert document["rule"], "a rule with no `rule:` block matches nothing"


@needs_ast_grep
def test_the_call_site_rule_matches_a_generation_call(tree):
    matches = scan_files(GOOGLE_RULE_DIR, [tree / "src" / "image.ts"], tree)

    assert [match.rule_id for match in matches] == ["google-imagen-call-site"]
    assert matches[0].path == "src/image.ts"


@needs_ast_grep
def test_prose_mentioning_imagen_is_not_a_call_site(tree):
    # The finding that must not happen: a README turned into a migration PR.
    assert scan_files(GOOGLE_RULE_DIR, [tree / "src" / "notes.ts"], tree) == []


@needs_ast_grep
def test_the_config_rule_matches_a_configured_model(tree):
    matches = scan_files(GOOGLE_RULE_DIR, [tree / "config.json"], tree)

    assert [match.rule_id for match in matches] == ["google-imagen-config"]
    assert matches[0].line_start == 2


@needs_ast_grep
def test_the_stripe_rule_matches_a_removed_method_call(stripe_tree):
    matches = scan_files(STRIPE_RULE_DIR, [stripe_tree / "src" / "checkout.ts"], stripe_tree)

    assert [match.rule_id for match in matches] == ["stripe-legacy-stripejs-call"]
    assert matches[0].path == "src/checkout.ts"


@needs_ast_grep
def test_a_same_named_method_on_another_object_is_not_a_stripe_call(stripe_tree):
    """`attachments.createSource(...)` is application code, not a retired API."""
    assert scan_files(STRIPE_RULE_DIR, [stripe_tree / "src" / "uploads.ts"], stripe_tree) == []


@needs_ast_grep
def test_the_stripe_config_rule_matches_a_pinned_api_version(stripe_tree):
    matches = scan_files(STRIPE_RULE_DIR, [stripe_tree / "stripe.json"], stripe_tree)

    assert [match.rule_id for match in matches] == ["stripe-api-version-pin"]


@needs_ast_grep
def test_one_providers_rules_do_not_confirm_anothers_call_sites(stripe_tree, tree):
    """The reason rules are namespaced: confirmation must come from the right provider.

    Running every rule against every candidate would set a `surface` naming a
    call shape the finding is not, and rank it as confirmed on that basis.
    """
    assert scan_files(GOOGLE_RULE_DIR, [stripe_tree / "src" / "checkout.ts"], stripe_tree) == []
    assert scan_files(STRIPE_RULE_DIR, [tree / "src" / "image.ts"], tree) == []


def test_missing_binary_skips_layer_b_instead_of_failing(tree, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    # Layer B sharpens Layer A. A repository must not be reported differently
    # because a binary is missing from the image.
    assert scan_files(GOOGLE_RULE_DIR, [tree / "src" / "image.ts"], tree) == []


def test_a_rule_the_binary_rejects_is_a_rule_error(tree, monkeypatch, tmp_path):
    broken = tmp_path / "rules"
    broken.mkdir()
    (broken / "broken.yml").write_text("id: broken\nrule: {\n", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: "/bin/false")

    with pytest.raises(AstGrepRuleError):
        scan_files(broken, [tree / "src" / "image.ts"], tree)


def test_matches_are_parsed_from_the_json_stream(tree, monkeypatch):
    """The stream parser is exercised without the binary.

    `--json=stream` emits one object per line; a buffering parser would hold a
    large result set in memory before the first row reached the caller.
    """
    stream = "\n".join(
        json.dumps(entry)
        for entry in (
            {
                "ruleId": "google-imagen-call-site",
                "file": "src/image.ts",
                "range": {"start": {"line": 5}, "end": {"line": 8}},
                "text": 'client.models.generateImages({ model: "imagen-4.0-generate-001" })',
            },
            {"not": "a match"},
        )
    )
    monkeypatch.setattr("shutil.which", lambda name: "/bin/true")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: __import__("subprocess").CompletedProcess(args[0], 0, stream, ""),
    )

    matches = scan_files(GOOGLE_RULE_DIR, [tree / "src" / "image.ts"], tree)

    assert matches[0].rule_id == "google-imagen-call-site"
    # ast-grep counts lines from zero; the inventory counts from one.
    assert matches[0].line_start == 6
    assert matches[0].line_end == 9
