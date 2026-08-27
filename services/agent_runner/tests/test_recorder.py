"""The worklog body the console draws Edit cards from."""

from types import SimpleNamespace

from patchapi_agent_runner.remediation.recorder import _body

from agents.trace import ToolStatus


def test_apply_patch_carries_the_unified_diff_after_the_summary() -> None:
    """The next 1s poll must see the hunk, not wait for the end-of-run artifact."""
    diff = "--- a/lib/gemini.ts\n+++ b/lib/gemini.ts\n@@ -1 +1 @@\n-old\n+new\n"
    body = _body(
        SimpleNamespace(
            tool="apply_patch",
            arguments={"diff": "<12 chars, sha256:abc>"},
            result_summary="applied",
            detail=diff,
            status=ToolStatus.OK,
        )
    )
    head, _, tail = body.partition("\n")
    assert head.startswith("apply_patch(")
    assert "applied" in head
    assert tail == diff
