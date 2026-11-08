"""What the index knows *for sure*: every symbol, where it is defined, which files exist.

Questions like "is there a function X?" or "what functions are in file Y?"
are answered from here, deterministically, before the model is allowed to
speak. The model cannot hallucinate a symbol it is never asked about.
"""
from __future__ import annotations

import difflib
import re
import threading
from dataclasses import dataclass, asdict

from ioc_index.store import Store

DEF_KINDS = {"function", "method", "class"}


@dataclass
class Symbol:
    name: str
    qualname: str
    kind: str
    path: str
    start_line: int
    end_line: int
    signature: str

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def loc(self) -> str:
        return f"{self.path}:{self.start_line}"


class SymbolIndex:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._lock = threading.Lock()
        self._version = -1
        self.symbols: list[Symbol] = []
        self.paths: set[str] = set()
        self._docs: list[tuple[dict, str]] = []

    def refresh(self) -> None:
        with self._lock:
            if self._version == self.store.version:
                return
            rows = self.store.all_documents()
            syms, paths, docs = [], set(), []
            for _, doc, m in rows:
                paths.add(m["path"])
                docs.append((m, doc))
                if m["kind"] in DEF_KINDS:
                    syms.append(Symbol(m["name"], m["symbol"], m["kind"], m["path"], m["start_line"],
                                       m["end_line"], m.get("signature", "")))
            self.symbols = sorted(syms, key=lambda s: (s.path, s.start_line))
            self.paths, self._docs, self._version = paths, docs, self.store.version

    # -------------------------------------------------------------------- lookups
    def find(self, ident: str) -> list[Symbol]:
        self.refresh()
        ident = ident.strip().strip("`'\"()").removesuffix("()")
        exact = [s for s in self.symbols if ident in (s.name, s.qualname) or s.qualname.endswith("." + ident)]
        if exact:
            return exact
        low = ident.lower()
        return [s for s in self.symbols if low in (s.name.lower(), s.qualname.lower())]

    def similar(self, ident: str, n: int = 3) -> list[str]:
        self.refresh()
        names = sorted({s.qualname for s in self.symbols} | {s.name for s in self.symbols})
        return difflib.get_close_matches(ident, names, n=n, cutoff=0.6)

    def resolve_path(self, fragment: str) -> list[str]:
        self.refresh()
        frag = fragment.strip().strip("`'\"").lstrip("./")
        if frag in self.paths:
            return [frag]
        hits = sorted(p for p in self.paths if p.endswith("/" + frag))
        if hits:
            return hits
        return sorted(p for p in self.paths if p.rsplit("/", 1)[-1] == frag.rsplit("/", 1)[-1])

    def in_file(self, path: str) -> list[Symbol]:
        self.refresh()
        return [s for s in self.symbols if s.path == path]

    def usages(self, ident: str, limit: int = 20) -> list[dict]:
        """Chunks that mention `ident` as a whole word, excluding its own definition line."""
        self.refresh()
        name = ident.split(".")[-1]
        pat = re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])")
        out = []
        for m, doc in self._docs:
            lines = doc.splitlines()
            for i, line in enumerate(lines):
                if not pat.search(line):
                    continue
                stripped = line.strip()
                if re.match(rf"(async\s+)?(def|class)\s+{re.escape(name)}\b", stripped):
                    continue
                out.append({"path": m["path"], "line": m["start_line"] + i, "symbol": m["symbol"], "code": stripped[:160]})
        out.sort(key=lambda u: (u["path"], u["line"]))
        return out[:limit]

    def known_names(self) -> set[str]:
        self.refresh()
        return {s.name for s in self.symbols} | {s.qualname for s in self.symbols}
