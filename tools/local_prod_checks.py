#!/usr/bin/env python3
"""Production-style local checks. Real Qloo for cold-run/timeout/401 checks (needs QLOO_API_KEY in env); a synthetic local
fake for failure, retry, concurrency and redaction checks (spends no quota). Writes docs/PHASE2_LOCAL_TESTS.md.
The server is started in a clean environment containing only what a host would inject."""
import json, os, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_KEY = os.environ.get("QLOO_API_KEY", "")
ROWS, CAPTURED = [], []  # CAPTURED: every response body / log we saw, scanned for secrets at the end
PY = sys.executable


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(port, path, data=None, timeout=30):
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(data).encode() if data is not None else None, {"Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            body = x.read().decode()
            code = x.status
    except urllib.error.HTTPError as e:
        body, code = e.read().decode(), e.code
    CAPTURED.append(body)
    return code, body, time.time() - t


def start(env_extra, tag):
    log = open(tempfile.gettempdir() + f"/vibespec_{tag}.log", "w+")
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(ROOT), **env_extra}  # NOT the developer's full environment
    port = int(env_extra.get("PORT") or free_port())
    env["PORT"] = str(port)
    t = time.time()
    proc = subprocess.Popen([PY, "-m", "vibespec"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            http(port, "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    return proc, port, log, time.time() - t


def stop(proc, log):
    proc.terminate()
    proc.wait(5)
    log.seek(0)
    text = log.read()
    CAPTURED.append(text)
    return text


def run_job(port, brief, timeout=200, poll=1.0):
    t0 = time.time()
    code, body, _ = http(port, "/api/jobs", brief)
    if code != 202:
        return {"submit_code": code, "body": body}
    jid = json.loads(body)["job_id"]
    first_step, seen = None, []
    while time.time() - t0 < timeout:
        _, b, _ = http(port, f"/api/jobs/{jid}")
        j = json.loads(b)
        if j["steps"] and first_step is None:
            first_step = round(time.time() - t0, 2)
        seen = j["steps"]
        if j["status"] in ("done", "failed", "timeout"):
            return {"submit_code": 202, "status": j["status"], "total_s": round(time.time() - t0, 1), "first_step_s": first_step, "steps": len(seen),
                    "error": j.get("error"), "result": j.get("result"), "raw": b}
        time.sleep(poll)
    return {"submit_code": 202, "status": "client-timeout", "total_s": timeout}


def row(name, ok, detail):
    ROWS.append((name, "PASS" if ok else "FAIL", detail))
    print(("PASS " if ok else "FAIL ") + name + " — " + detail, flush=True)


LIVE = {"concept": "Quiet 40-room boutique hotel for creative travellers", "city": "New York City", "anchors": ["Muji", "Aesop", "Patagonia"],
        "goals": "calm sound, a small library, natural amenities, places to explore on foot",
        "constraints": {"max_place_price_level": 2, "min_place_rating": 4.2, "min_book_year": 2012, "amenity_unit_budget_usd": 20, "exclude_terms": "Starbucks"}}
FAKE = {"concept": "Test hotel", "city": "Testville", "anchors": ["Alpha", "Beta"], "goals": "", "constraints": {"max_place_price_level": 2}}


def fake_server():
    port = free_port()
    p = subprocess.Popen([PY, str(ROOT / "tools" / "fake_qloo.py"), str(port)])
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/__mode?set=ok", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    return p, port


def mode(fport, m, delay=0.0):
    urllib.request.urlopen(f"http://127.0.0.1:{fport}/__mode?set={m}&delay={delay}", timeout=2).read()


def main():
    if not REAL_KEY:
        sys.exit("BLOCKED: QLOO_API_KEY not set (needed for the live checks)")
    cache = tempfile.mkdtemp(prefix="vibespec_cache_")
    base_env = {"QLOO_API_KEY": REAL_KEY, "VIBESPEC_CACHE_DIR": cache, "VIBESPEC_TRUST_PROXY": "1", "VIBESPEC_DAILY_CALL_CAP": "300", "PORT": "10000"}

    # 1+2: startup, bind, health, production-style env, UI load
    proc, port, log, boot = start(base_env, "main")
    out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
    code, body, _ = http(port, "/healthz")
    ui_code, ui, ui_t = http(port, "/")
    row("startup + health on $PORT", code == 200 and '"qloo_key_configured": true' in body, f"ready in {boot:.2f}s on PORT={port}; healthz {body.strip()}")
    row("binds 0.0.0.0 (all interfaces)", "*:" + str(port) in out, "lsof shows " + (out.splitlines()[-1].split()[-2] if out else "n/a"))
    row("UI loads fast", ui_code == 200 and ui_t < 1.0 and "<form" in ui, f"{len(ui)} bytes in {ui_t*1000:.0f} ms, zero external requests")
    ext = [u for u in ("http://", "https://") if f'src="{u}' in ui or f"href=\"{u}" in ui]
    row("UI has no external assets", not ext, "no external src/href")

    # 3: full cold live run (fresh cache), 60s behaviour
    r = run_job(port, LIVE)
    res = r.get("result") or {}
    prov = res.get("provenance", {})
    row("full form submission, live Qloo, cold cache", r.get("status") == "done" and res.get("status") == "complete" and len(res.get("domains", {})) == 4,
        f"status={r.get('status')}, total {r.get('total_s')}s, first visible step at {r.get('first_step_s')}s, {r.get('steps')} real steps, "
        f"live_calls={prov.get('live_calls')}, cache_hits={prov.get('cache_hits')}")
    row("cold run exceeds a typical 30s serverless limit (documents why polling is required)", (r.get("total_s") or 0) > 30, f"{r.get('total_s')}s")
    # 5a: health stays responsive while a slow job runs (use a second cold-ish fake later); here: warm re-run returns fast and truthful about cache
    r2 = run_job(port, LIVE)
    p2 = (r2.get("result") or {}).get("provenance", {})
    row("warm rerun discloses cache use", r2.get("status") == "done" and p2.get("live_calls") == 0 and p2.get("cache_hits", 0) > 0,
        f"{r2.get('total_s')}s, live_calls={p2.get('live_calls')}, cache_hits={p2.get('cache_hits')}")
    log_main = stop(proc, log)

    # no-key server: graceful
    pn, pnp, ln, _ = start({"VIBESPEC_CACHE_DIR": cache, "PORT": str(free_port())}, "nokey")
    c, b, _ = http(pnp, "/api/jobs", FAKE)
    row("missing key -> clear 503, no crash", c == 503, b.strip()[:90])
    stop(pn, ln)

    # 4: job timeout with real Qloo
    pt, ptp, lt, _ = start({**base_env, "PORT": str(free_port()), "VIBESPEC_JOB_TIMEOUT": "4", "VIBESPEC_CACHE_DIR": tempfile.mkdtemp(prefix="vs_to_")}, "timeout")
    rt = run_job(ptp, LIVE, timeout=90)
    row("timeout handled: labelled, partial real steps, no fake result", rt.get("status") == "timeout" and rt.get("steps", 0) >= 1 and (rt.get("result") or {}).get("status") != "complete",
        f"status={rt.get('status')} after {rt.get('total_s')}s with {rt.get('steps')} real steps; error='{rt.get('error')}'")
    stop(pt, lt)

    # invalid key against real Qloo
    pk, pkp, lk, _ = start({**base_env, "PORT": str(free_port()), "QLOO_API_KEY": "invalid-key-test-0000", "VIBESPEC_CACHE_DIR": tempfile.mkdtemp(prefix="vs_bad_")}, "badkey")
    rk = run_job(pkp, LIVE, timeout=60)
    row("invalid key (real 401) -> graceful failure message", rk.get("status") == "failed" and "401" in (rk.get("error") or "") and "API keys mismatch" not in (rk.get("error") or ""), f"status={rk.get('status')} error='{rk.get('error')}'")
    stop(pk, lk)

    # fake-Qloo based checks (no quota)
    fp, fport = fake_server()
    fenv = {**base_env, "QLOO_BASE_URL": f"http://127.0.0.1:{fport}", "QLOO_API_KEY": "FAKE-SECRET-KEY-98765", "VIBESPEC_CACHE_DIR": tempfile.mkdtemp(prefix="vs_fake_")}

    def fresh(extra=None, tag="fake"):
        fenv["VIBESPEC_CACHE_DIR"] = tempfile.mkdtemp(prefix="vs_fake_")
        return start({**fenv, "PORT": str(free_port()), **(extra or {})}, tag)

    mode(fport, "ok")
    s, sp, sl, _ = fresh()
    ok = run_job(sp, FAKE, poll=0.3)
    row("baseline against synthetic upstream", ok.get("status") == "done" and ok["result"]["status"] == "complete", f"{ok.get('total_s')}s")
    stop(s, sl)

    for m, label, check in [("429x2", "upstream 429 twice then OK: retries recover", lambda r: r.get("status") == "done" and r["result"]["status"] == "complete"),
                            ("500", "upstream 500 persistently: graceful, no crash", lambda r: r.get("status") == "failed" and "HTTP 500" in (r.get("error") or "") and "boom" not in (r.get("error") or "")),
                            ("malformed", "upstream malformed JSON: clear failure, not a misleading result", lambda r: r.get("status") == "failed" and "unexpected response" in (r.get("error") or "")),
                            ("empty", "upstream empty results: completes with warnings", lambda r: r.get("status") == "done")]:
        mode(fport, m)
        s, sp, sl, _ = fresh(tag=m)
        r = run_job(sp, FAKE, poll=0.3, timeout=120)
        mw = (r.get("result") or {}).get("missing_data", [])[:2]
        row(label, check(r), f"status={r.get('status')} result={((r.get('result') or {}).get('status'))} {r.get('total_s')}s error='{r.get('error')}' warnings={mw}")
        stop(s, sl)

    # retry button semantics: after failure the same server accepts a new submission once upstream recovers
    mode(fport, "500")
    s, sp, sl, _ = fresh(tag="retry")
    r_bad = run_job(sp, FAKE, poll=0.3, timeout=120)
    mode(fport, "ok")
    r_ok = run_job(sp, FAKE, poll=0.3)
    row("retry after upstream failure succeeds on same server", r_bad.get("status") in ("done", "failed") and r_ok.get("status") == "done" and r_ok["result"]["status"] == "complete",
        f"first={r_bad.get('status')}/{(r_bad.get('result') or {}).get('status')}, retry={r_ok.get('status')}")
    stop(s, sl)

    # concurrency: slow upstream so runs overlap; 2 running + 2 queued, extra rejected; health stays fast
    mode(fport, "ok", delay=0.4)
    s, sp, sl, _ = fresh({"VIBESPEC_MAX_RUNNING": "2", "VIBESPEC_MAX_QUEUED": "2", "VIBESPEC_RATE_PER_MIN": "100"}, "conc")
    codes, ids, lock = [], [], threading.Lock()

    def sub():
        c, b, _ = http(sp, "/api/jobs", FAKE)
        with lock:
            codes.append(c)
            if c == 202:
                ids.append(json.loads(b)["job_id"])

    ts = [threading.Thread(target=sub) for _ in range(7)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    lat = []
    t_end = time.time() + 6
    while time.time() < t_end:
        lat.append(http(sp, "/healthz")[2])
        time.sleep(0.2)
    done = 0
    for _ in range(200):
        sts = [json.loads(http(sp, f"/api/jobs/{i}")[1])["status"] for i in ids]
        if all(x in ("done", "failed", "timeout") for x in sts):
            done = sts.count("done")
            break
        time.sleep(0.5)
    lat.sort()
    row("concurrency: capacity enforced, accepted jobs all finish, health stays responsive",
        codes.count(202) == 4 and codes.count(429) == 3 and done == 4 and lat[int(len(lat) * 0.95) - 1] < 0.25,
        f"7 simultaneous submits -> {codes.count(202)} accepted, {codes.count(429)} rejected(429); {done}/4 finished; /healthz p95 {lat[int(len(lat)*0.95)-1]*1000:.0f} ms during load")
    stop(s, sl)
    mode(fport, "ok")
    s, sp, sl, _ = fresh({"VIBESPEC_RATE_PER_MIN": "3"}, "rate")
    cs = [http(sp, "/api/jobs", FAKE)[0] for _ in range(5)]
    row("per-IP submit rate limit", cs.count(429) >= 1, f"codes {cs}")
    stop(s, sl)

    # secret redaction: upstream echoes the key back in its 401 body
    mode(fport, "echo-key")
    s, sp, sl, _ = fresh(tag="echo")
    re_ = run_job(sp, FAKE, poll=0.3, timeout=60)
    log_echo = stop(s, sl)
    row("secret redaction when upstream echoes the key", "FAKE-SECRET-KEY-98765" not in (re_.get("raw") or "") + log_echo and "bad key" not in (re_.get("error") or ""),
        f"status={re_.get('status')}, error='{re_.get('error')}'; key absent from job JSON and server log")
    fp.terminate()

    leaked = [i for i, t in enumerate(CAPTURED) if REAL_KEY in t or "FAKE-SECRET-KEY-98765" in t.replace("[REDACTED]", "")]
    row("secret scan over all captured responses and server logs", not leaked, f"{len(CAPTURED)} captured bodies/logs scanned for the real key and the fake echo key; matches: {len(leaked)}")

    L = ["# Phase 2 — production-style local test results", "", f"Generated {time.strftime('%Y-%m-%d %H:%M')}. Server run in a clean environment (only PATH, PYTHONPATH and host-style vars). Live Qloo used for cold run, timeout, 401; synthetic upstream for the rest.", "",
         "| check | result | detail |", "|---|---|---|"] + [f"| {n} | {s} | {d.replace('|', '/')} |" for n, s, d in ROWS]
    (ROOT / "docs" / "PHASE2_LOCAL_TESTS.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    sys.exit(any(s == "FAIL" for _, s, _ in ROWS))


if __name__ == "__main__":
    main()
