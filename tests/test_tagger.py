import json

import pytest

from core.data import load_taxonomy
from core.tagger import keyword_tag, tag_feedback


def cats(text):
    return set(keyword_tag(text).categories())


@pytest.mark.parametrize("text,expected", [
    # synonyms
    ("He's a chain smoker", "smoking"), ("Vapes all day", "smoking"), ("Likes his whisky a bit too much", "drinking"),
    ("Too far, I'm not moving to Pune", "location_relocation"), ("Age gap is too much", "age"),
    ("Second marriage, not for me", "marital_status"), ("Mama's boy", "family_values"),
    ("Too career-focused, works 80 hour weeks", "career_income"), ("Eats meat, I'm pure veg", "diet"),
    # Hinglish
    ("sutta peeta hai, nahi chalega", "smoking"), ("daaru peeta hai", "drinking"), ("umar zyada hai", "age"),
    ("height mein chhota hai", "height"), ("padhai kam hai", "education"), ("bacche nahi chahiye usko", "children"),
    ("ghar wale bahut strict lage", "family_values"), ("bahut akdu hai", "personality"),
    ("vibe nahi aayi", "vague_no_spark"), ("pata nahi, kuch missing hai", "vague_no_spark"),
    ("dikhne mein theek nahi laga", "appearance"), ("kundli match nahi hui", "religion_community"),
    # typos
    ("He smokr", "smoking"), ("drinkes every weekend", "drinking"), ("non vegitarian, nahi chalega", "diet"),
    ("too arrogent", "personality"), ("not willing to relocte", "location_relocation"),
    ("she is divorsed", "marital_status"), ("no chemestry", "vague_no_spark"), ("religous differences", "religion_community"),
])
def test_detects(text, expected):
    assert expected in cats(text)


@pytest.mark.parametrize("text,absent", [
    ("Doesn't smoke which is good, but conversation was so dry", "smoking"),
    ("He doesnt drink, decent person, but no spark", "drinking"),
    ("non-smoker, nice family, just not my type", "smoking"),
    ("daaru nahi peeta, still no chemistry", "drinking"),
    ("Never drinks or smokes but too loud", "drinking"),
    ("Never drinks or smokes but too loud", "smoking"),
    ("I don't mind that he drinks socially, the problem is the distance", "drinking"),
    ("Drinking is fine with me, but he's too short", "drinking"),
    ("Quit smoking last year. Still not feeling it", "smoking"),
    ("Looks fine but conversation was boring", "appearance"),
    ("short tempered from what I heard", "height"),
    ("we spoke for an hour, no spark", "smoking"),
    ("Sutta peeta hai", "drinking"),
    ("saw a cigarette in his pics, that's a no", "appearance"),
])
def test_negation_and_acceptance_not_tagged(text, absent):
    assert absent not in cats(text)


def test_negation_keeps_the_real_reason():
    r = keyword_tag("I don't mind that he drinks socially, the problem is the distance")
    assert "location_relocation" in r.categories() and not r.is_vague


def test_not_okay_is_not_acceptance():
    assert "smoking" in cats("Sorry but he smokes regularly. Not okay with that at all.")
    assert "drinking" in cats("He drinks quite a lot, not comfortable with that")


def test_mixed_reasons_and_vague_flag():
    r = keyword_tag("Too far and honestly no spark")
    assert {"location_relocation", "vague_no_spark"} <= set(r.categories())
    assert not r.is_vague
    assert keyword_tag("no spark yaar").is_vague
    assert keyword_tag("hmm").is_vague


def test_evidence_is_exact_substring_and_sentiment():
    text = "He SMOKES!! I clearly mentioned no smokers"
    r = keyword_tag(text)
    assert all(t.evidence in text for t in r.tags)
    assert r.sentiment == "strong"
    assert keyword_tag("not my type").sentiment == "mild"


def test_llm_valid_json_is_used():
    taxonomy = load_taxonomy()
    payload = {"tags": [{"category": "drinking", "confidence": 0.9, "evidence": "drinks"}],
               "is_vague": False, "sentiment": "mild"}
    r, warn = tag_feedback("he drinks", taxonomy, lambda s, u, schema: json.dumps(payload))
    assert r.source == "llm" and r.categories() == ["drinking"] and warn is None


def test_llm_bad_json_retries_once_then_falls_back():
    calls = []

    def bad(s, u, schema):
        calls.append(1)
        return "sure! here are the tags: drinking"

    r, warn = tag_feedback("he drinks every weekend", load_taxonomy(), bad)
    assert len(calls) == 2
    assert r.source == "keyword" and "drinking" in r.categories() and warn


def test_llm_network_error_falls_back_without_retry():
    calls = []

    def boom(s, u, schema):
        calls.append(1)
        raise ConnectionError("offline")

    r, warn = tag_feedback("he smokes", load_taxonomy(), boom)
    assert len(calls) == 1 and r.source == "keyword" and "smoking" in r.categories()
