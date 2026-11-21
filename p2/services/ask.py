"""Answering Questions: from the Index for symbol questions, otherwise with the local model."""
from p1.config.settings import settings
from p1.core.llm import llm_client
from p1.models.chunk import SYMBOL_KINDS
from p2.models.answer import answer_factory
from p2.repositories.search_repository import search_repository
from p2.services.router import router_service
from p2.services.search import search_service


ANSWER_RULES = """You answer questions about a small Python project, using ONLY the code below.
Rules:
- Use only the code shown. If the answer is not in the code, say you don't know.
- Only mention functions, classes and methods from KNOWN SYMBOLS.
  If something the user asks about is not in KNOWN SYMBOLS, say it does not exist.
- Mention the file path when you refer to code.
- Answer briefly."""


class AskService:
    def __init__(self, settings, llm_client, answer_factory, search_repository, search_service, router_service):
        # debug: the six collaborators. POST /ask calls ask() on the object built at the bottom of this file.
        self.settings = settings
        self.llm_client = llm_client
        self.answer_factory = answer_factory
        self.search_repository = search_repository
        self.search_service = search_service
        self.router_service = router_service

    def known_symbols(self, chunks):
        """Every function, class and method in the files of these Chunks, as sorted lines "path: name (kind)"."""
        # debug: chunks are the top-k from search, for example one Chunk of calculator/core.py.
        # metadata_of_file then loads every Chunk of that file. SYMBOL_KINDS drops "module".
        # return == [
        #     "calculator/core.py: Calculator (class)",
        #     "calculator/core.py: Calculator.add (method)",
        #     "calculator/core.py: Calculator.divide (method)",
        #     "calculator/core.py: Calculator.multiply (method)",
        #     "calculator/core.py: Calculator.subtract (method)",
        # ]
        lines = set()
        for path in {chunk["path"] for chunk in chunks}:
            for meta in self.search_repository.metadata_of_file(path):
                if meta["kind"] in SYMBOL_KINDS:
                    lines.add(f"{path}: {meta['name']} ({meta['kind']})")
        return sorted(lines)

    def build_answer_prompt(self, question, chunks, symbols):
        """The text sent to the model: rules, KNOWN SYMBOLS, the retrieved code, then the Question."""
        # debug: question == "what happens on division by zero?"
        # one CODE block looks like:
        #   --- calculator/core.py lines 16-20 (Calculator.divide) ---
        #       def divide(self, a, b):
        #           ...
        # return is one string: ANSWER_RULES, then KNOWN SYMBOLS, then CODE, then QUESTION, then "ANSWER:"
        code = "\n\n".join(
            f"--- {c['path']} lines {c['start_line']}-{c['end_line']} ({c['name']}) ---\n{c['text']}" for c in chunks
        )
        symbols_text = "\n".join(symbols) or "(none)"
        return (f"{ANSWER_RULES}\n\nKNOWN SYMBOLS:\n{symbols_text}\n\nCODE:\n{code}\n\n"
                f"QUESTION:\n{question}\n\nANSWER:")

    def symbol_chunks(self, kinds):
        """Every Chunk of these kinds, in source order."""
        # debug: kinds == ["function", "async_function", "class", "method"]
        # of_kinds returns those Chunks. sorted puts calculator/core.py line 1 before line 4.
        # return[0]["name"] == "Calculator", return[1]["name"] == "Calculator.add"
        return sorted(self.search_repository.of_kinds(kinds), key=lambda chunk: (chunk["path"], chunk["start_line"]))

    def find_symbol(self, name):
        """The Chunks of every function, method or class called name ("divide" finds "Calculator.divide")."""
        # debug: name == "divide"
        # "Calculator.divide".endswith(".divide") is True, "divide" == "divide" would match a top-level function
        # return == [{name: "Calculator.divide", path: "calculator/core.py", start_line: 16, end_line: 20, ...}]
        # name == "power": return == []
        return [c for c in self.symbol_chunks(SYMBOL_KINDS) if c["name"] == name or c["name"].endswith("." + name)]

    def symbols_in_file(self, filename):
        """The Chunks of every function and method in the file(s) called filename, in source order.

        "core.py" finds "calculator/core.py" too, but not "hardcore.py". Classes are left out.
        """
        # debug: filename == "core.py" (backticks stripped)
        # kinds here are function, async_function, method. "Calculator" (class) is not included.
        # "calculator/core.py".endswith("/core.py") matches. "hardcore.py" does not.
        # return == [Calculator.add, Calculator.subtract, Calculator.multiply, Calculator.divide]
        filename = filename.strip().strip("`")
        chunks = self.symbol_chunks(["function", "async_function", "method"])
        return [c for c in chunks if c["path"] == filename or c["path"].endswith("/" + filename)]

    def answer_from_index(self, kind, value):
        """Answer a symbol question from the Index alone. The text is built from facts, so nothing is invented."""
        # debug: kind == "has_function", value == "power"
        #   answer == 'No. There is no function or method named "power" in the Target Project.'
        #   return == {"answer": answer, "sources": [], "used_llm": False}
        # kind == "has_function", value == "divide"
        #   answer == 'Yes. "divide" exists:\n- method Calculator.divide in calculator/core.py, lines 16-20'
        # kind == "file_functions", value == "core.py"
        #   answer == "calculator/core.py defines 4 functions: Calculator.add, "
        #             "Calculator.subtract, Calculator.multiply, Calculator.divide."
        if kind == "has_function":
            chunks = self.find_symbol(value)
            if chunks:
                places = [f"- {c['kind'].replace('_', ' ')} {c['name']} in {c['path']}, "
                          f"lines {c['start_line']}-{c['end_line']}" for c in chunks]
                answer = f'Yes. "{value}" exists:\n' + "\n".join(places)
            else:
                answer = f'No. There is no function or method named "{value}" in the Target Project.'
        else:  # "file_functions"
            chunks = self.symbols_in_file(value)
            lines = []
            for path in sorted({c["path"] for c in chunks}):  # the full path, even if the user typed "core.py"
                names = [c["name"] for c in chunks if c["path"] == path]
                noun = "function" if len(names) == 1 else "functions"
                lines.append(f"{path} defines {len(names)} {noun}: {', '.join(names)}.")
            answer = "\n".join(lines) or f'I found no functions in a file named "{value}".'
        return self.answer_factory.make_answer(answer, chunks, used_llm=False)

    def ask(self, question, k=5):
        """Answer one Question (no history). Return {"answer", "sources", "used_llm"}."""
        # debug: POST /ask. k == 5.
        # question == "is there a function power?"
        #   routed == ("has_function", "power"). The model is not called. used_llm == False.
        # question == "what functions are in core.py?"
        #   routed == ("file_functions", "core.py")
        # question == "what happens on division by zero?"
        #   routed == None. search() returns the top 5 Chunks. prompt goes to qwen2.5:3b.
        #   return == {"answer": "Calculator.divide raises ZeroDivisionError ...",
        #              "sources": [chunks], "used_llm": True}
        # empty Index on that last question: answer == "The Index is empty, so I cannot answer yet.", used_llm == False
        routed = self.router_service.route_question(question)
        if routed:  # "is there a function X?" and "what functions are in Y?" never reach the model
            return self.answer_from_index(*routed)
        chunks = self.search_service.search(question, k)
        if not chunks:  # nothing to ground an answer on, and a model without context invents things
            return self.answer_factory.make_answer("The Index is empty, so I cannot answer yet.", [], used_llm=False)
        prompt = self.build_answer_prompt(question, chunks, self.known_symbols(chunks))
        answer = self.llm_client.call_llm(self.settings.ANSWER_MODEL, prompt)
        return self.answer_factory.make_answer(answer.strip(), chunks, used_llm=True)


ask_service = AskService(settings, llm_client, answer_factory, search_repository, search_service, router_service)
