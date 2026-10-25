<!-- Sample entity names removed for the public repository. The original lives in a private folder. -->
# VibeSpec — Phase 0 API Feasibility Audit

Run: 2026-10-25, live, `https://hackathon.api.qloo.com`, ~25 GET calls. Key read from env `QLOO_API_KEY` only (not stored; fixtures hold response bodies, no headers). Harness: `smoke_test.py` (stdlib). Raw data (private, not published): `results.json`, `RAW_RUN.md`, `fixtures/`.

## 1. PASS/FAIL per endpoint

| Check | Verdict | Evidence |
|---|---|---|
| Brand resolution (`/search`, `types=urn:entity:brand`) | **PASS** | Aesop, Muji, Patagonia: HTTP 200, exact-name top hit, `entity_id` present, ~1.0–1.4 s |
| Brand → book | **FAIL (partial)** | Muji 200/20, Patagonia 200/20. **Aesop: HTTP 400** "All of the provided signal.interests.entities were invalid" — deterministic (retried, with and without explainability) |
| Brand → artist | **PASS** | 3/3 200, 20 results each, 20/20 named+id; ~4.5 s |
| Brand → brand | **PASS** | 3/3 200, 20 each; ~1.9 s |
| Brand → place (`filter.location.query=New York City`) | **PASS** | 3/3 200, 20 each, lat/lon/geohash/address present; 4.4–5.5 s |
| Explainability (`feature.explainability=true`) | **PASS** | Present per result and at top level on every successful call (60/60 results checked) |
| Local unsupported-param guard | PASS | `signal.bogus` rejected before sending |
| Auth error handling | PASS | bad key → 401, handled |

Warning-level behaviours: a nonsense brand query returned HTTP 200 with 5 fuzzy hits (a different, unrelated brand), so resolution **must require exact/near-exact name match**, never trust "n>0". Place results can repeat a name (e.g. two branches of the same café) because they are distinct locations with distinct ids; dedupe by `entity_id`, display by name+address.

## 2. Response schema audit (observed)

- Envelope `{success, results: {entities[], duration}, query}`. `/search` entity keys: `entity_id, name, types, popularity, properties, tags, disambiguation`.
- Insights entity keys: `entity_id, name, type, subtype, popularity, properties, external, disambiguation, query` (+ `location{lat,lon,geohash}`, `tags` for places).
- Per-result `query.affinity` (0–1) and `query.explainability["signal.interests.entities"] = [{entity_id, score}]`. Top-level `query.explainability` gives `effect_on_top3/5/10/all_recs` with `avg_score`.
- Explainability only attributes among *your input anchors*. With a single anchor every score is 1.0 — **no information**. It becomes meaningful only with multiple anchors (tested: combined 3-brand book query returned 200/20; per-anchor spread not yet analysed).
- Affinity is query-relative; do not compare across queries (consistent with the earlier Territory finding).
- `/search` doc page and Entity Type Parameter Guide returned 404 to my fetcher, so `/search` params (`query`, `types`, `take`) rest on the hackathon developer guide notes plus live success, not a fresh doc read. `/v2/insights` params were validated against the official parameter reference.

## 3. Anchor sensitivity (does changing the brand change candidates?)

Top-20 name overlap (Jaccard) between brand anchors: book 0.00, artist 0.00, brand 0.00, place 0.02. Candidate sets are almost entirely disjoint and thematically coherent per anchor (manually eyeballed; entity names omitted here to respect Qloo's repository restrictions). **Material change: YES.** Place: located vs unlocated Aesop query Jaccard 0.0, so location is actually applied.

## 4. Demonstration feasibility

Strong: brand→{artist, brand, place, book} gives distinct, explainable, plausible cultural neighbours; latency 1–5.5 s per call (place/artist ~5 s, so a demo must parallelise or pre-cache). Weak: (a) Aesop→book 400; (b) single-anchor explainability is trivial; (c) "taste neighbours" are affinity, not demand.

**Not evidenced by this audit (commercial assumptions, kept separate):** purchasing prices, conversion, inventory/availability, supplier contracts, whether hospitality guests would act on a book/artist suggestion. Qloo affinity supports "culturally coherent curation", nothing about revenue.

## 5. Five-day MVP risk

| Risk | Level | Mitigation |
|---|---|---|
| Some brands invalid for some domains (Aesop→book) | High | Per-domain fallback (try tags, or neighbouring brands as anchors); surface "no cultural signal" instead of guessing |
| Fuzzy search returns wrong brand | Med | exact-match gate + user confirm |
| Latency 5 s × many calls | Med | parallel + cache (private server-side cache is allowed) |
| Explainability trivial for single anchor | Med | use 2–3 anchors per room/venue brief |
| Quota/rate limits unpublished (no 429 seen in ~25 calls) | Med | call budget + cache |
| Commercial claims unsupported | High if overclaimed | frame as curation inspiration, no ROI claims |
| Docs gaps (`/search` page 404) | Low | live-verified |

## 6. Recommendation: **CONDITIONAL GO**

API functionality is sufficient to demo brand-anchored book/artist/brand/place curation with explainability. Conditions before building: (1) design for domain-invalid anchors (test tag/neighbour fallback first, ~1 h); (2) require multi-anchor briefs so explainability is non-trivial; (3) keep all copy to cultural affinity, no commercial outcome claims. A NO-GO would apply if the product depends on every brand working for every domain, or on proving commercial lift.

Not tested: stability across days, explainability spread with multiple anchors, additional brands/cities, rate-limit behaviour under load.
