"""Stage B: contextual suitability. Stage A (Qloo) says what the anchor audience likes; this module asks whether a
candidate fits THIS hotel brief, using only metadata Qloo actually returned. Affinity is never used here.

Verdicts: aligned (positive evidence for the brief), unverified (no evidence either way, or operational facts unknown),
conflict (evidence against an essential goal: not selected), reject (hard failure such as closed or excluded by name).
When metadata is missing the verdict is unverified, never aligned.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from .qloo import Candidate

GOAL_WORDS = {
    "calm": ("calm", "quiet", "minimal", "mellow", "relax", "serene", "mindful", "tranquil", "peaceful", "slow", "restful"),
    "eco": ("eco", "sustainab", "natural", "low-waste", "low waste", "organic", "green", "environment", "planet", "nature"),
    "walk": ("on foot", "walk", "stroll", "walkable"),
    "local": ("local", "intimate", "independent", "neighborhood", "neighbourhood", "hidden", "small"),
}
CALM_MUSIC = ("calm", "mellow", "ambient", "acoustic", "soft", "gentle", "soothing", "tranquil", "chill", "atmospheric", "ethereal",
              "warm", "intimate", "folk", "piano", "lo-fi", "dreamy", "relaxing", "meditative", "minimal", "downtempo", "classical")
ENERGETIC_MUSIC = ("energetic", "dynamic", "aggressive", "loud", "intense", "heavy", "punk", "metal", "hard rock", "j-rock",
                   "alternative rock", "hip hop", "rap", "edm", "dance", "party", "high-energy", "anthemic", "youthful")
ECO_TOPIC = ("nature", "forest", "tree", "climate", "environment", "ocean", "wild", "sustainab", "ecolog", "mountain", "river",
             "outdoor", "land", "earth", "garden", "plant", "landscape", "conservation")
DARK_TOPIC = ("war", "combat", "killing", "murder", "violence", "sniper", "terror", "death", "danger", "warrior", "navy seal")
AMENITY_CATEGORY = ("bath", "body", "skin", "beauty", "personal care", "fragrance", "candle", "home", "linen", "textile", "towel",
                    "tea", "coffee", "food", "beverage", "snack", "stationery", "homeware", "household", "soap", "ceramic", "kitchen")
NOT_A_SUPPLIER = ("media brand", "software", "publisher", "magazine", "news")  # cannot supply amenities at all
MARKETPLACE = ("marketplace", "platform")  # may stock amenities, but does not make them
LIVELY_PLACE = ("party", "high-energy", "nightclub", "rowdy", "loud")
WALK_KMH = 4.5


@dataclass(frozen=True)
class Profile:
    calm: bool
    eco: bool
    walk: bool
    local: bool
    hotel_latlon: tuple[float, float] | None = None
    max_walk_km: float = 1.5


@dataclass
class Suitability:
    verdict: str  # aligned | unverified | conflict | reject
    use: str
    fit: list[str] = field(default_factory=list)  # evidence FOR the brief
    against: list[str] = field(default_factory=list)  # evidence AGAINST (reason for conflict/reject)
    verified: list[str] = field(default_factory=list)  # operational facts present in Qloo metadata
    unknowns: list[str] = field(default_factory=list)  # missing evidence about FIT with the brief
    gaps: list[str] = field(default_factory=list)  # operational facts nobody has verified (hours, licensing, products, prices)
    next_action: str = ""
    label: str = ""  # short user-facing status
    discovery_lead: bool = False  # place with no evidence that it currently operates: shown last, clearly labelled


def profile(goals: str, concept: str, hotel_latlon: tuple[float, float] | None = None, max_walk_km: float = 1.5) -> Profile:
    text = f"{goals} {concept}".casefold()
    has = {k: any(w in text for w in ws) for k, ws in GOAL_WORDS.items()}
    return Profile(has["calm"], has["eco"], has["walk"], has["local"], hotel_latlon, max_walk_km)


def words_in(text: str, vocab: tuple[str, ...]) -> list[str]:
    """Whole-word (or whole-phrase) matches only, so 'rap' does not match 'grape'."""
    low = text.casefold()
    return sorted({w for w in vocab if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low)})


def _text(c: Candidate, *keys: str) -> str:
    parts = []
    for k in keys:
        v = c.props.get(k)
        parts.append(" ".join(map(str, v)) if isinstance(v, list) else str(v or ""))
    return " ".join(parts)


def music(c: Candidate, p: Profile) -> Suitability:
    s = Suitability("unverified", "Playlist candidate for lobby and rooms (artist level, not specific tracks)")
    descr = _text(c, "adjectives_for_music", "primary_genres", "performance_style") + " " + " ".join(c.tags)
    calm, loud = words_in(descr, CALM_MUSIC), words_in(descr, ENERGETIC_MUSIC)
    s.unknowns.append("Song-level tempo and volume are not in Qloo data: audition specific tracks before use")
    s.gaps.append("Public-performance licensing not checked: play only through a licensed background-music service")
    s.next_action = "Audition 3 to 5 tracks at lobby volume; source them through a licensed background-music provider."
    if p.calm and len(loud) >= 2 and len(loud) > len(calm):
        s.verdict, s.label = "conflict", "Too energetic for a calm brief"
        s.against.append(f"Artist descriptors suggest high energy: {', '.join(loud)}")
    elif p.calm and calm and len(calm) >= len(loud):
        s.verdict, s.label = "aligned", "Calm-leaning (artist level)"
        s.fit.append(f"Artist descriptors include {', '.join(calm)}" + (f"; also {', '.join(loud)}" if loud else "") + " (describes the artist, not specific songs)")
    elif not p.calm:
        s.label = "No atmosphere requirement stated"
    else:
        s.label = "Atmosphere unverified"
        s.unknowns.insert(0, "No calm-atmosphere evidence in artist metadata" + (f" (mixed: {', '.join(calm + loud)})" if calm or loud else ""))
    return s


def book(c: Candidate, p: Profile) -> Suitability:
    s = Suitability("unverified", "Guest library shelf")
    text = f"{c.name} {_text(c, 'description')}"
    eco, dark = words_in(text, ECO_TOPIC), words_in(text, DARK_TOPIC)
    s.gaps.append("Edition, format, availability and price not checked")
    s.next_action = "Order a reading copy and check the edition before shelving."
    if p.calm and len(dark) >= 2 and len(dark) > len(eco):
        s.verdict, s.label = "conflict", "Themes clash with a calm, mindful stay"
        s.against.append(f"Description centres on {', '.join(dark)}")
        return s
    if dark:
        s.unknowns.append(f"Mentions {', '.join(dark)}: check tone fits the brand")
    if p.eco and eco:
        s.verdict, s.label = "aligned", "On-theme topic"
        s.fit.append(f"Topic evidence for nature/sustainability: {', '.join(eco)}")
    elif p.eco:
        s.label = "Topic unverified"
        s.unknowns.insert(0, "No nature or sustainability topic evidence in Qloo metadata")
    else:
        s.label = "No topic requirement stated"
    if c.props.get("description"):
        s.verified.append("Qloo description available")
    return s


def brand(c: Candidate, p: Profile) -> Suitability:
    s = Suitability("unverified", "Brand-level partnership idea (no specific product selected)")
    kind = _text(c, "brand_type", "category_description", "industry")  # the brand's own category, not loose tags
    supplier_conflict, amenity, market = words_in(kind, NOT_A_SUPPLIER), words_in(kind, AMENITY_CATEGORY), words_in(kind, MARKETPLACE)
    s.gaps.append("No specific product, unit price, minimum order, availability or supplier terms verified")
    s.next_action = "Contact the brand's wholesale or hospitality team for an amenity product list and terms."
    if supplier_conflict and not amenity:
        s.verdict, s.label = "conflict", "Not a product supplier"
        s.against.append(f"Qloo describes it as {', '.join(supplier_conflict)}, not a maker of guest amenities")
        return s
    if market:
        s.unknowns.insert(0, "Qloo describes it as a marketplace or platform, not a manufacturer: products would come from its sellers")
    if amenity:
        s.fit.append(f"Category suggests in-room use: {', '.join(amenity)}")
    else:
        s.use = "Retail or co-branding partnership idea (category is not an in-room amenity)"
        s.unknowns.insert(0, "Category does not indicate in-room amenities")
    initiatives = c.props.get("sustainability_initiatives") or []
    if p.eco and initiatives:
        s.fit.append(f"Qloo metadata lists sustainability initiatives: {', '.join(initiatives[:4])} (brand-reported, not audited)")
    elif p.eco:
        s.unknowns.append("No sustainability initiatives listed in Qloo metadata")
    s.verdict = "aligned" if amenity and not market and (not p.eco or initiatives) else "unverified"
    s.label = "Amenity-category brand (no product verified)" if s.verdict == "aligned" else "Brand partnership idea (no product verified)"
    return s


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def place(c: Candidate, p: Profile) -> Suitability:
    s = Suitability("unverified", "Concierge recommendation for guests")
    genre, tags = str(c.props.get("primary_genre") or ""), " ".join(c.tags)
    if c.props.get("is_closed") is True:
        s.verdict, s.label = "reject", "Marked closed"
        s.against.append("Qloo marks it closed")
        return s
    if ":hotel" in genre or re.search(r"(?<![a-z])hotel(?![a-z])", tags.casefold()):
        s.verdict, s.label = "conflict", "Another hotel"
        s.against.append("It is a hotel, not a destination to send your own guests to")
        return s
    landmark = any(k in genre for k in ("landmark", "tourist_attraction", "observation", "skyscraper"))
    if landmark and p.local:
        s.verdict, s.label = "conflict", "Major landmark, not a local find"
        s.against.append("Qloo classifies it as a landmark or tourist attraction; the brief asks for local or intimate places")
        return s
    lively = words_in(_text(c, "ambience_description"), LIVELY_PLACE)
    if p.calm and lively:
        s.verdict, s.label = "conflict", "Atmosphere clashes with a calm brief"
        s.against.append(f"Ambience described as {', '.join(lively)}")
        return s
    hours = c.props.get("hours")
    if not hours:
        s.gaps.append("No opening hours in Qloo data: it may have closed. Do not describe it to guests as operating until confirmed")
        s.label, s.discovery_lead = "Discovery lead: opening hours unknown", True
    elif hours.get("days_open", 0) == 0:
        s.gaps.append("Qloo hours list it closed every day: confirm it operates before recommending")
        s.label, s.discovery_lead = "Discovery lead: opening hours unknown", True
    else:
        s.verified.append(f"Qloo lists opening hours on {hours['days_open']} days (may be out of date)")
        s.gaps.append("Current opening hours not confirmed")
    if c.props.get("business_rating"):
        s.verified.append(f"Qloo business rating {float(c.props['business_rating']):.1f}")
    ok_status = bool(hours) and hours.get("days_open", 0) > 0
    if p.hotel_latlon and c.geo:
        km = _km(p.hotel_latlon, (c.geo["lat"], c.geo["lon"]))
        if p.walk and km > p.max_walk_km:
            s.verdict, s.label = "conflict", "Too far to walk"
            s.against.append(f"{km:.1f} km straight-line from the hotel (limit {p.max_walk_km:g} km)")
            return s
        s.fit.append(f"{km:.1f} km straight-line from the hotel; at least {round(km / WALK_KMH * 60)} min on foot (straight-line estimate, real routes are longer)")
    else:
        s.unknowns.append("Distance from the hotel not checked: no precise hotel location was given")
    if "tourist attraction" in tags.casefold():
        s.unknowns.append("Qloo also tags it as a tourist attraction: check it suits a local, intimate recommendation")
    if c.props.get("short_description"):
        d = str(c.props["short_description"])
        s.fit.append("Qloo description: " + (d[:140].rsplit(" ", 1)[0] + "…" if len(d) > 140 else d))
    s.verdict = "aligned" if ok_status and p.hotel_latlon else "unverified"
    if s.verdict == "aligned":
        s.label = "Fits the brief within reach (hours listed, not confirmed)"
    elif not s.label:
        s.label = "City-level lead: distance from the hotel not checked"
    s.next_action = "Call or visit to confirm current opening hours and that the tone suits the hotel, then add it to the concierge list."
    return s


CHECKS = {"artist": music, "book": book, "brand": brand, "place": place}


def assess(c: Candidate, p: Profile) -> Suitability:
    return CHECKS[c.domain](c, p)


def exclusion(c: Candidate, terms: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Hard-exclude only when a term names the entity itself or its owner; other mentions are reported, not excluded."""
    hard, notes = [], []
    owner = _text(c, "owned_by", "parent_organization")
    for t in terms:
        if words_in(f"{c.name} {owner}", (t.casefold(),)):
            hard.append(f"named or owned by excluded term '{t}'")
            continue
        where = [k for k in ("known_partnerships", "description", "short_description") if words_in(_text(c, k), (t.casefold(),))]
        if where or words_in(" ".join(c.tags), (t.casefold(),)):
            notes.append(f"mentions '{t}' in {', '.join(where) or 'tags'} (association only, not excluded): review")
    return hard, notes


def as_dict(s: Suitability) -> dict[str, Any]:
    return {k: getattr(s, k) for k in ("verdict", "label", "use", "fit", "against", "verified", "unknowns", "gaps", "next_action")}
