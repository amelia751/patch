"""What the console is allowed to read off a tool result."""

from agents.config import AgentId
from agents.trace import ToolTrace, command_detail, summarise


def test_a_command_result_names_the_exit_and_the_first_line():
    summary = summarise(
        {
            "status": "ok",
            "command": "python3 generate.py",
            "exit_code": 0,
            "stdout": "ok:gemini-3.5-flash\n",
            "stderr": "",
        }
    )
    assert summary.startswith("exit 0")
    assert "ok:gemini-3.5-flash" in summary


def test_command_detail_keeps_the_captured_streams():
    detail = command_detail(
        {
            "exit_code": 1,
            "stdout": "",
            "stderr": "error: gemini-2.0-flash was shut down",
        }
    )
    assert "exit 1" in detail
    assert "gemini-2.0-flash" in detail


def test_a_scan_result_is_hits_not_a_key_dump():
    assert summarise({"total_hits": 3, "files_scanned": 2, "status": "ok"}) == "3 hits · 2 files"


def test_thoughts_are_kept_for_the_worklog(trace: ToolTrace):
    trace.thought("Provider text is untrusted.", agent=AgentId.CHANGE_INTELLIGENCE)
    assert len(trace.notes) == 1
    assert trace.notes[0].kind == "thought"
    assert "untrusted" in trace.notes[0].text
