"""Environment pins layer under the real environment, never over it."""

from packages.providers.dotenv import apply_defaults, parse_env_text, read_env_files


def test_comments_blanks_and_quotes():
    parsed = parse_env_text(
        '\n# a comment\nGCP_PROJECT=patch-505223\n\nQUOTED="global"\nBARE = spaced \nnot-a-pair\n'
    )
    assert parsed == {"GCP_PROJECT": "patch-505223", "QUOTED": "global", "BARE": "spaced"}


def test_the_first_file_wins(tmp_path):
    (tmp_path / ".env").write_text("GCP_PROJECT=override\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        "GCP_PROJECT=patch-505223\nGCP_VERTEX_LOCATION=global\n", encoding="utf-8"
    )

    merged = read_env_files([tmp_path / ".env", tmp_path / ".env.example"])

    assert merged == {"GCP_PROJECT": "override", "GCP_VERTEX_LOCATION": "global"}


def test_missing_files_are_skipped(tmp_path):
    assert read_env_files([tmp_path / "absent"]) == {}


def test_an_exported_value_is_never_overwritten():
    environ = {"GCP_PROJECT": "operator-choice"}

    applied = apply_defaults(
        {"GCP_PROJECT": "patch-505223", "GCP_VERTEX_LOCATION": "global"}, environ
    )

    assert environ["GCP_PROJECT"] == "operator-choice"
    assert environ["GCP_VERTEX_LOCATION"] == "global"
    assert applied == ["GCP_VERTEX_LOCATION"]


def test_the_repository_pins_are_readable(repo_root):
    """`.env.example` is the checked-in source for the non-secret pins."""
    pins = read_env_files([repo_root / ".env.example"])
    assert pins["PATCHAPI_REASONING_MODEL"] == "gemini-3.5-flash"
    assert pins["PATCHAPI_IMAGE_MODEL"] == "gemini-3.1-flash-image"
    assert pins["GCP_VERTEX_LOCATION"] == "global"
