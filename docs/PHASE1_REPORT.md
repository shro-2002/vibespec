# VibeSpec Phase 1 — Report and GO/NO-GO

Date 2026-10-25. Nothing deployed, pushed, published or submitted. `territory/` untouched (its one untracked file predates this work).

## 1. What exists
Local app (`python3 -m vibespec`, stdlib only), Qloo service, bounded agent, Markdown/JSON export, 17 offline tests (pass), multi-anchor validation, counterfactual eval harness, deploy checklist. Verified in the browser: form → agent → 4 domain chapters with attribution bars, rejected alternatives, anchor-influence table, trace, downloads; ambiguous-anchor confirmation flow and input validation verified via HTTP.

## 2. Multi-anchor validation (`MULTI_ANCHOR_REPORT.md`, ~28 live GETs)
- Per-anchor attribution is recoverable from documented `query.explainability` for every domain; multi-anchor shares are meaningful (e.g. Muji+Patagonia books 0.43/0.57).
- **Aesop in books: accepted (HTTP 200) but silently ignored.** Aesop alone → 400; Aesop+Muji → results identical to Muji alone (Jaccard 1.0), Aesop present in 0/20 results' explainability. Phase 0 recorded only the 400; the real behaviour is *400 if all anchors invalid, silent drop if some are*. The service detects this through zero explainability presence and discloses it.
- Leave-one-out changes the candidate set materially in artist/brand/place (drop-one Jaccard 0.03–0.74). Stop condition "contributions cannot be established" is **not** triggered.

## 3. Service and agent
- `qloo.py`: exact/near resolution; fuzzy hits (e.g. a short brand name that only fuzzily matches a longer one) require user confirmation; invalid/ignored/malformed/empty handled and disclosed; no substitution of anchors; place branches keep `entity_id` + geohash; disk cache + bounded concurrency + call budget; unsupported params rejected before sending.
- `agent.py`: state-driven tool loop (resolve → query domains in parallel → validate constraints → **revise** → leave-one-out audit → assemble), max 40 steps, 2 revisions per domain. Revision is chosen from *why* candidates were rejected (price cap → server-side `filter.price_level.max`; year → `filter.publication_year.min`; else next page). Live: place went 0/20 acceptable → 15 after a price-filter revision; brand 1/20 → 8 after paging.
- **Limitation, stated plainly:** the planner is rule-based, not LLM-driven. It is genuine state-dependent tool selection with evidence-triggered revision, but "agentic" here means a bounded policy, not model reasoning. Interpretation of free-text goals is keyword-based (domain emphasis only); constraints are structured fields.
- Budget: `verified_costs` is always empty. Qloo brand price ranges are shown as "indicative"; the unit budget is labelled a user assumption.

## 4. Counterfactual evaluation (`EVAL_REPORT.md`; 4 briefs, 80 picks per arm, baseline qwen3:14b with no Qloo)
| | Qloo agent | Qloo-free |
|---|---|---|
| Grounded in Qloo catalogue | 80/80 (by construction) | 58/80 |
| Constraints satisfied / violated / unverifiable | 65 / 0 / 15 | 36 / 5 / 39 |
| Claimed "meets constraints" but violated | – | 5 |
| Decision-set overlap (Jaccard) | 0.000 across 16 comparisons | |

How to read this honestly:
- **Overlap 0.000 shows the sets differ, not that Qloo's are better.** Baseline picks were mostly famous items (museums, landmark venues); Qloo's were niche affinity neighbours.
- **Grounding is circular and biased toward Qloo**: several "ungrounded" baseline picks are real (well-known landmarks and venues) but absent from Qloo or named differently. Do not call these hallucinations.
- **Agent "0 violated" is by construction** (it filters with the same checker). The independent signal is that the baseline *self-reported* compliance falsely 5 times and left 39/80 picks unverifiable, while every agent pick carries checkable evidence and cited attribution. That is a traceability/verifiability advantage, not a proven quality advantage.
- Agent faithfulness 80/80 is internal consistency of templated text against stored evidence, not semantic faithfulness.
- Diversity is mixed: agent higher in artists/brands/places, lower in books (0.48–0.79 vs ~0.85+).
- Anchor influence is real in the candidate pool (most drop-one set changes 0.5–1.0), except Aesop-for-books (0.0).
- **Not established: decision quality / relevance / human preference.** A blind A/B sheet (randomised, key stored separately) is in `private/eval/blind_sheet.md`; I could not score it. `score_blind.py` aggregates once filled. The stop condition "Qloo adds no value" cannot be evaluated until then; automated metrics neither confirm nor refute it.

## 5. Known limitations
Rule-based planner; keyword goal parsing; Aesop-type anchors silently ignored per domain (disclosed, not fixed — no tag/neighbour fallback tested); Qloo metadata coverage gaps (price/rating missing → "unverifiable"); `/search` docs page unreadable (params verified live); place city enforced by Qloo location filter and only spot-checked; ~60 s cold-run latency; per-process cache/limits; ~190 live Qloo calls used in this session (quota unpublished); Phase 0 `REPORT.md` contains sample entity names (scrub before public repo).

## 6. Deployment readiness (assessment only)
Secrets stay server-side, no third-party UI assets, security headers + rate/daily caps present. Blockers: needs a host that allows ~60 s requests and holds an env secret (long-lived container host such as a Docker-capable free tier; typical serverless 10–30 s limits would time out cold runs) — not verified on any host. Cache is ephemeral. See `DEPLOY_CHECKLIST.md`.

## 7. GO / NO-GO for full MVP: **CONDITIONAL GO**
Go on: working end-to-end slice, verifiable evidence trail, honest handling of invalid/ignored anchors, anchors demonstrably steering candidates. Conditions before investing in the full MVP: (1) run the blind human preference test (≥3 raters, 4 briefs) — if Qloo-powered is not preferred or at least equal, pivot the pitch to "verifiable, constraint-checked curation" or stop; (2) pick a long-request host and prove one cold run end to end; (3) decide the anchor fallback policy for ignored domains; (4) keep all claims to cultural affinity — no commercial impact. Deadline: Oct 30, 11:45 PM EDT (5 days).
