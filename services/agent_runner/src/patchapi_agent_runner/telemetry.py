"""Installing the trace exporter for one agent-lane process.

Each lane names itself, because "which process performed this run" is the first
question asked of a trace and Cloud Run gives all three the same image. The
worker pool, the named job, and the push-delivery service are separate
`service.name` values for that reason.

Installation happens in the entry point rather than on import: the provider is
global, and a module that installed one would win or lose by import order.
"""

from __future__ import annotations

import logging
from typing import Any, Final

SERVICE_REMEDIATE: Final[str] = "patchapi-remediate"
SERVICE_REMEDIATION_WORKER: Final[str] = "patchapi-remediation-worker"
SERVICE_AGENTS: Final[str] = "patchapi-agents"

log = logging.getLogger(__name__)


def install(service_name: str) -> Any | None:
    """Install the global tracer provider, or return `None` and say why not.

    Tracing is never allowed to be the reason a remediation does not run, so an
    import or credential problem here is logged and the lane continues untraced.
    """
    try:
        from packages.observability.export import (
            cloud_trace_unavailable_reason,
            configured_mode,
            install_process_tracing,
        )

        provider = install_process_tracing(service_name)
        reason = cloud_trace_unavailable_reason()
        log.info(
            "tracing installed for %s (mode=%s%s)",
            service_name,
            configured_mode(),
            f", cloud unavailable: {reason}" if reason else ", exporting to Cloud Trace",
        )
        return provider
    except Exception as exc:
        log.warning("tracing is off for %s: %s", service_name, exc)
        return None


def flush(provider: Any | None) -> None:
    """Export buffered spans before the process exits."""
    if provider is None:
        return
    try:
        from packages.observability.export import flush_tracing

        flush_tracing(provider)
    except Exception as exc:  # pragma: no cover - shutdown path
        log.warning("could not flush spans: %s", exc)


__all__ = ["SERVICE_AGENTS", "SERVICE_REMEDIATE", "SERVICE_REMEDIATION_WORKER", "flush", "install"]
