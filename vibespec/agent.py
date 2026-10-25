"""Bounded tool-selection agent: brief -> anchors -> Qloo queries -> constraint validation -> revision -> blueprint.

The planner is rule-based on purpose (no LLM needed, fully reproducible): each step picks the next tool from the
current state (unresolved anchor, unqueried domain, unvalidated domain, deficient domain), and a rejection-driven
revision step chooses a server-side filter or paging based on WHY candidates were rejected. Every step is traced.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Mapping

from .qloo import Anchor, Candidate, DomainResult, QlooService, Resolution, StopRun

DOMAINS = ("artist", "book", "brand", "place")
MAX_STEPS, MAX_REVISIONS, DEFAULT_PICKS = 40, 2, 4
KEYWORDS = {"artist": ("music", "sound", "playlist", "song", "listen"), "book": ("read", "book", "library", "literature"),
            "brand": ("amenit", "bath", "product", "brand", "scent", "linen"), "place": ("local", "neighborhood", "explor", "walk", "city", "culture", "dining")}
LABELS = {"artist": "Music identity", "book": "Guest literature", "brand": "Amenity brands", "place": "Local cultural guide"}


@dataclass(frozen=True)
class Constraints:
    max_place_price_level: int | None = None  # Qloo price_level 1-4
    min_place_rating: float | None = None
    min_book_year: int | None = None
    exclude_terms: tuple[str, ...] = ()
    amenity_unit_budget_usd: float | None = None  # USER-ENTERED assumption, never verified


@dataclass(frozen=True)
class Brief:
    concept: str
    city: str
    anchors: tuple[str, ...]
    goals: str = ""
    constraints: Constraints = Constraints()
    confirmed: Mapping[str, str] = field(default_factory=dict)  # anchor query -> entity_id the user confirmed

    def validate(self) -> None:
        if not 2 <= len(self.anchors) <= 3:
            raise ValueError("provide 2-3 cultural anchors")
        if not self.city.strip() or any(not a.strip() or len(a) > 80 for a in self.anchors):
            raise ValueError("city and anchors must be non-empty (anchors <= 80 chars)")
        if len(self.concept) > 500 or len(self.goals) > 800:
            raise ValueError("concept <= 500 chars, goals <= 800 chars")
        c = self.constraints
        if c.max_place_price_level is not None and not 1 <= c.max_place_price_level <= 4:
            raise ValueError("max_place_price_level must be 1-4")
        if c.min_place_rating is not None and not 0 <= c.min_place_rating <= 5:
            raise ValueError("min_place_rating must be 0-5")
        if c.amenity_unit_budget_usd is not None and c.amenity_unit_budget_usd < 0:
            raise ValueError("budget must be >= 0")


def interpret(brief: Brief) -> dict[str, int]:
    """Goals text -> picks per domain. Emphasised domains get 5, the rest 3; no signal -> 4 each."""
    text = brief.goals.casefold()
    hit = {d for d, ws in KEYWORDS.items() if any(w in text for w in ws)}
    if not hit:
        return {d: DEFAULT_PICKS for d in DOMAINS}
    return {d: 5 if d in hit else 3 for d in DOMAINS}


# ---- constraint validation (local, independent of Qloo scoring) ---------------------------------------------
def check(c: Candidate, cons: Constraints) -> tuple[list[tuple[str, str]], list[str]]:
    """Returns (violations [(code, reason)], unverifiable notes)."""
    bad: list[tuple[str, str]] = []
    unk: list[str] = []
    p = c.props
    blob = " ".join([c.name, str(p.get("description", "")), str(p.get("short_description", "")), *c.tags]).casefold()
    for term in cons.exclude_terms:
        if term.casefold() in blob:
            bad.append(("exclude", f"matches excluded term '{term}'"))
    if c.domain == "place":
        if p.get("is_closed") is True:
            bad.append(("closed", "marked closed in Qloo data"))
        _bound(bad, unk, "price", p.get("price_level"), cons.max_place_price_level, "price_level", upper=True)
        _bound(bad, unk, "rating", p.get("business_rating"), cons.min_place_rating, "business_rating", upper=False)
    if c.domain == "book":
        _bound(bad, unk, "year", p.get("publication_year"), cons.min_book_year, "publication_year", upper=False)
    if c.domain == "brand" and cons.amenity_unit_budget_usd is not None:
        lo = p.get("price_range_usd_min")
        if lo is None:
            unk.append("no Qloo price range, budget fit unknown")
        elif lo > cons.amenity_unit_budget_usd:
            bad.append(("budget", f"Qloo indicative minimum ${lo:g} exceeds your assumed ${cons.amenity_unit_budget_usd:g} (indicative, not a quote)"))
    return bad, unk


def _bound(bad, unk, code, value, limit, label, upper):
    if limit is None:
        return
    if value is None:
        unk.append(f"{label} missing, constraint unverifiable")
    elif (round(value, 1) > limit) if upper else (round(value, 1) < limit):
        bad.append((code, f"{label} {value:g} {'above max' if upper else 'below min'} {limit:g}"))


# ---- agent state --------------------------------------------------------------------------------------------
@dataclass
class State:
    brief: Brief
    picks: dict[str, int]
    resolutions: dict[str, Resolution] = field(default_factory=dict)
    anchors: list[Anchor] = field(default_factory=list)
    results: dict[str, DomainResult] = field(default_factory=dict)
    pool: dict[str, dict[str, Candidate]] = field(default_factory=dict)
    verdict: dict[str, dict[str, Any]] = field(default_factory=dict)
    revisions: Counter = field(default_factory=Counter)
    trace: list[dict[str, Any]] = field(default_factory=list)
    influence: dict[str, dict[str, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def next_action(s: State) -> tuple[str, str | None]:
    for q in s.brief.anchors:
        if q not in s.resolutions:
            return "resolve_anchor", q
    if any(r.status != "resolved" for r in s.resolutions.values()):
        return "halt_for_confirmation", None
    for d in DOMAINS:
        if d not in s.results:
            return "query_domain", d
    for d in DOMAINS:
        if d not in s.verdict:
            return "validate_constraints", d
    for d in DOMAINS:
        v = s.verdict[d]
        if len(v["accepted"]) < s.picks[d] and s.revisions[d] < MAX_REVISIONS and not v["exhausted"]:
            return "revise_query", d
    if len(s.anchors) > 1 and not s.influence:
        return "audit_influence", None
    return "finish", None


def run(brief: Brief, svc: QlooService, audit: bool = True, on_event=None) -> dict[str, Any]:
    """on_event(dict) receives real progress: {'step','tool','arg','phase':'running'|'done','outcome'}."""
    brief.validate()
    s = State(brief, interpret(brief))
    emit = on_event or (lambda e: None)
    for step in range(MAX_STEPS):
        tool, arg = next_action(s)
        if tool == "audit_influence" and not audit:
            break
        emit({"step": step + 1, "tool": tool, "arg": arg, "phase": "running", "outcome": None})
        try:
            out = _TOOLS[tool](s, svc, arg)
        except StopRun as e:  # e.g. deadline raised inside a worker thread
            s.warnings.append(str(e))
            out = "budget"
        s.trace.append({"step": step + 1, "tool": tool, "arg": arg, "outcome": out})
        emit({**s.trace[-1], "phase": "done"})
        if tool in ("halt_for_confirmation", "finish"):
            break
        if out == "budget":
            break
    else:
        s.warnings.append("step limit reached; blueprint may be incomplete")
    from .blueprint import build  # local import avoids a cycle
    bp = build(s)
    bp["provenance"] = {"source": "Qloo Insights API", "live_calls": svc.live_calls, "cache_hits": svc.cache_hits,
                        "note": "cache hits are real earlier Qloo responses held privately on the server"}
    return bp


# ---- tools --------------------------------------------------------------------------------------------------
def t_resolve(s: State, svc: QlooService, q: str) -> str:
    r = svc.resolve(q, s.brief.confirmed.get(q))
    s.resolutions[q] = r
    if r.status == "resolved" and r.anchor:
        s.anchors.append(r.anchor)
        return f"resolved '{q}' -> '{r.anchor.name}' ({r.anchor.match})"
    return f"'{q}' {r.status}: {r.note}"


def t_halt(s: State, svc: QlooService, _: None) -> str:
    return "stopped: " + "; ".join(f"'{q}' {r.status}" for q, r in s.resolutions.items() if r.status != "resolved")


def t_query(s: State, svc: QlooService, _: str) -> str:
    """Query every not-yet-queried domain in parallel (bounded by the service's worker pool)."""
    todo = [d for d in DOMAINS if d not in s.results]
    try:
        got = svc.query_domains(todo, s.anchors, s.brief.city)
    except StopRun as e:
        s.warnings.append(str(e))
        return "budget"
    parts = []
    for d, r in got.items():
        s.results[d] = r
        s.pool[d] = {c.id: c for c in r.candidates}
        parts.append(f"{d}: {len(r.candidates)} candidates, effective anchors {len(r.effective)}/{len(r.requested)}, rejected {len(r.rejected)}, ignored {len(r.ignored)}")
    return "; ".join(parts)


def t_validate(s: State, svc: QlooService, d: str) -> str:
    acc, rej, unk = [], [], {}
    for c in s.pool[d].values():
        bad, notes = check(c, s.brief.constraints)
        if bad:
            rej.append((c, bad))
        else:
            acc.append(c)
            if notes:
                unk[c.id] = notes
    prev = s.verdict.get(d, {})
    failed = s.results[d].error is not None  # an upstream failure will not improve by re-asking
    s.verdict[d] = {"accepted": acc, "rejected": rej, "unverified": unk, "exhausted": prev.get("exhausted", False) or failed}
    return f"{d}: {len(acc)} accepted, {len(rej)} rejected, {len(unk)} with unverifiable constraints"


def plan_revision(d: str, rejected, cons: Constraints, n: int) -> tuple[dict[str, Any], str]:
    """Choose a revision from WHY candidates were rejected."""
    codes = Counter(code for _, bad in rejected for code, _ in bad)
    top = codes.most_common(1)[0][0] if codes else None
    if n == 0 and d == "place" and top == "price" and cons.max_place_price_level:
        return {"filter.price_level.max": cons.max_place_price_level}, f"{codes['price']} places over price cap -> add server-side price filter"
    if n == 0 and d == "book" and top == "year" and cons.min_book_year:
        return {"filter.publication_year.min": cons.min_book_year}, f"{codes['year']} books too old -> add server-side year filter"
    return {"page": n + 2}, f"too few acceptable candidates (top rejection: {top or 'none'}) -> fetch next page"


def t_revise(s: State, svc: QlooService, d: str) -> str:
    extra, why = plan_revision(d, s.verdict[d]["rejected"], s.brief.constraints, s.revisions[d])
    s.revisions[d] += 1
    try:
        r = svc.query_domain(d, s.anchors, s.brief.city, extra)
    except StopRun as e:
        s.warnings.append(str(e))
        return "budget"
    before = len(s.pool[d])
    for c in r.candidates:
        s.pool[d].setdefault(c.id, c)
    s.warnings += [w for w in r.warnings if w not in s.warnings and "single anchor" not in w]
    new = len(s.pool[d]) - before
    s.verdict[d]["exhausted"] = new == 0
    t_validate(s, svc, d)
    return f"{d}: {why}; {new} new candidates; now {len(s.verdict[d]['accepted'])} accepted"


def t_audit(s: State, svc: QlooService, _: None) -> str:
    """Leave-one-anchor-out: how much does each anchor change each domain's candidate set (1 - Jaccard)."""
    jobs = [(d, a) for d in DOMAINS for a in s.anchors]

    def one(job):
        d, a = job
        rest = [x for x in s.anchors if x.id != a.id]
        return job, {c.id for c in svc.query_domain(d, rest, s.brief.city).candidates}

    try:
        with ThreadPoolExecutor(3) as ex:
            subs = dict(ex.map(one, jobs))
    except StopRun:
        s.warnings.append("influence audit skipped: call budget exhausted")
        s.influence = {"_skipped": {}}
        return "budget-truncated"
    for (d, a), sub in subs.items():
        full = {c.id for c in s.results[d].candidates}
        union = full | sub
        s.influence.setdefault(d, {})[a.name] = round(1 - len(full & sub) / len(union), 3) if union else 0.0
    return f"audited {len(s.influence)} domains"


_TOOLS = {"resolve_anchor": t_resolve, "halt_for_confirmation": t_halt, "query_domain": t_query, "validate_constraints": t_validate,
          "revise_query": t_revise, "audit_influence": t_audit, "finish": lambda s, svc, a: "ready to assemble"}
