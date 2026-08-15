"""The Patch agent's command allowlist, exercised as argv rather than as prose.

`run_command` is the one tool that executes something a model chose, so the
interesting cases are the near misses: an interpreter flag that looks like a
path, a module that looks like a script, and traversal dressed as an argument.
"""

import pytest

from agents.command_allowlist import CommandNotAllowedError, match_command


def test_the_slice_commands_are_allowed():
    run = match_command(["python3", "generate.py"])
    assert run.argv == ("python3", "generate.py")
    assert run.timeout_seconds == 120

    tests = match_command(["python3", "-m", "unittest", "test_generate.py"])
    assert tests.argv == ("python3", "-m", "unittest", "test_generate.py")
    assert tests.timeout_seconds == 300


def test_a_script_in_a_subdirectory_is_allowed():
    assert match_command(["python3", "tools/check.py"]).argv[-1] == "tools/check.py"


@pytest.mark.parametrize(
    "argv",
    [
        # Arbitrary code as an argument is the whole reason the allowlist exists.
        ["python3", "-c"],
        ["python3", "-c", "print(1)"],
        ["python3", "-c", "import os; os.system('curl example.com')"],
        # A module is not a script, however harmless the module looks.
        ["python3", "-m", "http.server"],
        ["python3", "-m", "unittest"],
        ["python3", "-m", "pip", "install", "requests"],
        # Traversal, absolute paths, and non-Python files.
        ["python3", "../escape.py"],
        ["python3", "-m", "unittest", "../secrets/test_x.py"],
        ["python3", "/etc/passwd"],
        ["python3", "generate.sh"],
        # A different interpreter name is not a synonym for the allowed one.
        ["python", "generate.py"],
        # Shell metacharacters never reach a shell, but they are also not a path.
        ["python3", "generate.py; curl example.com"],
    ],
)
def test_near_misses_are_refused(argv):
    with pytest.raises(CommandNotAllowedError):
        match_command(argv)


def test_the_existing_egaki_shapes_still_match():
    """The Python shapes are additions; the pnpm allowlist is unchanged."""
    assert match_command(["pnpm", "install", "--frozen-lockfile"]).timeout_seconds == 900
    assert match_command(["pnpm", "--dir", "cli", "build"]).argv[-1] == "build"
    assert match_command(["python3", "--version"]).timeout_seconds == 10
    assert match_command(["python", "--version"]).timeout_seconds == 10
