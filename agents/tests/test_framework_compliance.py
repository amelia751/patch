"""Google ADK is the only agent framework in the runtime path.

CLAUDE.md constraint 1 is a disqualification risk, so it is checked mechanically
rather than trusted to review. The scan reads the source of every runtime module
in this tree; it deliberately does not look at installed packages, because
google-adk's own optional test extras name several of these libraries and their
presence in a lockfile says nothing about what PatchAPI runs.
"""

import ast
from pathlib import Path

import pytest

# Frameworks the competition rules exclude from the runtime path. Matched on the
# top-level module name, so `langchain_core` and `langchain` both trip.
FORBIDDEN_FRAMEWORKS = frozenset(
    {
        "autogen",
        "crewai",
        "dspy",
        "langchain",
        "langchain_community",
        "langchain_core",
        "langgraph",
        "llama_index",
        "openai",
        "anthropic",
        "litellm",
    }
)

AGENTS_DIR = Path(__file__).resolve().parents[1]


def _runtime_modules() -> list[Path]:
    return sorted(
        path
        for path in AGENTS_DIR.rglob("*.py")
        if "tests" not in path.relative_to(AGENTS_DIR).parts
    )


def _imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("module", _runtime_modules(), ids=lambda p: p.name)
def test_no_foreign_agent_framework_is_imported(module):
    offending = _imported_roots(module.read_text(encoding="utf-8")) & FORBIDDEN_FRAMEWORKS
    assert not offending, f"{module.name} imports {', '.join(sorted(offending))}"


def test_the_tree_actually_uses_adk():
    """A passing exclusion check would be meaningless if nothing used ADK."""
    sources = " ".join(path.read_text(encoding="utf-8") for path in _runtime_modules())
    assert "google.adk" in sources


def test_the_experimental_environment_toolset_is_not_imported():
    """The fleet exposes read_file / list_dir / apply_patch / run_command.

    EnvironmentToolset's Execute / ReadFile / EditFile / WriteFile names would
    break the allowlist invariant, and Execute hard-codes a 30s timeout.
    """
    forbidden = {"EnvironmentToolset", "ExecuteBashTool", "ExecuteTool"}
    for module in _runtime_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[-1] for alias in node.names)
        assert not (imported & forbidden), f"{module.name} imports {imported & forbidden}"


def test_adk_is_never_imported_at_module_scope():
    """Import-time ADK would break collection wherever it is not installed."""
    for module in _runtime_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = _imported_roots(ast.unparse(node))
                assert "google" not in names or "adk" not in ast.unparse(node), (
                    f"{module.name} imports ADK at module scope"
                )
