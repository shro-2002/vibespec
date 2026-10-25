# VibeSpec Phase 1 — Multi-anchor validation

~28 live GETs (city for place: New York City). Aggregates only; entity data is in private/ (git-ignored).
Affinity values are NOT compared across queries; only set overlap and in-query explainability shares are used.

## book

| anchors | status | n | latency ms | per-anchor mean explain share (results containing anchor/n) |
|---|---|---|---|---|
| Muji | 200 | 20 | 1517 | Muji=1.0 (20) |
| Aesop | 400 | 0 | 835 | {'errors': [{'message': 'All of the provided signal.interests.entities |
| Patagonia | 200 | 20 | 1764 | Patagonia=1.0 (20) |
| Muji+Aesop | 200 | 20 | 1564 | Muji=1.0 (20); Aesop=0.0 (0) |
| Muji+Patagonia | 200 | 20 | 1716 | Muji=0.433 (20); Patagonia=0.567 (20) |
| Aesop+Patagonia | 200 | 20 | 1840 | Aesop=0.0 (0); Patagonia=1.0 (20) |
| Muji+Aesop+Patagonia | 200 | 20 | 1820 | Muji=0.433 (20); Aesop=0.0 (0); Patagonia=0.567 (20) |

Leave-one-out (Jaccard of top-20 ids, full triple vs triple minus anchor; 1.0 = anchor changed nothing):

- drop Aesop: 1.0
- drop Muji: 0.143
- drop Patagonia: 0.0

## artist

| anchors | status | n | latency ms | per-anchor mean explain share (results containing anchor/n) |
|---|---|---|---|---|
| Muji | 200 | 20 | 4618 | Muji=1.0 (20) |
| Aesop | 200 | 20 | 4683 | Aesop=1.0 (20) |
| Patagonia | 200 | 20 | 4601 | Patagonia=1.0 (20) |
| Muji+Aesop | 200 | 20 | 7102 | Muji=0.629 (20); Aesop=0.371 (20) |
| Muji+Patagonia | 200 | 20 | 4817 | Muji=0.603 (20); Patagonia=0.397 (20) |
| Aesop+Patagonia | 200 | 20 | 4683 | Aesop=0.498 (20); Patagonia=0.502 (20) |
| Muji+Aesop+Patagonia | 200 | 20 | 4535 | Muji=0.219 (20); Aesop=0.387 (20); Patagonia=0.394 (20) |

Leave-one-out (Jaccard of top-20 ids, full triple vs triple minus anchor; 1.0 = anchor changed nothing):

- drop Aesop: 0.026
- drop Muji: 0.739
- drop Patagonia: 0.026

## brand

| anchors | status | n | latency ms | per-anchor mean explain share (results containing anchor/n) |
|---|---|---|---|---|
| Muji | 200 | 20 | 1862 | Muji=1.0 (20) |
| Aesop | 200 | 20 | 1978 | Aesop=1.0 (20) |
| Patagonia | 200 | 20 | 1946 | Patagonia=1.0 (20) |
| Muji+Aesop | 200 | 20 | 2227 | Muji=0.501 (20); Aesop=0.499 (20) |
| Muji+Patagonia | 200 | 20 | 1937 | Muji=0.483 (20); Patagonia=0.517 (20) |
| Aesop+Patagonia | 200 | 20 | 1870 | Aesop=0.49 (20); Patagonia=0.51 (20) |
| Muji+Aesop+Patagonia | 200 | 20 | 1879 | Muji=0.334 (20); Aesop=0.347 (20); Patagonia=0.319 (20) |

Leave-one-out (Jaccard of top-20 ids, full triple vs triple minus anchor; 1.0 = anchor changed nothing):

- drop Aesop: 0.212
- drop Muji: 0.29
- drop Patagonia: 0.429

## place

| anchors | status | n | latency ms | per-anchor mean explain share (results containing anchor/n) |
|---|---|---|---|---|
| Muji | 200 | 20 | 5760 | Muji=1.0 (20) |
| Aesop | 200 | 20 | 4433 | Aesop=1.0 (20) |
| Patagonia | 200 | 20 | 5797 | Patagonia=1.0 (20) |
| Muji+Aesop | 200 | 20 | 5792 | Muji=0.488 (20); Aesop=0.512 (20) |
| Muji+Patagonia | 200 | 20 | 5693 | Muji=0.494 (20); Patagonia=0.506 (20) |
| Aesop+Patagonia | 200 | 20 | 5796 | Aesop=0.522 (20); Patagonia=0.478 (20) |
| Muji+Aesop+Patagonia | 200 | 20 | 5805 | Muji=0.329 (20); Aesop=0.353 (20); Patagonia=0.317 (20) |

Leave-one-out (Jaccard of top-20 ids, full triple vs triple minus anchor; 1.0 = anchor changed nothing):

- drop Aesop: 0.379
- drop Muji: 0.333
- drop Patagonia: 0.081

## Does Aesop contribute to combined book results?

- Aesop+Muji vs Muji alone: Jaccard 1.0; Aesop appears in explainability of 0/20 results (mean share 0.0); status 200
- Aesop+Patagonia vs Patagonia alone: Jaccard 1.0; Aesop appears in explainability of 0/20 results (mean share 0.0); status 200
