#!/usr/bin/env python3
"""VibeSpec Phase 1, Step 1: multi-anchor + leave-one-anchor-out validation.

Extends smoke_test.py (reuses its validated `call`, `entities`, `jaccard`). Key from env QLOO_API_KEY only.
Raw/slim results -> private/ (git-ignored). Report -> MULTI_ANCHOR_REPORT.md (aggregates only, no entity names).
"""
import hashlib, json, os, sys
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

from smoke_test import BRANDS, TARGETS, call, entities, jaccard

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
CITY = "New York City"
WORKERS = 3
SETS = [("Muji",), ("Aesop",), ("Patagonia",), ("Muji", "Aesop"), ("Muji", "Patagonia"), ("Aesop", "Patagonia"), ("Muji", "Aesop", "Patagonia")]


def cached_call(path, params, key):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / (hashlib.sha256(json.dumps([path, params], sort_keys=True).encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    res = call(path, params, key)
    if res["status"] == 200 and res["body"]:
        f.write_text(json.dumps(res))
    return res


def attribution(body, anchor_ids):
    """Per-anchor attribution from documented explainability fields."""
    ents = entities(body)
    n = max(len(ents), 1)
    per = {a: {"results_with_score": 0, "mean_score": 0.0} for a in anchor_ids}
    for e in ents:
        for item in ((e.get("query") or {}).get("explainability") or {}).get("signal.interests.entities", []) or []:
            a = item.get("entity_id")
            if a in per:
                per[a]["results_with_score"] += 1
                per[a]["mean_score"] += item.get("score", 0) / n
    agg = {}
    top = (((body or {}).get("query") or {}).get("explainability") or {}).get("signal.interests.entities") or {}
    for window, items in top.items():
        agg[window] = {i.get("entity_id"): i.get("avg_score") for i in items or []}
    for a in per:
        per[a]["mean_score"] = round(per[a]["mean_score"], 3)
    return per, agg


def run_one(args):
    domain, combo, ids, key = args
    p = {"filter.type": TARGETS[domain], "signal.interests.entities": ",".join(ids[b] for b in combo), "feature.explainability": "true", "take": 20}
    if domain == "place":
        p["filter.location.query"] = CITY
    r = cached_call("/v2/insights", p, key)
    ents = entities(r["body"])
    per, agg = attribution(r["body"], [ids[b] for b in combo])
    name = {v: k for k, v in ids.items()}
    return (domain, combo), {
        "status": r["status"], "latency_ms": r["latency_ms"], "error": r["error"], "n": len(ents),
        "ids": [e.get("entity_id") for e in ents],
        "per_anchor": {name[a]: v for a, v in per.items()},
        "aggregate": {w: {name.get(a, a): s for a, s in d.items()} for w, d in agg.items()},
        "malformed": sum(1 for e in ents if not (e.get("entity_id") and e.get("name"))),
    }


def main():
    key = os.environ.get("QLOO_API_KEY", "").strip()
    if not key:
        sys.exit("BLOCKED: QLOO_API_KEY not set")
    ids = {}
    for b in BRANDS:
        r = cached_call("/search", {"query": b, "types": TARGETS["brand"], "take": 5}, key)
        hit = next(e for e in entities(r["body"]) if e["name"].lower() == b.lower())
        ids[b] = hit["entity_id"]
    jobs = [(d, c, ids, key) for d in TARGETS for c in SETS]
    with ThreadPoolExecutor(WORKERS) as ex:
        out = dict(ex.map(run_one, jobs))
    out = {(d, frozenset(c)): v for (d, c), v in out.items()}
    SETS_F = [frozenset(c) for c in SETS]
    (HERE / "private" / "multi_anchor.json").write_text(json.dumps({f"{d}|{'+'.join(sorted(c))}": v for (d, c), v in out.items()}, indent=1))

    L = ["# VibeSpec Phase 1 — Multi-anchor validation", "", "~28 live GETs (city for place: " + CITY + "). Aggregates only; entity data is in private/ (git-ignored).",
         "Affinity values are NOT compared across queries; only set overlap and in-query explainability shares are used.", ""]
    verdict = {}
    for d in TARGETS:
        L += [f"## {d}", "", "| anchors | status | n | latency ms | per-anchor mean explain share (results containing anchor/n) |", "|---|---|---|---|---|"]
        for c in SETS:
            r = out[(d, frozenset(c))]
            pa = "; ".join(f"{k}={v['mean_score']} ({v['results_with_score']})" for k, v in r["per_anchor"].items())
            L.append(f"| {'+'.join(c)} | {r['status']} | {r['n']} | {r['latency_ms']} | {pa if r['status'] == 200 else (r['error'] or '')[:70]} |")
        # Leave-one-anchor-out against the full triple and pairwise contributions
        full = out[(d, frozenset(BRANDS))]
        L += ["", "Leave-one-out (Jaccard of top-20 ids, full triple vs triple minus anchor; 1.0 = anchor changed nothing):", ""]
        for a in BRANDS:
            rest = tuple(b for b in BRANDS if b != a)
            rr = out[(d, frozenset(rest))]
            j = round(jaccard(full["ids"], rr["ids"]), 3) if rr["status"] == 200 and full["status"] == 200 else None
            L.append(f"- drop {a}: {j}")
            verdict[(d, a)] = j
        L.append("")
    # Aesop-specific question
    L += ["## Does Aesop contribute to combined book results?", ""]
    for other in ("Muji", "Patagonia"):
        pair, alone = out[("book", frozenset((other, "Aesop")))], out[("book", frozenset((other,)))]
        j = round(jaccard(pair["ids"], alone["ids"]), 3)
        a = pair["per_anchor"]["Aesop"]
        L.append(f"- Aesop+{other} vs {other} alone: Jaccard {j}; Aesop appears in explainability of {a['results_with_score']}/{pair['n']} results (mean share {a['mean_score']}); status {pair['status']}")
    (HERE / "docs" / "MULTI_ANCHOR_REPORT.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
