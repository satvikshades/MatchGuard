from core.learning import learned_suggestions, reversal_flags, vague_flags


def test_priya_triggers_learned_drinking_deal_breaker(clients, profiles, shares, tagged):
    sugg = learned_suggestions(clients, profiles, shares, tagged)
    priya = [s for s in sugg if s.client_name == "Priya"]
    assert len(priya) == 1
    assert priya[0].category == "drinking" and priya[0].count >= 2


def test_confirmed_or_dismissed_suggestion_disappears(clients, profiles, shares, tagged):
    pid = next(c.id for c in clients if c.name == "Priya")
    for kwargs in ({"confirmed": {pid: ["drinking"]}}, {"dismissed": {pid: ["drinking"]}}):
        sugg = learned_suggestions(clients, profiles, shares, tagged, **kwargs)
        assert not [s for s in sugg if s.client_id == pid]


def test_only_seeded_suggestion_on_mock_data(clients, profiles, shares, tagged):
    sugg = learned_suggestions(clients, profiles, shares, tagged)
    assert [(s.client_name, s.category) for s in sugg] == [("Priya", "drinking")]


def test_rohan_triggers_reversal_flag(clients, profiles, shares, tagged):
    flags = reversal_flags(clients, profiles, shares, tagged)
    rohan = [f for f in flags if f.client_name == "Rohan"]
    assert len(rohan) == 1
    f = rohan[0]
    assert f.category == "career_income"
    rp, ap = profiles[f.rejected_profile_id], profiles[f.accepted_profile_id]
    assert (rp.profession, rp.seniority) == (ap.profession, ap.seniority)
    assert f.rejected_date < f.accepted_date
    # A reversal must never become an auto-add suggestion
    assert not [s for s in learned_suggestions(clients, profiles, shares, tagged) if s.client_name == "Rohan"]


def test_ananya_flagged_as_mostly_vague(clients, shares, tagged):
    flags = vague_flags(clients, shares, tagged)
    assert [f.client_name for f in flags] == ["Ananya"]
    assert flags[0].ratio > 0.6
