#!/usr/bin/env python3
"""Phase 2 controlled comparison. System A = engine + Qloo candidates. System B = SAME engine, validators, selection and
blueprint code + Qloo-free (LLM) candidate generation. Same briefs, constraints, take=20 per query, same revision limits.

Outputs (git-ignored, contain Qloo data): private/eval2/*.json, rater.html, blind_key.json
Public aggregate: docs/EVAL_CONTROLLED_REPORT.md (no entity names).
Human ratings are NOT fabricated: the report says PENDING until CSVs exist (see score_controlled.py).
"""
import json, os, random, sys
from pathlib import Path

from evaluate import BRIEFS, diversity, ground, pick_names, stem, verdict  # noqa: F401  (reuse Phase 1 helpers)
from run_brief import load
from vibespec.agent import DOMAINS, LABELS, interpret, run
from vibespec.llm_source import LLMService
from vibespec.qloo import Candidate, QlooService

HERE = Path(__file__).parent
OUT = HERE / "private" / "eval2"
RUBRIC = {"cultural_fit": "Do the picks reflect the brief's cultural anchors, concept and goals?",
          "coherence": "Do music, books, amenities and places feel like one deliberate identity, not four separate lists?",
          "usefulness": "Could a hotel team act on this plan (clear, specific, varied enough to choose from)?",
          "feasibility": "Are the picks real, plausible to obtain or visit in the city, and consistent with the stated constraints?"}


def run_arms(key, brief_id):
    brief = load(HERE / "briefs" / f"{brief_id}.json")
    OUT.mkdir(parents=True, exist_ok=True)
    arms = {}
    for arm, mk in (("A", lambda: QlooService(key, HERE / ".cache", budget=300)), ("B", lambda: LLMService(cache_dir=HERE / ".cache_llm"))):  # fresh service per brief: isolated call counts
        f = OUT / f"{brief_id}.{arm}.json"
        if f.exists():
            arms[arm] = json.loads(f.read_text())
            continue
        svc = mk()
        bp = run(brief, svc, audit=False)  # audit is analysis-only; disabled in both arms for parity
        bp["_calls"] = {"live": svc.live_calls, "cache_hits": svc.cache_hits}
        f.write_text(json.dumps(bp, indent=1, default=str))
        arms[arm] = bp
    return brief, arms


def plan_lists(bp):
    return {d: [p["name"] for p in bp["domains"][d]["selected"]] for d in DOMAINS}


def equalise(p1, p2):
    """Show equal list lengths per domain (first n in each arm's own ranking) so length cannot reveal identity."""
    n = {d: min(len(p1[d]), len(p2[d])) for d in p1}
    return {"1": {d: p1[d][:n[d]] for d in p1}, "2": {d: p2[d][:n[d]] for d in p2}}


def candidate_from_pick(p, d):
    return Candidate(p["id"], p["name"], d, None, {}, tuple(p["tags"]), p["props"])


