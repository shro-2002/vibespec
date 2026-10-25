"""Regression tests for Stage B (contextual suitability). Synthetic entities reproduce the metadata shapes behind the
real Phase 3 audit failures (energetic act for a calm lobby, landmark as a local find, no-hours venue, hotel as a
destination, exclusion matched on a partnership mention). No Qloo response data is stored here."""
from test_vibespec import Fake, brief, ent, svc

from vibespec.agent import Constraints, run
from vibespec.blueprint import rank, to_markdown
from vibespec.qloo import Candidate
from vibespec.suitability import assess, exclusion, profile

CALM_ECO_LOCAL = profile("Calm minimalist sound, nature books, natural low-waste amenities, local places to explore on foot", "eco boutique hotel")


def cand(domain, name="Synthetic", tags=(), geo=None, **props):
    return Candidate(f"{domain}-{name}", name, domain, 0.9, {}, tuple(tags), props, geo)


def test_energetic_artist_is_off_brief_for_calm_lobby():
    s = assess(cand("artist", adjectives_for_music=["Dynamic", "Emotive"], primary_genres=["Alternative Rock", "J-Rock"],
                    performance_style="energetic and expressive"), CALM_ECO_LOCAL)
    assert s.verdict == "conflict" and "energy" in s.against[0]


def test_calm_artist_aligned_but_never_claims_track_fit_or_licensing():
    s = assess(cand("artist", adjectives_for_music=["Warm", "Melodic"], primary_genres=["Indie Folk"]), CALM_ECO_LOCAL)
    assert s.verdict == "aligned"
    assert any("licensing not checked" in u for u in s.unknowns) and any("Track-level" in u for u in s.unknowns)
    assert not any(w in " ".join(s.fit).lower() for w in ("licensed", "cleared", "track"))


def test_landmark_is_not_a_local_find():
    s = assess(cand("place", primary_genre="urn:tag:genre:place:historical_landmark", hours={"days_listed": 7, "days_open": 0}), CALM_ECO_LOCAL)
    assert s.verdict == "conflict" and "landmark" in s.against[0]


def test_venue_without_hours_is_a_labelled_discovery_lead_ranked_last():
    no_hours = cand("place", "NoHours", primary_genre="urn:tag:genre:place:restaurant:organic", is_closed=False)
    open_one = cand("place", "Listed", primary_genre="urn:tag:genre:place:cafe", hours={"days_listed": 7, "days_open": 6})
    fits = {c.id: assess(c, CALM_ECO_LOCAL) for c in (no_hours, open_one)}
    lead = fits[no_hours.id]
    assert lead.verdict == "unverified" and lead.discovery_lead and "may have closed" in lead.unknowns[0]
    assert not lead.verified  # nothing operational is claimed
    assert [c.name for c in rank([no_hours, open_one], fits)] == ["Listed", "NoHours"]


def test_closed_and_hotels_are_never_destinations():
    assert assess(cand("place", is_closed=True), CALM_ECO_LOCAL).verdict == "reject"
    assert assess(cand("place", primary_genre="urn:tag:genre:place:hotel", hours={"days_listed": 7, "days_open": 7}), CALM_ECO_LOCAL).verdict == "conflict"


def test_walkability_requires_precise_hotel_location():
    near = cand("place", primary_genre="urn:tag:genre:place:cafe", hours={"days_listed": 7, "days_open": 7}, geo={"lat": 40.7230, "lon": -73.9880})
    s = assess(near, CALM_ECO_LOCAL)
    assert "Walking distance unknown" in " ".join(s.unknowns) and "on foot" not in " ".join(s.fit) and s.verdict == "unverified"
    located = profile("explore on foot", "", (40.7223, -73.9874))
    assert assess(near, located).verdict == "aligned" and "min on foot" in " ".join(assess(near, located).fit)
    far = cand("place", primary_genre="urn:tag:genre:place:cafe", hours={"days_listed": 7, "days_open": 7}, geo={"lat": 40.80, "lon": -73.95})
    assert assess(far, located).verdict == "conflict"


