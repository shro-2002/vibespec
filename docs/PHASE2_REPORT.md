# VibeSpec Phase 2 — deployment feasibility and controlled evaluation

2026-10-25. Nothing deployed, pushed, published or submitted; no money spent. `territory/` untouched. A local git repo was initialised in `vibe spec/` (no commits) only so the leak scanner can list what would be published.

## 1. Recommended host and exact configuration
**Render Free web service** (primary). Config is committed as `render.yaml` + `.python-version` (3.12): runtime python, no-op build (stdlib only), start `python -m vibespec` (binds `0.0.0.0:$PORT`, Render default 10000), health check `/healthz`, secret `QLOO_API_KEY` (`sync: false`), `VIBESPEC_TRUST_PROXY=1`, `VIBESPEC_DAILY_CALL_CAP=300`, `VIBESPEC_JOB_TIMEOUT=150`. Details and rationale: `docs/DEPLOY.md`. Verify the `plan: free` key in the dashboard (docs excerpt I read names a default plan `0.5c-512mb`, not Free).

## 2. Hosting risks and cost assumptions
$0 on Free (750 instance hours/month; over-bandwidth with no payment method suspends Free services). Material risks: spin-down after 15 min idle with ~1 min cold start for the first judge (Render's own docs); ephemeral disk loses cache and in-flight jobs; single instance; may be restarted any time; unknown hackathon-key quota and validity after 2026-10-30; X-Forwarded-For semantics unverified. A 24/7 keep-warm pinger is possible but unverified and consumes the hours budget. Full table in `docs/DEPLOY.md`.

## 3. Cold-start and long-request test plan
Nine numbered steps with pass criteria (wake time, first visible step, cold ≈36 s/21 calls, warm 0 live calls, three concurrent devices, mid-job restart, bad-key message, log inspection, next-day and judging-day repeats) in `docs/DEPLOY.md`. Not run on Render; requires your approval to deploy.

## 4. Locally executed production-style tests (`docs/PHASE2_LOCAL_TESTS.md`, all PASS)
Server run in a clean environment with host-style env vars. Redesign: synchronous request replaced by `POST /api/jobs` (202) + polling; UI shows only real agent events.
- Startup 0.12 s on `PORT=10000`; `lsof` shows `*:10000` (all interfaces); `/healthz` 200; UI 12.6 KB, 1 ms, no external assets.
- Full form submission, live Qloo, cold cache: done in 36.2 s, first visible step at 0.0 s, 12 real steps, 21 live calls. This exceeds typical 30 s serverless limits, confirming polling is needed. Warm rerun: 1.0 s, 0 live calls, 21 cache hits, disclosed in the UI.
- Timeout (4 s limit, real Qloo): labelled `timeout` after 5 s with 4 real partial steps, no fabricated result.
- Failures (synthetic upstream): 429×2 then OK recovers via retries; persistent 500 → clean failure "Qloo is temporarily unavailable (HTTP 500)"; malformed JSON → "unexpected response" (a first version wrongly reported "needs confirmation"; fixed after the test exposed it); empty results → completes with warnings; retry after failure succeeds on the same server. Real invalid key → "Qloo rejected this server's credentials (HTTP 401)", upstream body never shown.
- Concurrency: 7 simultaneous submits → 4 accepted (2 running + 2 queued), 3 rejected with 429; all 4 finished; `/healthz` p95 1 ms under load. Per-IP rate limit works.
- Secrets: upstream that echoes the key → absent from job JSON and server log; scan of 286 captured responses/logs for the real key and the echoed key: 0 matches. Logs record request line and status only.
- Offline suite: 27 tests pass (job manager, HTTP layer, redaction, LLM-source robustness plus all Phase 1 tests).
Limitations: single machine, loopback network; Render's proxy, spin-down and restart behaviour are untested.

## 5. Public repository security findings
- `git ls-files --cached --others --exclude-standard` lists 43 files; `tools/leak_scan.py` (key, key-like strings, 1,355 harvested Qloo entity names, forbidden paths) reports **CLEAN**.
- Kept private via `.gitignore`/`.dockerignore`: `.env*`, `.cache/`, `.cache_llm/`, `private/` (eval data, rater page, blind key), `fixtures/`, `results.json`, `RAW_RUN.md`. No Territory file lives in this tree.
- Found and fixed: Phase 0 report quoted sample Qloo entity names (artists, brands, venues) and Phase 1 eval listed baseline names; public copies scrubbed, originals moved to `private/`. The earlier root-level reports were relocated to `docs/`.
- Scanner limits: short single-word entity names and ordinary English words are skipped (review by eye); anchor/brand/city names typed as inputs are allow-listed as public names, not Qloo output; it cannot judge Qloo's terms themselves (re-read them).
- Added: MIT `LICENSE` (same holder as Territory), README, CI workflow (offline pytest, pinned `pytest==9.1.0`), `Dockerfile`, deploy docs. Runtime dependencies: none.
- Open item for you: the repo's GitHub "About" must show the license (rules); confirm Qloo's data-caching terms allow a private server-side cache (rules text I read does not address it).

## 6. Controlled evaluation status (`docs/EVAL_CONTROLLED_REPORT.md`)
Implemented and executed on 4 briefs. System A = engine + Qloo candidates. System B = **same agent loop, validator, revision, selection and blueprint code**, candidate generation by local `qwen3:14b` (temperature 0, 20 per query, constraints passed as prompt text on revision, attributes self-reported and flagged unverified; `vibespec/llm_source.py`). Request counts and candidate pools are reported per brief; parity is approximate (B used fewer requests; B pools 13–40 vs A 20–40 per domain).
Automated, non-quality results (Qloo affinity unused): overlap A vs B Jaccard 0.000; B picks found in Qloo catalogue 53/79 (absence ≠ fabrication); catalogue-metadata constraint check B: 32 satisfied / 6 violated / 41 unverifiable, A: 65 / 0 / 15 (A's numbers are not independent: A was filtered on the same metadata).
Human evaluation: **pending; no ratings exist or were invented.** Ready: offline blind rater page `private/eval2/rater.html` (tested in a browser; neutral "Plan 1/2", randomised per brief, equal list lengths, rubric: cultural fit, coherence, usefulness, feasibility, overall preference, exports CSV), key in `private/eval2/blind_key.json`, aggregator `score_controlled.py` (tested on synthetic CSV only; descriptive means + sign test). Blinding is imperfect (Qloo picks skew niche). The earlier Phase 1 sheet was superseded (its design compared unequal pipelines); its CSV/aggregation format was reused.
**Needed: ≥3 independent raters who did not build the system; drop their CSVs into `private/eval2/ratings/`.**

## 7. Agentic eligibility assessment (`docs/AGENTIC_AUDIT.md`)
Rules (read from qloo.devpost.com/rules): app must integrate Qloo and function as an agentic tool, use an agent framework, or extend an existing agent; Stage 1 pass/fail on theme and API fit; no LLM mandated. VibeSpec is a bounded, rule-based tool-selection and revision loop (state-dependent tool choice, human confirmation gate, evidence-triggered revision, disclosed tool failures, hard bounds). Credible under "agentic tool" at the lenient end; a judge expecting an LLM planner may call it a pipeline with branches. Never describe it as autonomous or LLM-reasoning. Strongest on Qloo depth (search + insights, four entity types, multi-anchor, location, server filters, explainability, influence audit, silent-ignore detection); untouched: tags, audiences, demographics, heatmaps.
Smallest strengthening steps (not implemented): (1) precise wording + show the trace and a forced revision in the demo; (2) evidence-driven anchor fallback using the anchor's own Qloo tags when an anchor is ignored (a 1-call probe returned 200 with 10 results; quality untested); (3) optional, default-off LLM interpreter behind the same legal-action gate, only if an LLM is available at no cost to judges. No framework/multi-agent rewrite.

## 8. Steps that require your explicit approval
1. Create the GitHub repo, set About + license, push (publication).
2. Create the Render service, enter the secret key, deploy; run the cold-start plan on it.
3. Decide on adding a payment method to Render (avoids suspension, risks charges) and on a keep-warm pinger.
4. Recruit ≥3 independent raters and share `rater.html` (it contains Qloo data in System A's names: private use only, do not publish).
5. Confirm with Qloo/the rules that a private server-side cache and the hackathon key remain valid through 2026-11-05; set `VIBESPEC_DAILY_CALL_CAP` accordingly.
6. Implement anchor-fallback and/or LLM interpreter (spend/time decision).
7. Devpost submission (deadline 2026-10-30 11:45 PM ET), demo video, text description wording (no LLM-planner claims, no quality-gain claims until the human result exists).
