"""The files of the Target Project on disk: which ones count, and how to read them."""
import os

from p1.config.settings import settings


class FileRepository:
    def __init__(self, settings):
        # debug: settings is the Settings object. TARGET_DIR == "/workspace" inside Docker.
        # SKIPPED_NAMES == {"node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__"}
        # Nothing is read from disk here.
        self.settings = settings

    def is_skipped(self, rel_path):
        """True if a path (relative to the Target Project) must never be indexed."""
        # debug: one path part is enough to skip the whole path.
        # is_skipped("calculator/core.py") == False
        # is_skipped("node_modules/pkg/index.js") == True   # part is in SKIPPED_NAMES
        # is_skipped(".env") == True                        # part starts with "."
        # is_skipped(".pytest_cache/README.md") == True
        # is_skipped("calculator/core.py.ioc.tmp") == True  # Patch Loop temp file
        # is_skipped("./main.py") == False                  # "." is ignored
        parts = rel_path.replace("\\", "/").split("/")
        for part in parts:
            if part in ("", "."):
                continue
            if part in self.settings.SKIPPED_NAMES or part.startswith("."):
                return True
        return parts[-1].endswith(".ioc.tmp")

    def read_text(self, path):
        """Return the file's text, or None if it is missing, a directory, binary or not UTF-8."""
        # debug: path == "/workspace/calculator/core.py"
        # data is raw bytes. A NUL in the first 8192 bytes means binary, return == None.
        # return == "class Calculator:\n    \"\"\"A calculator that works with floats.\"\"\"\n    ..."
        # missing file, a directory, or non-UTF-8: return == None
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
        # debug: full_path == "/workspace/calculator/core.py"
        # return == "calculator/core.py"  # the path stored on a Chunk
        return os.path.relpath(full_path, self.settings.TARGET_DIR).replace(os.sep, "/")

    def full_path(self, rel_path):
        """The real path of a path relative to the Target Project."""
        # debug: rel_path == "calculator/core.py"
        # return == "/workspace/calculator/core.py"
        return os.path.join(self.settings.TARGET_DIR, rel_path)

    def list_files(self, root):
        """Sorted absolute paths of every file under root that we should index."""
        # debug: root == "/workspace"
        # dirs that is_skipped drops are not walked: ".git", "__pycache__", "node_modules", ...
        # return == [
        #     "/workspace/calculator/__init__.py",
        #     "/workspace/calculator/core.py",
        #     "/workspace/main.py",
        #     ...
        # ]  # absolute, sorted. "*.ioc.tmp" and hidden files are absent.
        found = []
        for folder, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if not self.is_skipped(d)]  # do not even walk into skipped folders
            for name in names:
                path = os.path.join(folder, name)
                if not self.is_skipped(os.path.relpath(path, root)):
                    found.append(os.path.abspath(path))
        return sorted(found)


file_repository = FileRepository(settings)
