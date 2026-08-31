"""Which binding and which checks a change gets on a pinned repository."""

from pathlib import Path

from patchapi_agent_runner.remediation.slices import decide

STORYGEN = "amelia751/storygen"


def _storygen(tree: Path, *, image_gate: bool = False) -> Path:
    (tree / "lib").mkdir()
    (tree / "lib" / "gemini.ts").write_text(
        'export const MODEL = "gemini-2.0-flash";\n'
        'export const IMAGE_MODEL = "imagen-4.0-generate-001";\n',
        encoding="utf-8",
    )
    (tree / "generate.py").write_text("# MODEL gate\n", encoding="utf-8")
    if image_gate:
        (tree / "generate_image.py").write_text("# IMAGE_MODEL gate\n", encoding="utf-8")
        (tree / "test_generate_image.py").write_text("# IMAGE_MODEL tests\n", encoding="utf-8")
    return tree


def test_gemini20_keeps_the_model_gate(tmp_path: Path) -> None:
    decision = decide(
        repository=STORYGEN,
        change_id="gemini20-flash-shutdown-2026-06-01",
        identifiers=["gemini-2.0-flash"],
        tree=_storygen(tmp_path),
    )
    assert decision.ok
    assert decision.slice_ is not None
    assert decision.slice_.binding == "MODEL"
    assert decision.slice_.build_command == "python3 generate.py"
    assert decision.slice_.test_command == "python3 -m unittest test_generate.py"


def test_imagen_does_not_use_generate_py(tmp_path: Path) -> None:
    """generate.py only reads MODEL. Grading Imagen with it is a false fail."""
    decision = decide(
        repository=STORYGEN,
        change_id="imagen4-retirement-2026-08-17",
        identifiers=["imagen-4.0-generate-001"],
        tree=_storygen(tmp_path),
    )
    assert decision.ok
    assert decision.slice_ is not None
    assert decision.slice_.binding == "IMAGE_MODEL"
    assert "generate.py" not in decision.slice_.build_command
    assert decision.slice_.build_command == ""
    assert decision.slice_.test_command == ""


def test_imagen_uses_generate_image_when_the_tree_has_it(tmp_path: Path) -> None:
    decision = decide(
        repository=STORYGEN,
        change_id="imagen4-retirement-2026-08-17",
        identifiers=["imagen-4.0-generate-001"],
        tree=_storygen(tmp_path, image_gate=True),
    )
    assert decision.slice_ is not None
    assert decision.slice_.build_command == "python3 generate_image.py"
    assert decision.slice_.test_command == "python3 -m unittest test_generate_image.py"


def test_a_binding_without_a_local_gate_is_still_a_slice(tmp_path: Path) -> None:
    """Missing tests are a live-proof hold, not 'I cannot remediate this'."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "client.ts").write_text(
        'export const MODEL = "some-retired-id";\n',
        encoding="utf-8",
    )
    decision = decide(
        repository="acme/widget",
        change_id="some-retirement",
        identifiers=["some-retired-id"],
        tree=tmp_path,
        entrypoint="src/client.ts",
        excerpt='export const MODEL = "some-retired-id";',
    )
    assert decision.ok
    assert decision.slice_ is not None
    assert decision.slice_.binding == "MODEL"
    assert decision.slice_.build_command == ""
    assert decision.slice_.test_command == ""
