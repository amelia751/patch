"""Exporter selection, and the guarantee that tracing cannot break a run."""

import io

from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

from packages.observability.config import (
    ATTR_GCP_PROJECT,
    ENV_TRACE_EXPORTER,
    EXPORTER_AUTO,
    EXPORTER_CLOUD,
    EXPORTER_CONSOLE,
    EXPORTER_NONE,
    PROJECT_VARS,
)
from packages.observability.export import (
    build_processor,
    build_resource,
    cloud_project,
    cloud_trace_unavailable_reason,
    configured_mode,
)

CLOUD_ENV = {"GCP_PROJECT": "patch-test"}


def test_mode_defaults_to_auto():
    assert configured_mode({}) == EXPORTER_AUTO


def test_an_unknown_mode_falls_back_to_auto_rather_than_failing():
    assert configured_mode({ENV_TRACE_EXPORTER: "stackdriver"}) == EXPORTER_AUTO


def test_mode_is_read_case_insensitively():
    assert configured_mode({ENV_TRACE_EXPORTER: "Cloud"}) == EXPORTER_CLOUD


def test_cloud_is_unavailable_without_a_project():
    reason = cloud_trace_unavailable_reason({})
    assert reason is not None
    for name in PROJECT_VARS:
        assert name in reason


def test_either_project_variable_is_accepted():
    """The deployment sets `GCP_PROJECT` and the Google SDKs read
    `GOOGLE_CLOUD_PROJECT`; honouring one only traced to the console in
    production while reporting itself configured."""
    for name in PROJECT_VARS:
        assert cloud_project({name: "patch-test"}) == "patch-test"
        assert cloud_trace_unavailable_reason({name: "patch-test"}) != f"{name} is not set"


def test_the_project_is_attached_so_the_telemetry_api_can_route_the_span():
    resource = build_resource("patchapi-agents", CLOUD_ENV)
    assert resource.attributes[ATTR_GCP_PROJECT] == "patch-test"


def test_none_disables_tracing_entirely():
    assert build_processor(mode=EXPORTER_NONE, env=CLOUD_ENV) is None


def test_console_exports_as_spans_end():
    """A crashed run still has to leave the trace that explains why, which
    batching would defer past the crash."""
    processor = build_processor(mode=EXPORTER_CONSOLE, out=io.StringIO(), env=CLOUD_ENV)
    assert isinstance(processor, SimpleSpanProcessor)


def test_auto_falls_back_to_console_when_cloud_is_unreachable():
    processor = build_processor(mode=EXPORTER_AUTO, out=io.StringIO(), env={})
    assert isinstance(processor, SimpleSpanProcessor)


def test_cloud_requested_but_unavailable_still_yields_a_working_processor():
    """Asked-for-and-absent is a warning, never a dead provider: a trace backend
    must not be able to fail a remediation."""
    processor = build_processor(mode=EXPORTER_CLOUD, out=io.StringIO(), env={})
    assert isinstance(processor, SimpleSpanProcessor)


def test_cloud_batches_when_available():
    if cloud_trace_unavailable_reason(CLOUD_ENV) is not None:
        return
    processor = build_processor(mode=EXPORTER_CLOUD, env=CLOUD_ENV)
    assert isinstance(processor, BatchSpanProcessor)


def test_resource_carries_the_service_name():
    resource = build_resource("patchapi-remediation-worker")
    assert resource.attributes["service.name"] == "patchapi-remediation-worker"
