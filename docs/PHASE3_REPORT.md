# VibeSpec Phase 3 — from cultural discovery to hotel suitability

Local only: committed, not pushed or deployed. Entity-level analysis is in a private file (it names Qloo entities).

## 1. Root causes (traced in code and Qloo metadata)
The engine was one-stage: candidates were ranked by Qloo affinity within a query and checked only against numeric constraints. Goal text changed how many picks a section got, never whether a pick fit. The service discarded the metadata that could answer that (music descriptors, venue genre, opening hours, brand category, sustainability initiatives).
- Energetic rock act chosen for a "calm" lobby: its own descriptors (alternative rock, dynamic, energetic performance) were never read. Even now Qloo gives artist-level, not track-level, evidence.
- Skyscraper observation deck chosen as a "local, intimate" find: genre = historical landmark; passed the price/rating limits; the goal was never evaluated.
- A venue with no opening hours presented as a destination: only an explicit `is_closed: true` was rejected; missing hours were treated as fine.
- A retailer rejected for "Starbucks": substring match over all tags hit a reported brand partnership.
- Also: two hotels recommended as guest destinations, a media company as an "amenity", outdoor-apparel retailers presented as in-room amenities, a war/danger memoir for a mindful library, duplicate rejection rows.

## 2. Plan, ranked by impact and risk (all implemented)
1. Stage B suitability checks using real metadata (high impact, low risk: pure functions, conservative defaults). `vibespec/suitability.py`
2. Exclusion by name/owner only; mentions reported for review (high impact on trust, trivial risk).
3. Tiered selection: positive fit evidence > unverified > discovery leads; affinity only breaks ties; off-brief items never selected (medium risk: changes picks, covered by tests).
4. Revisions triggered by suitability failures, bounded to 2 per domain, stop with an explicit "no defensible candidate" (low risk: existing loop).
5. Actionable output per pick: use, fit evidence, Qloo-verified facts, checks before use, next step, alternative; optional hotel coordinates for walking estimates (UI + Markdown + JSON).
Not done (deliberately): LLM judgement (no reliable free deployable inference with measured benefit), external venue-status APIs (cost/terms), track-level audio analysis.

## 3. Decision engine
Stage A (unchanged): Qloo discovery and per-anchor attribution, shown as "cultural affinity, not a measure of fit".
Stage B: domain checks over Qloo metadata; verdicts aligned / unverified / conflict / reject; missing metadata => unverified, never aligned.
- Music: calm vs energetic artist descriptors; always flags "track-level tempo unknown" and "public-performance licensing not checked".
- Books: nature/sustainability topic evidence; dark-theme clash for calm briefs.
- Amenities: brand-level partnership idea only; media/software brands excluded; marketplaces never "aligned"; sustainability only when Qloo lists initiatives, labelled brand-reported.
- Places: closed => reject; hotels => off-brief; landmarks => off-brief for local/intimate briefs; party/high-energy ambience => off-brief for calm briefs; no hours => "discovery lead", ranked last; walking claims only with hotel coordinates (straight-line estimate).

## 4. Regression tests
12 new tests in `tests/test_suitability.py` built from the audit failures (synthetic entities, no Qloo data): energetic artist, calm artist without licence/track claims, landmark, no-hours lead ranked last, closed/hotel, walkability needs coordinates, exclusion by name/owner only, brand-level and sustainability evidence rules, book tone, suitability-driven revision, stop when nothing defensible, no operational guarantees in exports. Suite: 42 passed.

## 5. Before and after (same brief, same cached Qloo responses)
| section | before picks kept after | after: picks with positive fit evidence | candidates now off-brief | revisions |
|---|---|---|---|---|
| Soundscape | 1 of 5 | 5 of 5 | 31 | 1 (energy failures -> more candidates) |
| Library | 3 of 5 | 5 of 5 | 1 | 0 |
| Amenities | 4 of 5 | 1 of 5 (rest: partnership ideas, fit unverified) | 4 | 0 |
| Neighborhood | 2 of 5 | 0 of 5 without hotel coordinates; 4 of 5 with them | 5 | 0 |
The landmark, both hotels, the energetic acts and the media brand are gone with stated reasons; the no-hours venue drops to the bottom as a labelled lead; the partnership-mention retailer is no longer excluded (flagged for review instead).

## 6. Controlled evaluation (`EVAL_CONTROLLED_REPORT.md`)
Same engine both arms; A = Qloo candidates, B = local LLM candidates. 4 briefs: A 75 picks (some sections stopped short rather than pad), B 79. Positive fit evidence: A 38, B 5; screened out as off-brief: A 95, B 0. B's zero is not a strength: its candidates carry almost no descriptors, so Stage B cannot screen them and they stay "unverified". Human ratings: still pending, none fabricated; new rater packet at `private/eval2/rater.html` (randomised, blinded, equal lengths).

## 7. GO / NO-GO
CONDITIONAL GO for the judge demo and submission. The product now separates "the audience likes this" from "this fits your hotel", refuses unsupported operational, licensing and sustainability claims, and stops instead of padding. Conditions: (1) human blind ratings before any quality claim; (2) push and redeploy only after your approval; (3) keep the copy: affinity is not fit, Stage B is rule-based over Qloo metadata, nothing is verified operationally.
Remaining limits: keyword rules can mis-classify (e.g. a showroom tagged "destination"); artist-level only for music; opening hours from Qloo may be stale; amenities rarely reach "aligned" because Qloo brand metadata seldom names in-room product categories.

## 8. Judge demonstration
1. Run the NYC eco brief without hotel coordinates: show the energetic acts, landmark and hotels in "Did not fit your brief" with reasons, and the revision in the live panel.
2. Add hotel coordinates and rebuild: places switch from "distance unverified" to walking estimates; nothing claims walkability before that.
3. Open one card: use, fit evidence, what is verified, what to check, next step, alternative.
4. Show the partnership mention flagged, not excluded, and the no-hours venue labelled as a lead.
5. Close on the honesty line: Qloo supplies the cultural evidence; VibeSpec decides fit only from evidence it can show.