def main():
    key = os.environ.get("QLOO_API_KEY", "")
    if not key:
        sys.exit("BLOCKED: QLOO_API_KEY not set (System A and the existence oracle need it)")
    oracle_svc = QlooService(key, HERE / ".cache", budget=300)  # existence/metadata oracle only; never used to generate either arm
    rows, packet = [], []
    for bid in BRIEFS:
        brief, arms = run_arms(key, bid)
        if any(arms[a]["status"] != "complete" for a in arms):
            rows.append({"id": bid, "error": {a: arms[a]["status"] for a in arms}})
            continue
        picks_n = interpret(brief)
        row = {"id": bid, "domains": {}, "calls": {a: arms[a].get("_calls") for a in arms}}
        for d in DOMAINS:
            res = {}
            for a in ("A", "B"):
                items = arms[a]["domains"][d]["selected"]
                cands = [candidate_from_pick(p, d) for p in items]
                self_v = {"satisfied": 0, "violated": 0, "unverifiable": 0}
                for c in cands:
                    self_v[verdict(c, brief.constraints)] += 1
                if a == "A":
                    oracle, exist = [verdict(c, brief.constraints) for c in cands], len(cands)
                else:  # independent catalogue check of B's picks; failing to match is NOT proof of fabrication
                    grounded = [ground(oracle_svc, d, c.name, brief.city) for c in cands]
                    oracle = [verdict(g, brief.constraints) if g else "unverifiable" for g in grounded]
                    exist = sum(g is not None for g in grounded)
                    res["B_self_pass_oracle_violated"] = oracle.count("violated")  # B's picks all passed B's self-reported check
                res[a] = {"n": len(cands), "pool_size": arms[a]["domains"][d]["pool_size"],
                          "revisions": arms[a]["domains"][d]["revisions"], "self_check": self_v, "oracle_check": {k: oracle.count(k) for k in ("satisfied", "violated", "unverifiable")},
                          "found_in_catalogue": exist}
            na, nb = {stem(n) for n in plan_lists(arms["A"])[d]}, {stem(n) for n in plan_lists(arms["B"])[d]}
            res["overlap_jaccard"] = round(len(na & nb) / len(na | nb), 3) if na | nb else None
            row["domains"][d] = res
        rows.append(row)
        flip = random.Random("seed-" + bid).random() < 0.5
        mapping = {"1": "B" if flip else "A", "2": "A" if flip else "B"}  # neutral labels hide system identity
        packet.append({"id": bid, "concept": brief.concept, "city": brief.city, "anchors": list(brief.anchors), "goals": brief.goals,
                       "constraints": constraint_text(brief.constraints), "plans": equalise(plan_lists(arms[mapping["1"]]), plan_lists(arms[mapping["2"]])), "_map": mapping})
    (OUT / "rows.json").write_text(json.dumps(rows, indent=1, default=str))
    (OUT / "blind_key.json").write_text(json.dumps({p["id"]: p["_map"] for p in packet}, indent=1))
    write_rater_html(packet)
    write_report(rows)


def constraint_text(c):
    parts = [f"places: price level at most {c.max_place_price_level} (1-4)" if c.max_place_price_level else None,
             f"places: rating at least {c.min_place_rating}" if c.min_place_rating else None,
             f"books published {c.min_book_year} or later" if c.min_book_year else None,
             f"amenity brands: assumed unit budget ${c.amenity_unit_budget_usd:g}" if c.amenity_unit_budget_usd else None,
             f"exclude: {', '.join(c.exclude_terms)}" if c.exclude_terms else None]
    return "; ".join(p for p in parts if p) or "none"


def write_rater_html(packet):
    public = [{k: v for k, v in p.items() if k != "_map"} for p in packet]
    html = RATER_TEMPLATE.replace("__DATA__", json.dumps(public)).replace("__RUBRIC__", json.dumps(RUBRIC)).replace("__LABELS__", json.dumps(LABELS))
    (OUT / "rater.html").write_text(html)


