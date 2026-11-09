"""Answering Questions, and the one function that talks to the local model."""
import json
import os
import re
import urllib.error
import urllib.request

from p1 import index
from p2 import search

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
ANSWER_MODEL = "qwen2.5:3b"
PATCH_MODEL = "qwen2.5-coder:3b"


class LLMError(Exception):
    pass


def call_llm(model, prompt, json_mode=False):
    """Send a prompt to the local Ollama and return the model's reply as text.

    This is the only place in the project that talks to a model, and it only talks to OLLAMA_HOST.
    """
    body = {"model": model, "prompt": prompt, "stream": False}
    if json_mode:
        body["format"] = "json"
    request = urllib.request.Request(
        OLLAMA_HOST + "/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        # A 3B model on CPU is slow, so the timeout is long.
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read())["response"]
    except urllib.error.HTTPError as error:
        raise LLMError(f"Ollama at {OLLAMA_HOST} answered {error.code}: is the model pulled? Run `make models`.")
    except (urllib.error.URLError, TimeoutError) as error:
        raise LLMError(f"Ollama is not reachable at {OLLAMA_HOST}: {error}")


SYMBOL_KINDS = ["function", "async_function", "class", "method"]  # the Chunk kinds that are real symbols


def known_symbols(chunks):
    """Every function, class and method in the files of these Chunks, as sorted lines "path: name (kind)"."""
    lines = set()
    for path in {chunk["path"] for chunk in chunks}:
        found = index.get_collection().get(where={"path": path}, include=["metadatas"])
        for meta in found["metadatas"]:
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
    """Chunk dictionaries (the metadata plus "id" and "text") of every Chunk of these kinds, in source order."""
    found = index.get_collection().get(where={"kind": {"$in": kinds}})
    chunks = [dict(meta, id=id_, text=text)
              for id_, text, meta in zip(found["ids"], found["documents"], found["metadatas"])]
    return sorted(chunks, key=lambda chunk: (chunk["path"], chunk["start_line"]))


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


# Symbol questions are recognised with these patterns, one phrasing each. To teach the router a new
# phrasing, add one line to a list. The first capturing group of a pattern is the name asked about.
# A pattern must reach the end of the question (only "in the project", "?" or "." may follow the name),
# so "is there a function that divides numbers?" is not mistaken for a function called "that".
NAME = r"`?(\w+(?:\.\w+)*)`?"
END = r"(?: (?:in|в) .*)?\W*$"
# Russian words change their endings ("функция", "функции", "функцию"), so only the stem is matched.
RU_FUNCTION = r"(?:функци\w*|метод\w*)"
HAS_FUNCTION_PATTERNS = [
    r"is there (?:a |an |any )?(?:function|method) (?:called |named )?" + NAME + END,
    r"does (?:a |the |any )?(?:function|method) " + NAME + " exists?" + END,
    r"(?:есть|существует) ли (?:(?:в|у) (?:\S+ ){1,2})?" + RU_FUNCTION + " (?:с именем |под названием )?" + NAME + END,
]

# A file name needs an extension, so "what functions are in the project?" is not about a file called "project".
FILE = r"`?([\w./-]+\.\w+)`?"
IN_FILE = r"(?:in|inside|from|of) (?:the )?(?:file )?" + FILE + r"\W*$"
RU_IN_FILE = r"(?:в|из|внутри) (?:файле |файла )?" + FILE + r"\W*$"
FILE_FUNCTIONS_PATTERNS = [
    r"(?:what|which) (?:functions|methods) (?:are |exist )?(?:there )?(?:defined )?" + IN_FILE,
    r"(?:what|which) (?:functions|methods) (?:does|do) (?:the )?(?:file )?" + FILE + r" (?:have|contain|define)\W*$",
    r"what are (?:all )?the (?:functions|methods) (?:defined )?" + IN_FILE,
    r"(?:list|show)(?: me)? (?:all )?(?:the )?(?:functions|methods) " + IN_FILE,
    r"какие " + RU_FUNCTION + " (?:есть |определены |имеются )?" + RU_IN_FILE,
    r"какие " + RU_FUNCTION + " (?:содержит|имеет|определяет) (?:файл )?" + FILE + r"\W*$",
    r"(?:покажи|выведи|перечисли|список|перечень)\w* (?:все |всех )?" + RU_FUNCTION + " " + RU_IN_FILE,
]


def route_question(question):
    """Recognise a symbol question: ("has_function", name), ("file_functions", filename) or None.

    None means any other Question, which goes to the model.
    """
    question = question.strip()
    for kind, patterns in [("has_function", HAS_FUNCTION_PATTERNS), ("file_functions", FILE_FUNCTIONS_PATTERNS)]:
        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                return kind, match.group(1)
    return None


def ask(question, k=5):
    """Answer one Question (no history). Return {"answer", "sources", "used_llm"}."""
    chunks = search.search(question, k)
    if not chunks:  # nothing to ground an answer on, and a model without context invents things
        return {"answer": "The Index is empty, so I cannot answer yet.", "sources": [], "used_llm": False}
    prompt = build_answer_prompt(question, chunks, known_symbols(chunks))
    answer = call_llm(ANSWER_MODEL, prompt)
    return {"answer": answer.strip(), "sources": chunks, "used_llm": True}
