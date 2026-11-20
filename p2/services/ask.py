"""Answering Questions: from the Index for symbol questions, otherwise with the local model."""
from p1.config import settings
from p1.core import llm
from p1.models.chunk import SYMBOL_KINDS
from p2.models.answer import make_answer
from p2.repositories import search_repository
from p2.services import search
from p2.services.router import route_question


def known_symbols(chunks):
    """Every function, class and method in the files of these Chunks, as sorted lines "path: name (kind)"."""
    lines = set()
    for path in {chunk["path"] for chunk in chunks}:
        for meta in search_repository.metadata_of_file(path):
            if meta["kind"] in SYMBOL_KINDS:
                lines.add(f"{path}: {meta['name']} ({meta['kind']})")
    return sorted(lines)


ANSWER_RULES = """You answer questions about a small Python project, using ONLY the code below.
Rules:
- Use only the code shown. If the answer is not in the code, say you don't know.
- Only mention functions, classes and methods from KNOWN SYMBOLS.
  If something the user asks about is not in KNOWN SYMBOLS, say it does not exist.
- Mention the file path when you refer to code.
- Answer briefly."""


def build_answer_prompt(question, chunks, symbols):
    """The text sent to the model: rules, KNOWN SYMBOLS, the retrieved code, then the Question."""
    code = "\n\n".join(
        f"--- {c['path']} lines {c['start_line']}-{c['end_line']} ({c['name']}) ---\n{c['text']}" for c in chunks
    )
    symbols_text = "\n".join(symbols) or "(none)"
    return (f"{ANSWER_RULES}\n\nKNOWN SYMBOLS:\n{symbols_text}\n\nCODE:\n{code}\n\n"
            f"QUESTION:\n{question}\n\nANSWER:")


def symbol_chunks(kinds):
    """Every Chunk of these kinds, in source order."""
    return sorted(search_repository.of_kinds(kinds), key=lambda chunk: (chunk["path"], chunk["start_line"]))


def find_symbol(name):
    """The Chunks of every function, method or class called name ("divide" finds "Calculator.divide")."""
    return [c for c in symbol_chunks(SYMBOL_KINDS) if c["name"] == name or c["name"].endswith("." + name)]


def symbols_in_file(filename):
    """The Chunks of every function and method in the file(s) called filename, in source order.

    "core.py" finds "calculator/core.py" too, but not "hardcore.py". Classes are left out.
    """
    filename = filename.strip().strip("`")
    chunks = symbol_chunks(["function", "async_function", "method"])
    return [c for c in chunks if c["path"] == filename or c["path"].endswith("/" + filename)]


def answer_from_index(kind, value):
    """Answer a symbol question from the Index alone. The text is built from facts, so nothing is invented."""
    if kind == "has_function":
        chunks = find_symbol(value)
        if chunks:
            places = [f"- {c['kind'].replace('_', ' ')} {c['name']} in {c['path']}, lines {c['start_line']}-{c['end_line']}"
                      for c in chunks]
            answer = f'Yes. "{value}" exists:\n' + "\n".join(places)
        else:
            answer = f'No. There is no function or method named "{value}" in the Target Project.'
    else:  # "file_functions"
        chunks = symbols_in_file(value)
        lines = []
        for path in sorted({c["path"] for c in chunks}):  # the full path, even if the user typed "core.py"
            names = [c["name"] for c in chunks if c["path"] == path]
            noun = "function" if len(names) == 1 else "functions"
            lines.append(f"{path} defines {len(names)} {noun}: {', '.join(names)}.")
        answer = "\n".join(lines) or f'I found no functions in a file named "{value}".'
    return make_answer(answer, chunks, used_llm=False)


def ask(question, k=5):
    """Answer one Question (no history). Return {"answer", "sources", "used_llm"}."""
    routed = route_question(question)
    if routed:  # "is there a function X?" and "what functions are in Y?" never reach the model
        return answer_from_index(*routed)
    chunks = search.search(question, k)
    if not chunks:  # nothing to ground an answer on, and a model without context invents things
        return make_answer("The Index is empty, so I cannot answer yet.", [], used_llm=False)
    prompt = build_answer_prompt(question, chunks, known_symbols(chunks))
    answer = llm.call_llm(settings.ANSWER_MODEL, prompt)
    return make_answer(answer.strip(), chunks, used_llm=True)
