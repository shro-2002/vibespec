"""In-memory background jobs so the UI never holds a long HTTP request open.

Honest by design: `steps` contains only events the agent really emitted; a finished job holds the real result or the
real error. State is per-process and lost on restart/spin-down (Render Free), which the client reports as 'job lost'.
"""
from __future__ import annotations

import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

Runner = Callable[[Any, Callable[[dict], None], float], dict]  # (brief, on_event, deadline) -> blueprint


class Busy(RuntimeError):
    pass


class JobManager:
    def __init__(self, runner: Runner, max_running: int = 2, max_queued: int = 3, ttl_s: int = 900,
                 job_timeout_s: float = 150, redact: Callable[[str], str] = lambda s: s):
        self._runner, self._timeout, self._ttl, self._redact = runner, job_timeout_s, ttl_s, redact
        self._pool = ThreadPoolExecutor(max_running, thread_name_prefix="job")
        self._cap = max_running + max_queued
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = time.time()
        for k in [k for k, j in self._jobs.items() if j["status"] in ("done", "failed", "timeout") and now - j["finished"] > self._ttl]:
            del self._jobs[k]

    def submit(self, brief: Any) -> str:
        with self._lock:
            self._purge()
            if sum(j["status"] in ("queued", "running") for j in self._jobs.values()) >= self._cap:
                raise Busy("The service is busy; please retry in a minute.")
            jid = secrets.token_urlsafe(12)
            self._jobs[jid] = {"id": jid, "status": "queued", "created": time.time(), "started": None, "finished": None,
                               "steps": [], "result": None, "error": None}
        self._pool.submit(self._run, jid, brief)
        return jid

    def _run(self, jid: str, brief: Any) -> None:
        job = self._jobs[jid]
        job.update(status="running", started=time.time())
        deadline = job["started"] + self._timeout

        def on_event(e: dict) -> None:
            with self._lock:
                steps = job["steps"]
                if e["phase"] == "running":
                    steps.append({**e, "t": round(time.time() - job["started"], 1)})
                else:  # complete the matching running entry
                    for s in reversed(steps):
                        if s["step"] == e["step"]:
                            s.update(phase="done", outcome=e["outcome"], t=round(time.time() - job["started"], 1))
                            break

        try:
            bp = self._runner(brief, on_event, deadline)
            timed_out = time.time() >= deadline
            job.update(status="done" if bp.get("status") != "failed" else "failed", result=bp,
                       error=bp.get("error") if bp.get("status") == "failed" else None)
            if timed_out and bp.get("status") != "complete" and bp.get("status") != "needs_confirmation":
                job.update(status="timeout", error="The run hit its time limit before finishing.")
        except Exception as e:  # noqa: BLE001  never leak internals
            job.update(status="failed", error=self._redact(f"Run failed ({type(e).__name__})."))
        finally:
            job["finished"] = time.time()

    def get(self, jid: str) -> dict[str, Any] | None:
        with self._lock:
            j = self._jobs.get(jid)
            if not j:
                return None
            snap = {k: j[k] for k in ("id", "status", "steps", "error")}
            snap["elapsed_s"] = round((j["finished"] or time.time()) - (j["started"] or j["created"]), 1)
            snap["queued_ahead"] = sum(1 for o in self._jobs.values() if o["status"] in ("queued", "running") and o["created"] < j["created"]) if j["status"] == "queued" else 0
            snap["steps"] = [dict(s) for s in j["steps"]]
            if j["status"] in ("done", "failed", "timeout"):
                snap["result"] = j["result"]
            return snap
