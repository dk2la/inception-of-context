"""The patch format: structured JSON, never a diff.

    {"summary": "...", "files": [{"path": "main.py", "op": "create|modify|delete", "content": "<full file>"}]}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field

OPS = {"create", "modify", "delete"}
OP_ALIASES = {"update": "modify", "edit": "modify", "replace": "modify", "change": "modify",
              "add": "create", "new": "create", "remove": "delete"}


class PatchFormatError(ValueError):
    pass


@dataclass
class FileChange:
    path: str
    op: str
    content: str | None = None


@dataclass
class Patch:
    summary: str
    files: list[FileChange] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def paths(self) -> list[str]:
        return [f.path for f in self.files]


def _extract_json(raw: str) -> str:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        return fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise PatchFormatError("the model did not return a JSON object")
    return text[start:end + 1]


def parse_patch(raw: str | dict) -> Patch:
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            raise PatchFormatError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PatchFormatError("top-level JSON value must be an object")
    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise PatchFormatError('"files" must be a non-empty list of {path, op, content}')
    summary = data.get("summary")
    summary = summary.strip() if isinstance(summary, str) else ""
    out = []
    for i, f in enumerate(files):
        if not isinstance(f, dict):
            raise PatchFormatError(f"files[{i}] must be an object")
        path = f.get("path")
        if not isinstance(path, str) or not path.strip():
            raise PatchFormatError(f"files[{i}].path must be a non-empty string")
        path = path.strip().replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        op = str(f.get("op", "")).strip().lower()
        op = OP_ALIASES.get(op, op)
        if op not in OPS:
            raise PatchFormatError(f"files[{i}].op must be one of create, modify, delete (got {f.get('op')!r})")
        content = f.get("content")
        if op in ("create", "modify"):
            if content is None:
                content = "None"          # caught by the sanity check as an emptied file
            elif not isinstance(content, str):
                raise PatchFormatError(f"files[{i}].content must be a string with the complete file")
        else:
            content = None
        out.append(FileChange(path=path, op=op, content=content))
    return Patch(summary=summary or "(no summary)", files=out)
