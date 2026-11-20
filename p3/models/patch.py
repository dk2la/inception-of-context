"""The Patch the model proposes, and the record of one Attempt to apply it. Plain dicts, documented here."""
from typing import Optional, TypedDict

OPS = ("create", "modify", "delete")


class PatchFile(TypedDict):
    path: str  # relative to the Target Project
    op: str  # one of OPS
    content: str  # the COMPLETE new file ("" for delete)


class Patch(TypedDict):
    summary: str
    files: list  # of PatchFile


class Attempt(TypedDict):
    number: int  # 1, 2 or 3
    ok: bool  # True only if the Validation Command passed
    error: Optional[str]  # why it failed; sent to the model on the next Attempt
    patch: Optional[Patch]
    generation: Optional[dict]  # {ok, summary} or {ok, error}
    sanity: Optional[dict]  # {ok, reason}
    apply: Optional[dict]  # {ok, files} or {ok, error}
    validation: Optional[dict]  # {ok, log}


def new_attempt(number):
    """An Attempt where nothing has happened yet."""
    return {"number": number, "ok": False, "error": None, "patch": None,
            "generation": None, "sanity": None, "apply": None, "validation": None}
