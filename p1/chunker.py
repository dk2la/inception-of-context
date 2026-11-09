"""Cut a file into Chunks: one logical block each (a function, a class, a YAML key, ...)."""
import ast
import hashlib
import os
import re

# A line that starts a definition in almost any language: def, async def, class, function.
DEFINITION = re.compile(r"^\s*(?:async\s+def|def|class|function)\s+([A-Za-z_]\w*)")


def make_chunk(path, start_line, end_line, name, kind, text):
    """Return one Chunk as a dict with these keys:

    path        file path relative to the Target Project, with forward slashes
    start_line  first line of the Chunk (1-based, inclusive)
    end_line    last line of the Chunk (1-based, inclusive)
    name        symbol name; methods are "Class.method", the module header is "<module>"
    kind        function, async_function, class, method, module, yaml_key, heading or definition
    text        the exact source text of the Chunk
    hash        SHA-256 (hex) of text
    """
    return {
        "path": path,
        "start_line": start_line,
        "end_line": end_line,
        "name": name,
        "kind": kind,
        "text": text,
        "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def cut(lines, start, end):
    """Return lines start..end (1-based, inclusive) as one string."""
    return "\n".join(lines[start - 1 : end])


def start_line(node):
    """The first line of a function or class: its topmost decorator, or the def/class line."""
    return min([node.lineno] + [d.lineno for d in node.decorator_list])


def section(path, lines, start, end, name, kind):
    """Make a Chunk from lines start..end, leaving out blank lines at both edges."""
    while start < end and not lines[start - 1].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return make_chunk(path, start, end, name, kind, cut(lines, start, end))


def split_at(path, lines, starts, kind, keep_header=True):
    """Cut lines into one Chunk per (line_number, name) in starts, each running to the next one.

    The lines before the first start become a "<module>" Chunk, unless keep_header is False.
    """
    chunks = []
    first = starts[0][0] if starts else len(lines) + 1
    if keep_header and any(line.strip() for line in lines[: first - 1]):
        chunks.append(section(path, lines, 1, first - 1, "<module>", "module"))
    for i, (start, name) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else len(lines)
        chunks.append(section(path, lines, start, end, name, kind))
    return chunks


def chunk_by_regex(path, text):
    """Chunks for any text: one per line that looks like a definition."""
    lines = text.splitlines()
    starts = []
    for number, line in enumerate(lines, start=1):
        match = DEFINITION.match(line)
        if match:
            starts.append((number, match.group(1)))
    return split_at(path, lines, starts, "definition")


def chunk_yaml(path, text):
    """One Chunk per top-level key (a line that is not indented and looks like "name: ...")."""
    lines = text.splitlines()
    starts = []
    for number, line in enumerate(lines, start=1):
        if line[:1] not in ("", " ", "\t", "#", "-") and ":" in line:
            starts.append((number, line.split(":")[0].strip()))
    # Comments before the first key are left out, but a file without keys is kept whole.
    return split_at(path, lines, starts, "yaml_key", keep_header=not starts)


def chunk_markdown(path, text):
    """One Chunk per heading. A "#" inside a code fence is a comment, not a heading."""
    lines = text.splitlines()
    starts = []
    in_code = False
    for number, line in enumerate(lines, start=1):
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and line.startswith("#"):
            starts.append((number, line.lstrip("#").strip()))
    return split_at(path, lines, starts, "heading")


def chunk_file(path, text):
    """The one door into the chunker: pick the right chunker for the file's extension."""
    extension = os.path.splitext(path)[1].lower()
    if extension == ".py":
        return chunk_python(path, text)
    if extension in (".yml", ".yaml"):
        return chunk_yaml(path, text)
    if extension == ".md":
        return chunk_markdown(path, text)
    return chunk_by_regex(path, text)


def chunk_python(path, text):
    """Chunks for every top-level function and class, every method, and the module header.

    Python that does not parse is chunked with regular expressions instead.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return chunk_by_regex(path, text)
    lines = text.splitlines()
    chunks = []
    covered = set()  # lines that belong to a function or a class
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            kind = "function"
        elif isinstance(node, ast.AsyncFunctionDef):
            kind = "async_function"
        elif isinstance(node, ast.ClassDef):
            kind = "class"
        else:
            continue
        start, end = start_line(node), node.end_lineno
        covered.update(range(start, end + 1))
        chunks.append(make_chunk(path, start, end, node.name, kind, cut(lines, start, end)))
        if kind == "class":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start, end = start_line(item), item.end_lineno
                    name = node.name + "." + item.name
                    chunks.append(make_chunk(path, start, end, name, "method", cut(lines, start, end)))

    # The module header: every line that is not inside a function or a class.
    header = [n for n in range(1, len(lines) + 1) if n not in covered]
    while header and not lines[header[0] - 1].strip():
        header.pop(0)
    while header and not lines[header[-1] - 1].strip():
        header.pop()
    if header:
        header_text = "\n".join(lines[n - 1] for n in header)
        chunks.insert(0, make_chunk(path, header[0], header[-1], "<module>", "module", header_text))
    return chunks
