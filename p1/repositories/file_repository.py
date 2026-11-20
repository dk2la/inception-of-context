"""The files of the Target Project on disk: which ones count, and how to read them."""
import os

from p1.config.settings import settings


class FileRepository:
    def __init__(self, settings):
        self.settings = settings

    def is_skipped(self, rel_path):
        """True if a path (relative to the Target Project) must never be indexed."""
        parts = rel_path.replace("\\", "/").split("/")
        for part in parts:
            if part in ("", "."):
                continue
            if part in self.settings.SKIPPED_NAMES or part.startswith("."):
                return True
        return parts[-1].endswith(".ioc.tmp")

    def read_text(self, path):
        """Return the file's text, or None if it is missing, a directory, binary or not UTF-8."""
        try:
            with open(path, "rb") as f:
                data = f.read()
        except (FileNotFoundError, IsADirectoryError):
            return None
        if b"\x00" in data[:8192]:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def relative_path(self, full_path):
        """A path the way the Index stores it: relative to the Target Project, with forward slashes."""
        return os.path.relpath(full_path, self.settings.TARGET_DIR).replace(os.sep, "/")

    def full_path(self, rel_path):
        """The real path of a path relative to the Target Project."""
        return os.path.join(self.settings.TARGET_DIR, rel_path)

    def list_files(self, root):
        """Sorted absolute paths of every file under root that we should index."""
        found = []
        for folder, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if not self.is_skipped(d)]  # do not even walk into skipped folders
            for name in names:
                path = os.path.join(folder, name)
                if not self.is_skipped(os.path.relpath(path, root)):
                    found.append(os.path.abspath(path))
        return sorted(found)


file_repository = FileRepository(settings)
