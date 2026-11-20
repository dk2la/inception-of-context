"""The answer to a Question. A plain dict, documented here."""
from typing import TypedDict


class Answer(TypedDict):
    answer: str  # the text shown to the user
    sources: list  # the Chunks the answer is based on
    used_llm: bool  # False when it came from the Index alone (symbol questions, empty Index)


class AnswerFactory:
    def make_answer(self, answer, sources, used_llm):
        return {"answer": answer, "sources": sources, "used_llm": used_llm}


answer_factory = AnswerFactory()
