import time


def ids_by_symbol(ctx, path):
    return {m["symbol"]: (cid, m["hash"]) for cid, m in ctx.store.file_chunks(path).items()}


def test_full_sync_indexes_demo(ctx):
    stats = ctx.indexer.full_sync()
    assert stats["files"] >= 7 and stats["chunks"] == ctx.store.count() > 20
    syms = {m["symbol"] for _, m in ctx.store.all_metadata()}
    assert {"NoteService.search", "Storage.add", "greet", "validate"} <= syms
    again = ctx.indexer.full_sync()
    assert again["added"] == again["updated"] == again["removed"] == 0


def test_modify_touches_only_that_files_changed_chunks(ctx, target):
    ctx.indexer.full_sync()
    before_service = ids_by_symbol(ctx, "notes/service.py")
    before_storage = ids_by_symbol(ctx, "notes/storage.py")
    p = target / "notes/service.py"
    p.write_text(p.read_text().replace("term = (term or \"\").lower()", "term = (term or \"\").strip().lower()"))
    stats = ctx.indexer.index_file("notes/service.py")
    assert stats["updated"] == 1 and stats["added"] == 0 and stats["removed"] == 0
    after = ids_by_symbol(ctx, "notes/service.py")
    changed = [s for s in after if after[s][1] != before_service[s][1]]
    assert changed == ["NoteService.search"]
    assert ids_by_symbol(ctx, "notes/storage.py") == before_storage


def test_shifted_lines_are_metadata_only(ctx, target):
    ctx.indexer.full_sync()
    calls = []
    orig = ctx.embedder.embed
    ctx.embedder.embed = lambda texts: calls.append(len(texts)) or orig(texts)
    p = target / "main.py"
    p.write_text(p.read_text().replace('"""Entry point of the notes demo application."""',
                                       '"""Entry point of the notes demo application.\n\nMore docs.\n"""'))
    stats = ctx.indexer.index_file("main.py")
    assert calls == [1]                       # only the module header got re-embedded
    assert stats["moved"] >= 3


def test_delete_removes_chunks(ctx, target):
    ctx.indexer.full_sync()
    assert ctx.store.file_chunks("notes/cli.py")
    (target / "notes/cli.py").unlink()
    ctx.indexer.handle_path(target / "notes/cli.py")
    assert ctx.store.file_chunks("notes/cli.py") == {}
    import shutil
    shutil.rmtree(target / "tests")
    ctx.indexer.handle_path(target / "tests")
    assert not any(p.startswith("tests/") for p in ctx.store.all_paths())


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_watcher_create_modify_delete(ctx, target):
    ctx.indexer.full_sync()
    ctx.watcher.start()
    new = target / "notes/extra.py"
    new.write_text("def hello():\n    return 'hi'\n")
    assert wait_for(lambda: any(m["symbol"] == "hello" for m in ctx.store.file_chunks("notes/extra.py").values()))
    new.write_text("def hello():\n    return 'hi'\n\n\ndef bye():\n    return 'bye'\n")
    assert wait_for(lambda: len(ctx.store.file_chunks("notes/extra.py")) == 2)
    new.unlink()
    assert wait_for(lambda: ctx.store.file_chunks("notes/extra.py") == {})
    types = [e["type"] for e in ctx.events.recent(50)]
    assert "deleted" in types


def test_watcher_ignores_its_own_store(ctx, target, tmp_path):
    # store inside the target must still never be indexed
    from ioc_index.app import build_context
    from ioc_index.config import Settings
    s = Settings.from_env(target, chroma_path=target / ".chroma", embedder="fake", watch_mode="polling",
                          poll_interval=0.2, debounce=0.1)
    c = build_context(s)
    c.indexer.full_sync()
    assert not any(p.startswith(".chroma") for p in c.store.all_paths())
    s2 = Settings.from_env(target, chroma_path=target / "store", embedder="fake")
    c2 = build_context(s2)
    c2.indexer.full_sync()
    assert not any(p.startswith("store/") for p in c2.store.all_paths())
