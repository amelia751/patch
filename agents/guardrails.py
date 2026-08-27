"""Allowlist enforcement and trace capture at the tool boundary.

Two things happen here, and both have to happen at the boundary rather than
inside a tool.

*Enforcement.* `before_tool` refuses a call to a tool outside the agent's
allowlist before the function is entered. The tools an agent is given are
already filtered by `agents.tools.build_tools`, so this is the second barrier:
it catches a topology change, a transferred sub-agent, or a tool a future
deployment wires in without updating `agents.config`. A denial is recorded and
returned as a refusal, never raised — the model must see that it was stopped.

*Trace.* `after_tool` is the only place that knows where a tool call started and
ended, so it is where duration and result digests are captured. Everything the
dashboard renders and the audit reads comes from these two callbacks, which
means a tool cannot run untraced.
"""

from collections.abc import Callable
from time import perf_counter
from typing import Any, Final

from agents.config import MAX_TOOL_CALLS_PER_TURN, AgentId, tool_allowlist
from agents.tools.results import ReasonCode, is_refusal, refusal
from agents.trace import ToolStatus, ToolTrace, command_detail, summarise

# ADK types are imported lazily by the caller; the callbacks below only need the
# `name` attribute of the tool object, so this module stays importable — and
# unit-testable — without google-adk present.
_TOOL_NAME_ATTR: Final[str] = "name"


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, _TOOL_NAME_ATTR, tool))


def build_tool_guardrails(
    agent: AgentId,
    trace: ToolTrace,
    *,
    max_calls: int = MAX_TOOL_CALLS_PER_TURN,
) -> tuple[Callable[..., Any], Callable[..., Any]]:
    """Return `(before_tool, after_tool)` callbacks bound to `agent` and `trace`."""
    allowed = {str(name) for name in tool_allowlist(agent)}
    started: dict[int, float] = {}
    calls = {"count": 0}

    def _record(
        tool: Any,
        args: dict[str, Any],
        status: ToolStatus,
        result: Any,
        duration_ms: float,
        detail: str | None = None,
    ) -> None:
        trace.record(
            agent=agent,
            tool=_tool_name(tool),
            status=status,
            arguments=args,
            result=result,
            duration_ms=duration_ms,
            detail=detail,
        )

    def before_tool(
        tool: Any, args: dict[str, Any], tool_context: Any = None
    ) -> dict[str, Any] | None:
        """Refuse a call the agent may not make; otherwise start the clock.

        Returning a dict short-circuits the tool in ADK, which is what makes
        this an enforcement point rather than an observation point. ADK invokes
        callbacks by keyword, so the parameter names are part of the contract.
        """
        del tool_context  # the guardrail decides from the agent's grant, not from state
        name = _tool_name(tool)

        if name not in allowed:
            denial = refusal(
                ReasonCode.POLICY_DENIED,
                f"agent {agent} is not permitted to call {name!r}; the call was not executed",
                permitted_tools=sorted(allowed),
            )
            _record(tool, args, ToolStatus.DENIED, denial, 0.0, detail="tool outside allowlist")
            return denial

        calls["count"] += 1
        if calls["count"] > max_calls:
            stopped = refusal(
                ReasonCode.STAGE_NOT_READY,
                f"this turn has used its budget of {max_calls} tool calls without "
                "recording an output; stop and record HUMAN_REQUIRED",
            )
            _record(tool, args, ToolStatus.ERROR, stopped, 0.0, detail="tool-call budget exhausted")
            return stopped

        started[id(args)] = perf_counter()
        shown = ", ".join(f"{key}={summarise(value)}" for key, value in sorted(args.items()))
        trace.emit(f"  → {agent}.{name}({shown})")
        return None

    def after_tool(
        tool: Any,
        args: dict[str, Any],
        tool_response: Any,
        tool_context: Any = None,
    ) -> dict[str, Any] | None:
        """Record the completed call. Never alters the tool's own response."""
        del tool_context
        begun = started.pop(id(args), None)
        duration_ms = 0.0 if begun is None else (perf_counter() - begun) * 1000.0
        status = ToolStatus.REFUSED if is_refusal(tool_response) else ToolStatus.OK
        detail = None
        if status is ToolStatus.REFUSED and isinstance(tool_response, dict):
            detail = tool_response.get("message")
        elif isinstance(tool_response, dict) and "exit_code" in tool_response:
            detail = command_detail(tool_response)
        _record(tool, args, status, tool_response, duration_ms, detail=detail)
        if isinstance(tool_response, dict):
            if "exit_code" in tool_response:
                trace.emit(f"        exit {tool_response.get('exit_code')}")
                for stream in ("stdout", "stderr"):
                    text = str(tool_response.get(stream) or "").strip()
                    if text:
                        for line in text.splitlines()[-12:]:
                            trace.emit(f"        {stream}: {line}")
            tail = tool_response.get("visible_tail")
            if tail:
                trace.emit(f"        viewer: {str(tail).strip()[:240]}")
        return None

    return before_tool, after_tool


__all__ = ["build_tool_guardrails"]
