"""Cut a file into Chunks: one logical block each (a function, a class, a YAML key, ...).

Pure methods: text in, Chunks out. Nothing here reads or writes anything.
"""
import ast
import os
import re

from p1.models.chunk import chunk_factory

DEFINITION = re.compile(r"^\s*(?:async\s+def|def|class|function)\s+([A-Za-z_]\w*)")


class ChunkerService:
    """Cut a file into Chunks. chunk_file is the one door in; the other methods are its helpers."""

    def __init__(self, chunk_factory):
        self.chunk_factory = chunk_factory

    def cut(self, lines, start, end):
        """Return lines start..end (1-based, inclusive) as one string."""
        return "\n".join(lines[start - 1:end])

    def first_line(self, node):
        """The first line of a function or class: its topmost decorator, or the def/class line."""
        return min([node.lineno] + [d.lineno for d in node.decorator_list])

    def section(self, path, lines, start, end, name, kind):
        """Make a Chunk from lines start..end, leaving out blank lines at both edges."""
        while start < end and not lines[start - 1].strip():
            start += 1
        while end > start and not lines[end - 1].strip():
            end -= 1
        return self.chunk_factory.make_chunk(path, start, end, name, kind, self.cut(lines, start, end))

    def split_at(self, path, lines, starts, kind, keep_header=True):
        """Cut lines into one Chunk per (line_number, name) in starts, each running to the next one.

        The lines before the first start become a "<module>" Chunk, unless keep_header is False.
        """
        chunks = []
        first = starts[0][0] if starts else len(lines) + 1
        if keep_header and any(line.strip() for line in lines[: first - 1]):
            chunks.append(self.section(path, lines, 1, first - 1, "<module>", "module"))
        for i, (start, name) in enumerate(starts):
            end = starts[i + 1][0] - 1 if i + 1 < len(starts) else len(lines)
            chunks.append(self.section(path, lines, start, end, name, kind))
        return chunks

    def chunk_by_regex(self, path, text):
        """Chunks for any text: one per line that looks like a definition."""
        lines = text.splitlines()
        starts = []
        for number, line in enumerate(lines, start=1):
            match = DEFINITION.match(line)
            if match:
                starts.append((number, match.group(1)))
        return self.split_at(path, lines, starts, "definition")

    def chunk_yaml(self, path, text):
        """One Chunk per top-level key (a line that is not indented and looks like "name: ...")."""
        lines = text.splitlines()
        starts = []
        for number, line in enumerate(lines, start=1):
            if line[:1] not in ("", " ", "\t", "#", "-") and ":" in line:
                starts.append((number, line.split(":")[0].strip()))
        return self.split_at(path, lines, starts, "yaml_key", keep_header=not starts)

    def chunk_markdown(self, path, text):
        """One Chunk per heading. A "#" inside a code fence is a comment, not a heading."""
        lines = text.splitlines()
        starts = []
        in_code = False
        for number, line in enumerate(lines, start=1):
            if line.startswith("```"):
                in_code = not in_code
            elif not in_code and line.startswith("#"):
                starts.append((number, line.lstrip("#").strip()))
        return self.split_at(path, lines, starts, "heading")

    def chunk_python(self, path, text):
        """Chunks for every top-level function and class, every method, and the module header.

        Python that does not parse is chunked with regular expressions instead.
        """
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return self.chunk_by_regex(path, text)
        lines = text.splitlines()
        chunks = []
        covered = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                kind = "function"
            elif isinstance(node, ast.AsyncFunctionDef):
                kind = "async_function"
            elif isinstance(node, ast.ClassDef):
                kind = "class"
            else:
                continue
            start, end = self.first_line(node), node.end_lineno
            covered.update(range(start, end + 1))
            chunks.append(self.chunk_factory.make_chunk(path, start, end, node.name, kind, self.cut(lines, start, end)))
            if kind == "class":
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        start, end = self.first_line(item), item.end_lineno
                        name = node.name + "." + item.name
                        chunks.append(self.chunk_factory.make_chunk(
                            path, start, end, name, "method", self.cut(lines, start, end)))

        header = [n for n in range(1, len(lines) + 1) if n not in covered]
        while header and not lines[header[0] - 1].strip():
            header.pop(0)
        while header and not lines[header[-1] - 1].strip():
            header.pop()
        if header:
            header_text = "\n".join(lines[n - 1] for n in header)
            chunks.insert(0, self.chunk_factory.make_chunk(
                path, header[0], header[-1], "<module>", "module", header_text))
        return chunks

    def chunk_file(self, path, text):
        """The one door into the chunker: pick the right chunker for the file's extension."""
        extension = os.path.splitext(path)[1].lower()
        if extension == ".py":
            return self.chunk_python(path, text)
        if extension in (".yml", ".yaml"):
            return self.chunk_yaml(path, text)
        if extension == ".md":
            return self.chunk_markdown(path, text)
        return self.chunk_by_regex(path, text)


chunker_service = ChunkerService(chunk_factory)
