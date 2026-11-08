"""Grounded Q&A.

1. Symbol questions ("is there a function X?", "what functions are in Y?",
   "where is X defined?") are answered from the index, without the model.
2. Everything else is retrieve-then-generate. The model gets the top-k
   chunks plus pre-resolved *symbol facts* (what exists, what does not), and
   the answer is post-checked for names that appear nowhere in the index.
"""
from __future__ import annotations

import builtins
import re
import time
import uuid
from collections import OrderedDict

from .llm import LLMError
from .retriever import Retriever
from .symbols import Symbol, SymbolIndex

ID = r"`?(?P<id>[A-Za-z_][\w.]*)(?:\(\))?`?"
FILE = r"`?(?P<path>[\w./-]+\.[A-Za-z0-9]+)`?"
KIND_WORDS = r"(?:functions?|methods?|class(?:es)?|defs?|symbols?|функци\w*|метод\w*|класс\w*|символ\w*)"

LIST_PATTERNS = [
    re.compile(rf"\b(?:what|which|list|show|name|enumerate)\b.*?\b{KIND_WORDS}\b.*?\b(?:in|inside|of|from|does)\b\s+(?:the\s+)?(?:file\s+)?{FILE}", re.I),
    re.compile(rf"(?:какие|список|перечисли|покажи|назови|что за)\b.*?{KIND_WORDS}.*?\s(?:в|из|во)\s+(?:файле\s+)?{FILE}", re.I),
    re.compile(rf"{FILE}.*?\b(?:contains?|has|have|defines?|содержит|есть)\b.*?{KIND_WORDS}", re.I),
]
EXISTS_PATTERNS = [
    re.compile(rf"\b(?:is\s+there|are\s+there|do\s+we\s+have|does\s+the\s+(?:code|project|codebase)\s+have|exists?)\b.*?\b(?:function|method|class|def|symbol)\b\s+(?:called\s+|named\s+)?{ID}", re.I),
    re.compile(rf"\b(?:does|is)\s+(?:a\s+|the\s+)?(?:function|method|class)?\s*{ID}\s+(?:exist|defined|present|available)", re.I),
    re.compile(rf"(?:есть\s+ли|существует\s+ли|имеется\s+ли|определена?\s+ли)\s+(?:в\s+\S+\s+)?(?:такая\s+|такой\s+)?(?:функция|метод|класс)?\s*(?:с\s+именем\s+|под\s+названием\s+|по\s+имени\s+)?{ID}", re.I),
]
WHERE_DEF_PATTERNS = [
    re.compile(rf"\bwhere\s+(?:is|are)\s+(?:the\s+)?(?:function\s+|method\s+|class\s+)?{ID}\s+(?:defined|declared|implemented|located)", re.I),
    re.compile(rf"где\s+(?:находится|определена?|определ[её]н|объявлена?|реализована?)\s+(?:функция\s+|метод\s+|класс\s+)?{ID}", re.I),
]
WHERE_USED_PATTERNS = [
    re.compile(rf"\bwhere\s+(?:is|are)\s+(?:the\s+)?(?:function\s+|method\s+|class\s+)?{ID}\s+(?:used|called|referenced|invoked)", re.I),
    re.compile(rf"\bwho\s+(?:calls|uses)\s+{ID}", re.I),
    re.compile(rf"где\s+(?:используется|вызывается|применяется)\s+(?:функция\s+|метод\s+|класс\s+)?{ID}", re.I),
    re.compile(rf"кто\s+(?:вызывает|использует)\s+{ID}", re.I),
]
GENERIC_WORDS = {"function", "method", "class", "def", "file", "code", "a", "the", "it", "this", "that",
                 "функция", "метод", "класс", "файл", "такая", "такой"}

SYSTEM_PROMPT = """You are the code assistant of a small local project.
Rules:
- Answer ONLY from the SNIPPETS and FACTS below. They are the whole truth about the code.
- FACTS were computed from the index and are always correct. Never contradict them.
- Never mention a function, method, class or file that does not appear in the snippets or facts.
- If the snippets do not contain the answer, say so plainly ("The indexed code does not show ...").
- Be concise: a short explanation, cite locations as path:line.
"""

NOT_SYMBOLS = {"what", "which", "does", "do", "is", "the", "this", "that", "each", "every", "any", "some",
               "explain", "describe", "how", "why", "main", "python", "new", "my", "our", "your", "its", "all",
               "and", "or", "to", "for", "of", "in", "on", "with", "called", "named", "а", "и", "эта", "эту", "этот"}

PY_BUILTINS = set(dir(builtins)) | {"self", "cls", "super", "print", "len"}


