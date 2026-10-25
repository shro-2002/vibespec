# Phase 2 — production-style local test results

Generated 2026-10-25 15:04. Server run in a clean environment (only PATH, PYTHONPATH and host-style vars). Live Qloo used for cold run, timeout, 401; synthetic upstream for the rest.

| check | result | detail |
|---|---|---|
| startup + health on $PORT | PASS | ready in 0.12s on PORT=10000; healthz {"ok": true, "qloo_key_configured": true} |
| binds 0.0.0.0 (all interfaces) | PASS | lsof shows *:10000 |
| UI loads fast | PASS | 12628 bytes in 1 ms, zero external requests |
| UI has no external assets | PASS | no external src/href |
| full form submission, live Qloo, cold cache | PASS | status=done, total 36.2s, first visible step at 0.0s, 12 real steps, live_calls=21, cache_hits=0 |
| cold run exceeds a typical 30s serverless limit (documents why polling is required) | PASS | 36.2s |
| warm rerun discloses cache use | PASS | 1.0s, live_calls=0, cache_hits=21 |
| missing key -> clear 503, no crash | PASS | {"error": "Server is not configured with a Qloo key."} |
| timeout handled: labelled, partial real steps, no fake result | PASS | status=timeout after 5.0s with 4 real steps; error='The run hit its time limit before finishing.' |
| invalid key (real 401) -> graceful failure message | PASS | status=failed error='Qloo rejected this server's credentials (HTTP 401)' |
| baseline against synthetic upstream | PASS | 3.1s |
| upstream 429 twice then OK: retries recover | PASS | status=done result=complete 4.9s error='None' warnings=['No supplier prices, inventory, contractual rights, or revenue impact were verified. Qloo supplies cultural affinity and descriptive metadata only.'] |
| upstream 500 persistently: graceful, no crash | PASS | status=failed result=failed 13.1s error='Qloo is temporarily unavailable (HTTP 500)' warnings=[] |
| upstream malformed JSON: clear failure, not a misleading result | PASS | status=failed result=failed 0.3s error='Qloo returned an unexpected response' warnings=[] |
| upstream empty results: completes with warnings | PASS | status=done result=complete 4.6s error='None' warnings=['artist: empty result', 'book: empty result'] |
| retry after upstream failure succeeds on same server | PASS | first=failed/failed, retry=done |
| concurrency: capacity enforced, accepted jobs all finish, health stays responsive | PASS | 7 simultaneous submits -> 4 accepted, 3 rejected(429); 4/4 finished; /healthz p95 1 ms during load |
| per-IP submit rate limit | PASS | codes [202, 202, 202, 429, 429] |
| secret redaction when upstream echoes the key | PASS | status=failed, error='Qloo rejected this server's credentials (HTTP 401)'; key absent from job JSON and server log |
| secret scan over all captured responses and server logs | PASS | 286 captured bodies/logs scanned for the real key and the fake echo key; matches: 0 |
