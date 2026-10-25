#!/usr/bin/env python3
"""VibeSpec Phase 0: read-only Qloo API feasibility smoke test.

Key comes ONLY from env var QLOO_API_KEY. Without it every live check is BLOCKED (nothing fabricated).
Run:  QLOO_API_KEY=... python3 smoke_test.py      (stdlib only)
Outputs: fixtures/*.json (sanitized), results.json, REPORT.md
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_BASE = "https://hackathon.api.qloo.com"  # GET only, header X-Api-Key
_override = os.environ.get("QLOO_BASE_URL", "")
# Override is honoured ONLY for loopback (test fakes); a misconfigured remote host must never receive the key.
BASE = _override if urllib.parse.urlparse(_override).hostname in ("127.0.0.1", "localhost") else DEFAULT_BASE
BRANDS = ["Aesop", "Muji", "Patagonia"]
TARGETS = {"book": "urn:entity:book", "artist": "urn:entity:artist", "brand": "urn:entity:brand", "place": "urn:entity:place"}
SLEEP_S, TIMEOUT_S, MAX_RETRIES = 0.4, 20, 2

# Allow-list taken from the official /v2/insights parameter reference (docs.qloo.com insights-api-deep-dive).
INSIGHTS_PARAMS = {
    "filter.type", "filter.location.query", "filter.location", "filter.location.radius", "filter.tags",
    "filter.release_year.min", "filter.results.entities", "filter.exclude.entities", "filter.popularity.min",
    "filter.popularity.max", "filter.geocode.country_code", "filter.price_level.min", "filter.price_level.max",
    "signal.interests.entities", "signal.interests.tags", "signal.location.query", "signal.location",
    "signal.location.radius", "signal.location.weight", "signal.interests.entities.weight",
    "filter.publication_year.min", "filter.publication_year.max", "filter.exclude.tags", "filter.rating.min",
    "feature.explainability", "bias.trends", "diversify.by", "sort_by", "take", "offset", "page", "operator.signal.interests.tags",
}
SEARCH_PARAMS = {"query", "types", "take"}  # per Hackathon developer guide; docs.qloo.com /search page unreachable (404) -> verified live


class Unsupported(ValueError):
    pass


def validate(path, params):
    allowed = SEARCH_PARAMS if path == "/search" else INSIGHTS_PARAMS
    bad = sorted(set(params) - allowed)
    if bad:
        raise Unsupported(f"{path}: unsupported params {bad}")
    if path == "/v2/insights" and "filter.type" not in params:
        raise Unsupported("filter.type is required")


def call(path, params, key):
    """One GET. Returns dict(status, body, latency_ms, error). Never raises on HTTP/network problems."""
    validate(path, params)
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(MAX_RETRIES + 1):
        t0 = time.time()
        req = urllib.request.Request(url, headers={"X-Api-Key": key, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                raw, status = r.read(), r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read(), e.code
            if (status == 429 or status >= 500) and attempt < MAX_RETRIES:
                time.sleep(float(e.headers.get("Retry-After") or 2 * (attempt + 1)))
                continue
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < MAX_RETRIES:
                time.sleep(1 + attempt)
                continue
            return {"status": "network_error", "body": None, "latency_ms": int((time.time() - t0) * 1000), "error": type(e).__name__}
        ms = int((time.time() - t0) * 1000)
        try:
            body = json.loads(raw)
        except ValueError:
            return {"status": status, "body": None, "latency_ms": ms, "error": "malformed_json"}
        time.sleep(SLEEP_S)
        return {"status": status, "body": body, "latency_ms": ms, "error": None if status == 200 else str(body)[:200]}


def entities(body):
    """Both /search and /v2/insights have been seen with results as list or {entities: []}."""
    if not isinstance(body, dict):
        return []
    r = body.get("results")
    if isinstance(r, dict):
        r = r.get("entities")
    return r if isinstance(r, list) else []


def paths(obj, prefix="", out=None):
    out = Counter() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            out[p + ("" if v is not None else " (null)")] += 1
            paths(v, p, out)
    elif isinstance(obj, list):
        for v in obj:
            paths(v, prefix + "[]", out)
    return out


def save(name, res):
    # Key is never stored (headers are not recorded); bodies only.
    (HERE / "fixtures" / f"{name}.json").write_text(json.dumps({"status": res["status"], "body": res["body"]}, indent=1))


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def names(res):
    return [e.get("name") for e in entities(res["body"]) if e.get("name")]


def main():
    key = os.environ.get("QLOO_API_KEY", "").strip()
    R = {"checks": {}, "warnings": [], "blocked": not key}
    (HERE / "fixtures").mkdir(exist_ok=True)

    # Local negative control: unsupported params must be rejected, never silently sent.
    try:
        validate("/v2/insights", {"filter.type": "urn:entity:book", "signal.bogus": "x"})
        R["checks"]["local_unsupported_param_rejected"] = "FAIL"
    except Unsupported:
        R["checks"]["local_unsupported_param_rejected"] = "PASS"

    if not key:
        R["warnings"].append("QLOO_API_KEY not set: all live checks BLOCKED. Nothing fabricated.")
        finish(R)
        return

    # 1. Brand resolution
    ids = {}
    for b in BRANDS:
        res = call("/search", {"query": b, "types": TARGETS["brand"], "take": 5}, key)
        save(f"search_{b.lower()}", res)
        es = entities(res["body"])
        exact = [e for e in es if (e.get("name") or "").lower() == b.lower()]
        top = (exact or es or [None])[0]
        ids[b] = top.get("entity_id") or top.get("id") if top else None
        R["checks"][f"search_{b}"] = {"status": res["status"], "n": len(es), "resolved_name": top.get("name") if top else None,
                                      "exact_match": bool(exact), "id_present": bool(ids[b]), "latency_ms": res["latency_ms"],
                                      "fields": sorted(top.keys()) if top else []}
    miss = call("/search", {"query": "Zzqxv Nonexistent Brand 9137", "types": TARGETS["brand"], "take": 5}, key)
    R["checks"]["search_missing_entity"] = {"status": miss["status"], "n": len(entities(miss["body"])), "top": (names(miss) or [None])[0]}
    badkey = call("/search", {"query": "Aesop", "types": TARGETS["brand"], "take": 1}, "invalid-key-test")
    R["checks"]["auth_error_handling"] = {"status": badkey["status"], "handled_without_exception": True}

    # 2-5. Brand -> book/artist/brand/place, plus explainability and anchor sensitivity
    sets, schema = {}, Counter()
    for tgt, urn in TARGETS.items():
        for b in BRANDS:
            if not ids.get(b):
                R["checks"][f"{tgt}_from_{b}"] = {"status": "SKIPPED_UNRESOLVED_BRAND"}
                continue
            p = {"filter.type": urn, "signal.interests.entities": ids[b], "feature.explainability": "true", "take": 20}
            if tgt == "place":
                p["filter.location.query"] = "New York City"
            res = call("/v2/insights", p, key)
            save(f"insights_{tgt}_{b.lower()}", res)
            es = entities(res["body"])
            sets[(tgt, b)] = names(res)
            if res["body"]:
                paths(res["body"], out=schema)
            with_expl = sum(1 for e in es if isinstance((e.get("query") or {}).get("explainability"), (dict, list)))
            top_expl = isinstance(((res["body"] or {}).get("query") or {}).get("explainability"), (dict, list))
            complete = sum(1 for e in es if e.get("name") and (e.get("entity_id") or e.get("id")))
            R["checks"][f"{tgt}_from_{b}"] = {
                "status": res["status"], "n": len(es), "named_with_id": complete, "explainability_per_result": with_expl,
                "explainability_top_level": top_expl, "latency_ms": res["latency_ms"], "sample": sets[(tgt, b)][:5], "error": res["error"]}
    # Location sanity: does adding the location change place results?
    if ids.get("Aesop"):
        nl = call("/v2/insights", {"filter.type": TARGETS["place"], "signal.interests.entities": ids["Aesop"], "take": 20}, key)
        save("insights_place_aesop_nolocation", nl)
        R["checks"]["place_location_effect_jaccard_aesop"] = {"status": nl["status"], "jaccard_vs_located": round(jaccard(names(nl), sets.get(("place", "Aesop"), [])), 3)}
    # Combined anchors
    if all(ids.get(b) for b in BRANDS):
        res = call("/v2/insights", {"filter.type": TARGETS["book"], "signal.interests.entities": ",".join(ids[b] for b in BRANDS),
                                    "feature.explainability": "true", "take": 20}, key)
        save("insights_book_combined", res)
        R["checks"]["book_combined_anchors"] = {"status": res["status"], "n": len(entities(res["body"])), "sample": names(res)[:5]}

    # Anchor sensitivity (pairwise Jaccard of top-20 names per target)
    sens = {}
    for tgt in TARGETS:
        pairs = {f"{a}~{b}": round(jaccard(sets.get((tgt, a), []), sets.get((tgt, b), [])), 3) for i, a in enumerate(BRANDS) for b in BRANDS[i + 1:]}
        mean = sum(pairs.values()) / len(pairs)
        sens[tgt] = {"pairwise_jaccard": pairs, "mean": round(mean, 3), "material_change": mean < 0.5}
    R["anchor_sensitivity"] = sens
    R["response_field_paths"] = {k: v for k, v in sorted(schema.items())}

    for tgt in TARGETS:
        if sens[tgt]["mean"] == 0.0 and any(sets.get((tgt, b)) for b in BRANDS):
            R["warnings"].append(f"{tgt}: zero overlap across brand anchors (fully distinct, but verify results are not merely noise)")
    finish(R)


def verdict(R):
    """Programmatic PASS/FAIL per endpoint; no human adjustment."""
    c, v = R["checks"], {}
    if R["blocked"]:
        return {k: "BLOCKED" for k in ["brand_resolution", "brand_to_book", "brand_to_artist", "brand_to_brand", "brand_to_place", "explainability"]}
    v["brand_resolution"] = "PASS" if all(c[f"search_{b}"]["status"] == 200 and c[f"search_{b}"]["id_present"] for b in BRANDS) else "FAIL"
    for tgt in TARGETS:
        rows = [c.get(f"{tgt}_from_{b}", {}) for b in BRANDS]
        ok = all(r.get("status") == 200 and r.get("n", 0) >= 5 and r.get("named_with_id", 0) >= 0.8 * r["n"] for r in rows)
        v[f"brand_to_{tgt}"] = "PASS" if ok else "FAIL"
    ex = [c.get(f"{t}_from_{b}", {}) for t in TARGETS for b in BRANDS]
    ok_ex = sum(1 for r in ex if r.get("n") and r.get("explainability_per_result", 0) >= 0.5 * r["n"])
    v["explainability"] = "PASS" if ok_ex >= 0.75 * len(ex) else ("PARTIAL" if ok_ex else "FAIL")
    return v


def finish(R):
    R["verdicts"] = verdict(R)
    (HERE / "results.json").write_text(json.dumps(R, indent=1, default=str))
    lines = [f"# VibeSpec Phase 0 — raw run output ({'BLOCKED: no key' if R['blocked'] else 'live'})", "", "## Verdicts", ""]
    lines += [f"- {k}: **{v}**" for k, v in R["verdicts"].items()]
    lines += ["", "## Checks", "```json", json.dumps(R["checks"], indent=1, default=str), "```"]
    if "anchor_sensitivity" in R:
        lines += ["", "## Anchor sensitivity", "```json", json.dumps(R["anchor_sensitivity"], indent=1), "```"]
    if R["warnings"]:
        lines += ["", "## Warnings"] + [f"- {w}" for w in R["warnings"]]
    (HERE / "RAW_RUN.md").write_text("\n".join(lines) + "\n")
    print("\n".join(f"{k}: {v}" for k, v in R["verdicts"].items()))
    print("warnings:", R["warnings"])


if __name__ == "__main__":
    sys.exit(main())
