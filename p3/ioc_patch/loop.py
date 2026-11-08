"""The patch loop: generate -> sanity -> apply -> validate, up to 3 times, then commit or roll back."""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Callable

from ioc_api.llm import LLMError
from ioc_index.app import Context

from .applier import Snapshot, apply_patch
from .generator import PatchGenerator
from .sanity import check_patch
from .validator import run_validation

MAX_ATTEMPTS = 3


class LoopBusy(RuntimeError):
    pass


class PatchLoop:
    def __init__(self, ctx: Context, generator: PatchGenerator | None = None) -> None:
        self.ctx = ctx
        self.generator = generator or PatchGenerator(ctx)
        self._lock = threading.Lock()
        self.history: deque[dict] = deque(maxlen=20)

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def run(self, intent: str, k: int = 5, max_attempts: int = MAX_ATTEMPTS,
            emit: Callable[[dict], None] | None = None) -> dict:
        intent = (intent or "").strip()
        if not intent:
            raise ValueError("intent must not be empty")
        max_attempts = max(1, min(int(max_attempts), MAX_ATTEMPTS))
        if not self._lock.acquire(blocking=False):
            raise LoopBusy("a patch loop is already running")
        run_id = uuid.uuid4().hex[:10]
        t0 = time.time()
        target = self.ctx.settings.target
        snapshot = Snapshot(target)
        attempts: list[dict] = []
        feedback: list[dict] = []
        result = {"id": run_id, "intent": intent, "k": k, "max_attempts": max_attempts,
                  "status": "running", "attempts": attempts, "patch": None}

        def step(attempt: dict, stage: str, ok: bool = False, **data) -> dict:
            s = {"stage": stage, "ok": ok, **data}
            attempt["steps"].append(s)
            if emit:
                emit({"event": "step", "attempt": attempt["n"], **s})
            return s

        self.ctx.events.publish("patch", stage="start", intent=intent[:120], run=run_id)
        if emit:
            emit({"event": "start", "id": run_id, "intent": intent, "max_attempts": max_attempts})
        try:
            for n in range(1, max_attempts + 1):
                attempt = {"n": n, "steps": [], "ok": False}
                attempts.append(attempt)
                if emit:
                    emit({"event": "attempt", "attempt": n})
                # 1. generate
                g0 = time.time()
                try:
                    raw, patch, fmt_error, info = self.generator.generate(intent, k, feedback, attempt=n)
                except LLMError as exc:
                    step(attempt, "generate", False, error=str(exc), seconds=round(time.time() - g0, 2))
                    result.update(status="error", error=str(exc))
                    break
                if patch is None:
                    step(attempt, "generate", False, error=fmt_error, raw=raw[:4000], seconds=round(time.time() - g0, 2), **info)
                    feedback.append({"stage": "generate (JSON format)", "error": fmt_error, "raw": raw})
                    continue
                attempt["patch"] = patch.to_dict()
                step(attempt, "generate", True, summary=patch.summary, files=[f"{f.op} {f.path}" for f in patch.files],
                     seconds=round(time.time() - g0, 2), **info)
                # 2. sanity
                violations = check_patch(patch, target, self.ctx.indexer.filter)
                if violations:
                    step(attempt, "sanity", False, errors=violations)
                    feedback.append({"stage": "sanity check (patch refused, nothing was written)",
                                     "error": "\n".join(f"- {v}" for v in violations), "raw": raw})
                    continue
                step(attempt, "sanity", True)
                # 3. apply (atomic)
                try:
                    touched = apply_patch(patch, target, snapshot)
                except Exception as exc:
                    snapshot.restore()
                    step(attempt, "apply", False, error=f"{type(exc).__name__}: {exc}")
                    feedback.append({"stage": "apply", "error": str(exc), "raw": raw})
                    continue
                step(attempt, "apply", True, touched=touched)
                # 4. validate
                v = run_validation(target, touched)
                step(attempt, "validate", **v)
                self.ctx.events.publish("validate", ok=v["ok"], attempt=n, run=run_id)
                if v["ok"]:
                    attempt["ok"] = True
                    result.update(status="success", patch=patch.to_dict())
                    break
                restored = snapshot.restore()           # back to the exact pre-loop state before retrying
                step(attempt, "rollback", True, restored=restored, verified=snapshot.verify())
                feedback.append({"stage": "validation (command failed)", "error": v["output"], "raw": raw})
            else:
                result["status"] = "rolled_back"
            if result["status"] == "running":
                result["status"] = "rolled_back"
        except Exception as exc:                        # never leave the project half-written
            result.update(status="error", error=f"{type(exc).__name__}: {exc}")
        finally:
            if result["status"] != "success":
                snapshot.restore()
                result["rollback_verified"] = snapshot.verify()
                result["restored_files"] = sorted(snapshot.files)
            # silent reindex of everything the loop touched, whatever the outcome
            for rel in snapshot.files:
                try:
                    self.ctx.indexer.handle_path(target / rel)
                except Exception:
                    pass
            result["seconds"] = round(time.time() - t0, 2)
            result["attempt_count"] = len(attempts)
            self._lock.release()
        self.history.appendleft(result)
        kind = "success" if result["status"] == "success" else "rollback"
        self.ctx.events.publish(kind, run=run_id, attempts=len(attempts), status=result["status"],
                                files=(result["patch"] or {}).get("files") and [f["path"] for f in result["patch"]["files"]])
        if emit:
            emit({"event": "done", "result": result})
        return result