def test_exclusion_only_on_name_or_owner_mentions_are_flagged():
    partner = cand("brand", "Synthetic Fashion", known_partnerships=["Starbucks", "Salomon"])
    hard, notes = exclusion(partner, ("Starbucks",))
    assert not hard and "association only" in notes[0]
    assert exclusion(cand("brand", "Starbucks Reserve"), ("Starbucks",))[0]
    assert exclusion(cand("brand", "Acme", owned_by="Starbucks Corporation"), ("Starbucks",))[0]
    assert not exclusion(cand("brand", "Beamsville Co"), ("Beams",))[0]  # whole words only


def test_brand_claims_stay_brand_level_and_sustainability_needs_evidence():
    media = assess(cand("brand", brand_type=["Media Brand"], category_description="A digital lifestyle media platform"), CALM_ECO_LOCAL)
    assert media.verdict == "conflict"
    soap = assess(cand("brand", brand_type=["Consumer Brand"], category_description="Natural bath and body care"), CALM_ECO_LOCAL)
    assert soap.verdict == "unverified" and "No sustainability initiatives listed" in " ".join(soap.unknowns)
    assert not any("sustainab" in f.lower() for f in soap.fit)
    green = assess(cand("brand", brand_type=["Consumer Brand"], category_description="Natural bath and body care", sustainability_initiatives=["Refill program"]), CALM_ECO_LOCAL)
    assert green.verdict == "aligned" and "not audited" in green.fit[-1] and "no specific product" in green.use.lower()
    market = assess(cand("brand", category_description="An online marketplace for handmade home decor"), CALM_ECO_LOCAL)
    assert market.verdict == "unverified"


def test_book_topic_and_tone():
    assert assess(cand("book", "Trees and Rivers", description="A history of forests and climate"), CALM_ECO_LOCAL).verdict == "aligned"
    assert assess(cand("book", "Sniper", description="A memoir of war, combat and killing"), CALM_ECO_LOCAL).verdict == "conflict"


LOUD = dict(adjectives_for_music=["Dynamic"], primary_genres=["Alternative Rock", "J-Rock"], performance_style="energetic")
CALM = dict(adjectives_for_music=["Warm", "Gentle"], primary_genres=["Indie Folk"])


def test_agent_revises_on_suitability_failures_and_records_reasons():
    def artists(live, p):
        page = int(p.get("page", 1))
        return [ent(f"A{page}{n}", f"artist-{page}-{n}", live, **(LOUD if page == 1 else CALM)) for n in range(1, 9)]

    bp = run(brief(goals="calm quiet lobby"), svc(Fake(per_domain={"artist": artists})))
    rev = [t for t in bp["trace"] if t["tool"] == "revise_query" and t["arg"] == "artist"]
    assert rev and "off-brief" in rev[0]["outcome"]
    dom = bp["domains"]["artist"]
    assert all(p["name"].startswith("artist-2") for p in dom["selected"]) and dom["off_brief"][0]["reasons"]


def test_agent_stops_when_no_defensible_candidate():
    loud = {"artist": lambda live, p: [ent(f"L{p.get('page', 1)}{n}", f"loud-{p.get('page', 1)}-{n}", live, **LOUD) for n in range(1, 6)]}
    bp = run(brief(goals="calm quiet lobby"), svc(Fake(per_domain=loud)))
    assert bp["domains"]["artist"]["selected"] == [] and any("only 0 of" in m for m in bp["missing_data"])
    assert len([t for t in bp["trace"] if t["tool"] == "revise_query" and t["arg"] == "artist"]) == 2  # bounded


def test_markdown_makes_no_operational_guarantees():
    md = to_markdown(run(brief(goals="calm, local places on foot", constraints=Constraints()), svc(Fake())))
    low = md.lower()
    for claim in ("is open", "is licensed", "licence cleared", "cleared for", "walkable", "guaranteed", "in stock"):
        assert claim not in low
    assert "check before using" in low and "next step" in low
