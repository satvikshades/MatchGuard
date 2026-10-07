"""Hard filter + soft-fit scoring. Pure functions, no Streamlit."""
from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Client, Profile, Violation, education_rank

# Learned deal-breakers the filter knows how to enforce. Anything else that a
# client confirms is stored as a note but cannot be applied mechanically.
ENFORCEABLE_LEARNED = {"smoking", "drinking", "marital_status", "children", "diet", "religion_community"}

RULE_LABELS = {
    "gender": "Gender (not seeking)",
    "age": "Age outside range",
    "height": "Below minimum height",
    "location": "Location / won't relocate",
    "religion": "Religion",
    "diet": "Diet",
    "education": "Education below minimum",
    "smoking": "Smokes",
    "drinking": "Drinks",
    "children": "Children mismatch",
    "marital_status": "Marital status",
}


def violations(client: Client, profile: Profile, learned: Optional[Iterable[str]] = None,
               include_gender: bool = True) -> List[Violation]:
    """Every stated preference, deal-breaker and confirmed learned rule this profile breaks."""
    p, db, sp = profile, client.deal_breakers, client.stated_preferences
    learned = set(learned or [])
    out: List[Violation] = []

    def add(rule, category, message, is_learned=False):
        out.append(Violation(rule=rule, category=category, message=message, learned=is_learned))

    if include_gender and p.gender != client.seeking:
        add("gender", "other", "Not the gender the client is seeking")
    if not (sp.age_min <= p.age <= sp.age_max):
        add("age", "age", f"Age {p.age} outside preferred {sp.age_min}-{sp.age_max}")
    if p.height_cm < sp.height_min_cm:
        add("height", "height", f"Height {p.height_cm} cm below minimum {sp.height_min_cm} cm")
    if p.city not in sp.cities_ok and not sp.open_to_relocation and not p.open_to_relocation:
        add("location", "location_relocation",
            f"Lives in {p.city}, won't relocate; client wants {', '.join(sp.cities_ok)} and won't move")
    if sp.religion != "any" and p.religion not in sp.religion:
        add("religion", "religion_community", f"Religion {p.religion} not in {', '.join(sp.religion)}")
    if sp.diet != "any" and p.diet not in sp.diet:
        add("diet", "diet", f"Diet {p.diet} not in {', '.join(sp.diet)}")
    if education_rank(p.education) < education_rank(sp.education_min):
        add("education", "education", f"Education {p.education} below minimum {sp.education_min}")

    # Deal-breakers (stated)
    if db.smoking and p.smokes:
        add("smoking", "smoking", "Smokes - client deal-breaker")
    if db.drinking and p.drinks != "never":
        add("drinking", "drinking", f"Drinks ({p.drinks}) - client deal-breaker")
    if db.wants_children != "open" and p.wants_children != "open" and p.wants_children != db.wants_children:
        add("children", "children",
            f"Wants children: {p.wants_children}; client: {db.wants_children} - deal-breaker")
    if not db.divorced_ok and p.marital_status == "divorced":
        add("marital_status", "marital_status", "Divorced - client deal-breaker")

    # Learned deal-breakers (confirmed by the client in Tab 3). Skip if a stated rule already fired.
    fired = {v.rule for v in out}
    if "smoking" in learned and p.smokes and "smoking" not in fired:
        add("smoking", "smoking", "Smokes - learned deal-breaker (client confirmed)", True)
    if "drinking" in learned and p.drinks != "never" and "drinking" not in fired:
        add("drinking", "drinking", f"Drinks ({p.drinks}) - learned deal-breaker (client confirmed)", True)
    if "marital_status" in learned and p.marital_status != "never_married" and "marital_status" not in fired:
        add("marital_status", "marital_status",
            f"{p.marital_status.replace('_', ' ').title()} - learned deal-breaker (client confirmed)", True)
    if "children" in learned and "children" not in fired and db.wants_children == "open" and p.wants_children == "no":
        add("children", "children", "Doesn't want children - learned deal-breaker (client confirmed)", True)
    if "diet" in learned and "diet" not in fired and p.diet != client.diet:
        add("diet", "diet", f"Diet {p.diet} differs from client's {client.diet} - learned deal-breaker", True)
    if "religion_community" in learned and "religion" not in fired and p.religion != client.religion:
        add("religion", "religion_community",
            f"Religion {p.religion} differs from client's {client.religion} - learned deal-breaker", True)
    return out


