import pytest

from core.metrics import avoidable_rejections, funnel, simulate


@pytest.fixture(scope="module")
def cmap(clients):
    return {c.id: c for c in clients}


def test_avoidable_rejection_rate_is_about_35_percent(shares, cmap, profiles):
    a = avoidable_rejections(shares, cmap, profiles)
    assert a["rate"] == pytest.approx(0.35, abs=0.03)


def test_funnel_matches_brief(shares):
    f = funnel(shares)
    assert f["shares"] == 120
    assert f["acceptance_rate"] == pytest.approx(0.31, abs=0.02)
    mm = f["by_matchmaker"].acceptance_rate
    assert mm["A"] == pytest.approx(0.44, abs=0.02)
    assert mm["B"] == pytest.approx(0.21, abs=0.02)


def test_simulation_reports_false_positives_honestly(shares, cmap, profiles):
    s = simulate(shares, cmap, profiles)
    a = avoidable_rejections(shares, cmap, profiles)
    assert s["blocked_rejected"] == a["avoidable"]
    assert s["blocked_accepted"] > 0  # some liked profiles broke a stated rule - must be visible
    assert s["projected_rate"] > s["baseline_rate"]
    assert s["remaining_shares"] == 120 - s["blocked"]


def test_learned_rules_extend_simulation(shares, cmap, profiles, client_by_name):
    pid = client_by_name["Priya"].id
    base = simulate(shares, cmap, profiles)
    learned = simulate(shares, cmap, profiles, {pid: ["drinking"]})
    # Her 2 drinking rejections, plus any other drinker she happened to reject for a different reason
    assert learned["blocked_rejected"] >= base["blocked_rejected"] + 2
    assert learned["blocked_accepted"] == base["blocked_accepted"]