def _match(patterns, question):
    for p in patterns:
        m = p.search(question)
        if m:
            return m
    return None


def classify(question: str) -> tuple[str, str] | None:
    q = question.strip()
    if m := _match(LIST_PATTERNS, q):
        return "list_file", m.group("path")
    if m := _match(WHERE_DEF_PATTERNS, q):
        if m.group("id").lower() not in GENERIC_WORDS:
            return "where_defined", m.group("id")
    if m := _match(EXISTS_PATTERNS, q):
        if m.group("id").lower() not in GENERIC_WORDS:
            return "exists", m.group("id")
    if m := _match(WHERE_USED_PATTERNS, q):
        if m.group("id").lower() not in GENERIC_WORDS:
            return "where_used", m.group("id")
    return None


def _fmt_sym(s: Symbol) -> str:
    sig = f" — `{s.signature}`" if s.signature else ""
    return f"- {s.kind} `{s.qualname}` at {s.path}:{s.start_line}-{s.end_line}{sig}"


def code_identifiers(question: str) -> list[str]:
    """Identifier-looking tokens worth checking against the index (snake/camel/dotted/backticked/called)."""
    pattern = (r"`([^`]+)`|([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)|([A-Za-z_]\w*)\(\)"
               r"|\b([a-z]+_\w+|[a-z]+[A-Z]\w*|[A-Z][a-z]+[A-Z]\w*)\b")
    found = []
    for m in re.finditer(pattern, question):
        tok = next(g for g in m.groups() if g).strip().removesuffix("()")
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", tok):
            continue
        if re.search(r"\.(py|js|ts|md|ya?ml|toml|json|txt|cfg|ini|sh)$", tok):
            continue                      # file names are not symbols
        found.append(tok)
    # "the authenticate function", "function authenticate", "метод archive"
    kinds = r"(?:function|method|class|def|функци\w*|метод\w*|класс\w*)"
    for m in re.finditer(rf"{kinds}\s+(?:called\s+|named\s+)?`?([A-Za-z_]\w*)`?|`?([A-Za-z_]\w*)`?\s+{kinds}", question, re.I):
        tok = m.group(1) or m.group(2)
        if tok.lower() not in GENERIC_WORDS and tok.lower() not in NOT_SYMBOLS:
            found.append(tok)
    return list(dict.fromkeys(found))


