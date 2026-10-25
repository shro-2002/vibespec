"""Stdlib web server. GET / (UI), GET /healthz, POST /api/jobs (202 + id), GET /api/jobs/<id> (poll).

Binds 0.0.0.0 on $PORT (Render default 10000). Key only from env QLOO_API_KEY; it is redacted from every response and log line.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .agent import Brief, Constraints, run
from .blueprint import to_markdown
from .jobs import Busy, JobManager
from .qloo import QlooService

STATIC = Path(__file__).parent / "static" / "index.html"
MAX_BODY = 8_000
JOB_ID = re.compile(r"^/api/jobs/([A-Za-z0-9_-]{8,40})$")


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


class Config:
    def __init__(self) -> None:
        self.rate_per_min = env_int("VIBESPEC_RATE_PER_MIN", 6)
        self.poll_per_min = env_int("VIBESPEC_POLL_PER_MIN", 240)
        self.daily_call_cap = env_int("VIBESPEC_DAILY_CALL_CAP", 300)
        self.run_budget = env_int("VIBESPEC_RUN_BUDGET", 45)
        self.job_timeout = env_int("VIBESPEC_JOB_TIMEOUT", 150)
        self.max_running = env_int("VIBESPEC_MAX_RUNNING", 2)
        self.max_queued = env_int("VIBESPEC_MAX_QUEUED", 3)
        self.cache_dir = os.environ.get("VIBESPEC_CACHE_DIR", ".cache")
        self.trust_proxy = os.environ.get("VIBESPEC_TRUST_PROXY", "") == "1"
        self.key = os.environ.get("QLOO_API_KEY", "").strip()


CFG = Config()
_lock = threading.Lock()
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_spent = {"day": time.strftime("%Y-%m-%d"), "calls": 0}


def redact(text: str) -> str:
    return text.replace(CFG.key, "[REDACTED]") if CFG.key else text


def allow(ip: str, kind: str, limit: int) -> bool:
    now = time.time()
    with _lock:
        q = _hits[(ip, kind)]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reserve_budget() -> int:
    """Daily live-call cap shared by all visitors (protects the hackathon key quota). Returns this run's budget."""
    with _lock:
        today = time.strftime("%Y-%m-%d")
        if _spent["day"] != today:
            _spent.update(day=today, calls=0)
        grant = max(0, min(CFG.run_budget, CFG.daily_call_cap - _spent["calls"]))
        _spent["calls"] += grant
        return grant


def parse_brief(d: dict) -> Brief:
    c = d.get("constraints") or {}

    def num(key: str, cast):
        return cast(c[key]) if c.get(key) not in (None, "") else None

    ex = c.get("exclude_terms")
    terms = tuple(x.strip() for x in ex.split(",") if x.strip()) if isinstance(ex, str) else tuple(str(x) for x in (ex or ()))
    cons = Constraints(num("max_place_price_level", int), num("min_place_rating", float), num("min_book_year", int), terms, num("amenity_unit_budget_usd", float))
    anchors = tuple(str(a).strip() for a in (d.get("anchors") or []) if str(a).strip())
    return Brief(str(d.get("concept", "")).strip(), str(d.get("city", "")).strip(), anchors, str(d.get("goals", "")).strip(), cons,
                 {str(k): str(v) for k, v in (d.get("confirmed") or {}).items()})


def runner(brief: Brief, on_event, deadline: float) -> dict:
    grant = reserve_budget()
    if grant == 0:
        return {"status": "failed", "error": "Daily demo capacity reached; try again tomorrow.", "trace": [], "anchors": [], "brief": {}}
    svc = QlooService(CFG.key, CFG.cache_dir, budget=grant, deadline=deadline)
    bp = run(brief, svc, on_event=on_event)
    bp["markdown"] = to_markdown(bp)
    return bp


JOBS = JobManager(runner, CFG.max_running, CFG.max_queued, job_timeout_s=CFG.job_timeout, redact=redact)


class Handler(BaseHTTPRequestHandler):
    server_version = "VibeSpec"

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        for k, v in {"Content-Type": ctype, "Content-Length": str(len(body)), "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                     "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'",
                     "Cache-Control": "no-store"}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":  # HEAD gets headers only (uptime monitors and link checkers use it)
            self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, redact(json.dumps(obj, default=str)).encode())

    def _ip(self) -> str:
        if CFG.trust_proxy:
            return self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        return self.client_address[0]

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/healthz":
            return self._json(200, {"ok": True, "qloo_key_configured": bool(CFG.key)})
        if path == "/":
            return self._send(200, STATIC.read_bytes(), "text/html; charset=utf-8")
        m = JOB_ID.match(path)
        if m:
            if not allow(self._ip(), "poll", CFG.poll_per_min):
                return self._json(429, {"error": "Polling too fast."})
            snap = JOBS.get(m.group(1))
            return self._json(200, snap) if snap else self._json(404, {"error": "Job not found (it may have expired or the server restarted)."})
        self._json(404, {"error": "not found"})

    do_HEAD = do_GET  # noqa: N815

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/jobs":
            return self._json(404, {"error": "not found"})
        if not CFG.key:
            return self._json(503, {"error": "Server is not configured with a Qloo key."})
        if not allow(self._ip(), "submit", CFG.rate_per_min):
            return self._json(429, {"error": "Too many requests; wait a minute."})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY:
                return self._json(413, {"error": "Request body too large or empty."})
            brief = parse_brief(json.loads(self.rfile.read(n)))
            brief.validate()
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError) as e:
            return self._json(400, {"error": f"Invalid brief: {e}"})
        try:
            self._json(202, {"job_id": JOBS.submit(brief)})
        except Busy as e:
            self._json(429, {"error": str(e)})

    def log_message(self, fmt: str, *args) -> None:  # request line + status only; never headers or bodies
        line = f"{self.command} {re.sub(r'/api/jobs/[A-Za-z0-9_-]+', '/api/jobs/<id>', self.path.split('?')[0])} {args[1] if len(args) > 1 else ''}"
        print(redact(line), flush=True)


def main() -> None:
    port = env_int("PORT", 10000)
    print(f"VibeSpec listening on 0.0.0.0:{port} (key configured: {bool(CFG.key)})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
