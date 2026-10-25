"""Job manager + HTTP layer tests (offline; fake runner, no Qloo)."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from vibespec import app
from vibespec.jobs import Busy, JobManager


def wait(jm, jid, until=("done", "failed", "timeout"), t=5):
    end = time.time() + t
    while time.time() < end:
        s = jm.get(jid)
        if s["status"] in until:
            return s
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def ok_runner(brief, on_event, deadline):
    on_event({"step": 1, "tool": "resolve_anchor", "arg": "x", "phase": "running", "outcome": None})
    on_event({"step": 1, "tool": "resolve_anchor", "arg": "x", "phase": "done", "outcome": "resolved"})
    return {"status": "complete", "trace": []}


def test_job_success_exposes_only_real_steps():
    jm = JobManager(ok_runner)
    s = wait(jm, jm.submit({}))
    assert s["status"] == "done" and s["result"]["status"] == "complete"
    assert [x["phase"] for x in s["steps"]] == ["done"] and s["steps"][0]["outcome"] == "resolved"


def test_busy_when_capacity_exceeded():
    gate = threading.Event()
    jm = JobManager(lambda b, e, d: gate.wait(5) and {"status": "complete"}, max_running=1, max_queued=1)
    a, b = jm.submit({}), jm.submit({})
    with pytest.raises(Busy):
        jm.submit({})
    assert jm.get(b)["status"] == "queued" and jm.get(b)["queued_ahead"] == 1
    gate.set()
    wait(jm, a), wait(jm, b)


def test_timeout_is_labelled_and_never_fakes_a_result():
    def slow(brief, on_event, deadline):
        time.sleep(0.15)
        return {"status": "failed", "error": "x", "trace": []}

    jm = JobManager(slow, job_timeout_s=0.05)
    s = wait(jm, jm.submit({}))
    assert s["status"] == "timeout" and "time limit" in s["error"]


def test_runner_exception_is_generic_and_redacted():
    def boom(brief, on_event, deadline):
        raise RuntimeError("SECRET123 leaked")

    jm = JobManager(boom, redact=lambda s: s.replace("SECRET123", "[REDACTED]"))
    s = wait(jm, jm.submit({}))
    assert s["status"] == "failed" and "SECRET123" not in json.dumps(s) and "leaked" not in s["error"]


def test_finished_jobs_expire():
    jm = JobManager(ok_runner, ttl_s=0)
    jid = jm.submit({})
    wait(jm, jid)
    time.sleep(0.01)
    jm.submit({})  # purge runs on submit
    assert jm.get(jid) is None


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setattr(app.CFG, "key", "KEY-XYZ")
    monkeypatch.setattr(app, "JOBS", JobManager(lambda b, e, d: {"status": "complete", "echo": "KEY-XYZ", "trace": []}))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def req(url, data=None):
    r = urllib.request.Request(url, json.dumps(data).encode() if data is not None else None, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as x:
            return x.status, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


GOOD = {"concept": "H", "city": "X", "anchors": ["A", "B"], "goals": ""}


def test_http_submit_poll_redacts_secret(server):
    code, body = req(server + "/api/jobs", GOOD)
    assert code == 202
    jid = json.loads(body)["job_id"]
    for _ in range(100):
        code, body = req(f"{server}/api/jobs/{jid}")
        if json.loads(body)["status"] == "done":
            break
        time.sleep(0.02)
    assert "KEY-XYZ" not in body and "[REDACTED]" in body


def test_http_validation_and_unknown(server):
    assert req(server + "/api/jobs", {"anchors": ["only"]})[0] == 400
    assert req(server + "/api/jobs", {**GOOD, "constraints": {"max_place_price_level": "abc"}})[0] == 400
    assert req(server + "/api/jobs/doesnotexist1")[0] == 404
    assert req(server + "/healthz")[0] == 200 and "KEY-XYZ" not in req(server + "/healthz")[1]
    big = urllib.request.Request(server + "/api/jobs", b"{" + b" " * 9000 + b"}", {"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(big)
    assert e.value.code == 413


def test_parse_brief_constraints():
    b = app.parse_brief({**GOOD, "constraints": {"max_place_price_level": "2", "exclude_terms": "a, b", "min_place_rating": ""}})
    assert b.constraints.max_place_price_level == 2 and b.constraints.exclude_terms == ("a", "b") and b.constraints.min_place_rating is None


def test_head_requests_are_supported(server):
    r = urllib.request.Request(server + "/healthz", method="HEAD")
    with urllib.request.urlopen(r) as x:
        assert x.status == 200 and x.read() == b"" and x.headers["X-Content-Type-Options"] == "nosniff"
