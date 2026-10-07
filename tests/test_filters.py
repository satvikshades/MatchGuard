from core.filters import hard_filter, shortlist, violations


def _compatible(client, profiles):
    return next(p for p in profiles.values() if not violations(client, p))


def test_smoking_deal_breaker_blocks_smoker(client_by_name, profiles):
    priya = client_by_name["Priya"]
    assert priya.deal_breakers.smoking
    ok = _compatible(priya, profiles)
    smoker = ok.model_copy(update={"smokes": True})
    vs = violations(priya, smoker)
    assert [v.rule for v in vs] == ["smoking"]
    assert vs[0].message == "Smokes - client deal-breaker"
    assert violations(priya, ok) == []


def test_smoker_allowed_when_not_a_deal_breaker(client_by_name, profiles):
    aditya = client_by_name["Aditya"]
    assert not aditya.deal_breakers.smoking
    smoker = _compatible(aditya, profiles).model_copy(update={"smokes": True})
    assert violations(aditya, smoker) == []


def test_age_range_is_inclusive(client_by_name, profiles):
    priya = client_by_name["Priya"]
    sp = priya.stated_preferences
    base = _compatible(priya, profiles)
    assert violations(priya, base.model_copy(update={"age": sp.age_min})) == []
    assert violations(priya, base.model_copy(update={"age": sp.age_max})) == []
    assert [v.rule for v in violations(priya, base.model_copy(update={"age": sp.age_min - 1}))] == ["age"]
    assert [v.rule for v in violations(priya, base.model_copy(update={"age": sp.age_max + 1}))] == ["age"]


def test_learned_drinking_rule_excludes_drinkers(client_by_name, profiles):
    priya = client_by_name["Priya"]
    drinker = _compatible(priya, profiles).model_copy(update={"drinks": "socially"})
    assert violations(priya, drinker) == []  # drinking is not a stated deal-breaker
    vs = violations(priya, drinker, learned=["drinking"])
    assert [v.rule for v in vs] == ["drinking"] and vs[0].learned


def test_hard_filter_and_shortlist(client_by_name, profiles):
    priya = client_by_name["Priya"]
    passing, excluded = hard_filter(priya, list(profiles.values()))
    assert len(passing) + len(excluded) == 200
    assert all(p.gender == "M" for p in passing)
    top = shortlist(priya, list(profiles.values()))
    assert 0 < len(top) <= 15
    assert all(0 <= score <= 100 and why for _, score, why in top)
    assert [s for _, s, _ in top] == sorted([s for _, s, _ in top], reverse=True)


def test_every_client_has_a_full_top_15(clients, profiles):
    for c in clients:
        assert len(shortlist(c, list(profiles.values()))) == 15, c.name
