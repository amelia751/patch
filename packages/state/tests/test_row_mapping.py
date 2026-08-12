"""Row mapping, without a database.

The SQL itself is exercised against real Postgres by
`scripts/verify_control_api_reads.sh`. What is covered here is the translation
layer between what the driver hands back and what the contracts require —
because that is where a wrong answer would be silently well-formed.
"""

import pytest

from packages.state.config import (
    MissingDatabaseUrlError,
    cors_origins,
    database_url,
)
from packages.state.dashboard import _checks, _is_uuid, _usage
from packages.state.runs import _is_uuid as _runs_is_uuid


class TestDatabaseUrl:
    def test_returns_the_configured_dsn(self):
        assert database_url({"DATABASE_URL": "postgresql://host/db"}) == "postgresql://host/db"

    def test_missing_dsn_raises_rather_than_defaulting(self):
        # Guessing at localhost would let a service report another
        # environment's run state as this one's.
        with pytest.raises(MissingDatabaseUrlError):
            database_url({})

    def test_blank_dsn_is_treated_as_missing(self):
        with pytest.raises(MissingDatabaseUrlError):
            database_url({"DATABASE_URL": "   "})


class TestCorsOrigins:
    def test_unset_allows_no_origin(self):
        assert cors_origins({}) == ()

    def test_splits_and_trims(self):
        origins = cors_origins({"PATCHAPI_CORS_ORIGINS": "http://a.test, http://b.test"})
        assert origins == ("http://a.test", "http://b.test")

    def test_drops_empty_entries(self):
        assert cors_origins({"PATCHAPI_CORS_ORIGINS": "http://a.test,,"}) == ("http://a.test",)


class TestUuidGuard:
    def test_accepts_a_uuid(self):
        assert _is_uuid("5eedda7a-0005-4000-8000-000000000001")
        assert _runs_is_uuid("5eedda7a-0005-4000-8000-000000000001")

    def test_rejects_a_non_uuid(self):
        # A run id that cannot identify a row is reported as not found rather
        # than raising: the caller asked about a run that does not exist.
        assert not _is_uuid("run-000000000001")
        assert not _runs_is_uuid("../../etc/passwd")


class TestUsageMapping:
    def test_maps_a_row_and_narrows_confidence_to_float(self):
        from decimal import Decimal

        usage = _usage(
            {
                "identifier": "imagen-4.0-generate-001",
                "surface": None,
                "file_path": "cli/src/cli/cli.ts",
                "line_start": 418,
                "line_end": None,
                "detection_layer": "A_DETERMINISTIC",
                "confidence": Decimal("0.90"),
                "observed_sha": "c09e1a44200ff5e951746e013035e68aeb3a14b1",
            }
        )

        assert usage.identifier == "imagen-4.0-generate-001"
        assert usage.line_end is None
        # Decimal would serialize as a JSON string and read as text in the UI.
        assert isinstance(usage.confidence, float)
        assert usage.confidence == pytest.approx(0.9)

    def test_rejects_a_path_that_escapes_the_repository(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _usage(
                {
                    "identifier": "x",
                    "surface": None,
                    "file_path": "../../etc/passwd",
                    "line_start": 1,
                    "line_end": None,
                    "detection_layer": "A_DETERMINISTIC",
                    "confidence": 1.0,
                    "observed_sha": "c09e1a44200ff5e951746e013035e68aeb3a14b1",
                }
            )


class TestVerificationChecks:
    def test_reads_named_checks(self):
        checks = _checks([{"name": "build", "passed": True}, {"name": "tests", "passed": False}])

        assert [(check.name, check.passed) for check in checks] == [
            ("build", True),
            ("tests", False),
        ]

    def test_ignores_extra_keys_rather_than_failing_the_page(self):
        # The stored report is a document that may gain keys. A strict splat
        # would turn that into a 500 on the page whose job is to display it.
        checks = _checks([{"name": "build", "passed": True, "duration_ms": 1200}])

        assert len(checks) == 1
        assert checks[0].name == "build"

    def test_skips_entries_that_are_not_checks(self):
        assert _checks([{"note": "no verdict here"}, "not a dict"]) == ()

    def test_a_non_list_payload_yields_no_checks(self):
        # Never invent a passing check from a malformed report.
        assert _checks({"verdict": "PASS"}) == ()
        assert _checks(None) == ()
