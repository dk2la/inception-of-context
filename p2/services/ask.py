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
        self.settings = settings
        self.llm_client = llm_client
        self.answer_factory = answer_factory
        self.search_repository = search_repository
        self.search_service = search_service
        self.router_service = router_service

    def known_symbols(self, chunks):
        """Every function, class and method in the files of these Chunks, as sorted lines "path: name (kind)"."""
        lines = set()
        for path in {chunk["path"] for chunk in chunks}:
            for meta in self.search_repository.metadata_of_file(path):
                if meta["kind"] in SYMBOL_KINDS:
                    lines.add(f"{path}: {meta['name']} ({meta['kind']})")
        return sorted(lines)

    def build_answer_prompt(self, question, chunks, symbols):
        """The text sent to the model: rules, KNOWN SYMBOLS, the retrieved code, then the Question."""
        code = "\n\n".join(
            f"--- {c['path']} lines {c['start_line']}-{c['end_line']} ({c['name']}) ---\n{c['text']}" for c in chunks
        )
        symbols_text = "\n".join(symbols) or "(none)"
        return (f"{ANSWER_RULES}\n\nKNOWN SYMBOLS:\n{symbols_text}\n\nCODE:\n{code}\n\n"
                f"QUESTION:\n{question}\n\nANSWER:")

    def symbol_chunks(self, kinds):
        """Every Chunk of these kinds, in source order."""
        return sorted(self.search_repository.of_kinds(kinds), key=lambda chunk: (chunk["path"], chunk["start_line"]))

    def find_symbol(self, name):
        """The Chunks of every function, method or class called name ("divide" finds "Calculator.divide")."""
        return [c for c in self.symbol_chunks(SYMBOL_KINDS) if c["name"] == name or c["name"].endswith("." + name)]

    def symbols_in_file(self, filename):
        """The Chunks of every function and method in the file(s) called filename, in source order.

        "core.py" finds "calculator/core.py" too, but not "hardcore.py". Classes are left out.
        """
        filename = filename.strip().strip("`")
        chunks = self.symbol_chunks(["function", "async_function", "method"])
        return [c for c in chunks if c["path"] == filename or c["path"].endswith("/" + filename)]

    def answer_from_index(self, kind, value):
        """Answer a symbol question from the Index alone. The text is built from facts, so nothing is invented."""
        if kind == "has_function":
            chunks = self.find_symbol(value)
            if chunks:
                places = [f"- {c['kind'].replace('_', ' ')} {c['name']} in {c['path']}, lines {c['start_line']}-{c['end_line']}"
                          for c in chunks]
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
