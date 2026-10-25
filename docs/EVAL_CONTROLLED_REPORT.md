# VibeSpec Phase 3 — controlled comparison with Stage B suitability (System A: Qloo vs System B: same engine, Qloo-free candidates)

Status of human ratings: **PENDING — none collected, none fabricated.** Run `python3 score_controlled.py` after raters export CSVs.

## Design
- Same agent loop, constraint validator, revision logic, selection and blueprint code in both arms; only candidate generation differs.
- A: Qloo `/v2/insights` (take=20 per query, server-side filters during revisions). B: local `qwen3:14b` (temperature 0), take=20 per query, constraints as prompt text during revisions, attributes self-reported (flagged unverified). Details: `vibespec/llm_source.py`.
- Same 4 briefs, constraints, pick counts, revision limits (2 per domain), influence audit disabled in both.
- Qloo affinity is not used as a success metric. Human rubric (1-5): cultural fit, coherence, usefulness, feasibility, plus overall preference A/B/tie. Plans are shown as neutral 'Plan 1/2', order randomised per brief, system key stored separately.
- Blinding limit: Qloo picks tend to be niche, so a rater may guess identity; raters are told not to try.

## Budget and candidate parity

Requests per run = live + cache hits (A: Qloo requests incl. 2-3 anchor lookups, B: LLM generations). Pool = candidates generated per domain before validation (cap 20 per query).

| brief | A requests | B requests | A pool a/b/br/pl | B pool a/b/br/pl |
|---|---|---|---|---|
| eval_london | 6 | 4 | 20/20/20/20 | 20/20/13/19 |
| eval_la | 10 | 6 | 20/20/40/60 | 20/22/40/20 |
| eval_chicago | 8 | 6 | 20/20/20/60 | 20/20/40/18 |
| eval_nyc | 8 | 4 | 20/20/40/40 | 13/19/20/20 |

Parity is approximate, not exact: A needs anchor lookups and sometimes pages/filters; B needs none, so B used fewer requests. Plans shown to raters are truncated to equal list lengths per domain.

## Automated secondary checks (not a quality measure)

Oracle = Qloo catalogue lookup (existence + metadata) applied to B's picks; A's picks carry Qloo metadata already, so A's numbers are not independent of how A was selected. Missing from catalogue != fabricated.

| | A (Qloo) | B (Qloo-free) |
|---|---|---|
| picks | 75 | 79 |
| picks found in Qloo catalogue | 75 (by construction) | 52 |
| oracle constraint check: satisfied | 73 | 32 |
| oracle constraint check: violated | 0 | 5 |
| oracle constraint check: unverifiable | 2 | 42 |
| B picks whose self-reported attributes passed but catalogue metadata violates | – | 5 |
| Stage B: picks with positive fit evidence (each arm judged on its own metadata) | 38 | 5 |
| Stage B: candidates screened out as off-brief | 95 | 0 |

Stage B rows are not quality scores: B's metadata is mostly the generator's own short descriptions, so B has less evidence to be judged on, which is itself part of what Qloo supplies.

Pick overlap A vs B: mean Jaccard 0.000 over 16 comparisons (difference is not improvement).

## Human evaluation

PENDING. Rater page: `private/eval2/rater.html` (offline, exports CSV). Raters needed: >=3 independent, none of whom built the system.
