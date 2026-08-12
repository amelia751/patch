"""Hashed captures: the digest is what makes a cited URL reviewable."""

import hashlib
from datetime import UTC, datetime

import pytest

from packages.providers.google.snapshot import (
    sha256_file,
    sha256_hex,
    snapshot_from_file,
    snapshot_matches_file,
)

URL = "https://ai.google.dev/gemini-api/docs/deprecations"


def test_hashes_agree_with_hashlib(tmp_path):
    page = tmp_path / "page.html"
    page.write_bytes(b"<html>imagen-4.0-generate-001</html>")
    assert sha256_file(page) == hashlib.sha256(page.read_bytes()).hexdigest()
    assert sha256_hex(page.read_bytes()) == sha256_file(page)


def test_snapshot_records_uri_hash_and_time(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<html>deprecations</html>", encoding="utf-8")
    retrieved = datetime(2026, 8, 11, 23, 0, tzinfo=UTC)

    snapshot = snapshot_from_file(source_url=URL, path=page, retrieved_at=retrieved)

    assert snapshot.content_uri == page.resolve().as_uri()
    assert snapshot.content_sha256 == sha256_file(page)
    assert snapshot.retrieved_at == retrieved
    assert snapshot_matches_file(snapshot, page) is True


def test_a_rewritten_page_no_longer_matches(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<html>deprecations</html>", encoding="utf-8")
    snapshot = snapshot_from_file(source_url=URL, path=page)

    page.write_text("<html>deprecations, revised</html>", encoding="utf-8")

    assert snapshot_matches_file(snapshot, page) is False


def test_a_deleted_page_no_longer_matches(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<html>deprecations</html>", encoding="utf-8")
    snapshot = snapshot_from_file(source_url=URL, path=page)

    page.unlink()

    assert snapshot_matches_file(snapshot, page) is False


def test_snapshotting_absent_bytes_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        snapshot_from_file(source_url=URL, path=tmp_path / "never-captured.html")
