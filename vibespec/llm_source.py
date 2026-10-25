"""System B candidate source: Qloo-free, LLM-generated candidates behind the SAME interface as QlooService.

Documented approach (kept deliberately comparable, not a strawman):
- Same agent loop, validation, revision, selection and blueprint code as System A; only candidate generation differs.
- Per domain and query it asks a local LLM (default qwen3:14b via Ollama, temperature 0) for `take` candidates ranked by
  fit to the brief and anchors, in the same count as System A (take=20), with the attributes the validators need.
- Revisions: Qloo server-side filters have no equivalent, so the same constraint is passed as a prompt instruction;
  paging = "give the next candidates, excluding these names".
- Attributes (year, price level, rating, price) are SELF-REPORTED by the generator and flagged as unverified.
- No per-anchor attribution exists, so none is shown and anchor-balance selection degrades to ranking order.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .qloo import Anchor, Candidate, DomainResult, Resolution, StopRun

OLLAMA = "http://localhost:11434/api/chat"
SHAPE = {
    "artist": '{"name": "", "why": ""}',
    "book": '{"name": "<title>", "author": "", "publication_year": 0, "why": ""}',
    "brand": '{"name": "", "price_min_usd": 0, "why": ""}',
    "place": '{"name": "", "neighborhood": "", "price_level": 1, "rating": 0.0, "why": ""}',
}
NOUN = {"artist": "music artists", "book": "books", "brand": "amenity brands for a hotel", "place": "real places (venues, cafes, shops, cultural spots)"}


def slug(domain: str, name: str) -> str:
    return f"llm:{domain}:{re.sub(r'[^a-z0-9]+', '-', name.casefold()).strip('-')}"


class LLMService:
    def __init__(self, model: str = "qwen3:14b", cache_dir: str | Path | None = ".cache_llm", deadline: float | None = None, host: str = OLLAMA):
        self.model, self._dir, self._deadline, self._host = model, Path(cache_dir) if cache_dir else None, deadline, host
        self.live_calls = self.cache_hits = 0
        self._seen: dict[str, list[str]] = {}
        self._concurrency_note = "sequential"

    def resolve(self, query: str, confirmed_id: str | None = None, types: str = "") -> Resolution:
        return Resolution(query, "resolved", Anchor(f"anchor:{query.casefold()}", query, "user-provided (no entity resolution without Qloo)"))

    def query_domains(self, domains, anchors, city=None, extra=None):
        return {d: self.query_domain(d, anchors, city, (extra or {}).get(d)) for d in domains}  # Ollama serialises anyway

    def _chat(self, prompt: str) -> dict:
        key = hashlib.sha256(prompt.encode()).hexdigest()
        f = self._dir / f"{key}.json" if self._dir else None
        if f and f.exists():
            self.cache_hits += 1
            return json.loads(f.read_text())
        import time
        if self._deadline is not None and time.time() >= self._deadline:
            raise StopRun("time limit reached")
        req = urllib.request.Request(self._host, json.dumps({"model": self.model, "stream": False, "think": False, "format": "json",
                                     "options": {"temperature": 0, "num_predict": 4500}, "messages": [{"role": "user", "content": prompt}]}).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            out = json.loads(json.loads(r.read())["message"]["content"])
        self.live_calls += 1
        if f:
            self._dir.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(out))
        return out

    def query_domain(self, domain: str, anchors: list[Anchor], city: str | None = None, extra: Mapping[str, Any] | None = None, take: int = 20) -> DomainResult:
        extra = extra or {}
        hints = []
        if "filter.price_level.max" in extra:
            hints.append(f"every place MUST have price_level <= {extra['filter.price_level.max']} (scale 1-4)")
        if "filter.publication_year.min" in extra:
            hints.append(f"every book MUST be published in {extra['filter.publication_year.min']} or later")
        seen = self._seen.setdefault(domain, [])
        names = ", ".join(a.name for a in anchors)
        prompt = (f"You curate cultural experiences for a boutique hotel. Cultural anchors (brands whose taste to reflect): {names}."
                  + (f" City: {city}." if city and domain == "place" else "")
                  + f" List exactly {take} {NOUN[domain]}, ranked best fit first. "
                  + (f"Constraints: {'; '.join(hints)}. " if hints else "")
                  + (f"Do NOT repeat any of: {'; '.join(seen[-60:])}. " if seen else "")
                  + f'Reply ONLY JSON {{"items":[{SHAPE[domain]}, ...]}}. Use real items only.')
        warnings = (f"{domain}: candidate attributes are self-reported by the generator and unverified",)
        try:
            items = self._chat(prompt).get("items") or []
        except StopRun:
            raise
        except Exception as e:  # noqa: BLE001
            return DomainResult(domain, tuple(a.id for a in anchors), tuple(a.id for a in anchors), {}, (), (), {}, (f"{domain}: generator failed ({type(e).__name__})",), 0, str(e)[:100])
        cands, ids = [], set()
        for it in items[:take]:
            if isinstance(it, str):  # generators sometimes return bare names; accept them
                it = {"name": it}
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            if not name or slug(domain, name) in ids:
                continue
            ids.add(slug(domain, name))
            seen.append(name)
            props: dict[str, Any] = {"short_description": str(it.get("why") or "")[:280], "description": str(it.get("why") or "")[:280]}
            if domain == "book":
                props.update(publication_year=_num(it.get("publication_year"), int))
            if domain == "brand":
                props.update(price_range_usd_min=_num(it.get("price_min_usd"), float))
            if domain == "place":
                props.update(price_level=_num(it.get("price_level"), int), business_rating=_num(it.get("rating"), float),
                             address=f"{it.get('neighborhood') or ''}, {city or ''}".strip(", "))
            cands.append(Candidate(slug(domain, name), name, domain, None, {}, (), {k: v for k, v in props.items() if v is not None}))
        return DomainResult(domain, tuple(a.id for a in anchors), tuple(a.id for a in anchors), {}, (), tuple(cands), {}, warnings, 0, None, dict(extra))


def _num(v: Any, t) -> Any:
    try:
        return t(v) if v not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return None
