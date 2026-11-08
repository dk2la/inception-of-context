from ioc_index.walker import FileFilter


def test_skips_vendor_hidden_binary_and_store(tmp_path):
    t = tmp_path
    for d in ["node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__", ".hidden", "store", "src"]:
        (t / d).mkdir()
        (t / d / "f.py").write_text("x = 1\n")
    (t / "bin.dat").write_bytes(b"\x00\x01\x02")
    (t / "ok.py").write_text("y = 2\n")
    (t / "ok.py.ioc.tmp").write_text("y = 3\n")
    ff = FileFilter(t, excluded=[t / "store"])
    assert list(ff.walk()) == ["ok.py", "src/f.py"]
    assert ff.is_excluded_path(t / "store" / "chroma.sqlite3")
    assert ff.rel(t / ".." / "outside.py") is None
