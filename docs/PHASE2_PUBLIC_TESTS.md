# Public deployment test results — https://vibespec.onrender.com (Render Free, Oregon)

Run 2026-10-25 against the real deployment (commit 5bc30e2 + env var set in the dashboard). Harness: `tools/public_checks.py` (black-box, no key needed).

| check | result | detail |
|---|---|---|
| health + key configured | PASS | 422 ms, `qloo_key_configured: true` (key itself never exposed) |
| HEAD / (uptime monitors) | PASS | 200. First deploy returned 501; fixed (commit 5bc30e2) and redeployed |
| cold demo run | PASS | 24.4 s total, first visible step 0.8 s, 12 real steps, 21 live Qloo calls |
| warm rerun | PASS | 2.2 s, 0 live calls, 21 cache hits (disclosed in UI) |
| 3 concurrent distinct cold runs | PASS | finished in 12.1 / 16.9 / 20.6 s; `/healthz` p95 427 ms during load |
| bad input | PASS | 1 anchor -> 400, unknown job -> 404, oversized -> 413, non-JSON -> 400 (the first suite run showed 429 for "oversized" only because the per-IP limiter was already exhausted by earlier submits; re-tested after the window) |
| rate limit | PASS | 429 after 6 submissions per minute |
| idle wake after >15 min | PASS | first request answered in 22.1 s (Render docs say "about one minute"); next demo run 25.1 s with 21 live calls, confirming the cache does not survive spin-down |
| logs | PASS | request line + status only; job ids redacted; log search for api key / X-Api / authorization / bearer / qloo found nothing |
| browser UI end to end | PASS | form -> live progress (8 steps by 9 s) -> 4 chapters, 20 cards, influence table, data-freshness footer |

Observations: a deploy only picks up a newly added env var after a redeploy (the dashboard save did not trigger one; I triggered it). Concurrency capacity (2 running + 3 queued) was not exceeded on the live service; over-capacity behaviour was verified locally. Not tested: mid-job restart on Render, bad-key behaviour on Render (would require changing your key), behaviour after 2026-10-30 (key validity), real mobile networks.
