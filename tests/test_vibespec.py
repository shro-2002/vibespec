"""Offline tests: a fake transport stands in for Qloo (no network, no key)."""
import pytest

from smoke_test import Unsupported
from vibespec.agent import Brief, Constraints, check, plan_revision, run
from vibespec.blueprint import select, to_markdown
from vibespec.qloo import Anchor, BudgetExceeded, QlooService

IDS = {"Alpha": "A1", "Beta": "B2", "Gamma": "G3"}


def ent(i, name, anchors, **props):
    ex = [{"entity_id": a, "score": 1 / len(anchors)} for a in anchors]
    e = {"entity_id": i, "name": name, "properties": props, "query": {"affinity": 1 - int(i[1:]) / 100, "explainability": {"signal.interests.entities": ex}}}
    if "address" in props:
        e["location"] = {"lat": 1.0, "lon": 2.0, "geohash": "gh" + i}
    return e


class Fake:
    """Programmable Qloo. `invalid` anchors 400 for a domain; `ignored` anchors are accepted but get no attribution."""

    def __init__(self, invalid=None, ignored=None, per_domain=None):
        self.invalid, self.ignored, self.calls, self.per_domain = invalid or {}, ignored or {}, [], per_domain or {}

    def __call__(self, path, params):
        self.calls.append((path, dict(params)))
        if path == "/search":
            q = params["query"]
            hits = {"alpha": [("A1", "Alpha")], "beta": [("B2", "Beta")], "gamma": [("G3", "Gamma")],
                    "twin": [("T1", "Twin"), ("T2", "Twin")], "zzz nonsense": [("X9", "Big Baller Brand")]}.get(q.casefold(), [])
            return {"status": 200, "latency_ms": 1, "error": None, "body": {"results": [{"entity_id": i, "name": n, "disambiguation": "d"} for i, n in hits]}}
        d = params["filter.type"].split(":")[-1]
        anchors = params["signal.interests.entities"].split(",")
        bad = [a for a in anchors if a in self.invalid.get(d, ())]
        if len(bad) == len(anchors):
            return {"status": 400, "latency_ms": 1, "error": "All of the provided signal.interests.entities were invalid", "body": {"errors": []}}
        live = [a for a in anchors if a not in bad and a not in self.ignored.get(d, ())] or [a for a in anchors if a not in bad]
        make = self.per_domain.get(d) or (lambda live, params: [ent(f"{d[0].upper()}{n}", f"{d}-{n}", live) for n in range(1, 9)])
        return {"status": 200, "latency_ms": 1, "error": None, "body": {"results": {"entities": make(live, params)}, "query": {}}}


def svc(fake, **kw):
    return QlooService("k", cache_dir=None, transport=fake, **kw)


ANCH = [Anchor("A1", "Alpha", "exact"), Anchor("B2", "Beta", "exact")]


def test_resolve_exact_and_unknown_fuzzy_rejected():
    s = svc(Fake())
    assert s.resolve("alpha").status == "resolved"
    r = s.resolve("zzz nonsense")
    assert r.status == "ambiguous" and r.anchor is None  # fuzzy hit must not be auto-accepted
    assert s.resolve("nothing here").status == "not_found"


def test_ambiguous_duplicate_needs_confirmation_then_resolves():
    s = svc(Fake())
    assert s.resolve("twin").status == "ambiguous"
    assert s.resolve("twin", confirmed_id="T2").anchor.match == "confirmed"


def test_partly_invalid_anchor_is_ignored_and_disclosed_not_substituted():
    f = Fake(invalid={"book": ("A1",)})
    r = svc(f).query_domain("book", ANCH)
    assert r.ignored == ("A1",) and not r.rejected
    assert r.candidates and all("A1" not in c.attribution for c in r.candidates)
    assert not any("G3" in str(c) for _, c in f.calls)  # no other anchor was introduced


def test_all_anchors_invalid_returns_empty_with_warning():
    f = Fake(invalid={"book": ("A1", "B2")})
    r = svc(f).query_domain("book", ANCH)
    assert not r.candidates and "no anchor is valid" in r.warnings[0] and set(r.rejected) == {"A1", "B2"}
    assert len(f.calls) == 1  # no wasteful per-anchor probing


def test_silently_ignored_anchor_detected():
    r = svc(Fake(ignored={"book": ("A1",)})).query_domain("book", ANCH)
    assert r.ignored == ("A1",) and any("contributed nothing" in w for w in r.warnings)


def test_malformed_and_empty_responses():
    bad = {"book": lambda live, p: [{"entity_id": "", "name": "x"}, ent("B1", "ok", live)]}
    r = svc(Fake(per_domain=bad)).query_domain("book", ANCH)
    assert len(r.candidates) == 1 and any("malformed" in w for w in r.warnings)
    r = svc(Fake(per_domain={"book": lambda live, p: []})).query_domain("book", ANCH)
    assert any("empty" in w for w in r.warnings)


def test_distinct_place_branches_keep_identity():
    two = {"place": lambda live, p: [ent("P1", "Cafe", live, address="1 A St"), ent("P2", "Cafe", live, address="9 B St")]}
    r = svc(Fake(per_domain=two)).query_domain("place", ANCH, city="X")
    assert [c.id for c in r.candidates] == ["P1", "P2"] and r.candidates[0].geo["geohash"] != r.candidates[1].geo["geohash"]


def test_unsupported_param_and_budget_guard():
    with pytest.raises(Unsupported):
        svc(Fake()).query_domain("book", ANCH, extra={"signal.bogus": 1})
    s = svc(Fake(), budget=1)
    s.resolve("alpha")
    with pytest.raises(BudgetExceeded):
        s.resolve("beta")


