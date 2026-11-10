import os
import shutil
import sys

from p1 import index
from p1.index import chunk_id, get_collection, index_all, list_files, main, reindex_file


def test_chunk_id_is_a_stable_64_character_hex_string():
    first = chunk_id("calculator/core.py", "def add(): pass")
    assert first == chunk_id("calculator/core.py", "def add(): pass")
    assert len(first) == 64
    assert set(first) <= set("0123456789abcdef")


def test_chunk_id_changes_with_text_and_with_path():
    base = chunk_id("a.py", "x = 1")
    assert base != chunk_id("a.py", "x = 2")
    assert base != chunk_id("b.py", "x = 1")


def test_chunk_id_keeps_path_and_text_apart():
    assert chunk_id("a", "bc") != chunk_id("ab", "c")


# --- helpers ---

CALC = '''import math


class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
'''


def write(target, name, text):
    """Write a file into the temporary Target Project and return its absolute path."""
    path = os.path.join(target, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def ids_of(path):
    return set(get_collection().get(where={"path": path})["ids"])


def names_of(path):
    found = get_collection().get(where={"path": path}, include=["metadatas"])
    return sorted(m["name"] for m in found["metadatas"])


# --- the collection ---


def test_collection_starts_empty_and_is_shared(temp_index):
    assert get_collection().count() == 0
    assert get_collection() is get_collection()


def test_index_survives_a_restart(temp_index):
    get_collection().add(ids=["x"], documents=["hello"], metadatas=[{"path": "a.py"}])
    index._collection = None  # like a new process
    assert get_collection().count() == 1


def test_temp_index_does_not_point_at_the_real_folders(temp_index):
    assert not index.CHROMA_DIR.startswith("/data")
    assert index.TARGET_DIR == temp_index


# --- reindex_file: a new file ---


def test_reindex_adds_the_chunks_of_a_new_file(temp_index):
    count = reindex_file(write(temp_index, "calc.py", CALC))
    assert count == 4  # module header, class, two methods
    assert get_collection().count() == 4
    assert names_of("calc.py") == ["<module>", "Calculator", "Calculator.add", "Calculator.subtract"]


def test_stored_paths_are_relative_with_forward_slashes(temp_index):
    reindex_file(write(temp_index, "pkg/mod.py", "def f():\n    pass\n"))
    assert names_of("pkg/mod.py") == ["f"]


def test_reindex_of_an_empty_file_writes_nothing(temp_index):
    before = index.INDEX_VERSION
    assert reindex_file(write(temp_index, "empty.py", "")) == 0
    assert get_collection().count() == 0
    assert index.INDEX_VERSION == before


def test_identical_functions_in_one_file_do_not_crash(temp_index):
    text = "def a():\n    pass\n\n\ndef a():\n    pass\n"
    assert reindex_file(write(temp_index, "dup.py", text)) == 1


# --- reindex_file: a changed file ---


def test_editing_one_function_replaces_only_its_chunk(temp_index):
    path = write(temp_index, "m.py", "import os\n\n\ndef a():\n    return 1\n\n\ndef b():\n    return 2\n")
    reindex_file(path)
    before = ids_of("m.py")
    write(temp_index, "m.py", "import os\n\n\ndef a():\n    return 1\n\n\ndef b():\n    return 22\n")
    assert reindex_file(path) == 3
    after = ids_of("m.py")
    assert len(before - after) == 1
    assert len(after - before) == 1
    assert len(before & after) == 2  # the module header and a() are untouched


def test_reindexing_an_unchanged_file_writes_nothing(temp_index):
    path = write(temp_index, "calc.py", CALC)
    reindex_file(path)
    ids, version = ids_of("calc.py"), index.INDEX_VERSION
    for _ in range(5):
        reindex_file(path)
    assert ids_of("calc.py") == ids
    assert index.INDEX_VERSION == version
    assert get_collection().count() == 4


def test_a_function_removed_from_the_file_leaves_the_index(temp_index):
    path = write(temp_index, "m.py", "def a():\n    return 1\n\n\ndef b():\n    return 2\n")
    reindex_file(path)
    write(temp_index, "m.py", "def a():\n    return 1\n")
    reindex_file(path)
    assert names_of("m.py") == ["a"]


def test_editing_one_file_leaves_other_files_alone(temp_index):
    a = write(temp_index, "a.py", "def a():\n    return 1\n")
    b = write(temp_index, "b.py", "def b():\n    return 1\n")
    reindex_file(a)
    reindex_file(b)
    b_ids = ids_of("b.py")
    write(temp_index, "a.py", "def a():\n    return 2\n")
    reindex_file(a)
    assert ids_of("b.py") == b_ids


# --- reindex_file: deleted, skipped, binary ---


def test_deleting_a_file_removes_its_chunks(temp_index):
    helpers = write(temp_index, "helpers.py", "def one():\n    pass\n\n\ndef two():\n    pass\n")
    other = write(temp_index, "other.py", "def keep():\n    pass\n")
    reindex_file(helpers)
    reindex_file(other)
    os.remove(helpers)
    assert reindex_file(helpers) == 0
    assert ids_of("helpers.py") == set()
    assert names_of("other.py") == ["keep"]


def test_skipped_paths_are_never_indexed(temp_index):
    for name in ["__pycache__/x.py", "core.py.ioc.tmp", ".hidden.py", "node_modules/y.js"]:
        assert reindex_file(write(temp_index, name, "def f():\n    pass\n")) == 0
    assert get_collection().count() == 0


def test_a_text_file_that_becomes_binary_loses_its_chunks(temp_index):
    path = write(temp_index, "a.py", "def f():\n    pass\n")
    reindex_file(path)
    assert get_collection().count() == 1
    with open(path, "wb") as f:
        f.write(b"\x00\x01\x02")
    assert reindex_file(path) == 0
    assert get_collection().count() == 0


def test_binary_files_have_no_chunks(temp_index):
    path = os.path.join(temp_index, "logo.png")
    with open(path, "wb") as f:
        f.write(b"\x89PNG\x00\x00")
    assert reindex_file(path) == 0
    assert get_collection().count() == 0


def test_a_path_that_never_existed_is_ignored(temp_index):
    before = index.INDEX_VERSION
    assert reindex_file(os.path.join(temp_index, "ghost.py")) == 0
    assert index.INDEX_VERSION == before


def test_a_path_outside_the_target_project_is_ignored(temp_index, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("def f():\n    pass\n")
    assert reindex_file(str(outside)) == 0
    assert get_collection().count() == 0


# --- list_files ---


def test_list_files_returns_sorted_absolute_paths_without_junk(tmp_path):
    for name in ["main.py", "calculator/core.py", ".git/config", "venv/lib/site.py",
                 "calculator/__pycache__/core.pyc", "calculator/core.py.ioc.tmp", ".env", "docs/build.md"]:
        write(str(tmp_path), name, "x")
    found = list_files(str(tmp_path))
    assert [os.path.relpath(p, tmp_path) for p in found] == ["calculator/core.py", "docs/build.md", "main.py"]
    assert all(os.path.isabs(p) for p in found)


def test_list_files_of_an_empty_folder(tmp_path):
    assert list_files(str(tmp_path)) == []


def test_list_files_on_the_real_target(real_target):
    found = [os.path.relpath(p, real_target) for p in list_files(real_target)]
    assert "calculator/core.py" in found
    assert "main.py" in found


# --- index_all ---


def test_index_all_indexes_every_file_and_returns_the_count(temp_index):
    write(temp_index, "a.py", "def a():\n    pass\n")
    write(temp_index, "b.py", "def b():\n    pass\n")
    write(temp_index, "notes.md", "# Title\ntext\n")
    assert index_all() == 3
    assert names_of("notes.md") == ["Title"]


def test_second_index_all_writes_nothing(temp_index):
    write(temp_index, "calc.py", CALC)
    index_all()
    version = index.INDEX_VERSION
    assert index_all() == 4
    assert index.INDEX_VERSION == version


def test_index_all_picks_up_edits_made_while_the_server_was_down(temp_index):
    write(temp_index, "m.py", "def a():\n    return 1\n\n\ndef b():\n    return 2\n")
    write(temp_index, "other.py", "def o():\n    pass\n")
    index_all()
    before, other = ids_of("m.py"), ids_of("other.py")
    write(temp_index, "m.py", "def a():\n    return 1\n\n\ndef b():\n    return 3\n")
    index_all()
    assert len(ids_of("m.py") - before) == 1
    assert ids_of("other.py") == other


def test_index_all_removes_files_deleted_while_the_server_was_down(temp_index):
    gone = write(temp_index, "gone.py", "def g():\n    pass\n")
    write(temp_index, "kept.py", "def k():\n    pass\n")
    index_all()
    os.remove(gone)
    assert index_all() == 1
    assert names_of("gone.py") == []


def test_index_all_never_indexes_skipped_files(temp_index):
    write(temp_index, "__pycache__/x.py", "def x():\n    pass\n")
    write(temp_index, ".hidden.py", "def h():\n    pass\n")
    write(temp_index, "main.py", "def m():\n    pass\n")
    assert index_all() == 1


def test_index_all_on_the_real_target_finds_the_four_methods(temp_index, real_target):
    shutil.copytree(real_target, temp_index, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    index_all()
    methods = [n for n in names_of("calculator/core.py") if n.startswith("Calculator.")]
    assert methods == ["Calculator.add", "Calculator.divide", "Calculator.multiply", "Calculator.subtract"]


# --- the console command ---


def test_console_command_prints_a_summary(temp_index, monkeypatch, capsys):
    write(temp_index, "a.py", "def a():\n    pass\n")
    write(temp_index, "b.py", "def b():\n    pass\n\n\ndef c():\n    pass\n")
    monkeypatch.setattr(sys, "argv", ["p1.index", temp_index])
    main()
    assert capsys.readouterr().out == "indexed 3 chunks from 2 files\n"


def test_moved_chunks_keep_their_ids_but_get_new_line_numbers(temp_index):
    path = write(temp_index, "m.py", "def a():\n    return 1\n")
    reindex_file(path)
    before = ids_of("m.py")
    write(temp_index, "m.py", "import os\n\n\ndef a():\n    return 1\n")  # a() moved down
    reindex_file(path)
    found = get_collection().get(where={"name": "a"}, include=["metadatas"])
    assert [m["start_line"] for m in found["metadatas"]] == [4]
    assert before <= ids_of("m.py")


def test_moved_chunks_do_not_change_the_index_version(temp_index):
    path = write(temp_index, "m.py", "def a():\n    return 1\n")
    reindex_file(path)
    version = index.INDEX_VERSION
    write(temp_index, "m.py", "\n\ndef a():\n    return 1\n")  # a() moved down, nothing else changed
    reindex_file(path)
    assert index.INDEX_VERSION == version
