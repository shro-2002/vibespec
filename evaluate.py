#!/usr/bin/env python3
"""Phase 1 Step 5: Qloo-powered agent vs Qloo-free baseline (local qwen3:14b via Ollama), identical briefs.

Outputs: private/eval/* (git-ignored raw), EVAL_REPORT.md (aggregates), private/eval/blind_sheet.* for HUMAN scoring.
Qloo is used for (a) the agent arm and (b) as an existence/metadata oracle to GROUND baseline picks. That oracle use
is disclosed: grounding/constraint numbers for the baseline are only as good as Qloo's catalogue.
Qloo affinity is never used as a success metric.
"""
import json, os, random, re, sys, urllib.request
from itertools import combinations
from pathlib import Path

from run_brief import load
from smoke_test import TARGETS, entities
from vibespec.agent import DOMAINS, LABELS, check, interpret, run
from vibespec.qloo import Candidate, QlooService, norm

HERE = Path(__file__).parent
OUT = HERE / "private" / "eval"
MODEL = "qwen3:14b"
CITY_KEY = {"london": "london", "los angeles": "los angeles", "chicago": "chicago", "new york city": "new york"}
BRIEFS = ["eval_london", "eval_la", "eval_chicago", "eval_nyc"]


def stem(name: str) -> str:
    return norm(re.sub(r"\(.*?\)", "", name.split(":")[0]))