def hard_filter(client: Client, profiles: List[Profile], learned: Optional[Iterable[str]] = None
                ) -> Tuple[List[Profile], Dict[str, List[Violation]]]:
    """Returns (passing profiles, {excluded profile id: violations})."""
    learned = list(learned or [])
    passing, excluded = [], {}
    for p in profiles:
        v = violations(client, p, learned)
        if v:
            excluded[p.id] = v
        else:
            passing.append(p)
    return passing, excluded


def exclusion_breakdown(excluded: Dict[str, List[Violation]]) -> Counter:
    """Count of profiles excluded per rule (a profile can count under several rules)."""
    c: Counter = Counter()
    for vs in excluded.values():
        for rule in {v.rule + (" (learned)" if v.learned else "") for v in vs}:
            c[rule] += 1
    return c


# ----------------------------------------------------------------------------- scoring

def score_profile(client: Client, p: Profile) -> Tuple[int, str]:
    """Soft fit 0-100 plus a one-line explanation of the strongest reasons."""
    sp = client.stated_preferences
    parts: List[Tuple[float, str]] = []  # (points, reason) for explanation ranking
    score = 0.0

    mid = (sp.age_min + sp.age_max) / 2
    half = max((sp.age_max - sp.age_min) / 2, 1)
    age_pts = 20 * max(0.0, 1 - abs(p.age - mid) / (half + 1))
    score += age_pts
    if age_pts >= 14:
        parts.append((age_pts, f"age {p.age} sits in the middle of the {sp.age_min}-{sp.age_max} range"))

    if p.community == client.community:
        score += 15
        parts.append((15, f"same community ({p.community})"))
    elif p.religion == client.religion:
        score += 8
        parts.append((8, f"same religion ({p.religion})"))

    edu_gap = abs(education_rank(p.education) - education_rank(client.education))
    edu_pts = {0: 15, 1: 9}.get(edu_gap, 3)
    score += edu_pts
    if edu_gap == 0:
        parts.append((edu_pts, f"same education level ({p.education})"))

    if p.city == client.city:
        score += 15
        parts.append((15, f"also in {p.city}"))
    elif p.city in sp.cities_ok:
        score += 10
        parts.append((10, f"in {p.city}, one of the client's preferred cities"))
    elif p.open_to_relocation:
        score += 6
        parts.append((6, f"open to relocating from {p.city}"))

    if p.diet == client.diet:
        score += 10
        parts.append((10, f"same diet ({p.diet})"))

    shared = sorted(set(p.interests) & set(client.interests))
    int_pts = min(len(shared), 3) * 5
    score += int_pts
    if shared:
        parts.append((int_pts + 1, f"shares {', '.join(shared)}"))

    if p.drinks == "never" and client.deal_breakers.drinking is None:
        score += 2
    score += 3 if p.height_cm >= sp.height_min_cm + 5 else 0
    score += 2 if p.marital_status == "never_married" else 0

    parts.sort(key=lambda x: -x[0])
    why = "; ".join(r for _, r in parts[:3]) or "meets all stated preferences"
    return int(round(min(score, 100))), why[0].upper() + why[1:]


def shortlist(client: Client, profiles: List[Profile], learned: Optional[Iterable[str]] = None,
              top_n: int = 15) -> List[Tuple[Profile, int, str]]:
    passing, _ = hard_filter(client, profiles, learned)
    scored = [(p, *score_profile(client, p)) for p in passing]
    scored.sort(key=lambda x: (-x[1], x[0].id))
    return scored[:top_n]
