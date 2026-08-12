"""Evaluation of readiness probes.

Readiness is separate from liveness on purpose: a control plane that cannot
reach Postgres is still alive and must keep serving `/healthz`, but it must not
be sent traffic. A probe that raises counts as not ready — readiness never
fails open.
"""

from collections.abc import Sequence

from patchapi_control_api.models import ReadinessCheck
from patchapi_control_api.ports import ReadinessProbe


async def evaluate(probes: Sequence[ReadinessProbe]) -> tuple[ReadinessCheck, ...]:
    """Run every probe and report one check per probe, in declaration order."""
    checks: list[ReadinessCheck] = []
    for probe in probes:
        try:
            reason = await probe.check()
        # A probe that raises has answered the question: not ready. Letting the
        # exception escape would turn one unreachable dependency into a 500 on
        # the endpoint an operator uses to find out which dependency is out.
        except Exception as exc:
            # The exception type, not its message: a probe may carry a DSN or a
            # host name in its text, and readiness output is widely readable.
            checks.append(
                ReadinessCheck(
                    name=probe.name, ready=False, detail=f"probe raised {type(exc).__name__}"
                )
            )
            continue
        checks.append(ReadinessCheck(name=probe.name, ready=reason is None, detail=reason))
    return tuple(checks)
