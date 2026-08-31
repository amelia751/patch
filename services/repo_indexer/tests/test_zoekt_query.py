"""The indexed read path: what is asked, what comes back, and what is refused.

The pattern and query-construction tests are pure and always run. The response
parsing runs against a stubbed webserver, because the property under test is
that this client reads zoekt's document correctly — not that zoekt is installed.
"""

import base64
import re

import httpx
import pytest
from patchapi_repo_indexer.errors import UnknownProviderError, ZoektUnavailableError
from patchapi_repo_indexer.zoekt import query as query_module
from patchapi_repo_indexer.zoekt.patterns import (
    GOOGLE_GEMINI20_FAMILY,
    GOOGLE_GEMINI_FAMILY,
    GOOGLE_IMAGEN_FAMILY,
    GOOGLE_IMAGEN_PREVIEW,
    GOOGLE_VERTEX_ROUTED,
    compile_patterns,
    match_identifiers,
    patterns_for,
    provider_patterns,
)
from patchapi_repo_indexer.zoekt.query import build_query, repository_file_count, search_shards
from patchapi_repo_indexer.zoekt.shard import ShardRef

REPOSITORY = "amelia751/storygen"
SHARD = ShardRef(REPOSITORY, "main")

GA_MODEL = "imagen-4.0-generate-001"
FAST_MODEL = "imagen-4.0-fast-generate-001"
ULTRA_MODEL = "imagen-4.0-ultra-generate-001"
PREVIEW_MODEL = "imagen-4.0-generate-preview-06-06"


