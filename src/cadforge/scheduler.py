"""Bounded specialist execution and explicit per-arm resource accounting."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass, field
from threading import Lock
import time


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class BudgetLedger:
    max_attempts: int = 3
    max_tool_calls: int = 12
    max_model_tokens: int = 0
    attempts: int = 0
    tool_calls: int = 0
    model_tokens: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def consume(self, *, attempts: int = 0, tool_calls: int = 0, model_tokens: int = 0):
        increments = dict(attempts=attempts, tool_calls=tool_calls, model_tokens=model_tokens)
        with self._lock:
            if any(not isinstance(v, int) or v < 0 for v in increments.values()):
                raise ValueError("resource increments must be nonnegative integers")
            for name, amount in increments.items():
                if getattr(self, name) + amount > getattr(self, "max_" + name):
                    raise BudgetExceeded(name)
            for name, amount in increments.items():
                setattr(self, name, getattr(self, name) + amount)

    def snapshot(self):
        with self._lock:
            return {k: getattr(self, k) for k in ("max_attempts", "max_tool_calls", "max_model_tokens",
                                                 "attempts", "tool_calls", "model_tokens")}


def run_specialists(jobs, worker, max_workers: int = 4):
    """Return ordered audit records. Worker errors remain visible, never pass."""
    jobs = list(jobs)
    if not 1 <= max_workers <= 32:
        raise ValueError("max_workers must be between 1 and 32")
    if len({j.id for j in jobs}) != len(jobs):
        raise ValueError("specialist IDs must be unique")

    def run(job):
        start = time.monotonic()
        try:
            output = worker(job)
            return dict(job_id=job.id, discipline=job.discipline, lens=job.lens,
                        status="completed", output=output, duration_seconds=time.monotonic() - start)
        except Exception as error:
            return dict(job_id=job.id, discipline=job.discipline, lens=job.lens,
                        status="failed", error=f"{type(error).__name__}: {error}",
                        usage=getattr(error, "cadforge_usage", {}),
                        duration_seconds=time.monotonic() - start)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        contexts=[copy_context() for _ in jobs]
        return list(executor.map(lambda pair:pair[0].run(run,pair[1]),zip(contexts,jobs)))
