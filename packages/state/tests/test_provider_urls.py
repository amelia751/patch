"""Provider connection URLs parse project / dataset / table or fail closed."""

from packages.state.provider_urls import UnsupportedProviderUrl, parse_provider_url


def test_service_usage_url_reads_the_project() -> None:
    parsed = parse_provider_url(
        "catalog",
        "https://serviceusage.googleapis.com/v1/projects/patch-505223/services",
    )
    assert parsed.adapter == "service_usage"
    assert parsed.parsed == {"project": "patch-505223"}
    assert parsed.canonical_url.endswith("/projects/patch-505223/services")


def test_service_usage_url_ignores_query() -> None:
    parsed = parse_provider_url(
        "catalog",
        "https://serviceusage.googleapis.com/v1/projects/patch-505223/services?filter=state:ENABLED",
    )
    assert parsed.parsed["project"] == "patch-505223"


def test_unknown_catalog_url_fails_closed() -> None:
    try:
        parse_provider_url("catalog", "https://cloud.google.com/apis")
    except UnsupportedProviderUrl as exc:
        assert exc.code == "unsupported_catalog_url"
    else:
        raise AssertionError("expected UnsupportedProviderUrl")


def test_bigquery_console_link_reads_p_d_t() -> None:
    parsed = parse_provider_url(
        "changes",
        "https://console.cloud.google.com/bigquery?p=bigquery-public-data&d=google_cloud_release_notes&t=release_notes",
    )
    assert parsed.adapter == "bigquery_release_notes"
    assert parsed.parsed == {
        "project": "bigquery-public-data",
        "dataset": "google_cloud_release_notes",
        "table": "release_notes",
    }
    assert parsed.canonical_url == "bigquery-public-data.google_cloud_release_notes.release_notes"


def test_dotted_table_id_is_accepted() -> None:
    parsed = parse_provider_url(
        "changes",
        "bigquery-public-data.google_cloud_release_notes.release_notes",
    )
    assert parsed.parsed["table"] == "release_notes"


def test_unknown_changes_url_fails_closed() -> None:
    try:
        parse_provider_url("changes", "https://cloud.google.com/release-notes")
    except UnsupportedProviderUrl as exc:
        assert exc.code == "unsupported_changes_url"
    else:
        raise AssertionError("expected UnsupportedProviderUrl")


def test_empty_url_fails_closed() -> None:
    try:
        parse_provider_url("catalog", "   ")
    except UnsupportedProviderUrl:
        return
    raise AssertionError("expected UnsupportedProviderUrl")
