"""Daily call-budget accounting: reservations vs dispatched requests, races, retries, cache hits, failures."""
import threading
import time
import urllib.error

import pytest

import smoke_test
from test_vibespec import Fake, brief, svc
from vibespec import app
from vibespec.budget import DailyBudget
from vibespec.qloo import BudgetExceeded, QlooService


def balanced(b: DailyBudget) -> bool:
    s = b.snapshot()
    return s["reserved"] >= 0 and s["dispatched"] >= 0 and s["dispatched"] + s["reserved"] <= s["cap"]


def test_reserve_and_close_returns_unused_headroom():
    b = DailyBudget(cap=100, per_run=45)
    lease = b.reserve()
    assert lease.grant == 45 and b.snapshot()["reserved"] == 45 and b.snapshot()["dispatched"] == 0
    lease.close(used=6)
    assert b.snapshot() | {"scope": ""} == {"day": b.snapshot()["day"], "cap": 100, "dispatched": 6, "reserved": 0, "available": 94, "scope": ""}


def test_warm_cached_run_consumes_nothing():
    b = DailyBudget(cap=100, per_run=45)
    for _ in range(50):
        b.reserve().close(used=0)
    assert b.snapshot()["dispatched"] == 0 and b.snapshot()["available"] == 100


def test_close_is_idempotent_and_never_negative():
    b = DailyBudget(cap=100, per_run=45)
    lease = b.reserve()
    assert lease.close(10) is True and lease.close(10) is False and lease.close(45) is False
    assert b.snapshot()["dispatched"] == 10 and b.snapshot()["reserved"] == 0
    other = b.reserve()
    other.close(-5)  # nonsense input
    assert b.snapshot()["dispatched"] == 10 and balanced(b)


def test_usage_above_grant_is_clamped_to_the_grant():
    b = DailyBudget(cap=100, per_run=10)
    b.reserve().close(used=999)
    assert b.snapshot()["dispatched"] == 10 and balanced(b)


def test_budget_exhaustion_then_recovery():
    b = DailyBudget(cap=60, per_run=45)
    a, c = b.reserve(), b.reserve()
    assert (a.grant, c.grant) == (45, 15) and b.reserve().grant == 0
    a.close(used=20)  # 25 headroom returned
    d = b.reserve()
    assert d.grant == 25 and balanced(b)
    c.close(15), d.close(25)
    assert b.reserve().grant == 0 and b.snapshot()["dispatched"] == 60


