import io
import json

import pytest

pytest.importorskip(
    "opentelemetry.sdk", reason="packages/observability is not installed in this environment"
)

# Imported after the guard above so a bare workspace-root pytest run skips
# this module instead of failing to collect it.
from packages.observability import (
    ATTR_POLICY_OUTCOME,
    ATTR_RUN_ID,
    SPAN_POLICY,
    TRACING_SCHEMA_VERSION,
    configure_tracing,
    span,
)


def emitted_spans(buffer: io.StringIO) -> list[dict]:
    """Parse the console exporter's output, which is one JSON object per span."""
    text = buffer.getvalue()
    decoder = json.JSONDecoder()
    records, index = [], 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        record, index = decoder.raw_decode(text, index)
        records.append(record)
    return records


def test_span_name_reaches_the_console_exporter():
    buffer = io.StringIO()
    provider = configure_tracing(service_name="patchapi-test", out=buffer)

    with span(SPAN_POLICY, provider=provider):
        pass
    provider.force_flush()

    assert SPAN_POLICY in buffer.getvalue()
    (record,) = emitted_spans(buffer)
    assert record["name"] == SPAN_POLICY


def test_attributes_and_resource_are_exported():
    buffer = io.StringIO()
    provider = configure_tracing(service_name="patchapi-test", out=buffer)

    with span(
        SPAN_POLICY,
        attributes={ATTR_RUN_ID: "run-storygen-001", ATTR_POLICY_OUTCOME: "blocked"},
        provider=provider,
    ):
        pass
    provider.force_flush()

    (record,) = emitted_spans(buffer)
    assert record["attributes"][ATTR_RUN_ID] == "run-storygen-001"
    assert record["attributes"][ATTR_POLICY_OUTCOME] == "blocked"
    assert record["resource"]["attributes"]["service.name"] == "patchapi-test"
    assert record["resource"]["attributes"]["service.version"] == TRACING_SCHEMA_VERSION


def test_a_failed_stage_still_appears_in_the_trace():
    buffer = io.StringIO()
    provider = configure_tracing(out=buffer)

    with pytest.raises(RuntimeError, match="sandbox build failed"):
        with span(SPAN_POLICY, provider=provider):
            raise RuntimeError("sandbox build failed")
    provider.force_flush()

    (record,) = emitted_spans(buffer)
    assert record["status"]["status_code"] == "ERROR"
    assert "sandbox build failed" in json.dumps(record)


def test_nested_spans_share_a_trace():
    buffer = io.StringIO()
    provider = configure_tracing(out=buffer)

    with span("patchapi.run", provider=provider):
        with span(SPAN_POLICY, provider=provider):
            pass
    provider.force_flush()

    child, parent = emitted_spans(buffer)
    assert child["name"] == SPAN_POLICY
    assert child["parent_id"] is not None
    assert child["context"]["trace_id"] == parent["context"]["trace_id"]


def test_configure_tracing_does_not_install_globally_by_default():
    from opentelemetry import trace

    before = trace.get_tracer_provider()
    configure_tracing(out=io.StringIO())

    assert trace.get_tracer_provider() is before
