# VibeSpec Phase 1 — Qloo agent vs unstructured LLM baseline (SUPERSEDED by the Phase 2 controlled comparison)

Known design flaw: the baseline was a less structured pipeline than the agent, so differences mix 'Qloo' with 'engineering'. See EVAL_CONTROLLED_REPORT.md.

4 identical briefs, baseline = qwen3:14b (local, temperature 0, no Qloo access). Live Qloo calls this run: 112 (cache reuse otherwise).
Qloo affinity is NOT used as a success metric. Qloo is used as a catalogue/metadata oracle to ground and verify BOTH arms (disclosed; favours entities Qloo knows).

## Aggregate (all domains, all briefs)

| metric | Qloo agent | Qloo-free baseline |
|---|---|---|
| picks | 80 | 80 |
| grounded in Qloo catalogue (real entity; place also in right city) | 80/80 (by construction) | 58/80 |
| constraint check: satisfied | 65 | 36 |
| constraint check: violated | 0 | 5 |
| constraint check: unverifiable | 15 | 39 |
| baseline picks that claimed 'meets constraints' but violated them | – | 5 |
| explanation faithfulness (agent: cited shares + rank + constraint claims re-verified) | 80/80 | not checkable (free text) |

Decision-set overlap (mean Jaccard of picks, per domain per brief): **0.000** over 16 comparisons (0 = disjoint).

Diversity (mean pairwise 1-Jaccard of Qloo tags; higher = more varied):

| brief | domain | agent | baseline | overlap |
|---|---|---|---|---|
| eval_london | artist | 0.96 | 0.777 (tagged 5/5) | 0.0 |
| eval_london | book | None | 0.851 (tagged 5/5) | 0.0 |
| eval_london | brand | 0.884 | 0.827 (tagged 4/5) | 0.0 |
| eval_london | place | 0.971 | None (tagged 1/5) | 0.0 |
| eval_la | artist | 0.953 | 0.877 (tagged 5/5) | 0.0 |
| eval_la | book | 0.792 | 0.882 (tagged 4/5) | 0.0 |
| eval_la | brand | 0.922 | 0.828 (tagged 2/5) | 0.0 |
| eval_la | place | 1.0 | None (tagged 0/5) | 0.0 |
| eval_chicago | artist | 0.964 | 0.87 (tagged 5/5) | 0.0 |
| eval_chicago | book | 0.792 | 0.869 (tagged 5/5) | 0.0 |
| eval_chicago | brand | 0.973 | 0.935 (tagged 4/5) | 0.0 |
| eval_chicago | place | 0.982 | 0.584 (tagged 2/5) | 0.0 |
| eval_nyc | artist | 0.982 | 0.937 (tagged 4/5) | 0.0 |
| eval_nyc | book | 0.484 | 0.866 (tagged 5/5) | 0.0 |
| eval_nyc | brand | 0.852 | 0.864 (tagged 5/5) | 0.0 |
| eval_nyc | place | 0.964 | 0.915 (tagged 2/5) | 0.0 |

## Anchor influence on agent candidate sets (leave-one-out set change)

- eval_london: `{'artist': {'Aesop': 0.621, 'Muji': 0.974}, 'book': {'Aesop': 0.0, 'Muji': 1.0}, 'brand': {'Aesop': 0.824, 'Muji': 0.75}, 'place': {'Aesop': 0.667, 'Muji': 0.621}}`
- eval_la: `{'artist': {'Patagonia': 0.571, 'Lululemon': 0.519, 'Aesop': 0.71}, 'book': {'Patagonia': 0.71, 'Lululemon': 0.919, 'Aesop': 0.0}, 'brand': {'Patagonia': 0.71, 'Lululemon': 0.667, 'Aesop': 0.824}, 'place': {'Patagonia': 0.667, 'Lululemon': 0.788, 'Aesop': 0.621}}`
- eval_chicago: `{'artist': {'IKEA': 0.621, 'Muji': 1.0}, 'book': {'IKEA': 0.947, 'Muji': 0.947}, 'brand': {'IKEA': 0.519, 'Muji': 1.0}, 'place': {'IKEA': 0.571, 'Muji': 0.462}}`
- eval_nyc: `{'artist': {'Carhartt': 0.857, 'Aesop': 0.974}, 'book': {'Carhartt': 1.0, 'Aesop': 0.0}, 'brand': {'Carhartt': 0.919, 'Aesop': 0.947}, 'place': {'Carhartt': 0.919, 'Aesop': 0.667}}`

## Baseline picks not found in Qloo

(Names omitted from the public copy. Not found in the catalogue is not the same as fabricated.)

## Not measured here
- Relevance/coherence/preference: needs human raters. Blind sheet written to private/eval/blind_sheet.md (+ blind_scores.csv, key in blind_key.json); run `python3 score_blind.py` after filling.