def write_report(rows):
    ok = [r for r in rows if "domains" in r]
    L = ["# VibeSpec Phase 2 — controlled comparison (System A: Qloo vs System B: same engine, Qloo-free candidates)", "",
         "Status of human ratings: **PENDING — none collected, none fabricated.** Run `python3 score_controlled.py` after raters export CSVs.", "",
         "## Design", "- Same agent loop, constraint validator, revision logic, selection and blueprint code in both arms; only candidate generation differs.",
         "- A: Qloo `/v2/insights` (take=20 per query, server-side filters during revisions). B: local `qwen3:14b` (temperature 0), take=20 per query, constraints as prompt text during revisions, attributes self-reported (flagged unverified). Details: `vibespec/llm_source.py`.",
         "- Same 4 briefs, constraints, pick counts, revision limits (2 per domain), influence audit disabled in both.",
         "- Qloo affinity is not used as a success metric. Human rubric (1-5): cultural fit, coherence, usefulness, feasibility, plus overall preference A/B/tie. Plans are shown as neutral 'Plan 1/2', order randomised per brief, system key stored separately.",
         "- Blinding limit: Qloo picks tend to be niche, so a rater may guess identity; raters are told not to try.", "",
         "## Budget and candidate parity", "",
         "Requests per run = live + cache hits (A: Qloo requests incl. 2-3 anchor lookups, B: LLM generations). Pool = candidates generated per domain before validation (cap 20 per query).", "",
         "| brief | A requests | B requests | A pool a/b/br/pl | B pool a/b/br/pl |", "|---|---|---|---|---|"]
    pool = lambda r, arm: "/".join(str(r["domains"][d][arm]["pool_size"]) for d in DOMAINS)  # noqa: E731
    L += [f"| {r['id']} | {r['calls']['A']['live'] + r['calls']['A']['cache_hits']} | {r['calls']['B']['live'] + r['calls']['B']['cache_hits']} | {pool(r, 'A')} | {pool(r, 'B')} |" for r in ok]
    L += ["", "Parity is approximate, not exact: A needs anchor lookups and sometimes pages/filters; B needs none, so B used fewer requests. Plans shown to raters are truncated to equal list lengths per domain."]
    tot = lambda arm, k, sub: sum(r["domains"][d][arm][k][sub] if sub else r["domains"][d][arm][k] for r in ok for d in DOMAINS)  # noqa: E731
    L += ["", "## Automated secondary checks (not a quality measure)", "",
          "Oracle = Qloo catalogue lookup (existence + metadata) applied to B's picks; A's picks carry Qloo metadata already, so A's numbers are not independent of how A was selected. Missing from catalogue != fabricated.", "",
          "| | A (Qloo) | B (Qloo-free) |", "|---|---|---|",
          f"| picks | {tot('A','n',None)} | {tot('B','n',None)} |",
          f"| picks found in Qloo catalogue | {tot('A','found_in_catalogue',None)} (by construction) | {tot('B','found_in_catalogue',None)} |",
          f"| oracle constraint check: satisfied | {tot('A','oracle_check','satisfied')} | {tot('B','oracle_check','satisfied')} |",
          f"| oracle constraint check: violated | {tot('A','oracle_check','violated')} | {tot('B','oracle_check','violated')} |",
          f"| oracle constraint check: unverifiable | {tot('A','oracle_check','unverifiable')} | {tot('B','oracle_check','unverifiable')} |",
          f"| B picks whose self-reported attributes passed but catalogue metadata violates | – | {sum(r['domains'][d].get('B_self_pass_oracle_violated', 0) for r in ok for d in DOMAINS)} |", ""]
    ov = [r["domains"][d]["overlap_jaccard"] for r in ok for d in DOMAINS if r["domains"][d]["overlap_jaccard"] is not None]
    L += [f"Pick overlap A vs B: mean Jaccard {sum(ov)/len(ov):.3f} over {len(ov)} comparisons (difference is not improvement).", "",
          "## Human evaluation", "", "PENDING. Rater page: `private/eval2/rater.html` (offline, exports CSV). Raters needed: >=3 independent, none of whom built the system.", ""]
    (HERE / "docs" / "EVAL_CONTROLLED_REPORT.md").write_text("\n".join(L))
    print("\n".join(L))