def llm_baseline(brief, picks) -> dict:
    c = brief.constraints
    cons = [f"places: price_level (Qloo-style 1-4 scale) <= {c.max_place_price_level}" if c.max_place_price_level else None,
            f"places: rating >= {c.min_place_rating}" if c.min_place_rating else None,
            f"books published in {c.min_book_year} or later" if c.min_book_year else None,
            f"amenity brands: unit price at most ${c.amenity_unit_budget_usd:g}" if c.amenity_unit_budget_usd else None,
            f"avoid anything involving: {', '.join(c.exclude_terms)}" if c.exclude_terms else None]
    prompt = f"""You are a hospitality cultural curator. Hotel concept: {brief.concept}. City: {brief.city}.
Cultural anchors (brands whose taste the hotel should reflect): {', '.join(brief.anchors)}. Goals: {brief.goals}
Constraints: {'; '.join(x for x in cons if x) or 'none'}.
Pick exactly {picks['artist']} real music artists, {picks['book']} real books, {picks['brand']} real amenity brands, {picks['place']} real places in {brief.city}.
Reply ONLY JSON: {{"artist":[{{"name":"","why":"","meets_constraints":true}}],"book":[{{"title":"","author":"","why":"","meets_constraints":true}}],"brand":[{{"name":"","why":"","meets_constraints":true}}],"place":[{{"name":"","neighborhood":"","why":"","meets_constraints":true}}]}}"""
    req = urllib.request.Request("http://localhost:11434/api/chat", json.dumps({"model": MODEL, "stream": False, "think": False, "format": "json",
                                 "options": {"temperature": 0, "num_predict": 3000}, "messages": [{"role": "user", "content": prompt}]}).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


def cached(path: Path, fn):
    if path.exists():
        return json.loads(path.read_text())
    val = fn()
    path.write_text(json.dumps(val, indent=1, default=str))
    return val


def ground(svc, domain, name, city):
    """Resolve a pick to a Qloo entity: exact normalised name (and city for places). Returns Candidate or None."""
    res = svc._get("/search", {"query": name, "types": TARGETS[domain], "take": 10})
    for e in entities(res["body"]):
        if not (e.get("entity_id") and e.get("name")) or stem(e["name"]) != stem(name):
            continue
        if domain == "place" and CITY_KEY.get(city.lower(), city.lower()) not in str((e.get("properties") or {}).get("address", "")).lower():
            continue
        return svc._candidate(domain, e)
    return None


def pick_names(domain, items):
    return [i.get("title") if domain == "book" else i.get("name") for i in items if (i.get("title") if domain == "book" else i.get("name"))]


def verdict(cand, cons):
    if cand is None:
        return "unverifiable"
    bad, unk = check(cand, cons)
    return "violated" if bad else ("unverifiable" if unk else "satisfied")


def diversity(cands):
    t = [set(c.tags) for c in cands if c.tags]
    pairs = list(combinations(t, 2))
    return round(sum(1 - len(a & b) / len(a | b) for a, b in pairs) / len(pairs), 3) if pairs else None


def faithful(bp):
    """Agent claims vs stored evidence: cited shares, rank text, and 'constraints met' re-verified."""
    ok = tot = 0
    cons = load(HERE / "briefs" / f"{bp['_id']}.json").constraints
    for d, dom in bp["domains"].items():
        for p in dom["selected"]:
            tot += 1
            cited = all(f"{a} {v:.0%}" in p["why"] for a, v in p["attribution"].items())
            rank = f"Ranked #{p['rank_in_query']} of {p['of']}" in p["why"]
            cand = Candidate(p["id"], p["name"], d, None, {}, tuple(p["tags"]), p["props"])
            ok += cited and rank and not check(cand, cons)[0]
    return ok, tot


def main():
    key = os.environ.get("QLOO_API_KEY", "")
    if not key:
        sys.exit("BLOCKED: QLOO_API_KEY not set")
    OUT.mkdir(parents=True, exist_ok=True)
    svc = QlooService(key, HERE / ".cache", budget=400)
    rows, blind = [], []
    for bid in BRIEFS:
        brief = load(HERE / "briefs" / f"{bid}.json")
        picks = interpret(brief)
        bp = cached(OUT / f"{bid}.agent.json", lambda: run(brief, svc))
        bp["_id"] = bid
        if bp["status"] != "complete":
            rows.append({"id": bid, "error": bp["status"]})
            continue
        base = cached(OUT / f"{bid}.baseline.json", lambda: llm_baseline(brief, picks))
        row = {"id": bid, "anchors": [a["name"] for a in bp["anchors"]], "domains": {}}
        for d in DOMAINS:
            a_items = bp["domains"][d]["selected"]
            b_items = (base.get(d) or [])[: picks[d]]
            a_names, b_names = [p["name"] for p in a_items], pick_names(d, b_items)
            a_c = [Candidate(p["id"], p["name"], d, None, {}, tuple(p["tags"]), p["props"]) for p in a_items]
            b_c = [ground(svc, d, n, brief.city) for n in b_names]
            sa, sb = {s: 0 for s in ("satisfied", "violated", "unverifiable")}, {s: 0 for s in ("satisfied", "violated", "unverifiable")}
            for c in a_c:
                sa[verdict(c, brief.constraints)] += 1
            for c in b_c:
                sb[verdict(c, brief.constraints)] += 1
            claims = [(bool(i.get("meets_constraints")), verdict(c, brief.constraints)) for i, c in zip(b_items, b_c)]
            sa_n, sb_n = {stem(n) for n in a_names}, {stem(n) for n in b_names}
            row["domains"][d] = {
                "overlap_jaccard": round(len(sa_n & sb_n) / len(sa_n | sb_n), 3) if sa_n | sb_n else None,
                "agent": {"n": len(a_names), "grounded": len(a_names), **sa, "diversity": diversity(a_c)},
                "baseline": {"n": len(b_names), "grounded": sum(c is not None for c in b_c), **sb, "diversity": diversity([c for c in b_c if c]),
                             "claimed_met_but_violated": sum(1 for cl, v in claims if cl and v == "violated"),
                             "ungrounded_examples": [n for n, c in zip(b_names, b_c) if c is None][:3]}}
        row["agent_faithfulness"] = faithful(bp)
        row["influence"] = bp["anchor_influence"]["leave_one_out_set_change"]
        rows.append(row)
        rnd = random.Random(bid)
        flip = rnd.random() < 0.5
        arms = {"A": ("baseline" if flip else "agent"), "B": ("agent" if flip else "baseline")}
        blind.append({"id": bid, "brief": brief, "arms": arms, "agent": {d: [p["name"] for p in bp["domains"][d]["selected"]] for d in DOMAINS},
                      "baseline": {d: pick_names(d, (base.get(d) or [])[: picks[d]]) for d in DOMAINS}})
    (OUT / "eval_rows.json").write_text(json.dumps(rows, indent=1, default=str))
    write_blind(blind)
    write_report(rows, svc)


def write_blind(blind):
    (OUT / "blind_key.json").write_text(json.dumps({b["id"]: b["arms"] for b in blind}, indent=1))
    L = ["# Blind comparison — fill in `blind_scores.csv`", "", "Score each option 1-5 on: fit_to_brief, coherence, specificity; then name overall preferred option (A/B/tie).", ""]
    for b in blind:
        br = b["brief"]
        L += [f"## {b['id']}: {br.concept} — {br.city}", f"Anchors: {', '.join(br.anchors)}. Goals: {br.goals}", ""]
        for opt in ("A", "B"):
            src = b["arms"][opt]
            L.append(f"### Option {opt}")
            L += [f"- **{LABELS[d]}**: " + "; ".join(b[src][d]) for d in DOMAINS]
            L.append("")
    (OUT / "blind_sheet.md").write_text("\n".join(L))
    (OUT / "blind_scores.csv").write_text("brief,option,fit_to_brief,coherence,specificity\n" + "".join(f"{b['id']},{o},,,\n" for b in blind for o in "AB")
                                         + "".join(f"{b['id']},overall_pref(A/B/tie),,,\n" for b in blind))


def write_report(rows, svc):
    ok = [r for r in rows if "domains" in r]
    def agg(arm, field):
        return sum(r["domains"][d][arm][field] for r in ok for d in DOMAINS)
    n = {a: agg(a, "n") for a in ("agent", "baseline")}
    L = ["# VibeSpec Phase 1 — Qloo agent vs Qloo-free baseline", "",
         f"4 identical briefs, baseline = {MODEL} (local, temperature 0, no Qloo access). Live Qloo calls this run: {svc.live_calls} (cache reuse otherwise).",
         "Qloo affinity is NOT used as a success metric. Qloo is used as a catalogue/metadata oracle to ground and verify BOTH arms (disclosed; favours entities Qloo knows).", "",
         "## Aggregate (all domains, all briefs)", "", "| metric | Qloo agent | Qloo-free baseline |", "|---|---|---|",
         f"| picks | {n['agent']} | {n['baseline']} |",
         f"| grounded in Qloo catalogue (real entity; place also in right city) | {agg('agent','grounded')}/{n['agent']} (by construction) | {agg('baseline','grounded')}/{n['baseline']} |"]
    for s in ("satisfied", "violated", "unverifiable"):
        L.append(f"| constraint check: {s} | {agg('agent', s)} | {agg('baseline', s)} |")
    L.append(f"| baseline picks that claimed 'meets constraints' but violated them | – | {agg('baseline', 'claimed_met_but_violated')} |")
    f_ok, f_tot = (sum(r['agent_faithfulness'][i] for r in ok) for i in (0, 1))
    L += [f"| explanation faithfulness (agent: cited shares + rank + constraint claims re-verified) | {f_ok}/{f_tot} | not checkable (free text) |", ""]
    ov = [r["domains"][d]["overlap_jaccard"] for r in ok for d in DOMAINS if r["domains"][d]["overlap_jaccard"] is not None]
    L += [f"Decision-set overlap (mean Jaccard of picks, per domain per brief): **{sum(ov)/len(ov):.3f}** over {len(ov)} comparisons (0 = disjoint).", "",
          "Diversity (mean pairwise 1-Jaccard of Qloo tags; higher = more varied):", "", "| brief | domain | agent | baseline | overlap |", "|---|---|---|---|---|"]
    for r in ok:
        for d in DOMAINS:
            x = r["domains"][d]
            L.append(f"| {r['id']} | {d} | {x['agent']['diversity']} | {x['baseline']['diversity']} (tagged {x['baseline']['grounded']}/{x['baseline']['n']}) | {x['overlap_jaccard']} |")
    L += ["", "## Anchor influence on agent candidate sets (leave-one-out set change)", ""] + [f"- {r['id']}: `{r['influence']}`" for r in ok]
    ung = [(r["id"], d, r["domains"][d]["baseline"]["ungrounded_examples"]) for r in ok for d in DOMAINS if r["domains"][d]["baseline"]["ungrounded_examples"]]
    L += ["", "## Baseline picks not found in Qloo (not necessarily hallucinated: may be absent from Qloo)", ""] + [f"- {i}/{d}: {ex}" for i, d, ex in ung]
    L += ["", "## Not measured here", "- Relevance/coherence/preference: needs human raters. Blind sheet written to private/eval/blind_sheet.md (+ blind_scores.csv, key in blind_key.json); run `python3 score_blind.py` after filling.", ""]
    (HERE / "private" / "phase1" / "EVAL_REPORT.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
