"""Answering Questions, and the one function that talks to the local model."""
import json
import os
import re
import urllib.error
import urllib.request

from p1 import index

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


def known_symbols(chunks):
    """Every function, class and method in the files of these Chunks, as sorted lines "path: name (kind)"."""
    lines = set()
    for path in {chunk["path"] for chunk in chunks}:
        found = index.get_collection().get(where={"path": path}, include=["metadatas"])
        for meta in found["metadatas"]:
            if meta["kind"] in ("function", "async_function", "class", "method"):
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
    kinds = ["function", "async_function", "method", "class"]
    return [c for c in symbol_chunks(kinds) if c["name"] == name or c["name"].endswith("." + name)]


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
END = r"(?: in .*)?\W*$"
HAS_FUNCTION_PATTERNS = [
    r"is there (?:a |an |any )?(?:function|method) (?:called |named )?" + NAME + END,
    r"does (?:a |the |any )?(?:function|method) " + NAME + " exists?" + END,
]


def route_question(question):
    """Recognise a symbol question: ("has_function", name), or None for any other Question."""
    for pattern in HAS_FUNCTION_PATTERNS:
        match = re.search(pattern, question.strip(), re.IGNORECASE)
        if match:
            return "has_function", match.group(1)
    return None
