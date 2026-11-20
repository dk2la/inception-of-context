"""The layer rules (docs/adr/0006-layers-inside-each-part.md).

Inside each part (p1, p2, p3), a layer imports only the layers below it:
views -> services -> repositories -> models, and schemas are used by views only.
A part may use an earlier part (p2 uses p1, p3 uses p1 and p2), never a later one.
p1/config and p1/core are shared by everything; they import no layer and no other part.
"""
import ast
import pathlib

import pytest


ROOT = pathlib.Path(__file__).parent.parent
PARTS = ["p1", "p2", "p3"]
LAYERS = ["models", "schemas", "repositories", "services", "views"]

# For each layer: the layers it may import (in its own part or an earlier one). p1.config and p1.core always.
ALLOWED = {
    "models": {"models"},
    "schemas": {"schemas"},
    "repositories": {"models", "repositories"},
    "services": {"models", "repositories", "services"},
    "views": {"schemas", "services"},
}


def imported_modules(path):
    """Every module a file imports, as dotted names."""
    names = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names += [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
    return names


def files_of(*folders):
    return sorted(p for folder in folders for p in (ROOT / folder).rglob("*.py") if "__pycache__" not in p.parts)


SHARED = {"config", "core"}  # only in p1, the part every other part builds on


def test_every_part_has_the_same_layers():
    for part in PARTS:
        folders = {p.name for p in (ROOT / part).iterdir() if p.is_dir() and not p.name.startswith("__")}
        assert folders == set(LAYERS) | (SHARED if part == "p1" else set()), part


@pytest.mark.parametrize("part", PARTS)
@pytest.mark.parametrize("layer", LAYERS)
def test_a_layer_imports_only_the_layers_below_it(part, layer):
    earlier_or_same = PARTS[:PARTS.index(part) + 1]
    for path in files_of(f"{part}/{layer}"):
        for name in imported_modules(path):
            parts = name.split(".")
            if parts[0] not in PARTS or len(parts) < 2 or parts[1] not in LAYERS:
                continue  # config, core, the standard library or a package
            where = f"{part}/{layer}/{path.name} imports {name}"
            assert parts[0] in earlier_or_same, where + " (a later part)"
            assert parts[1] in ALLOWED[layer], where + " (a layer above it)"


@pytest.mark.parametrize("part", PARTS)
def test_a_part_never_uses_a_later_part(part):
    later = PARTS[PARTS.index(part) + 1:]
    for path in files_of(part):
        for name in imported_modules(path):
            assert name.split(".")[0] not in later, f"{path.relative_to(ROOT)} imports {name}"


def test_config_and_core_import_no_layer_and_no_other_part():
    for path in files_of("p1/config", "p1/core"):
        for name in imported_modules(path):
            parts = name.split(".")
            if parts[0] in PARTS:
                assert parts[0] == "p1" and parts[1] in SHARED, f"{path.relative_to(ROOT)} imports {name}"


def test_all_source_files_are_inside_p1_p2_p3():
    """The subject (Chapter IV): every source file lives in p1, p2 or p3. tests/ and target/ are not the project."""
    outside = [p for p in ROOT.glob("*.py")] + [p for d in ROOT.iterdir() if d.is_dir() and d.name not in
                                                 {*PARTS, "tests", "target", "docs", ".git"} and
                                                 not d.name.startswith(".") for p in d.rglob("*.py")]
    assert outside == []


def test_only_core_database_talks_to_chroma():
    users = [p for p in files_of(*PARTS) if "chromadb" in p.read_text()]
    assert [p.relative_to(ROOT).as_posix() for p in users] == ["p1/core/chroma_db.py"]


def test_only_core_llm_talks_to_the_model():
    users = [p for p in files_of(*PARTS) if "urllib.request" in p.read_text()]
    assert [p.relative_to(ROOT).as_posix() for p in users] == ["p1/core/llm.py"]
