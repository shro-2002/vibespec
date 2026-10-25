#!/usr/bin/env python3
"""Synthetic Qloo stand-in for failure/latency testing (loopback only). No real Qloo data.
Control: GET /__mode?set=ok|429x2|500|malformed|empty|echo-key&delay=0.5"""
import json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

STATE = {"mode": "ok", "delay": 0.0, "n": 0}
LOCK = threading.Lock()


def eid(prefix, i):
    return f"{prefix}-{i:04d}".upper()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body, raw=False, headers=None):
        data = body.encode() if raw else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/__mode":
            with LOCK:
                STATE.update(mode=q.get("set", "ok"), delay=float(q.get("delay", 0)), n=0)
            return self.reply(200, {"ok": True, **STATE})
        with LOCK:
            STATE["n"] += 1
            n, mode = STATE["n"], STATE["mode"]
        time.sleep(STATE["delay"])
        if mode == "429x2" and n <= 2:
            return self.reply(429, {"error": "rate limited"}, headers={"Retry-After": "1"})
        if mode == "500":
            return self.reply(500, {"error": "boom"})
        if mode == "malformed":
            return self.reply(200, "<<not json>>", raw=True)
        if mode == "echo-key":
            return self.reply(401, {"error": f"bad key {self.headers.get('X-Api-Key')}"})
        if u.path == "/search":
            name = q.get("query", "x")
            return self.reply(200, {"results": [{"entity_id": eid("ANCH", abs(hash(name)) % 9999), "name": name, "disambiguation": "synthetic"}]})
        if mode == "empty":
            return self.reply(200, {"success": True, "results": {"entities": []}, "query": {}})
        dom = q["filter.type"].split(":")[-1]
        anchors = q.get("signal.interests.entities", "").split(",")
        start = (int(q.get("page", 1)) - 1) * 20
        ents = []
        for i in range(start, start + int(q.get("take", 20))):
            e = {"entity_id": eid(dom[:3], i), "name": f"Synthetic {dom} {i}", "properties": {"price_level": 1 + i % 4, "business_rating": 3.5 + (i % 4) * 0.4,
                 "publication_year": 2005 + i % 20, "price_range_usd_min": 10 + 10 * (i % 5), "address": f"{i} Test St"},
                 "query": {"affinity": 1 - i / 100, "explainability": {"signal.interests.entities": [{"entity_id": a, "score": 1 / len(anchors)} for a in anchors]}}}
            if dom == "place":
                e["location"] = {"lat": 1.0, "lon": 2.0, "geohash": f"gh{i}"}
            ents.append(e)
        return self.reply(200, {"success": True, "results": {"entities": ents}, "query": {}})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
