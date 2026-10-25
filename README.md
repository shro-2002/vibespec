# VibeSpec

Evidence-first cultural experience blueprints for boutique hotels, built on the [Qloo](https://www.qloo.com) Insights API for the Qloo Agentic Hackathon 2026.

Give a hotel concept, a city and 2-3 cultural anchors (brands). A bounded, rule-based agent loop (no LLM planner) resolves the anchors, queries Qloo for music, books, amenity brands and local places, checks your constraints, revises its queries from rejection evidence, and returns an inspectable blueprint: selected options with per-anchor attribution, rejected alternatives with reasons, missing-data warnings, a leave-one-out influence table and the full decision trace.

**What it does not do:** Qloo provides cultural affinity and descriptive metadata only. VibeSpec makes no claim about prices, inventory, contractual rights or revenue. Budget figures are your own assumptions or labelled "indicative".

## Run locally
Python 3.10+, standard library only.
```bash
export QLOO_API_KEY=...        # server-side only; get one via the hackathon developer guide
python3 -m vibespec            # http://localhost:10000  (set PORT to change)
```
Offline tests (no key, no network):
```bash
pip install -r requirements-dev.txt && python3 -m pytest -q
```
CLI: `python3 run_brief.py briefs/demo_nyc.json --md`

## Configuration (environment)
| Variable | Default | Meaning |
|---|---|---|
| `QLOO_API_KEY` | – | required for live runs; never logged or returned (redacted) |
| `PORT` | 10000 | listens on 0.0.0.0 |
| `VIBESPEC_DAILY_CALL_CAP` | 300 | Qloo HTTP requests (retries included) per day, all visitors, this process only |
| `VIBESPEC_RUN_BUDGET` | 45 | live calls per run |
| `VIBESPEC_JOB_TIMEOUT` | 150 | seconds before a run is cut off (labelled timeout) |
| `VIBESPEC_MAX_RUNNING` / `VIBESPEC_MAX_QUEUED` | 2 / 3 | concurrency; extra submissions get 429 |
| `VIBESPEC_RATE_PER_MIN` | 6 | per-IP submissions |
| `VIBESPEC_TRUST_PROXY` | off | set `1` behind a trusted proxy to use X-Forwarded-For |
| `VIBESPEC_CACHE_DIR` | `.cache` | private response cache (contains Qloo data; never commit) |

## Call-budget accounting
A run reserves up to `VIBESPEC_RUN_BUDGET` requests, spends only what it dispatches (cache hits cost nothing; every HTTP attempt, retries included, counts), and always returns the unused reservation exactly once, whether it succeeds, fails, times out or crashes. When the day's budget is spent, runs that can be answered from the private cache still work; new Qloo lookups are declined with a clear message. `/healthz` shows `dispatched`, `reserved` and `available`.

**Limits:** the counter is process-local. A restart or redeploy resets it to zero, and it knows nothing about Qloo's real quota or other users of the same key. It protects the key from this app's own traffic; it is not durable quota protection.

## How it works
`vibespec/qloo.py` resolve + query service (typed results, retries, cache, budget, deadline) · `agent.py` tool loop and constraint checks · `blueprint.py` assembly/Markdown · `jobs.py` background jobs + polling · `app.py` + `static/index.html` UI · `llm_source.py` Qloo-free candidate source used only for the controlled evaluation.
Findings worth knowing: a brand can be accepted by Qloo yet silently ignored for a domain (detected through explainability and disclosed); HTTP 400 means no anchor was valid; explainability attribution is only informative with 2+ anchors.

## Docs
`docs/PHASE0_REPORT.md`, `MULTI_ANCHOR_REPORT.md`, `PHASE1_REPORT.md`, `PHASE2_LOCAL_TESTS.md`, `EVAL_CONTROLLED_REPORT.md`, `AGENTIC_AUDIT.md`, `DEPLOY.md`, `DEPLOY_CHECKLIST.md`.

## Data and licensing
No Qloo response data is included; `.cache/`, `private/`, `fixtures/` are git-ignored and `tools/leak_scan.py` checks what would be published. The UI uses no third-party fonts, scripts or images. MIT licensed (see `LICENSE`). Dependencies at runtime: none.