def test_cache_avoids_second_call():
    f = Fake()
    s = svc(f)
    s.resolve("alpha"); s.resolve("alpha")
    assert len(f.calls) == 1


def test_constraints_flag_violation_and_unverifiable():
    s = svc(Fake(per_domain={"place": lambda live, p: [ent("P1", "Pricey", live, price_level=4, business_rating=4.9), ent("P2", "NoData", live)]}))
    c1, c2 = s.query_domain("place", ANCH, city="X").candidates
    cons = Constraints(max_place_price_level=2, min_place_rating=4.0)
    assert check(c1, cons)[0][0][0] == "price"
    bad, unk = check(c2, cons)
    assert not bad and len(unk) == 2  # missing data is flagged, not assumed OK


def test_rating_rounding_boundary():
    c = svc(Fake(per_domain={"place": lambda live, p: [ent("P1", "Edge", live, price_level=1, business_rating=4.1999998)]})).query_domain("place", ANCH, city="X").candidates[0]
    assert not check(c, Constraints(min_place_rating=4.2))[0]


def test_select_guarantees_anchor_coverage():
    cands = [svc(Fake()).query_domain("book", ANCH).candidates][0]
    only_a = [c for c in cands]
    chosen = select(only_a, 3, ["A1", "B2"])
    assert len(chosen) == 3 and len({c.id for c in chosen}) == 3


def test_revision_choice_follows_rejection_reason():
    rej = [(None, [("price", "x")]), (None, [("price", "y")])]
    extra, why = plan_revision("place", rej, Constraints(max_place_price_level=2), 0)
    assert extra == {"filter.price_level.max": 2} and "price" in why
    extra2, _ = plan_revision("place", rej, Constraints(max_place_price_level=2), 1)
    assert extra2 == {"page": 3}


def brief(**kw):
    base = dict(concept="Hotel", city="X", anchors=("Alpha", "Beta"), goals="")
    return Brief(**{**base, **kw})


def test_agent_end_to_end_with_revision():
    # page 1 all over price cap, filtered query returns acceptable places -> agent must revise and recover
    def places(live, p):
        if "filter.price_level.max" in p:
            return [ent(f"P{n}", f"ok-{n}", live, price_level=1, business_rating=4.5, address="a") for n in range(10, 16)]
        return [ent(f"P{n}", f"dear-{n}", live, price_level=4, business_rating=4.5, address="a") for n in range(1, 9)]

    f = Fake(per_domain={"place": places})
    bp = run(brief(constraints=Constraints(max_place_price_level=2)), svc(f))
    assert bp["status"] == "complete"
    tools = [t["tool"] for t in bp["trace"]]
    assert "revise_query" in tools and tools[-1] == "finish"
    assert all(p["name"].startswith("ok") for p in bp["domains"]["place"]["selected"])
    assert bp["domains"]["place"]["rejected"] and bp["budget"]["verified_costs"] == []
    assert "No supplier prices" in " ".join(bp["missing_data"])
    assert "Cultural Experience Blueprint" in to_markdown(bp)


def test_agent_halts_for_confirmation_and_never_queries():
    f = Fake()
    bp = run(brief(anchors=("Alpha", "zzz nonsense")), svc(f))
    assert bp["status"] == "needs_confirmation" and bp["confirmations_needed"][0]["query"] == "zzz nonsense"
    assert not any(p == "/v2/insights" for p, _ in f.calls)


def test_agent_reports_ignored_and_rejected_anchor_without_substitution():
    f = Fake(invalid={"book": ("A1",), "artist": ("A1", "B2")}, ignored={"brand": ("B2",)})
    bp = run(brief(), svc(f))
    assert bp["domains"]["book"]["anchors_ignored"] == ["Alpha"]
    assert set(bp["domains"]["artist"]["anchors_rejected"]) == {"Alpha", "Beta"} and not bp["domains"]["artist"]["selected"]
    assert bp["domains"]["brand"]["anchors_ignored"] == ["Beta"]
    assert any("only 0 of" in m for m in bp["missing_data"])
    assert not any("G3" in str(c) for _, c in f.calls)


def test_brief_validation():
    with pytest.raises(ValueError):
        brief(anchors=("only one",)).validate()
    with pytest.raises(ValueError):
        brief(constraints=Constraints(max_place_price_level=9)).validate()


def test_upstream_errors_are_user_safe():
    s = QlooService("k", cache_dir=None, transport=lambda p, q: {"status": 500, "body": {"error": "internal secret detail"}, "latency_ms": 1, "error": "internal secret detail"})
    r = s.resolve("alpha")
    assert r.status == "error" and "HTTP 500" in r.note and "secret" not in r.note
    s = QlooService("k", cache_dir=None, transport=lambda p, q: {"status": 200, "body": None, "latency_ms": 1, "error": None})
    assert "unexpected response" in s.resolve("alpha").note
    bp = run(brief(), s)
    assert bp["status"] == "failed" and "unexpected response" in bp["error"]


def test_llm_source_tolerates_messy_generator_output_and_flags_unverified():
    from vibespec.llm_source import LLMService

    s = LLMService(cache_dir=None)
    s._chat = lambda prompt: {"items": ["Bare Name", {"name": "Proper", "publication_year": "2019"}, 42, {"name": ""}, {"name": "Proper"}]}
    r = s.query_domain("book", [Anchor("a", "Alpha", "x")], take=20)
    assert [c.name for c in r.candidates] == ["Bare Name", "Proper"] and r.candidates[1].props["publication_year"] == 2019
    assert any("self-reported" in w for w in r.warnings) and not r.candidates[0].attribution