def encoded(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def line_match_payload(path: str, line: str, line_number: int, needle: str) -> dict:
    return {
        "Result": {
            "Files": [
                {
                    "Repository": REPOSITORY,
                    "FileName": path,
                    "Branches": ["main"],
                    "LineMatches": [
                        {
                            "Line": encoded(line),
                            "LineNumber": line_number,
                            "LineFragments": [
                                {"LineOffset": line.index(needle), "MatchLength": len(needle)}
                            ],
                        }
                    ],
                }
            ]
        }
    }


@pytest.fixture
def webserver(monkeypatch):
    """Stub `zoekt-webserver`, recording what it was asked."""
    calls: list[tuple[str, dict]] = []

    def respond(url, json, timeout):
        calls.append((url, json))
        payload = respond.payload
        if isinstance(payload, Exception):
            raise payload
        return httpx.Response(respond.status, json=payload, request=httpx.Request("POST", url))

    respond.payload = {"Result": {"Files": []}}
    respond.status = 200
    respond.calls = calls
    monkeypatch.setattr(query_module.httpx, "post", respond)
    return respond


# --- patterns ---------------------------------------------------------------


@pytest.mark.parametrize("model", [GA_MODEL, FAST_MODEL, ULTRA_MODEL])
def test_the_family_pattern_matches_every_ga_member(model):
    assert re.search(GOOGLE_IMAGEN_FAMILY, model)


def test_the_family_pattern_catches_a_member_no_watchlist_names():
    # The reason Layer A is an index and not a literal grep.
    assert re.search(GOOGLE_IMAGEN_FAMILY, "imagen-5.0-ultra-generate-004")


def test_the_family_pattern_does_not_match_the_preview_identifier():
    assert re.search(GOOGLE_IMAGEN_FAMILY, PREVIEW_MODEL) is None


def test_the_preview_pattern_is_its_own_finding():
    # It has its own replacement and its own retirement date, so it must not be
    # folded into the GA family.
    assert re.search(GOOGLE_IMAGEN_PREVIEW, PREVIEW_MODEL)
    assert re.search(GOOGLE_IMAGEN_PREVIEW, GA_MODEL) is None


def test_the_gemini_family_names_current_and_retired_ids():
    compiled = compile_patterns(patterns_for("google"))
    assert match_identifiers("gemini-3.1-flash-image", compiled) == ("gemini-3.1-flash-image",)
    assert match_identifiers("gemini-3.5-flash", compiled) == ("gemini-3.5-flash",)
    assert match_identifiers("gemini-2.5-flash", compiled) == ("gemini-2.5-flash",)
    assert re.search(GOOGLE_GEMINI_FAMILY, "gemini-3.5-flash")


def test_the_gemini20_pattern_matches_the_retired_flash_family():
    assert re.search(GOOGLE_GEMINI20_FAMILY, "gemini-2.0-flash")
    assert re.search(GOOGLE_GEMINI20_FAMILY, "gemini-2.0-flash-lite-001")
    compiled = compile_patterns(patterns_for("google"))
    assert match_identifiers('MODEL = "gemini-2.0-flash"', compiled) == ("gemini-2.0-flash",)


def test_match_identifiers_names_the_concrete_model_in_a_line():
    compiled = compile_patterns(patterns_for("google"))

    found = match_identifiers(f'  model: "vertex/{GA_MODEL}",', compiled)

    assert found == (f"vertex/{GA_MODEL}",)


def test_match_identifiers_reports_two_models_on_one_line():
    compiled = compile_patterns(patterns_for("google"))

    found = match_identifiers(f'["{GA_MODEL}", "{PREVIEW_MODEL}"]', compiled)

    assert found == (GA_MODEL, PREVIEW_MODEL)


def test_an_identifier_outside_the_family_is_added_as_a_literal():
    patterns = patterns_for("google", ["imagegeneration@006"])

    assert patterns[:3] == (GOOGLE_VERTEX_ROUTED, GOOGLE_IMAGEN_FAMILY, GOOGLE_IMAGEN_PREVIEW)
    assert re.search(patterns[-1], "imagegeneration@006")


def test_a_watchlist_identifier_the_family_covers_is_not_duplicated():
    assert patterns_for("google", [GA_MODEL]) == provider_patterns()["google"]


def test_a_service_host_is_indexed_as_its_own_identifier():
    """A whole-service shutdown names no model, so the host is the only key a
    finding can join on."""
    compiled = compile_patterns(patterns_for("google"))

    found = match_identifiers('const HOST = "dialogflow.googleapis.com";', compiled)

    assert found == ("dialogflow.googleapis.com",)


def test_unknown_provider_has_no_patterns():
    with pytest.raises(UnknownProviderError):
        patterns_for("acme")


# --- query construction -----------------------------------------------------


def test_the_query_anchors_the_repository_name():
    query = build_query([GOOGLE_IMAGEN_FAMILY], [SHARD])

    assert f"repo:^{REPOSITORY}$" in query
    assert "case:yes" in query
    assert GOOGLE_IMAGEN_FAMILY in query


def test_the_query_cannot_reach_a_neighbouring_repository():
    query = build_query([GOOGLE_IMAGEN_FAMILY], [ShardRef("acme/api", "main")])

    # `acme/api-internal` is a different tenant boundary, and an unanchored
    # `repo:acme/api` would read it.
    assert "repo:^acme/api$" in query


def test_a_single_repository_term_is_not_parenthesised():
    """`(repo:^x$)` matches nothing, and says so with zero hits rather than an error.

    Zoekt answers a group holding only a `repo:` atom with an empty result and
    HTTP 200 — indistinguishable from a repository that is genuinely unaffected.
    The parentheses exist only to bind the `or` across several shards.
    """
    query = build_query([GOOGLE_IMAGEN_FAMILY], [SHARD])

    assert f"({'repo:^' + REPOSITORY + '$'})" not in query


def test_several_shards_are_bound_as_a_group():
    query = build_query([GOOGLE_IMAGEN_FAMILY], [SHARD, ShardRef("acme/api", "main")])

    # Without the parentheses the trailing pattern would bind to the last
    # `or` branch, scoping the search to one repository instead of both.
    assert f"(repo:^{REPOSITORY}$ or repo:^acme/api$)" in query


def test_a_query_must_name_its_shards():
    with pytest.raises(ValueError):
        build_query([GOOGLE_IMAGEN_FAMILY], [])


def test_a_query_must_have_a_pattern():
    with pytest.raises(ValueError):
        build_query([], [SHARD])


# --- response parsing -------------------------------------------------------


def test_a_line_match_becomes_a_scoped_result(webserver):
    line = f'  model: "{GA_MODEL}",'
    webserver.payload = line_match_payload("src/image.ts", line, 12, GA_MODEL)

    matches = search_shards([GOOGLE_IMAGEN_FAMILY], [SHARD])

    assert len(matches) == 1
    assert matches[0].path == "src/image.ts"
    assert matches[0].line_number == 12
    assert matches[0].line == line
    assert matches[0].matched_text == GA_MODEL


def test_chunk_matches_are_read_too(webserver):
    line = f'const MODEL = "{PREVIEW_MODEL}";'
    webserver.payload = {
        "Result": {
            "Files": [
                {
                    "Repository": REPOSITORY,
                    "FileName": "src/preview.ts",
                    "Branches": ["main"],
                    "ChunkMatches": [
                        {
                            "Content": encoded(line),
                            "ContentStart": {"LineNumber": 7, "Column": 1},
                            "Ranges": [
                                {
                                    "Start": {
                                        "LineNumber": 7,
                                        "Column": line.index(PREVIEW_MODEL) + 1,
                                    },
                                    "End": {
                                        "LineNumber": 7,
                                        "Column": line.index(PREVIEW_MODEL)
                                        + len(PREVIEW_MODEL)
                                        + 1,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    }

    matches = search_shards([GOOGLE_IMAGEN_PREVIEW], [SHARD])

    assert [(match.line_number, match.matched_text) for match in matches] == [(7, PREVIEW_MODEL)]


def test_a_result_from_an_unrequested_repository_is_dropped(webserver):
    line = f'model = "{GA_MODEL}"'
    payload = line_match_payload("src/image.ts", line, 3, GA_MODEL)
    payload["Result"]["Files"][0]["Repository"] = "someone-else/private"
    webserver.payload = payload

    # Filtering late is one forgotten condition from a tenancy breach; the
    # client refuses anything it did not ask for.
    assert search_shards([GOOGLE_IMAGEN_FAMILY], [SHARD]) == []


def test_a_result_from_another_branch_is_dropped(webserver):
    line = f'model = "{GA_MODEL}"'
    payload = line_match_payload("src/image.ts", line, 3, GA_MODEL)
    payload["Result"]["Files"][0]["Branches"] = ["release"]
    webserver.payload = payload

    assert search_shards([GOOGLE_IMAGEN_FAMILY], [SHARD]) == []


def test_a_shard_without_branch_metadata_is_kept(webserver):
    line = f'model = "{GA_MODEL}"'
    payload = line_match_payload("src/image.ts", line, 3, GA_MODEL)
    payload["Result"]["Files"][0]["Branches"] = []
    webserver.payload = payload

    # A tree indexed without refs carries no branches. Dropping it would turn
    # "indexed differently" into "not affected".
    assert len(search_shards([GOOGLE_IMAGEN_FAMILY], [SHARD])) == 1


def test_an_unreachable_webserver_is_unavailable_not_empty(webserver):
    webserver.payload = httpx.ConnectError("connection refused")

    with pytest.raises(ZoektUnavailableError):
        search_shards([GOOGLE_IMAGEN_FAMILY], [SHARD])


def test_a_server_error_is_unavailable_not_empty(webserver):
    webserver.status = 503

    with pytest.raises(ZoektUnavailableError):
        search_shards([GOOGLE_IMAGEN_FAMILY], [SHARD])


def test_a_response_without_a_result_is_unavailable(webserver):
    webserver.payload = {"Error": "no shards"}

    with pytest.raises(ZoektUnavailableError):
        search_shards([GOOGLE_IMAGEN_FAMILY], [SHARD])


def test_no_matches_is_a_real_answer(webserver):
    webserver.payload = {"Result": {"Files": []}}

    assert search_shards([GOOGLE_IMAGEN_FAMILY], [SHARD]) == []


def test_the_document_count_comes_from_the_list_api(webserver):
    webserver.payload = {"List": {"Repos": [{"Stats": {"Documents": 484}}]}}

    assert repository_file_count(SHARD) == 484
    assert webserver.calls[-1][0].endswith("/api/list")


def test_a_malformed_list_response_is_unavailable(webserver):
    webserver.payload = {"List": None}

    with pytest.raises(ZoektUnavailableError):
        repository_file_count(SHARD)
