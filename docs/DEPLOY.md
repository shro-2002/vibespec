# Deploying VibeSpec on Render Free (prepared, NOT deployed)

Nothing below has been run on Render. Facts marked (docs) come from Render's public docs read 2026-10-25; everything else is from local tests (`PHASE2_LOCAL_TESTS.md`).

## Configuration
`render.yaml` in the repo root is the whole config (Blueprint):
- runtime `python`, Python pinned by `.python-version` = `3.12` (docs: `.python-version` may omit the patch version; Render's current default is 3.14.x)
- `buildCommand`: no-op (required by Render for non-Docker services; the app is standard-library only)
- `startCommand`: `python -m vibespec` — binds `0.0.0.0` and `$PORT` (docs: Render sets PORT=10000; service must bind 0.0.0.0)
- `healthCheckPath: /healthz` (docs: 2xx/3xx healthy, 5 s timeout, instance restarted after 60 s of consecutive failures)
- env: `QLOO_API_KEY` (`sync: false`: typed in the dashboard), `VIBESPEC_TRUST_PROXY=1`, `VIBESPEC_DAILY_CALL_CAP=300`, `VIBESPEC_JOB_TIMEOUT=150`
- `plan: free` — verify the exact plan name in the dashboard before creating the service.
Alternative without Blueprint: New > Web Service > connect repo > Runtime Python, same start command and env vars.

## Why a background job + polling
Cold runs take ~36 s (21 live Qloo calls, measured). The browser never waits on one long request: `POST /api/jobs` returns 202 immediately, the UI polls `GET /api/jobs/<id>` every 1.2 s and shows only real agent steps. Worst-case request time is milliseconds, so provider request timeouts (a Render staff reply on the forum mentions 100 min; the docs I read state none) are irrelevant.

## Risks and cost assumptions
| Item | Fact / assumption |
|---|---|
| Cost | $0 on Free. Docs: 750 free instance hours per workspace per month (one always-on service = 744 h). Over bandwidth with no payment method => all Free services suspended for the rest of the month (docs). Decide deliberately whether to add a payment method (avoids suspension, risks overage billing). |
| Spin-down | Docs: after 15 min without inbound traffic; cold start "about one minute". A judge's first visit may wait ~1 min. Say so in the Devpost testing instructions. |
| Keep-warm | An external pinger every <15 min would keep it awake but burns the 750 h budget; unverified whether Render treats this as acceptable. Not set up. |
| Ephemeral disk | Docs: local files lost on restart/redeploy/spin-down. The private Qloo cache and in-memory jobs vanish; each cold start repays ~21 live calls per new brief. A job in flight during a restart ends as "job lost" in the UI (tested path: 404 handling). |
| Quota | `VIBESPEC_DAILY_CALL_CAP=300` ≈ 14 cold runs/day for all visitors. The hackathon key's true limit and whether it stays valid through 2026-11-05 are UNKNOWN; ask Qloo or watch for 401/429 (UI shows a clear message). |
| Single instance | Docs: Free cannot scale out. Capacity 2 concurrent + 3 queued runs; extra submissions get 429 "busy" (tested). |
| Client IP | Per-IP limits trust `X-Forwarded-For` only when `VIBESPEC_TRUST_PROXY=1`; Render's header semantics not verified, so the global daily cap is the real protection. |
| Restarts | Docs: Free instances "may be restarted at any time". |
| Qloo data rules | Server-side private cache only; no Qloo data in the repo; re-read the Qloo terms before submission (not verified here). |

## Cold-start and long-request test plan (run after approval, on the real service)
1. Deploy; open `/healthz` (expect 200, `qloo_key_configured: true`, no key anywhere in the response).
2. Idle 16+ minutes; time first byte of `/` (expect ~60 s wake; record it). Then submit the demo brief: expect first visible step < 2 s after load and completion ~35–45 s, `live_calls ≈ 21`.
3. Repeat immediately: expect `live_calls = 0`, `cache_hits ≈ 21`, ~1 s (cache disclosed in UI).
4. Three browsers/devices at once (including a phone on cellular): all finish or get a clear 429 busy message.
5. Trigger a manual restart mid-job: UI must show "server restarted or job expired", Retry works.
6. Set a bad key temporarily: UI shows "Qloo rejected this server's credentials (HTTP 401)", no raw upstream text.
7. Read Render logs: no key, no request bodies, job ids redacted.
8. Next day: repeat step 2 to catch key expiry/quota changes; again on 2026-11-02 (judging starts) and 2026-11-05.
9. Pass criteria: demo completes < 90 s from a cold wake on three consecutive tries; no secret in logs; every failure shows a human-readable message.

## Fallback if Render Free proves unreliable
The same code runs in any Docker host (`Dockerfile`, stdlib only). Do not switch hosts without verifying secrets handling and long-request behavior first.
