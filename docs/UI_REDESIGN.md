# UI redesign (local; not deployed)

Scope: front end only. Backend endpoints, job/polling contract, Qloo service and decision engine are unchanged. The only server change is serving `/static/*` (a flat, extension-whitelisted directory) and tightening the CSP to `'self'` (no inline script or style).

## Design audit of the previous UI
- A single-page form with ~10 equal-weight inputs before any explanation of value; "required" and "optional" looked the same.
- No preview of what a result looks like; the value had to be inferred from a paragraph.
- Progress was an unstyled list of step strings; stages, anchors and revisions were not distinguishable.
- Results were one long list of identical cards; anchor contribution was a thin bar with no explanation of what the numbers mean, no treatment for ignored anchors beyond a line of text, and no overview of how anchors shaped the whole blueprint.
- Inline styles and scripts (permissive CSP); focus order and heading structure not designed.
Before screenshots: `docs/ui/before_*` (landing). Results screenshots contain Qloo data and are kept in the private `private/ui/` folder.

## Visual language
Paper `#f3eee5`, linen cards `#fbf8f1`, charcoal `#1c1a17`, clay `#a4442b` (kept from the original brand), plus moss and slate used **only** as anchor colours in data so colour always means "which anchor". Sections are told apart by tinted header panels and icons, not by hue. Type: Palatino-family serif for headlines (system fonts, no downloads) over a humanist system sans. Varied radii (14 px cards, 22 px panels, pills for actions). Motion: one rise-in on the blueprint summary and width transitions on bars; everything off under `prefers-reduced-motion`. Light and dark themes.

## Structure
1. Landing: promise headline, one-sentence mechanism, anatomy sheet of a recommendation (clearly labelled placeholder text), how-it-works (a real sequence), honest "what Qloo provides / what VibeSpec never invents", then a three-step guided form (required vs optional pills, anchor chips with suggestions, constraints collapsed, one-click NYC example).
2. Live activity panel (real job events only): stage timeline, resolved anchors, per-section retrieval tiles (counts and ignored anchors parsed from real step outcomes), validation tiles, revision cards with the real reason, full step log. States: queued, running, failed, timed out, lost, busy, confirm-anchors. A badge states "Rule-based agent loop, no language model".
3. Blueprint: summary with real totals; sticky section nav; "How your anchors shaped this blueprint" (interactive evidence map: lines only where Qloo reported a share, thickness = share, dashed = single usable anchor, amber notes for ignored/rejected anchors; anchor lens chips that dim cards by lead anchor; table alternative; leave-one-out meters); four sections (Soundscape, Library, Amenities, Neighborhood) each with an evidence funnel (retrieved, met constraints, selected), cards (attribution bar and shares, constraint chips: green = verified, amber = unknown), "Why this pick", and "Considered but not chosen"; evidence notes and budget; decision trace; Markdown/JSON export (same mechanism as before).

## Verification (real browser, real Qloo data)
- Desktop 1280 and mobile 390 (no horizontal overflow); light and dark; no console or CSP errors.
- End-to-end runs: NYC example (cold and warm), an anchor-confirmation flow (ambiguous short brand name, then rebuild), daily-cap error alert, empty-section states (rendered from a synthetic object in the console), lens filtering (11 of 20 cards dimmed for one anchor), map-node click reveals the card, keyboard names on all controls.
- Contrast measured from computed styles: all body and chip text >= 5.1:1 in light; dark mode fixed after a 2.6:1 tag was found.
- Tests: 30 offline tests pass (new: static assets, no path traversal, CSP without `unsafe-inline`, every referenced asset exists).

## Known limitations
- The map is hidden below 760 px; mobile uses the lens chips and the table instead.
- Live-panel detail is parsed from the existing step outcome strings; a wording change in the agent would degrade it to showing raw text (it falls back gracefully).
- No automated accessibility engine (axe) was run; checks were manual and computed-style based. Screen-reader behaviour was not tested.
- Pick counts depend on the goals keywords; an empty goals field gives 4 per section.
- Real Qloo data appears in results screenshots, which stay private.
