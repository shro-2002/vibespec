#!/usr/bin/env python3
"""Black-box checks against a deployed VibeSpec URL. Needs no key (the server holds it).
usage: python3 tools/public_checks.py https://host [idle]   -> prints a markdown table"""
import json, sys, threading, time, urllib.error, urllib.request
from pathlib import Path

BASE = sys.argv[1].rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
ROWS = []


def http(path, data=None, timeout=60, method=None):
    r = urllib.request.Request(BASE + path, json.dumps(data).encode() if data is not None else None, {"Content-Type": "application/json"}, method=method)
    t = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x:
            return x.status, x.read().decode(), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), time.time() - t


def run_job(brief, poll=1.0, timeout=240):
    t0 = time.time()
    code, body, _ = http("/api/jobs", brief)
    if code != 202:
        return {"code": code, "body": body}
    jid = json.loads(body)["job_id"]
    first = None
    while time.time() - t0 < timeout:
        _, b, _ = http(f"/api/jobs/{jid}")
        j = json.loads(b)
        if j["steps"] and first is None:
            first = round(time.time() - t0, 1)
        if j["status"] in ("done", "failed", "timeout"):
            res = j.get("result") or {}
            return {"code": 202, "status": j["status"], "total": round(time.time() - t0, 1), "first": first, "steps": len(j["steps"]), "result": res, "error": j.get("error"), "raw": b}
        time.sleep(poll)
    return {"code": 202, "status": "client-timeout"}


def row(name, ok, detail):
    ROWS.append((name, "PASS" if ok else "FAIL", detail))
    print(("PASS " if ok else "FAIL ") + name + " — " + detail, flush=True)


def brief(name):
    d = json.load(open(ROOT / "briefs" / f"{name}.json"))
    return d


def main():
    idle = len(sys.argv) > 2 and sys.argv[2] == "idle"
    if idle:
        t = time.time()
        code, body, dt = http("/healthz", timeout=180)
        row("idle wake: first request after >=15 min idle", code == 200, f"HTTP {code} after {dt:.1f}s (wall {time.time()-t:.1f}s)")
        r = run_job(brief("demo_nyc"))
        p = (r.get("result") or {}).get("provenance", {})
        row("post-wake demo run", r.get("status") == "done", f"{r.get('total')}s, live_calls={p.get('live_calls')}, cache_hits={p.get('cache_hits')}")
    else:
        code, body, dt = http("/healthz")
        row("health + key configured", code == 200 and '"qloo_key_configured": true' in body, f"{body.strip()} in {dt*1000:.0f} ms")
        code, body, dt = http("/", method="HEAD")
        row("HEAD / (uptime monitors)", code == 200, f"HTTP {code}")
        r = run_job(brief("demo_nyc"))
        res, p = r.get("result") or {}, (r.get("result") or {}).get("provenance", {})
        row("cold demo run via public URL", r.get("status") == "done" and res.get("status") == "complete" and len(res.get("domains", {})) == 4,
            f"{r.get('total')}s total, first step {r.get('first')}s, {r.get('steps')} steps, live_calls={p.get('live_calls')}, cache_hits={p.get('cache_hits')}")
        r2 = run_job(brief("demo_nyc"))
        p2 = (r2.get("result") or {}).get("provenance", {})
        row("warm rerun discloses cache", r2.get("status") == "done" and p2.get("live_calls") == 0 and p2.get("cache_hits", 0) > 0, f"{r2.get('total')}s, live={p2.get('live_calls')}, cache={p2.get('cache_hits')}")
        out, lock = [], threading.Lock()

        def go(name):
            x = run_job(brief(name))
            with lock:
                out.append((name, x.get("status"), x.get("total"), (x.get("result") or {}).get("status")))

        ts = [threading.Thread(target=go, args=(n,)) for n in ("eval_london", "eval_la", "eval_chicago")]
        lat = []
        [t.start() for t in ts]
        while any(t.is_alive() for t in ts):
            lat.append(http("/healthz")[2])
            time.sleep(0.5)
        lat.sort()
        row("3 concurrent distinct cold runs", len(out) == 3 and all(o[1] == "done" and o[3] == "complete" for o in out),
            f"{[(o[0], o[2]) for o in out]}; /healthz p95 {lat[int(len(lat)*0.95)-1]*1000:.0f} ms during load")
        c1 = http("/api/jobs", {"anchors": ["only"]})[0]
        c2 = http("/api/jobs/doesnotexist1")[0]
        big = urllib.request.Request(BASE + "/api/jobs", b"{" + b" " * 9000 + b"}", {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(big)
            c3 = 200
        except urllib.error.HTTPError as e:
            c3 = e.code
        row("bad input handling", (c1, c2, c3) == (400, 404, 413), f"1 anchor->{c1}, unknown job->{c2}, oversized->{c3}")
        codes = [http("/api/jobs", {"concept": "x", "city": "y", "anchors": ["a"]})[0] for _ in range(8)]
        row("rate limit reachable", 429 in codes, f"codes {codes}")
    (ROOT / "private" / ("public_idle.md" if idle else "public_checks.md")).write_text("\n".join(f"| {n} | {s} | {d} |" for n, s, d in ROWS))
    sys.exit(any(s == "FAIL" for _, s, _ in ROWS))


main()
