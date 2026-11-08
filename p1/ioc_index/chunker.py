"""Logical chunking: one chunk per function, method, class header or config block.

Python goes through the `ast` module (exact line ranges, decorators included,
methods nested in classes). Anything that does not parse falls back to regex
boundaries; YAML / TOML / INI are split per top-level block, Markdown per
heading. Chunks partition the file: each one runs from its boundary to the
line before the next boundary, so the Files view can show every line.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, asdict


@dataclass
class Chunk:
    path: str
    start_line: int          # 1-based, inclusive
    end_line: int            # 1-based, inclusive (trailing blank lines trimmed)
    kind: str                # module | class | function | method | config | section | block
    symbol: str              # qualified name (NoteService.search), key name, heading...
    name: str                # short name (search)
    signature: str           # first line of the definition, for symbol facts
    text: str
    language: str
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            self.hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)


LANG_BY_SUFFIX = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".rb": "ruby", ".php": "php", ".sh": "shell",
    ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".json": "json", ".md": "markdown", ".markdown": "markdown",
}


def language_of(path: str) -> str:
    lower = path.lower()
    for sfx, lang in LANG_BY_SUFFIX.items():
        if lower.endswith(sfx):
            return lang
    if lower.rsplit("/", 1)[-1] in ("makefile", "dockerfile"):
        return lower.rsplit("/", 1)[-1]
    return "text"


@dataclass
class _Boundary:
    line: int
    kind: str
    symbol: str
    name: str
    signature: str


def chunk_file(path: str, text: str) -> list[Chunk]:
    lang = language_of(path)
    lines = text.splitlines()
    if not lines or not text.strip():
        return []
    bounds: list[_Boundary] | None = None
    if lang == "python":
        bounds = _python_bounds(text, lines)
    if bounds is None:
        if lang in ("yaml", "toml", "ini"):
            bounds = _config_bounds(lines, lang)
        elif lang == "markdown":
            bounds = _markdown_bounds(lines)
        elif lang in ("json", "text", "makefile", "dockerfile"):
            bounds = _paragraph_bounds(lines, lang)
        else:
            bounds = _regex_code_bounds(lines, lang)
    return _materialize(path, lang, lines, bounds)


# --------------------------------------------------------------------------- python (ast)

def _python_bounds(text: str, lines: list[str]) -> list[_Boundary] | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    bounds: list[_Boundary] = [_Boundary(1, "module", "<module>", "<module>", "")]

    def first_line(node: ast.AST) -> int:
        decos = getattr(node, "decorator_list", None) or []
        return min([node.lineno] + [d.lineno for d in decos])

    def sig(node: ast.AST) -> str:
        line = lines[node.lineno - 1].strip()
        return line[:200]

    def visit_body(body: list[ast.stmt], prefix: str, in_class: bool) -> None:
        prev_was_def = False
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{stmt.name}"
                bounds.append(_Boundary(first_line(stmt), "method" if in_class else "function",
                                        qual, stmt.name, sig(stmt)))
                prev_was_def = True
            elif isinstance(stmt, ast.ClassDef):
                qual = f"{prefix}{stmt.name}"
                bounds.append(_Boundary(first_line(stmt), "class", qual, stmt.name, sig(stmt)))
                visit_body(stmt.body, qual + ".", in_class=True)
                prev_was_def = True
            else:
                if prev_was_def:
                    # statements after a definition (e.g. `if __name__ == ...`) open a new block
                    owner = prefix[:-1] if prefix else "<module>"
                    kind = "class" if in_class else "module"
                    bounds.append(_Boundary(stmt.lineno, kind, owner, owner.rsplit(".", 1)[-1], ""))
                prev_was_def = False

    visit_body(tree.body, "", in_class=False)
    return bounds


# --------------------------------------------------------------------------- fallbacks

_CODE_DEF = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:default\s+)?(?:pub(?:\(\w+\))?\s+)?(?:async\s+)?(?:static\s+)?"
    r"(?P<kw>def|class|function|func|fn|interface|struct|impl|trait|enum|type)\s+"
    r"(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_$][\w$]*)"
)
_JS_ARROW = re.compile(r"^(?P<indent>\s*)(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(?[^=]*\)?\s*=>")


def _regex_code_bounds(lines: list[str], lang: str) -> list[_Boundary]:
    bounds = [_Boundary(1, "module", "<module>", "<module>", "")]
    classes: list[tuple[int, str]] = []    # (indent, name) stack, python-ish nesting by indent
    for i, line in enumerate(lines, start=1):
        m = _CODE_DEF.match(line) or _JS_ARROW.match(line)
        if not m:
            continue
        indent = len(m.group("indent").expandtabs(4))
        name = m.group("name")
        kw = m.groupdict().get("kw") or "function"
        while classes and classes[-1][0] >= indent:
            classes.pop()
        prefix = ".".join(n for _, n in classes)
        qual = f"{prefix}.{name}" if prefix else name
        if kw in ("class", "interface", "struct", "impl", "trait", "enum", "type"):
            kind = "class"
            classes.append((indent, name))
        else:
            kind = "method" if prefix else "function"
        # python decorators directly above belong to the definition
        start = i
        while start > 1 and lines[start - 2].strip().startswith("@"):
            start -= 1
        bounds.append(_Boundary(start, kind, qual, name, line.strip()[:200]))
    return bounds


_YAML_KEY = re.compile(r"^(?P<name>[A-Za-z0-9_\"'][^:#]*?)\s*:(?:\s|$)")
_TOML_SECTION = re.compile(r"^\[+(?P<name>[^\]]+)\]+")


def _config_bounds(lines: list[str], lang: str) -> list[_Boundary]:
    bounds = [_Boundary(1, "config", "<header>", "<header>", "")]
    for i, line in enumerate(lines, start=1):
        m = _TOML_SECTION.match(line) if lang in ("toml", "ini") else _YAML_KEY.match(line)
        if m:
            name = m.group("name").strip().strip("\"'")
            start = i
            while start > 1 and lines[start - 2].lstrip().startswith("#"):
                start -= 1      # leading comments document the block below them
            bounds.append(_Boundary(start, "config", name, name, line.strip()[:200]))
    return bounds


def _markdown_bounds(lines: list[str]) -> list[_Boundary]:
    bounds = [_Boundary(1, "section", "<intro>", "<intro>", "")]
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and re.match(r"^#{1,6}\s+\S", line):
            title = line.lstrip("#").strip()
            bounds.append(_Boundary(i, "section", title, title, line.strip()[:200]))
    return bounds


def _paragraph_bounds(lines: list[str], lang: str, soft_limit: int = 60) -> list[_Boundary]:
    """Blank-line separated blocks, merged until a block reaches ~soft_limit lines."""
    bounds = [_Boundary(1, "block", "block 1", "block 1", "")]
    current_start = 1
    for i in range(2, len(lines) + 1):
        if not lines[i - 2].strip() and lines[i - 1].strip() and i - current_start >= soft_limit:
            n = len(bounds) + 1
            bounds.append(_Boundary(i, "block", f"block {n}", f"block {n}", ""))
            current_start = i
    return bounds


# --------------------------------------------------------------------------- materialize

def _materialize(path: str, lang: str, lines: list[str], bounds: list[_Boundary]) -> list[Chunk]:
    # Several boundaries can land on the same line (the default file-header
    # boundary at line 1 and a definition that starts there). The most
    # specific one, i.e. the last declared, wins.
    by_line: dict[int, _Boundary] = {}
    for b in bounds:
        by_line[b.line] = b
    ordered = [by_line[k] for k in sorted(by_line)]
    chunks: list[Chunk] = []
    for idx, b in enumerate(ordered):
        start = b.line
        stop = (ordered[idx + 1].line - 1) if idx + 1 < len(ordered) else len(lines)
        end = stop
        while end >= start and not lines[end - 1].strip():
            end -= 1
        if end < start:
            continue        # empty region (e.g. blank lines before the first def)
        text = "\n".join(lines[start - 1:end])
        chunks.append(Chunk(path=path, start_line=start, end_line=end, kind=b.kind, symbol=b.symbol,
                            name=b.name, signature=b.signature, text=text, language=lang))
    return chunks
