"""Turns an intent into a JSON patch with the local coder model."""
from __future__ import annotations

import json
import re

from ioc_index.app import Context

from .schema import Patch, parse_patch

SYSTEM_PROMPT = """You are a precise code-editing engine for a small project.
You receive a change request, the current content of the relevant files and some context.
Reply with ONLY one JSON object, nothing else:
{"summary": "<one line>", "files": [{"path": "<relative path>", "op": "create|modify|delete", "content": "<COMPLETE new file content>"}]}

Rules:
- "content" is the COMPLETE new content of the file, from the first line to the last. Not a diff, not a fragment.
  Copy every existing line that does not need to change EXACTLY as it is: same quotes, docstrings,
  comments, blank lines and order. Only add or edit the lines the request needs.
- Use "modify" only for files shown under CURRENT FILES, "create" only for files that do not exist yet.
- Inside the JSON string escape double quotes as \" and newlines as \n. Do NOT turn \"\"\" docstrings into '''
  and do NOT drop the module docstring on the first line.
- Touch as few files as possible (never more than 3).
- Write real, working code. Never leave a function body as `pass`, `...` or `return None`.
- Keep imports, names and style consistent with the project. Respect the FACTS about which symbols exist.
- Never copy the <<<IOC_...>>> marker lines into "content".
"""

MAX_FULL_FILES = 3
MAX_FILE_CHARS = 16000


def _wrap(path: str, text: str) -> str:
    return f"<<<IOC_FILE {path}>>>\n{text.rstrip()}\n<<<IOC_END>>>"


class PatchGenerator:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    @property
    def llm(self):
        return self.ctx.extras["llm"]

    def select_files(self, intent: str, hits: list[dict]) -> list[str]:
        """Files sent in full: those the intent names explicitly, then the files of the best chunks."""
        paths = sorted(self.ctx.store.all_paths())
        chosen: list[str] = []
        for tok in re.findall(r"[\w./-]+\.[A-Za-z0-9]+", intent):
            tok = tok.strip("./`'\"")
            for p in paths:
                if p == tok or p.endswith("/" + tok) or p.rsplit("/", 1)[-1] == tok:
                    if p not in chosen:
                        chosen.append(p)
        for h in hits:
            if len(chosen) >= MAX_FULL_FILES:
                break
            if h["path"] not in chosen and h["kind"] not in ("section",) and not h["path"].endswith(".md"):
                chosen.append(h["path"])
        return chosen[:MAX_FULL_FILES]

    def build_messages(self, intent: str, k: int, feedback: list[dict]) -> tuple[list[dict], dict]:
        hits = self.ctx.extras["retriever"].search(intent, k)
        files = self.select_files(intent, hits)
        target = self.ctx.settings.target
        current = []
        for p in files:
            full = target / p
            if full.is_file():
                current.append(_wrap(p, full.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]))
        snippets = [f"<<<IOC_CHUNK {h['path']}:{h['start_line']}-{h['end_line']} {h['symbol']}>>>\n{h['text']}\n<<<IOC_END>>>"
                    for h in hits if h["path"] not in files]
        facts = self.ctx.extras["ask"]._facts_for(intent)["lines"] if "ask" in self.ctx.extras else []
        all_paths = sorted(self.ctx.store.all_paths())
        user = [f"CHANGE REQUEST: {intent}",
                "PROJECT FILES: " + ", ".join(all_paths)]
        if facts:
            user.append("FACTS (from the index, always true):\n" + "\n".join(f"- {f}" for f in facts))
        user.append("CURRENT FILES (full content):\n" + ("\n\n".join(current) or "(none selected)"))
        if snippets:
            user.append("OTHER RELEVANT CODE (read-only context):\n" + "\n\n".join(snippets))
        user.append('Return the JSON object now.')
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "\n\n".join(user)}]
        for fb in feedback:
            messages.append({"role": "assistant", "content": fb["raw"][:6000]})
            messages.append({"role": "user", "content":
                             f"That attempt failed at the {fb['stage']} step:\n{fb['error'][:3000]}\n\n"
                             "The project was rolled back to its original state, so CURRENT FILES above are still accurate. "
                             "Fix the problem and return the corrected, COMPLETE JSON object."})
        info = {"files_in_prompt": files, "context": [{"path": h["path"], "symbol": h["symbol"], "score": h["score"]} for h in hits]}
        return messages, info

    def generate(self, intent: str, k: int = 5, feedback: list[dict] | None = None, attempt: int = 1) -> tuple[str, Patch | None, str | None, dict]:
        """Returns (raw_text, patch_or_None, format_error_or_None, prompt_info)."""
        messages, info = self.build_messages(intent, k, feedback or [])
        raw = self.llm.chat(self.ctx.settings.code_model, messages, json_mode=True,
                            temperature=0.1 if attempt == 1 else 0.3, num_ctx=12288, num_predict=4096)
        try:
            return raw, parse_patch(raw), None, info
        except ValueError as exc:
            return raw, None, str(exc), info


def pretty(patch: Patch) -> str:
    return json.dumps(patch.to_dict(), indent=2, ensure_ascii=False)
