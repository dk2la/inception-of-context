"""The Target Project files a Patch writes: the Snapshot before, the write itself, and the Rollback."""
import os
import shutil

from p1.config import settings
from p1.repositories.file_repository import full_path


def take_snapshot(paths):
    """Remember the exact bytes of each file before a Patch touches it (None if the file does not exist)."""
    snapshot = {}
    for rel_path in paths:
        if os.path.isfile(full_path(rel_path)):
            with open(full_path(rel_path), "rb") as f:
                snapshot[rel_path] = f.read()
        else:
            snapshot[rel_path] = None
    return snapshot


def restore_snapshot(snapshot):
    """Rollback: put every file back as the Snapshot saw it, and delete the files (and folders) that did not exist."""
    for rel_path, data in snapshot.items():
        path = full_path(rel_path)
        if data is not None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        elif os.path.exists(path):
            os.remove(path)
            # The folders made for a new file go too, as long as nothing else is in them.
            folder = os.path.dirname(path)
            while os.path.normpath(folder) != os.path.normpath(settings.TARGET_DIR) and not os.listdir(folder):
                os.rmdir(folder)
                folder = os.path.dirname(folder)


def apply_patch(patch):
    """Write the Patch to disk and return the paths it touched.

    New contents go to <file>.ioc.tmp first and are swapped in with os.replace only when all of them
    are written, so a file is never left half written. Deletes come last.
    """
    paths = []
    try:
        for entry in patch["files"]:
            if entry["op"] != "delete":
                path = full_path(entry["path"])
                os.makedirs(os.path.dirname(path), exist_ok=True)
                paths.append(path)
                with open(path + ".ioc.tmp", "w", encoding="utf-8") as f:
                    f.write(entry["content"])
                if os.path.exists(path):
                    shutil.copymode(path, path + ".ioc.tmp")  # os.replace must not change the file's mode
        for path in paths:
            os.replace(path + ".ioc.tmp", path)
    except Exception:
        for path in paths:
            if os.path.exists(path + ".ioc.tmp"):
                os.remove(path + ".ioc.tmp")
        raise
    for entry in patch["files"]:
        if entry["op"] == "delete":
            os.remove(full_path(entry["path"]))
    return [entry["path"] for entry in patch["files"]]