class AskService:
    def __init__(self, retriever: Retriever, symbols: SymbolIndex, llm, model: str) -> None:
        self.retriever = retriever
        self.symbols = symbols
        self.llm = llm
        self.model = model
        self.sessions: "OrderedDict[str, list[dict]]" = OrderedDict()

    # ------------------------------------------------------------------ public
    def ask(self, question: str, k: int = 5, session_id: str | None = None, use_llm: bool = True) -> dict:
        t0 = time.time()
        question = (question or "").strip()
        if not question:
            raise ValueError("question must not be empty")
        session_id = session_id or uuid.uuid4().hex[:12]
        sources = self.retriever.search(question, k)
        shape = classify(question)
        if shape:
            answer, facts = self._deterministic(*shape)
            result = {"mode": f"symbol:{shape[0]}", "answer": answer, "facts": facts}
            if shape[0] == "where_used" and use_llm and facts["found"]:
                # add a grounded explanation on top of the exact usage list
                try:
                    expl = self._generate(question, sources, facts["lines"], session_id)
                    result["answer"] = answer + "\n\n" + expl["answer"]
                    result["model"] = self.model
                except LLMError as exc:
                    result["llm_error"] = str(exc)
        else:
            facts = self._facts_for(question)
            if not use_llm:
                result = {"mode": "retrieve", "answer": "", "facts": facts}
            else:
                gen = self._generate(question, sources, facts["lines"], session_id)
                if facts["missing"]:
                    names = ", ".join(f"`{n}`" for n in facts["missing"])
                    gen["answer"] = f"{names} does not exist in the indexed code.\n\n{gen['answer']}"
                result = {"mode": "rag", "facts": facts, "model": self.model, **gen}
        self._remember(session_id, question, result["answer"])
        result.update({"question": question, "k": k, "session_id": session_id,
                       "sources": sources, "seconds": round(time.time() - t0, 2)})
        return result

    def reset(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    # ------------------------------------------------------------------ deterministic answers
    def _deterministic(self, shape: str, arg: str) -> tuple[str, dict]:
        if shape == "list_file":
            paths = self.symbols.resolve_path(arg)
            if not paths:
                known = ", ".join(sorted(self.symbols.paths)) or "nothing"
                return (f"There is no file `{arg}` in the index. Indexed files: {known}.",
                        {"found": False, "path": arg})
            parts, all_syms = [], []
            for p in paths:
                syms = self.symbols.in_file(p)
                all_syms += [s.to_dict() for s in syms]
                if syms:
                    parts.append(f"`{p}` defines {len(syms)} symbol(s):\n" + "\n".join(_fmt_sym(s) for s in syms))
                else:
                    parts.append(f"`{p}` is indexed but defines no functions, methods or classes.")
            return "\n\n".join(parts), {"found": True, "paths": paths, "symbols": all_syms}

        matches = self.symbols.find(arg)
        if not matches:
            similar = self.symbols.similar(arg)
            hint = f" Closest names in the index: {', '.join(f'`{s}`' for s in similar)}." if similar else ""
            return (f"No. There is no function, method or class named `{arg}` in the indexed code.{hint}",
                    {"found": False, "symbol": arg, "similar": similar, "lines": [f"`{arg}` does not exist in the index."]})
        listing = "\n".join(_fmt_sym(s) for s in matches)
        facts = {"found": True, "symbol": arg, "matches": [s.to_dict() for s in matches],
                 "lines": [f"`{s.qualname}` is a {s.kind} defined at {s.path}:{s.start_line}-{s.end_line}" for s in matches]}
        if shape == "exists":
            return f"Yes. `{arg}` exists in the index:\n{listing}", facts
        if shape == "where_defined":
            return f"`{arg}` is defined at:\n{listing}", facts
        uses = self.symbols.usages(arg)
        facts["usages"] = uses
        facts["lines"] += [f"`{arg}` is referenced at {u['path']}:{u['line']} in {u['symbol']}: {u['code']}" for u in uses]
        if not uses:
            return f"`{arg}` is defined but no usage of it appears in the indexed code:\n{listing}", facts
        use_lines = "\n".join(f"- {u['path']}:{u['line']} (in `{u['symbol']}`): `{u['code']}`" for u in uses)
        return f"`{arg}` is defined at:\n{listing}\n\nIt is referenced at:\n{use_lines}", facts

    def _facts_for(self, question: str) -> dict:
        lines, missing, present = [], [], []
        for ident in code_identifiers(question):
            matches = self.symbols.find(ident)
            if matches:
                present.append(ident)
                lines += [f"`{s.qualname}` is a {s.kind} defined at {s.path}:{s.start_line}-{s.end_line}" for s in matches[:3]]
            elif not self.symbols.resolve_path(ident):
                missing.append(ident)
                lines.append(f"`{ident}` does NOT exist anywhere in the indexed code.")
        return {"present": present, "missing": missing, "lines": lines}

    # ------------------------------------------------------------------ generation
    def _generate(self, question: str, sources: list[dict], fact_lines: list[str], session_id: str) -> dict:
        snippets = "\n\n".join(
            f"### [{i}] {h['path']}:{h['start_line']}-{h['end_line']} ({h['kind']} {h['symbol']})\n{h['text']}"
            for i, h in enumerate(sources, start=1)) or "(no snippets matched)"
        facts = "\n".join(f"- {f}" for f in fact_lines) or "- (none)"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += self.sessions.get(session_id, [])[-6:]
        messages.append({"role": "user", "content": f"FACTS:\n{facts}\n\nSNIPPETS:\n{snippets}\n\nQUESTION: {question}"})
        answer = self.llm.chat(self.model, messages, temperature=0.1, num_predict=512).strip()
        unknown = self._unknown_names(answer, sources, question)
        if unknown:
            answer += ("\n\n⚠ Not found in the index: " + ", ".join(f"`{u}`" for u in unknown) +
                       ". Treat any statement about them as unverified.")
        return {"answer": answer, "unverified": unknown}

    def _unknown_names(self, answer: str, sources: list[dict], question: str) -> list[str]:
        known = self.symbols.known_names()
        corpus = "\n".join(h["text"] for h in sources) + "\n" + question
        out = []
        for m in re.finditer(r"`([A-Za-z_][\w.]*)\(?\)?`|\b([A-Za-z_][\w.]*)\(", answer):
            name = (m.group(1) or m.group(2)).rstrip(".")
            short = name.split(".")[-1]
            if (name in known or short in known or short in PY_BUILTINS or
                    re.search(rf"(?<![\w]){re.escape(short)}(?![\w])", corpus) or "/" in name):
                continue
            if re.search(r"\.\w{1,4}$", name):      # file names like main.py
                continue
            out.append(name)
        return list(dict.fromkeys(out))

    def _remember(self, session_id: str, question: str, answer: str) -> None:
        hist = self.sessions.setdefault(session_id, [])
        hist += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
        del hist[:-6]
        self.sessions.move_to_end(session_id)
        while len(self.sessions) > 100:
            self.sessions.popitem(last=False)
