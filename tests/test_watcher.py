import os
import sys
import time

import pytest

from p1 import index


# --- the event list ---


def test_add_event_appends_an_event_with_the_time_it_happened(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    before = time.time()
    index.add_event("indexed", "a.py", 3)
    assert len(index.EVENTS) == 1
    event = index.EVENTS[0]
    assert (event["type"], event["path"], event["chunks"]) == ("indexed", "a.py", 3)
    assert before <= event["time"] <= time.time()


def test_events_keep_the_order_they_were_added_in(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    index.add_event("indexed", "a.py", 1)
    index.add_event("deleted", "a.py", 0)
    assert [(e["type"], e["chunks"]) for e in index.EVENTS] == [("indexed", 1), ("deleted", 0)]


def test_add_event_refuses_an_unknown_type(monkeypatch):
    monkeypatch.setattr(index, "EVENTS", [])
    with pytest.raises(ValueError):
        index.add_event("changed", "a.py", 1)
    assert index.EVENTS == []


# --- watch(): slower tests that use the real filesystem and wait for its events ---


def wait_until(condition, seconds=5):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.1)
    return False


def write(target, name, text):
    path = os.path.join(target, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def happened(type, path):
    """True once the Watcher has recorded this kind of event for this path."""
    return any(e["type"] == type and e["path"] == path for e in index.EVENTS)


def chunks_of(path):
    return index.get_collection().get(where={"path": path})["ids"]


def test_watcher_indexes_a_new_file(temp_index, monkeypatch):
    """Slower test: real filesystem events."""
    monkeypatch.setattr(index, "EVENTS", [])
    observer = index.watch(temp_index)
    try:
        write(temp_index, "a.py", "def a():\n    return 1\n")
        assert wait_until(lambda: happened("indexed", "a.py"))
        assert len(chunks_of("a.py")) > 0
    finally:
        observer.stop()
        observer.join()


def test_watcher_reindexes_an_edited_file(temp_index, monkeypatch):
    """Slower test: real filesystem events."""
    monkeypatch.setattr(index, "EVENTS", [])
    write(temp_index, "a.py", "def a():\n    return 1\n")
    index.index_all()
    observer = index.watch(temp_index)
    try:
        write(temp_index, "a.py", "def a():\n    return 1\n\n\ndef b():\n    return 2\n")
        assert wait_until(lambda: any(e["path"] == "a.py" and e["chunks"] == 2 for e in index.EVENTS))
        assert len(chunks_of("a.py")) == 2
    finally:
        observer.stop()
        observer.join()


def test_watcher_removes_the_chunks_of_a_deleted_file(temp_index, monkeypatch):
    """Slower test: real filesystem events."""
    monkeypatch.setattr(index, "EVENTS", [])
    path = write(temp_index, "a.py", "def a():\n    return 1\n")
    index.index_all()
    observer = index.watch(temp_index)
    try:
        os.remove(path)
        assert wait_until(lambda: happened("deleted", "a.py"))
        assert chunks_of("a.py") == []
        assert all(e["chunks"] == 0 for e in index.EVENTS if e["type"] == "deleted")
    finally:
        observer.stop()
        observer.join()


def test_watcher_ignores_temporary_hidden_and_skipped_files(temp_index, monkeypatch):
    """Slower test: real filesystem events."""
    monkeypatch.setattr(index, "EVENTS", [])
    observer = index.watch(temp_index)
    try:
        write(temp_index, "b.py.ioc.tmp", "def b():\n    pass\n")
        write(temp_index, ".swap.py", "def s():\n    pass\n")
        write(temp_index, "__pycache__/c.py", "def c():\n    pass\n")
        write(temp_index, "marker.py", "def m():\n    return 1\n")  # written last, so it is the proof we waited long enough
        assert wait_until(lambda: happened("indexed", "marker.py"))
        time.sleep(1)
        assert [e["path"] for e in index.EVENTS] == ["marker.py"] * len(index.EVENTS)
        assert index.get_collection().count() == 1
    finally:
        observer.stop()
        observer.join()


def test_watcher_watches_new_subfolders_and_reports_only_files(temp_index, monkeypatch):
    """Slower test: real filesystem events."""
    monkeypatch.setattr(index, "EVENTS", [])
    observer = index.watch(temp_index)
    try:
        os.makedirs(os.path.join(temp_index, "sub"))
        write(temp_index, "sub/a.py", "def a():\n    return 1\n")  # files in a new subfolder are watched too
        assert wait_until(lambda: happened("indexed", "sub/a.py"))
        assert all(e["path"] == "sub/a.py" for e in index.EVENTS)
    finally:
        observer.stop()
        observer.join()


def test_a_failing_event_does_not_stop_the_watcher(temp_index, monkeypatch, capsys):
    """Slower test: real filesystem events."""
    monkeypatch.setattr(index, "EVENTS", [])
    real_reindex = index.reindex_file

    def broken_for_bad_py(full_path):
        if full_path.endswith("bad.py"):
            raise RuntimeError("boom")
        return real_reindex(full_path)

    monkeypatch.setattr(index, "reindex_file", broken_for_bad_py)
    observer = index.watch(temp_index)
    try:
        write(temp_index, "bad.py", "def bad():\n    pass\n")
        write(temp_index, "good.py", "def good():\n    return 1\n")
        assert wait_until(lambda: happened("indexed", "good.py"))
        assert not happened("indexed", "bad.py")
        assert "bad.py" in capsys.readouterr().out
    finally:
        observer.stop()
        observer.join()


def test_watcher_ignores_the_opened_events_that_reading_a_file_causes_on_linux(temp_index, monkeypatch):
    from watchdog.events import FileClosedNoWriteEvent, FileOpenedEvent

    monkeypatch.setattr(index, "EVENTS", [])
    path = write(temp_index, "a.py", "def a():\n    return 1\n")
    for event in [FileOpenedEvent(path), FileClosedNoWriteEvent(path)]:
        index.Handler().on_any_event(event)
    assert index.EVENTS == []


def test_renaming_a_file_removes_the_old_path_and_indexes_the_new_one(temp_index, monkeypatch):
    """Slower test: real filesystem events."""
    monkeypatch.setattr(index, "EVENTS", [])
    observer = index.watch(temp_index)
    try:
        write(temp_index, "old.py", "def a():\n    return 1\n")
        assert wait_until(lambda: happened("indexed", "old.py"))
        os.rename(os.path.join(temp_index, "old.py"), os.path.join(temp_index, "new.py"))
        assert wait_until(lambda: happened("deleted", "old.py") and happened("indexed", "new.py"))
        assert chunks_of("old.py") == []
        assert len(chunks_of("new.py")) > 0
    finally:
        observer.stop()
        observer.join()


def test_replacing_a_file_through_an_ioc_tmp_file_reindexes_the_real_file_only(temp_index, monkeypatch):
    """Slower test: real filesystem events. This is how the Patch Loop writes files."""
    monkeypatch.setattr(index, "EVENTS", [])
    observer = index.watch(temp_index)
    try:
        write(temp_index, "x.py", "def x():\n    return 1\n")
        assert wait_until(lambda: happened("indexed", "x.py"))
        write(temp_index, "x.py.ioc.tmp", "def x():\n    return 1\n\n\ndef y():\n    return 2\n")
        os.replace(os.path.join(temp_index, "x.py.ioc.tmp"), os.path.join(temp_index, "x.py"))
        assert wait_until(lambda: any(e["path"] == "x.py" and e["chunks"] == 2 for e in index.EVENTS))
        assert not any("ioc.tmp" in e["path"] for e in index.EVENTS)
    finally:
        observer.stop()
        observer.join()


# --- WATCH_POLLING ---


def test_watch_polling_uses_the_polling_observer_and_still_indexes_files(temp_index, monkeypatch, capsys):
    """Slower test: polling looks at the folder about once a second."""
    from watchdog.observers.polling import PollingObserver

    monkeypatch.setattr(index, "EVENTS", [])
    monkeypatch.setenv("WATCH_POLLING", "1")
    observer = index.watch(temp_index)
    try:
        assert isinstance(observer, PollingObserver)
        assert "(polling)" in capsys.readouterr().out
        write(temp_index, "a.py", "def a():\n    return 1\n")
        assert wait_until(lambda: happened("indexed", "a.py"), seconds=10)
        assert len(chunks_of("a.py")) > 0
    finally:
        observer.stop()
        observer.join()


@pytest.mark.parametrize("value", [None, "0", "yes"])
def test_without_watch_polling_one_the_normal_observer_is_used(temp_index, monkeypatch, capsys, value):
    from watchdog.observers.polling import PollingObserver

    monkeypatch.delenv("WATCH_POLLING", raising=False)
    if value:
        monkeypatch.setenv("WATCH_POLLING", value)
    observer = index.watch(temp_index)
    try:
        assert not isinstance(observer, PollingObserver)
        assert "(notifications)" in capsys.readouterr().out
    finally:
        observer.stop()
        observer.join()


# --- python -m p1.index --watch ---


def test_console_command_with_watch_prints_each_event_once_and_stops_on_ctrl_c(temp_index, monkeypatch, capsys):
    from types import SimpleNamespace

    write(temp_index, "a.py", "def a():\n    pass\n")
    monkeypatch.setattr(index, "EVENTS", [])
    monkeypatch.setattr(sys, "argv", ["p1.index", temp_index, "--watch"])
    observer = SimpleNamespace(stopped=False, joined=False)
    observer.stop = lambda: setattr(observer, "stopped", True)
    observer.join = lambda: setattr(observer, "joined", True)
    monkeypatch.setattr(index, "watch", lambda root=None: observer)
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:  # the Watcher "does" two things while main() sleeps
            index.add_event("indexed", "a.py", 1)
            index.add_event("deleted", "b.md", 0)
        elif len(sleeps) == 2:  # nothing new: nothing may be printed again
            pass
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", fake_sleep)
    index.main()
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["indexed 1 chunks from 1 files", "indexed a.py (1 chunks)", "deleted b.md (0 chunks)"]
    assert observer.stopped and observer.joined


def test_console_command_without_watch_does_not_start_the_watcher(temp_index, monkeypatch, capsys):
    write(temp_index, "a.py", "def a():\n    pass\n")
    monkeypatch.setattr(sys, "argv", ["p1.index", temp_index])
    monkeypatch.setattr(index, "watch", lambda root=None: pytest.fail("the Watcher must not start"))
    index.main()
    assert capsys.readouterr().out == "indexed 1 chunks from 1 files\n"


def test_console_command_follows_a_symlinked_folder_so_watcher_paths_match(temp_index, tmp_path, monkeypatch):
    """On macOS /tmp is a symlink, and the Watcher reports the real path."""
    link = tmp_path / "link"
    link.symlink_to(temp_index)
    monkeypatch.setattr(sys, "argv", ["p1.index", str(link)])
    index.main()
    assert index.TARGET_DIR == os.path.realpath(temp_index)