RATER_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Blind plan rating</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1000px;margin:0 auto;padding:16px;color:#1d1b18;background:#faf8f4}h1,h2{font-family:Georgia,serif}
.brief{border:1px solid #ddd5c8;border-radius:12px;padding:16px;margin:20px 0;background:#fff}.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.plan{border:1px solid #ddd5c8;border-radius:10px;padding:12px}.plan h3{margin:0 0 6px}ul{margin:4px 0;padding-left:18px}.r{display:grid;gap:4px;margin:8px 0}
.r label{font-size:.9rem}.scale{display:flex;gap:10px;flex-wrap:wrap}button{font:inherit;padding:10px 18px;border-radius:999px;border:1px solid #1d1b18;background:#1d1b18;color:#fff;cursor:pointer;min-height:44px}
input[type=text],textarea{font:inherit;padding:8px;border:1px solid #ddd5c8;border-radius:8px;width:100%}small{color:#6b645b}</style></head><body>
<h1>Blind plan rating</h1><p>Each brief has two anonymous plans. Score each on the four criteria (1 = poor, 5 = excellent), then choose overall preference. Judge only what you see; do not try to guess who made a plan. Look items up if unsure they exist.</p>
<p><label>Your rater ID (any short name or code) <input id="rater" type="text" maxlength="40"></label></p><div id="root"></div><p><button id="dl">Download my ratings (CSV)</button> <small id="msg"></small></p>
<script>
const DATA=__DATA__,RUBRIC=__RUBRIC__,LABELS=__LABELS__,root=document.getElementById('root');
function el(t,a={},...k){const e=document.createElement(t);for(const[x,v]of Object.entries(a))e.setAttribute(x,v);for(const c of k.flat())e.append(c.nodeType?c:document.createTextNode(c));return e}
for(const b of DATA){const box=el('section',{class:'brief'},el('h2',{},`${b.concept} — ${b.city}`),el('p',{},`Cultural anchors: ${b.anchors.join(', ')}. Goals: ${b.goals||'(none)'}`),el('p',{},el('small',{},`Constraints: ${b.constraints}`)));
 const plans=el('div',{class:'plans'});
 for(const p of['1','2']){const c=el('div',{class:'plan'},el('h3',{},`Plan ${p}`));
  for(const[d,names]of Object.entries(b.plans[p]))c.append(el('div',{},el('b',{},LABELS[d]),el('ul',{},names.map(n=>el('li',{},n)))));
  for(const[k,q]of Object.entries(RUBRIC)){const g=el('div',{class:'r'},el('label',{},`${k.replace('_',' ')}: ${q}`),el('div',{class:'scale'},[1,2,3,4,5].map(n=>el('label',{},el('input',{type:'radio',name:`${b.id}|${p}|${k}`,value:n}),' '+n))));c.append(g)}
  plans.append(c)}
 box.append(plans,el('div',{class:'r'},el('label',{},'Overall preference for this brief:'),el('div',{class:'scale'},['1','2','tie'].map(v=>el('label',{},el('input',{type:'radio',name:`${b.id}|overall`,value:v}),' '+(v==='tie'?'Tie':'Plan '+v))))),el('label',{},'Comment (optional)',el('textarea',{name:`${b.id}|comment`,rows:2})));
 root.append(box)}
document.getElementById('dl').onclick=()=>{const rater=(document.getElementById('rater').value||'anon').replace(/[^\w-]/g,'_'),rows=[['rater','brief','plan','cultural_fit','coherence','usefulness','feasibility','overall_pref','comment']],val=n=>{const x=document.querySelector(`input[name="${n}"]:checked`);return x?x.value:''};
 let missing=0;for(const b of DATA){for(const p of['1','2']){const v=Object.keys(RUBRIC).map(k=>val(`${b.id}|${p}|${k}`));missing+=v.filter(x=>!x).length;rows.push([rater,b.id,p,...v,'',''])}
  const o=val(`${b.id}|overall`);if(!o)missing++;rows.push([rater,b.id,'overall','','','','',o,(document.querySelector(`[name="${b.id}|comment"]`).value||'').replace(/[\r\n]+/g,' ')])}
 const csv=rows.map(r=>r.map(c=>`"${String(c).replace(/"/g,'""')}"`).join(',')).join('\n'),a=el('a',{href:URL.createObjectURL(new Blob([csv],{type:'text/csv'})),download:`ratings_${rater}.csv`});a.click();
 document.getElementById('msg').textContent=missing?`${missing} answer(s) still blank; file downloaded anyway.`:'Complete. Send the CSV file back.'};
</script></body></html>"""

if __name__ == "__main__":
    main()
