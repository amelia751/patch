"""Manifest parsing: what a tree declares it depends on, and where it says so."""

from packages.repo_scan.classify import UsageKind, classify_path
from packages.repo_scan.dependencies import GO, NPM, PYPI, is_manifest, parse_manifest

PACKAGE_JSON = """{
  "name": "egaki",
  "dependencies": {
    "@google/genai": "^1.4.0",
    "next": "15.0.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0"
  }
}
"""

PYPROJECT = """[project]
name = "storygen"
dependencies = [
    "google-genai>=1.2,<2",
    "fastapi>=0.115",
]

[project.optional-dependencies]
dev = ["pytest>=8"]
"""

POETRY = """[tool.poetry.dependencies]
python = "^3.12"
google-generativeai = "^0.8.3"
httpx = { version = "^0.27", extras = ["http2"] }
"""

REQUIREMENTS = """# runtime
google-genai==1.2.0
fastapi>=0.115  # api
-r other.txt
git+https://github.com/example/thing.git
"""

GO_MOD = """module example.com/app

go 1.22

require (
\tgoogle.golang.org/genai v0.5.0 // indirect
\tgithub.com/pkg/errors v0.9.1
)
"""


def _named(hits, name):
    return next(hit for hit in hits if hit.name == name)


def test_package_json_reads_every_dependency_section() -> None:
    hits = parse_manifest(PACKAGE_JSON, path="package.json")

    names = {hit.name for hit in hits}
    assert names == {"@google/genai", "next", "typescript"}
    assert all(hit.ecosystem == NPM for hit in hits)


def test_a_dependency_carries_the_line_that_pins_it() -> None:
    """A finding without a line is not evidence a reviewer can check."""
    hit = _named(parse_manifest(PACKAGE_JSON, path="package.json"), "@google/genai")

    assert hit.line_number == 4
    assert hit.excerpt == '"@google/genai": "^1.4.0",'
    assert hit.constraint == "^1.4.0"


def test_pyproject_reads_project_and_optional_groups() -> None:
    hits = parse_manifest(PYPROJECT, path="pyproject.toml")

    names = {hit.name for hit in hits}
    assert names == {"google-genai", "fastapi", "pytest"}
    assert _named(hits, "google-genai").constraint == ">=1.2,<2"
    assert all(hit.ecosystem == PYPI for hit in hits)


def test_poetry_tables_yield_the_version_not_the_table() -> None:
    hits = parse_manifest(POETRY, path="pyproject.toml")

    assert _named(hits, "httpx").constraint == "^0.27"
    assert "python" not in {hit.name for hit in hits}


def test_requirements_skips_pip_directives_and_urls() -> None:
    hits = parse_manifest(REQUIREMENTS, path="requirements.txt")

    assert {hit.name for hit in hits} == {"google-genai", "fastapi"}
    assert _named(hits, "google-genai").line_number == 2


def test_go_mod_reads_the_require_block() -> None:
    hits = parse_manifest(GO_MOD, path="go.mod")

    assert {hit.name for hit in hits} == {
        "google.golang.org/genai",
        "github.com/pkg/errors",
    }
    assert _named(hits, "google.golang.org/genai").constraint == "v0.5.0"
    assert all(hit.ecosystem == GO for hit in hits)


def test_a_malformed_manifest_yields_nothing_rather_than_raising() -> None:
    """One unreadable file in a monorepo must not fail the whole index."""
    assert parse_manifest("{not json", path="package.json") == []
    assert parse_manifest("[[[", path="pyproject.toml") == []


def test_an_unrelated_file_is_not_a_manifest() -> None:
    assert not is_manifest("tsconfig.json")
    assert parse_manifest(PACKAGE_JSON, path="tsconfig.json") == []


def test_requirements_is_configuration_not_prose() -> None:
    """`.txt` would otherwise read the file that pins the SDK as documentation,
    which classification treats as not worth acting on."""
    assert classify_path("requirements.txt") is UsageKind.CONFIGURATION
    assert classify_path("services/api/go.mod") is UsageKind.CONFIGURATION
    assert classify_path("tests/requirements.txt") is UsageKind.TEST
