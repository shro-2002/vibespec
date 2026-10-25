"""Reliable Qloo service: resolve anchors, query domains, detect invalid/ignored anchors, typed results.

Never substitutes an anchor silently: rejected (HTTP 400) and ignored (200 but zero explainability) anchors are
reported on the DomainResult. Responses are cached privately on disk (never commit `.cache/`).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Mapping

from smoke_test import TARGETS, call, entities, validate

NEAR_RATIO = 0.9
DESC_MAX = 280
DOMAIN_PROPS = {
    "book": ("publication_year", "page_count", "description"),
    "artist": ("description", "obscurity_scale", "start_year"),
    "brand": ("short_description", "price_range_usd_min", "price_range_usd_max", "industry"),
    "place": ("address", "price_level", "business_rating", "is_closed", "short_description", "hotel_class"),
}

Transport = Callable[[str, Mapping[str, Any]], dict]


class StopRun(RuntimeError):
    """Cooperative stop: the run must end now (budget or deadline), keeping what it already has."""


class BudgetExceeded(StopRun):
    pass


class DeadlineExceeded(StopRun):
    pass


@dataclass(frozen=True)
class Anchor:
    id: str
    name: str
    match: str  # exact | near | confirmed


@dataclass(frozen=True)
class Resolution:
    query: str
    status: str  # resolved | ambiguous | not_found | error
    anchor: Anchor | None = None
    candidates: tuple[tuple[str, str, str], ...] = ()  # (id, name, disambiguation) for the user to confirm
    note: str = ""


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    domain: str
    affinity: float | None
    attribution: Mapping[str, float]  # anchor_id -> explainability score for this result
    tags: tuple[str, ...]
    props: Mapping[str, Any]
    geo: Mapping[str, Any] | None = None  # place only: lat, lon, geohash (identity of the branch)


@dataclass(frozen=True)
class DomainResult:
    domain: str
    requested: tuple[str, ...]
    effective: tuple[str, ...]
    rejected: Mapping[str, str]  # anchor_id -> reason (HTTP 400 invalid for this domain)
    ignored: tuple[str, ...]  # accepted by API but contributed nothing (0 explainability presence)
    candidates: tuple[Candidate, ...]
    aggregate: Mapping[str, Mapping[str, float]]  # window -> anchor_id -> avg_score
    warnings: tuple[str, ...]
    latency_ms: int = 0
    error: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)


def friendly(status: Any) -> str:
    """User-safe description of an upstream failure; never includes the upstream body."""
    if status in (401, 403):
        return "Qloo rejected this server's credentials (HTTP %s)" % status
    if status == 429:
        return "Qloo rate limit reached (HTTP 429)"
    if isinstance(status, int) and status >= 500:
        return "Qloo is temporarily unavailable (HTTP %s)" % status
    if status == "malformed_response":
        return "Qloo returned an unexpected response"
    return "Qloo request failed (%s)" % status


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()


class QlooService:
    def __init__(self, api_key: str | None = None, cache_dir: str | Path | None = ".cache", workers: int = 3,
                 budget: int = 60, transport: Transport | None = None, deadline: float | None = None):
        self._transport = transport or (lambda path, params: call(path, dict(params), api_key or ""))
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._workers, self._budget, self._live, self._deadline, self.cache_hits = workers, budget, 0, deadline, 0
        self._lock = threading.Lock()
        self._mem: dict[str, dict] = {}

    @property
    def live_calls(self) -> int:
        return self._live

    def _get(self, path: str, params: Mapping[str, Any]) -> dict:
        validate(path, dict(params))  # unsupported params are an error, never silently sent
        key = hashlib.sha256(json.dumps([path, dict(params)], sort_keys=True, default=str).encode()).hexdigest()
        if key in self._mem:
            self.cache_hits += 1
            return self._mem[key]
        f = self._cache_dir / f"{key}.json" if self._cache_dir else None
        if f and f.exists():
            self._mem[key] = json.loads(f.read_text())
            self.cache_hits += 1
            return self._mem[key]
        with self._lock:
            if self._deadline is not None and time.time() >= self._deadline:
                raise DeadlineExceeded("time limit reached")
            if self._live >= self._budget:
                raise BudgetExceeded(f"live call budget of {self._budget} exhausted")
            self._live += 1
        res = self._transport(path, params)
        if res["status"] == 200 and res["body"] is None:  # 200 but unparseable
            res = {**res, "status": "malformed_response", "error": "malformed JSON"}
        if res["status"] in (200, 400) and res["body"] is not None:  # 400s are deterministic, cache to save quota
            self._mem[key] = res
            if f and res["status"] == 200:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(res))
        return res

    # ---- resolution -------------------------------------------------------------------------------------
    def resolve(self, query: str, confirmed_id: str | None = None, types: str = TARGETS["brand"]) -> Resolution:
        res = self._get("/search", {"query": query, "types": types, "take": 5})
        if res["status"] != 200:
            return Resolution(query, "error", note=friendly(res["status"]))
        hits = [e for e in entities(res["body"]) if e.get("entity_id") and e.get("name")]
        if confirmed_id:
            hit = next((e for e in hits if e["entity_id"] == confirmed_id), None)
            if hit:
                return Resolution(query, "resolved", Anchor(hit["entity_id"], hit["name"], "confirmed"))
        q = norm(query)
        exact = [e for e in hits if norm(e["name"]) == q]
        near = [e for e in hits if SequenceMatcher(None, norm(e["name"]), q).ratio() >= NEAR_RATIO]
        pick, kind = (exact, "exact") if exact else (near, "near")
        cands = tuple((e["entity_id"], e["name"], str(e.get("disambiguation") or "")) for e in hits)
        if len(pick) == 1:
            return Resolution(query, "resolved", Anchor(pick[0]["entity_id"], pick[0]["name"], kind))
        if len(pick) > 1:
            return Resolution(query, "ambiguous", candidates=cands, note="multiple entities match; user must confirm")
        if hits:
            return Resolution(query, "ambiguous", candidates=cands, note="no exact match; closest fuzzy hits need user confirmation")
        return Resolution(query, "not_found", note="no entity returned")

    # ---- domain queries ---------------------------------------------------------------------------------
    def query_domain(self, domain: str, anchors: list[Anchor], city: str | None = None,
                     extra: Mapping[str, Any] | None = None, take: int = 20) -> DomainResult:
        ids = [a.id for a in anchors]
        base: dict[str, Any] = {"filter.type": TARGETS[domain], "feature.explainability": "true", "take": take, **(extra or {})}
        if domain == "place" and city:
            base["filter.location.query"] = city
        warnings: list[str] = []
        rejected: dict[str, str] = {}
        res = self._get("/v2/insights", {**base, "signal.interests.entities": ",".join(ids)})
        effective = list(ids)
        # Observed live: a MIXED set with some invalid anchors returns 200 and silently ignores them (detected below via
        # explainability); HTTP 400 "were invalid" means NO anchor is usable in this domain.
        if res["status"] == 400 and "invalid" in (res["error"] or "").lower():
            rejected = {i: "rejected by Qloo for this domain (HTTP 400 invalid anchor)" for i in ids}
            return DomainResult(domain, tuple(ids), (), rejected, (), (), {}, (f"{domain}: no anchor is valid for this domain; no recommendations produced",),
                                res["latency_ms"], res["error"], base)
        if res["status"] != 200:
            return DomainResult(domain, tuple(ids), tuple(effective), rejected, (), (), {}, (f"{domain}: {friendly(res['status'])}",), res["latency_ms"], friendly(res["status"]), base)
        ents = entities(res["body"])
        good = [e for e in ents if e.get("entity_id") and e.get("name")]
        if len(good) < len(ents):
            warnings.append(f"{domain}: dropped {len(ents) - len(good)} malformed entities (missing id or name)")
        if not good:
            warnings.append(f"{domain}: empty result")
        cands = tuple(self._candidate(domain, e) for e in dict((e["entity_id"], e) for e in good).values())
        ignored: tuple[str, ...] = ()
        if len(effective) > 1:
            present = {i for c in cands for i in c.attribution}
            ignored = tuple(i for i in effective if i not in present and cands)
            for i in ignored:
                warnings.append(f"{domain}: anchor {i} was accepted by the API but contributed nothing (0 explainability); excluded from attribution")
        elif cands:
            warnings.append(f"{domain}: single anchor, explainability is trivial (score 1.0)")
        agg = (((res["body"] or {}).get("query") or {}).get("explainability") or {}).get("signal.interests.entities") or {}
        aggregate = {w: {i.get("entity_id"): i.get("avg_score") for i in items or []} for w, items in agg.items()} if isinstance(agg, dict) else {}
        return DomainResult(domain, tuple(ids), tuple(effective), rejected, ignored, cands, aggregate, tuple(warnings), res["latency_ms"], None, base)

    def query_domains(self, domains: list[str], anchors: list[Anchor], city: str | None = None,
                      extra: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, DomainResult]:
        extra = extra or {}
        with ThreadPoolExecutor(self._workers) as ex:
            futs = {d: ex.submit(self.query_domain, d, anchors, city, extra.get(d)) for d in domains}
            return {d: f.result() for d, f in futs.items()}

    @staticmethod
    def _candidate(domain: str, e: dict) -> Candidate:
        q = e.get("query") or {}
        attr = {i["entity_id"]: float(i.get("score", 0)) for i in (q.get("explainability") or {}).get("signal.interests.entities", []) or [] if i.get("entity_id")}
        p = e.get("properties") or {}
        props = {k: (str(p[k])[:DESC_MAX] if isinstance(p[k], str) else p[k]) for k in DOMAIN_PROPS[domain] if p.get(k) is not None}
        loc = e.get("location") if domain == "place" else None
        geo = {k: loc[k] for k in ("lat", "lon", "geohash") if k in loc} if isinstance(loc, dict) else None
        tags = tuple(t["name"] for t in (e.get("tags") or []) if isinstance(t, dict) and t.get("name"))
        return Candidate(e["entity_id"], e["name"], domain, q.get("affinity"), attr, tags, props, geo)