def test_concurrent_reservations_never_exceed_the_cap():
    b = DailyBudget(cap=100, per_run=45)
    leases, violations, gate = [], [], threading.Barrier(40)

    def worker():
        gate.wait()
        lease = b.reserve()
        if not balanced(b):
            violations.append(b.snapshot())
        leases.append(lease)
        time.sleep(0.002)
        lease.close(used=lease.grant // 3)
        if not balanced(b):
            violations.append(b.snapshot())

    ts = [threading.Thread(target=worker) for _ in range(40)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not violations and b.snapshot()["reserved"] == 0 and sum(l.grant for l in leases) >= 100 - 1
    assert b.snapshot()["dispatched"] <= 100


def test_day_rollover_ignores_yesterdays_usage_but_releases_its_reservation():
    day = ["2026-10-25"]
    b = DailyBudget(cap=100, per_run=45, today=lambda: day[0])
    lease = b.reserve()
    day[0] = "2026-10-26"
    assert b.snapshot()["dispatched"] == 0 and b.snapshot()["reserved"] == 45  # still held until the run closes
    lease.close(used=30)
    assert b.snapshot()["dispatched"] == 0 and b.snapshot()["reserved"] == 0


# ---- service-level accounting (attempts, retries, in-flight hard cap) ---------------------------------------------
def test_retries_count_as_dispatched_requests():
    s = QlooService("k", cache_dir=None, budget=20, transport=lambda p, q: {"status": 200, "body": {"results": []}, "latency_ms": 1, "error": None, "attempts": 3})
    s.resolve("x")
    assert s.live_calls == 3


def test_cache_hits_do_not_dispatch():
    s = QlooService("k", cache_dir=None, budget=20, transport=Fake())
    s.resolve("alpha"), s.resolve("alpha"), s.resolve("alpha")
    assert s.live_calls == 1 and s.cache_hits == 2


def test_inflight_reservation_makes_the_run_cap_hard_under_concurrency():
    s = QlooService("k", cache_dir=None, budget=10, transport=lambda p, q: (time.sleep(0.01) or {"status": 200, "body": {"results": []}, "latency_ms": 1, "error": None, "attempts": 3}))
    errors, gate = [], threading.Barrier(8)

    def worker(i):
        gate.wait()
        try:
            s._get("/search", {"query": f"q{i}", "types": "urn:entity:brand", "take": 1})
        except BudgetExceeded:
            errors.append(i)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert s.live_calls <= 10 and s._inflight == 0 and errors  # some calls were declined, none overshot


def test_failed_transport_still_counts_worst_case_and_releases_inflight():
    def boom(p, q):
        raise RuntimeError("network down")

    s = QlooService("k", cache_dir=None, budget=10, transport=boom)
    with pytest.raises(RuntimeError):
        s._get("/search", {"query": "x", "types": "urn:entity:brand", "take": 1})
    assert s._inflight == 0 and s.live_calls == 3


def test_call_reports_attempts_and_honours_the_attempt_cap(monkeypatch):
    sent = []

    def fake_urlopen(req, timeout=0):
        sent.append(1)
        raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, None)

    monkeypatch.setattr(smoke_test.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(smoke_test.time, "sleep", lambda s: None)
    r = smoke_test.call("/search", {"query": "x", "types": "urn:entity:brand", "take": 1}, "k")
    assert r["attempts"] == len(sent) == smoke_test.MAX_RETRIES + 1
    sent.clear()
    r = smoke_test.call("/search", {"query": "x", "types": "urn:entity:brand", "take": 1}, "k", max_attempts=1)
    assert r["attempts"] == len(sent) == 1


# ---- app runner: lease lifecycle for success, failure, timeout, exhaustion --------------------------------------
@pytest.fixture()
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(app.CFG, "key", "k")
    monkeypatch.setattr(app, "BUDGET", DailyBudget(cap=100, per_run=45))
    made = []

    def make(key, cache_dir, budget, deadline):
        s = QlooService(key, tmp_path, budget=budget, deadline=deadline, transport=Fake())
        made.append(s)
        return s

    monkeypatch.setattr(app, "QlooService", make)
    return made


def test_cold_then_warm_run_charges_only_real_calls(wired):
    app.runner(brief(), lambda e: None, time.time() + 60)
    first = app.BUDGET.snapshot()["dispatched"]
    assert first == wired[0].live_calls > 0 and app.BUDGET.snapshot()["reserved"] == 0
    app.runner(brief(), lambda e: None, time.time() + 60)
    assert wired[1].live_calls == 0 and app.BUDGET.snapshot()["dispatched"] == first  # warm run is free


def test_crash_releases_the_reservation_once(wired, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(app, "run", explode)
    with pytest.raises(RuntimeError):
        app.runner(brief(), lambda e: None, time.time() + 60)
    assert app.BUDGET.snapshot()["reserved"] == 0 and app.BUDGET.snapshot()["dispatched"] == 0


def test_timeout_releases_the_unused_reservation(wired):
    bp = app.runner(brief(), lambda e: None, time.time() - 1)  # deadline already passed
    assert bp["status"] != "complete" and wired[0].live_calls == 0
    assert app.BUDGET.snapshot()["reserved"] == 0 and app.BUDGET.snapshot()["dispatched"] == 0


def test_exhausted_budget_blocks_cold_runs_but_serves_warm_ones(wired):
    app.runner(brief(), lambda e: None, time.time() + 60)  # warm the cache
    app.BUDGET.reserve().close(used=0)
    hog = [app.BUDGET.reserve() for _ in range(5)]  # hold everything that is left
    assert app.BUDGET.reserve().grant == 0
    warm = app.runner(brief(), lambda e: None, time.time() + 60)
    assert warm["status"] == "complete" and wired[-1].live_calls == 0
    cold = app.runner(brief(anchors=("Alpha", "Gamma")), lambda e: None, time.time() + 60)
    assert cold["status"] == "failed" and "Daily demo capacity" in cold["error"]
    [h.close(0) for h in hog]
    assert app.BUDGET.snapshot()["reserved"] == 0


def test_concurrent_jobs_never_exceed_the_daily_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(app.CFG, "key", "k")
    monkeypatch.setattr(app, "BUDGET", DailyBudget(cap=60, per_run=45))
    peak = []
    monkeypatch.setattr(app, "QlooService", lambda key, cache_dir, budget, deadline: QlooService(key, tmp_path / str(time.time_ns()), budget=budget, deadline=deadline, transport=Fake()))
    gate = threading.Barrier(6)

    def go():
        gate.wait()
        app.runner(brief(), lambda e: None, time.time() + 60)
        peak.append(app.BUDGET.snapshot())

    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    snap = app.BUDGET.snapshot()
    assert snap["dispatched"] <= 60 and snap["reserved"] == 0 and all(p["dispatched"] + p["reserved"] <= 60 for p in peak)
