"""The Patch the model proposes, and the record of one Attempt to apply it. Plain dicts, documented here."""
from typing import Optional, TypedDict

OPS = ("create", "modify", "delete")


class PatchFile(TypedDict):
    path: str
    op: str
    content: str


class Patch(TypedDict):
    summary: str
    files: list


class Attempt(TypedDict):
    number: int
    ok: bool
    error: Optional[str]
    patch: Optional[Patch]
    generation: Optional[dict]
    sanity: Optional[dict]
    apply: Optional[dict]
    validation: Optional[dict]


class AttemptFactory:
    def new_attempt(self, number):
        """An Attempt where nothing has happened yet."""
        return {"number": number, "ok": False, "error": None, "patch": None,
                "generation": None, "sanity": None, "apply": None, "validation": None}


attempt_factory = AttemptFactory()
