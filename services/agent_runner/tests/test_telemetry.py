"""What a trace is allowed to carry off the machine that produced it."""

from patchapi_agent_runner import telemetry


def test_message_content_is_withheld_by_default():
    """ADK's own default is to write the prompt and the response onto the span.

    A PatchAPI prompt quotes provider release notes and the customer's source,
    so accepting that default would export untrusted third-party text and
    private code to a trace backend — past the boundary the intake gate holds.
    """
    env: dict[str, str] = {}
    telemetry._withhold_message_content(env)
    assert env["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] == "false"


def test_an_operator_can_still_opt_in():
    """Debugging one run is a legitimate reason to want the prompt on the span."""
    env = {"ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "true"}
    telemetry._withhold_message_content(env)
    assert env["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] == "true"


def test_adk_honours_the_variable_this_module_sets():
    """Pins the coupling rather than the constant.

    The name and the default both live in ADK, so a version bump that renamed
    the variable or flipped the default would otherwise reopen the leak with
    every test still passing.
    """
    tracing = __import__("google.adk.telemetry.tracing", fromlist=["tracing"])
    assert tracing.ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS == "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"

    import os

    previous = os.environ.get("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS")
    try:
        telemetry._withhold_message_content()
        assert tracing._should_add_request_response_to_spans() is False
    finally:
        if previous is None:
            os.environ.pop("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", None)
        else:
            os.environ["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] = previous


def test_the_three_lanes_name_themselves_distinctly():
    """Cloud Run gives all three the same image; `service.name` is what tells a
    reader which lane performed the run."""
    names = {
        telemetry.SERVICE_REMEDIATE,
        telemetry.SERVICE_REMEDIATION_WORKER,
        telemetry.SERVICE_AGENTS,
    }
    assert len(names) == 3


def test_flush_tolerates_an_uninstalled_provider():
    """Tracing must never be the reason a completed run reports as crashed."""
    telemetry.flush(None)
