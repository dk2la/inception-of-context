"""The answer to a Question. A plain dict, documented here."""
from typing import TypedDict


class Answer(TypedDict):
    answer: str
    sources: list
    used_llm: bool


class AnswerFactory:
    def make_answer(self, answer, sources, used_llm):
        return {"answer": answer, "sources": sources, "used_llm": used_llm}


answer_factory = AnswerFactory()
