"""Assemble the inspectable decision brief from agent state, and render it as Markdown."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .qloo import Candidate
from .suitability import as_dict

NO_VERIFIED = ("No supplier prices, inventory, contractual rights, or revenue impact were verified. Qloo supplies cultural affinity "
               "and descriptive metadata only.")


def _affinity(c: Candidate) -> float:
    return c.affinity if c.affinity is not None else 0.0


TIER = {"aligned": 0, "unverified": 1}


def rank(accepted: list[Candidate], fit: dict | None = None) -> list[Candidate]:
    """Stage B decides the order: positive fit evidence first, then unverified; affinity only breaks ties within a tier."""
    fit = fit or {}
    def tier(c: Candidate) -> int:
        f = fit.get(c.id)
        return 2 if getattr(f, "discovery_lead", False) else TIER.get(getattr(f, "verdict", "unverified"), 1)
    return sorted(accepted, key=lambda c: (tier(c), -_affinity(c)))


def select(accepted: list[Candidate], k: int, anchor_ids: list[str], fit: dict | None = None) -> list[Candidate]:
    """Best Stage B tier first; within it, each contributing anchor leads at least one pick (coherence)."""
    ranked = rank(accepted, fit)
    best_tier = [c for c in ranked if TIER.get(getattr((fit or {}).get(c.id), "verdict", "unverified"), 1) == 0] or ranked
    chosen: list[Candidate] = []
    for a in anchor_ids:
        lead = next((c for c in best_tier if c not in chosen and c.attribution and max(c.attribution, key=c.attribution.get) == a), None)
        if lead and len(chosen) < k:
            chosen.append(lead)
    chosen += [c for c in ranked if c not in chosen][: k - len(chosen)]
    return [c for c in ranked if c in chosen]


def _shares(c: Candidate, names: dict[str, str]) -> dict[str, float]:
    return {names[i]: round(v, 3) for i, v in c.attribution.items() if i in names}


def _pick(c: Candidate, rank: int, n: int, names: dict[str, str], checks: list[str], unverified: list[str], fit=None, alternative=None) -> dict[str, Any]:
    sh = _shares(c, names)
    primary = max(sh, key=sh.get) if sh else None
    pct = ", ".join(f"{a} {v:.0%}" for a, v in sh.items()) or "no per-anchor attribution returned"
    why = f"Ranked #{rank} of {n} acceptable results in this query. Anchor attribution: {pct}."
    if checks:
        why += (" Constraints met (where data existed): " if unverified else " Constraints met: ") + "; ".join(checks) + "."
    out = {"id": c.id, "name": c.name, "rank_in_query": rank, "of": n, "attribution": sh, "primary_anchor": primary, "why": why,
           "unverified": unverified, "props": dict(c.props), "geo": dict(c.geo) if c.geo else None, "tags": list(c.tags[:6])}
    if fit is not None:  # Stage B: kept separate from the affinity evidence above
        out["suitability"] = {**as_dict(fit), "unknowns": list(dict.fromkeys(fit.unknowns + unverified))}
        out["alternative"] = alternative
    return out


def _checks_run(d: str, cons) -> list[str]:
    out = []
    if d == "place":
        out += [f"price_level <= {cons.max_place_price_level}"] * (cons.max_place_price_level is not None)
        out += [f"rating >= {cons.min_place_rating}"] * (cons.min_place_rating is not None)
        out.append("not marked closed")
    if d == "book" and cons.min_book_year is not None:
        out.append(f"published >= {cons.min_book_year}")
    if d == "brand" and cons.amenity_unit_budget_usd is not None:
        out.append(f"Qloo indicative min <= your assumed ${cons.amenity_unit_budget_usd:g}")
    if cons.exclude_terms:
        out.append("no excluded terms")
    return out


def build(s) -> dict[str, Any]:
    b, names = s.brief, {a.id: a.name for a in s.anchors}
    pending = [{"query": q, "status": r.status, "note": r.note, "candidates": [{"id": i, "name": n, "disambiguation": dis} for i, n, dis in r.candidates]}
               for q, r in s.resolutions.items() if r.status != "resolved"]
    out: dict[str, Any] = {"status": "needs_confirmation" if pending else "failed", "brief": asdict(b), "interpretation": s.picks,
                           "anchors": [{"name": a.name, "id": a.id, "match": a.match} for a in s.anchors], "confirmations_needed": pending,
                           "domains": {}, "missing_data": list(s.warnings), "trace": s.trace}
    errs = [r.note for r in s.resolutions.values() if r.status == "error"]
    if errs:
        out.update(status="failed", error=errs[0], confirmations_needed=[p for p in pending if p["status"] != "error"])
        return out
    if pending or len(s.results) < 4 or len(s.verdict) < 4:
        if not pending:
            out["error"] = "run stopped before completion: " + "; ".join(s.warnings) if s.warnings else "run stopped before completion"
        return out
    missing = out["missing_data"]
    for d, r in s.results.items():
        v = s.verdict[d]
        sel = select(v["accepted"], s.picks[d], [i for i in r.effective if i not in r.ignored], s.fit)
        ranked = sorted(v["accepted"], key=_affinity, reverse=True)  # affinity rank, reported as Stage A evidence only
        spare = [c for c in rank(v["accepted"], s.fit) if c not in sel]
        checks = _checks_run(d, b.constraints)
        picks = [_pick(c, ranked.index(c) + 1, len(ranked), names, checks, v["unverified"].get(c.id, []), s.fit.get(c.id),
                       {"name": spare[i].name, "label": s.fit[spare[i].id].label} if i < len(spare) and spare[i].id in s.fit else None)
                 for i, c in enumerate(sel)]
        outranked = [{"name": c.name, "rank_in_query": ranked.index(c) + 1, "reason": "acceptable but outranked or not needed for anchor balance"}
                     for c in spare][:5]
        rejected = list({c.name: {"name": c.name, "reasons": [reason for _, reason in bad]} for c, bad in v["rejected"]}.values())
        off_brief = list({c.name: {"name": c.name, "label": f.label, "reasons": f.against} for c, f in v.get("off_brief", [])}.values())
        missing += list(r.warnings)
        missing += [f"{domain_label(d)}: {len(v['unverified'])} candidate(s) had constraints that could not be verified from Qloo data"] * bool(v["unverified"])
        missing += [f"{domain_label(d)}: only {len(picks)} of {s.picks[d]} requested picks available after {s.revisions[d]} revision(s)"] * (len(picks) < s.picks[d])
        out["domains"][d] = {"label": domain_label(d), "selected": picks, "outranked": outranked, "rejected": rejected, "off_brief": off_brief, "revisions": s.revisions[d],
                             "pool_size": len(s.pool[d]), "anchors_rejected": {names.get(i, i): why for i, why in r.rejected.items()},
                             "anchors_ignored": [names.get(i, i) for i in r.ignored], "latency_ms": r.latency_ms}
    out["status"] = "complete"
    out["anchor_influence"] = {"leave_one_out_set_change": s.influence, "mean_attribution_in_picks": _mean_attr(out["domains"], list(names.values()))}
    out["budget"] = _budget(out["domains"].get("brand", {}).get("selected", []), b.constraints.amenity_unit_budget_usd)
    missing.append(NO_VERIFIED)
    named = [_by_name(m, names) for m in missing]
    out["missing_data"] = list(dict.fromkeys(named))
    return out


def _by_name(text: str, names: dict[str, str]) -> str:
    for i, n in names.items():
        text = text.replace(i, n)
    return text


def domain_label(d: str) -> str:
    from .agent import LABELS
    return LABELS[d]


def _mean_attr(domains: dict, anchor_names: list[str]) -> dict[str, dict[str, float]]:
    res = {}
    for d, dom in domains.items():
        n = max(len(dom["selected"]), 1)
        res[d] = {a: round(sum(p["attribution"].get(a, 0) for p in dom["selected"]) / n, 3) for a in anchor_names}
    return res


def _budget(brands: list[dict], unit: float | None) -> dict[str, Any]:
    rows = []
    for p in brands:
        lo, hi = p["props"].get("price_range_usd_min"), p["props"].get("price_range_usd_max")
        fit = "unknown" if unit is None or lo is None else ("within" if lo <= unit else "above")
        rows.append({"brand": p["name"], "qloo_indicative_usd_min": lo, "qloo_indicative_usd_max": hi, "fit_vs_user_assumption": fit})
    return {"verified_costs": [], "user_assumptions": {"amenity_unit_budget_usd": unit}, "indicative_qloo_brand_price_ranges": rows,
            "disclaimer": "Verified costs: none. Qloo ranges are indicative metadata, not quotes. The unit budget is your own assumption."}


def to_markdown(bp: dict[str, Any]) -> str:
    b = bp["brief"]
    L = [f"# Cultural Experience Blueprint — {b['concept'][:80] or 'Boutique hotel'} ({b['city']})", "",
         f"Anchors: {', '.join(a['name'] for a in bp['anchors'])}. Status: **{bp['status']}**.", ""]
    if bp["status"] != "complete":
        L += ["## Needs your input", *[f"- '{c['query']}': {c['status']} — {c['note']}" for c in bp["confirmations_needed"]]]
        return "\n".join(L) + "\n"
    for d, dom in bp["domains"].items():
        L += [f"## {dom['label']}", ""]
        for p in dom["selected"]:
            loc = f" — {p['props'].get('address')}" if p["props"].get("address") else ""
            L.append(f"- **{p['name']}**{loc}. {p['why']}" + (f" Unverified: {'; '.join(p['unverified'])}." if p["unverified"] else ""))
            st = p.get("suitability")
            if st:
                L.append(f"  - Use: {st['use']}. Status: {st['label']}.")
                L += [f"  - Fits your goals: {x}" for x in st["fit"]] + [f"  - Verified (Qloo metadata): {x}" for x in st["verified"]]
                L += [f"  - Check before using: {x}" for x in st["unknowns"]] + [f"  - Next step: {st['next_action']}"]
                if p.get("alternative"):
                    L.append(f"  - Alternative: {p['alternative']['name']} ({p['alternative']['label']})")
        for a, why in dom["anchors_rejected"].items():
            L.append(f"- _Anchor {a} not used here:_ {why}")
        for a in dom["anchors_ignored"]:
            L.append(f"- _Anchor {a} accepted by Qloo but contributed nothing here._")
        if dom["rejected"]:
            L += ["", "Rejected:", *[f"- {r['name']}: {'; '.join(r['reasons'])}" for r in dom["rejected"][:8]]]
        if dom.get("off_brief"):
            L += ["", "Did not fit the brief:", *[f"- {r['name']}: {r['label']} ({'; '.join(r['reasons'])})" for r in dom["off_brief"][:8]]]
        L.append("")
    L += ["## Anchor influence (leave-one-out change in candidate set, 0=no change)", f"`{bp['anchor_influence']['leave_one_out_set_change']}`", "",
          "## Budget", bp["budget"]["disclaimer"], "", "## Missing data / warnings", *[f"- {m}" for m in bp["missing_data"]], "",
          "## Decision trace", *[f"{t['step']}. {t['tool']}({t['arg'] or ''}) — {t['outcome']}" for t in bp["trace"]]]
    return "\n".join(L) + "\n"
