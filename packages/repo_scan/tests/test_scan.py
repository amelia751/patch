import pytest

from packages.repo_scan import (
    UsageKind,
    classify_path,
    scan_text,
    scan_tree,
    should_scan_file,
)

IMAGEN = "imagen-4.0-generate-001"


@pytest.fixture
def checkout(tmp_path):
    """A miniature repository shaped like the Egaki demo target."""
    (tmp_path / "cli" / "src").mkdir(parents=True)
    (tmp_path / "cli" / "src" / "image.ts").write_text(
        'const MODEL = "imagen-4.0-generate-001";\nexport function generate() {}\n',
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "usage.md").write_text(
        "Pass `imagen-4.0-generate-001` to pick the model.\n", encoding="utf-8"
    )
    (tmp_path / "cli" / "src" / "image.test.ts").write_text(
        'expect(MODEL).toBe("imagen-4.0-generate-001");\n', encoding="utf-8"
    )
    (tmp_path / "node_modules" / "junk").mkdir(parents=True)
    (tmp_path / "node_modules" / "junk" / "bundle.js").write_text(
        'var m="imagen-4.0-generate-001"\n', encoding="utf-8"
    )
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


def test_scan_tree_finds_the_identifier_and_skips_vendored_code(checkout):
    result = scan_tree(checkout, [IMAGEN])

    assert result.matched_identifiers == (IMAGEN,)
    paths = [hit.path for hit in result.hits]
    assert paths == ["cli/src/image.test.ts", "cli/src/image.ts", "docs/usage.md"]
    assert not any("node_modules" in path for path in paths)


def test_runtime_hits_exclude_docs_and_tests(checkout):
    result = scan_tree(checkout, [IMAGEN])

    assert [hit.path for hit in result.runtime_hits] == ["cli/src/image.ts"]


def test_scan_is_deterministic(checkout):
    first = scan_tree(checkout, [IMAGEN])
    second = scan_tree(checkout, [IMAGEN])

    assert first.hits == second.hits


def test_empty_tree_yields_empty_inventory(tmp_path):
    result = scan_tree(tmp_path, [IMAGEN])

    assert result.hits == ()
    assert result.matched_identifiers == ()
    assert result.files_scanned == 0


def test_no_identifiers_means_no_hits(checkout):
    assert scan_tree(checkout, []).hits == ()


def test_scan_text_reports_line_numbers_and_bounded_excerpts():
    text = "first\nmodel = 'imagen-4.0-generate-001'\n"
    (hit,) = scan_text(text, [IMAGEN], path="cli/src/image.ts")

    assert hit.line_number == 2
    assert hit.excerpt == "model = 'imagen-4.0-generate-001'"
    assert hit.usage_kind is UsageKind.RUNTIME_SOURCE


def test_matching_is_literal_not_fuzzy():
    assert scan_text("imagen-4.0-generate-002\n", [IMAGEN], path="a.ts") == []


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("cli/src/image.ts", UsageKind.RUNTIME_SOURCE),
        ("cli/src/image.test.ts", UsageKind.TEST),
        ("tests/fixtures/payload.json", UsageKind.TEST),
        ("examples/basic/main.py", UsageKind.EXAMPLE),
        ("docs/usage.md", UsageKind.DOCUMENTATION_EXAMPLE),
        ("README.md", UsageKind.DOCUMENTATION_EXAMPLE),
        ("config/models.yaml", UsageKind.CONFIGURATION),
        (".env", UsageKind.CONFIGURATION),
    ],
)
def test_classify_path(path, expected):
    assert classify_path(path) is expected


def test_binary_and_unknown_extensions_are_not_read(tmp_path):
    assert not should_scan_file(tmp_path / "logo.png")
    assert should_scan_file(tmp_path / "Dockerfile")


def test_scan_root_must_exist(tmp_path):
    with pytest.raises(NotADirectoryError):
        scan_tree(tmp_path / "missing", [IMAGEN])


def test_usage_kind_vocabulary_matches_the_pinned_contract():
    """The wire strings here must not drift from `packages.schemas.enums`."""
    schema_enums = pytest.importorskip(
        "packages.schemas.enums", reason="packages/schemas is not installed in this environment"
    )

    assert {kind.value for kind in UsageKind} == {kind.value for kind in schema_enums.UsageKind}
