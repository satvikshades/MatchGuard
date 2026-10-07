"""Learned deal-breakers, reversal detection and vague-rejection flags. Pure functions."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Hashable, List, Optional

from pydantic import BaseModel

from .models import Client, Profile, ShareRecord, TaggedReason

MIN_CONFIDENCE = 0.6

# Categories that can become a new deal-breaker the hard filter can enforce.
LEARNABLE = {"smoking", "drinking", "children", "marital_status", "diet", "religion_community"}

CATEGORY_LABELS = {
    "age": "age", "height": "height", "location_relocation": "location / relocation",
    "religion_community": "religion / community", "diet": "diet", "education": "education",
    "career_income": "career-focused / income", "smoking": "smoking", "drinking": "drinking",
    "children": "children", "marital_status": "marital status", "family_values": "family values",
    "personality": "personality", "appearance": "appearance", "vague_no_spark": "vague / no spark", "other": "other",
}

# The trait a rejection was "about". If an accepted profile has the same trait, the rejection reason
# isn't a reliable rule for this client. None = profile doesn't have the trait.
TraitFn = Callable[[Client, Profile], Optional[Hashable]]
TRAITS: Dict[str, TraitFn] = {
    "smoking": lambda c, p: True if p.smokes else None,
    "drinking": lambda c, p: True if p.drinks != "never" else None,
    "children": lambda c, p: p.wants_children,
    "marital_status": lambda c, p: p.marital_status if p.marital_status != "never_married" else None,
    "diet": lambda c, p: p.diet,
    "religion_community": lambda c, p: p.religion,
    "career_income": lambda c, p: (p.profession, p.seniority),
    "education": lambda c, p: p.education,
    "location_relocation": lambda c, p: p.city if (p.city not in c.stated_preferences.cities_ok
                                                     and not p.open_to_relocation) else None,
}


def describe_trait(category: str, p: Profile) -> str:
    return {
        "smoking": "smokes", "drinking": f"drinks ({p.drinks})", "children": f"wants children: {p.wants_children}",
        "marital_status": p.marital_status.replace("_", " "), "diet": p.diet, "religion_community": p.religion,
        "career_income": f"{p.seniority} {p.profession}", "education": p.education,
        "location_relocation": f"lives in {p.city}, won't relocate",
    }.get(category, category)


def covered_by_stated(client: Client, category: str) -> bool:
    db, sp = client.deal_breakers, client.stated_preferences
    return {
        "smoking": db.smoking, "drinking": db.drinking is True, "children": db.wants_children != "open",
        "marital_status": not db.divorced_ok, "diet": sp.diet != "any", "religion_community": sp.religion != "any",
    }.get(category, True)


class Suggestion(BaseModel):
    client_id: str
    client_name: str
    category: str
    count: int
    share_ids: List[str]
    evidence: List[str]


class ReversalFlag(BaseModel):
    client_id: str
    client_name: str
    category: str
    trait: str
    rejected_share_id: str
    rejected_date: str
    rejected_profile_id: str
    rejected_feedback: str
    accepted_share_id: str
    accepted_date: str
    accepted_profile_id: str


class VagueFlag(BaseModel):
    client_id: str
    client_name: str
    vague: int
    total: int

    @property
    def ratio(self) -> float:
        return self.vague / self.total if self.total else 0.0


def _concrete_categories(tr: TaggedReason) -> List[str]:
    return [t.category for t in tr.tags
            if t.confidence >= MIN_CONFIDENCE and t.category not in ("vague_no_spark", "other")]


def reversal_flags(clients: List[Client], profiles: Dict[str, Profile], shares: List[ShareRecord],
                   tagged: Dict[str, TaggedReason]) -> List[ReversalFlag]:
    """Client rejected a profile for trait X but accepted another profile with the same X (before or after)."""
    cmap = {c.id: c for c in clients}
    flags: List[ReversalFlag] = []
    for s in shares:
        if s.outcome != "rejected" or s.share_id not in tagged:
            continue
        c, rp = cmap[s.client_id], profiles[s.profile_id]
        for cat in _concrete_categories(tagged[s.share_id]):
            fn = TRAITS.get(cat)
            trait = fn(c, rp) if fn else None
            if trait is None:
                continue
            for a in shares:
                if a.client_id == s.client_id and a.outcome == "accepted" and fn(c, profiles[a.profile_id]) == trait:
                    flags.append(ReversalFlag(
                        client_id=c.id, client_name=c.name, category=cat, trait=describe_trait(cat, rp),
                        rejected_share_id=s.share_id, rejected_date=s.date, rejected_profile_id=s.profile_id,
                        rejected_feedback=s.feedback_text, accepted_share_id=a.share_id, accepted_date=a.date,
                        accepted_profile_id=a.profile_id))
    return flags


def learned_suggestions(clients: List[Client], profiles: Dict[str, Profile], shares: List[ShareRecord],
                        tagged: Dict[str, TaggedReason], confirmed: Optional[Dict[str, List[str]]] = None,
                        dismissed: Optional[Dict[str, List[str]]] = None, min_count: int = 2) -> List[Suggestion]:
    """>= min_count rejections for the same learnable category that the client never stated as a deal-breaker."""
    confirmed, dismissed = confirmed or {}, dismissed or {}
    cmap = {c.id: c for c in clients}
    reversed_cats = {(f.client_id, f.category) for f in reversal_flags(clients, profiles, shares, tagged)}
    buckets: Dict[tuple, List[ShareRecord]] = defaultdict(list)
    for s in shares:
        if s.outcome != "rejected" or s.share_id not in tagged:
            continue
        c = cmap[s.client_id]
        for cat in set(_concrete_categories(tagged[s.share_id])):
            if cat not in LEARNABLE or covered_by_stated(c, cat):
                continue
            if TRAITS[cat](c, profiles[s.profile_id]) is None:  # tag must match the actual profile
                continue
            buckets[(c.id, cat)].append(s)
    out = []
    for (cid, cat), ss in sorted(buckets.items()):
        if len(ss) < min_count or (cid, cat) in reversed_cats:
            continue
        if cat in confirmed.get(cid, []) or cat in dismissed.get(cid, []):
            continue
        ev = [next(t.evidence for t in tagged[s.share_id].tags if t.category == cat) for s in ss]
        out.append(Suggestion(client_id=cid, client_name=cmap[cid].name, category=cat, count=len(ss),
                              share_ids=[s.share_id for s in ss], evidence=ev))
    return out


def vague_flags(clients: List[Client], shares: List[ShareRecord], tagged: Dict[str, TaggedReason],
                threshold: float = 0.6, min_rejections: int = 3) -> List[VagueFlag]:
    out = []
    for c in clients:
        rej = [s for s in shares if s.client_id == c.id and s.outcome == "rejected" and s.share_id in tagged]
        vague = sum(1 for s in rej if tagged[s.share_id].is_vague)
        if len(rej) >= min_rejections and vague / len(rej) > threshold:
            out.append(VagueFlag(client_id=c.id, client_name=c.name, vague=vague, total=len(rej)))
    return out


# ----------------------------------------------------------------------------- persistence
def load_learned(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data.setdefault("confirmed", {})
    data.setdefault("dismissed", {})
    return data


def save_learned(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2))
