"""A unified diff of a proposed file against what is on disk. Nothing is written."""
import difflib


class DiffService:
    def unified(self, path, old, new):
        """One unified diff. old and new are the full file texts ("" if the file is new)."""
        return "".join(difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a/" + path,
            tofile="b/" + path,
        ))


diff_service = DiffService()
