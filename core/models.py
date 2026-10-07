"""Pydantic schemas shared by every MatchGuard module."""
from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

EDUCATION_LEVELS = ["Diploma", "Bachelors", "Masters", "PhD"]

Gender = Literal["F", "M"]
ChildrenPref = Literal["yes", "no", "open"]
DrinkHabit = Literal["never", "socially", "regularly"]
MaritalStatus = Literal["never_married", "divorced", "widowed"]


def education_rank(level: str) -> int:
    return EDUCATION_LEVELS.index(level) if level in EDUCATION_LEVELS else 0


class StatedPreferences(BaseModel):
    age_min: int
    age_max: int
    height_min_cm: int
    cities_ok: List[str]
    open_to_relocation: bool
    religion: Union[List[str], Literal["any"]] = "any"
    diet: Union[List[str], Literal["any"]] = "any"
    education_min: str = "Bachelors"


class DealBreakers(BaseModel):
    smoking: bool = False  # True = smokers are a deal-breaker
    drinking: Optional[bool] = None  # True = drinkers are a deal-breaker, None = never discussed
    wants_children: ChildrenPref = "open"
    divorced_ok: bool = True


class Client(BaseModel):
    id: str
    name: str
    age: int
    gender: Gender
    city: str
    religion: str
    community: str
    diet: str
    education: str
    profession: str
    interests: List[str] = Field(default_factory=list)
    stated_preferences: StatedPreferences
    deal_breakers: DealBreakers
    about: str

    @property
    def seeking(self) -> str:
        return "M" if self.gender == "F" else "F"


class Profile(BaseModel):
    id: str
    name: str
    gender: Gender
    age: int
    height_cm: int
    city: str
    open_to_relocation: bool
    religion: str
    community: str
    diet: str
    education: str
    profession: str
    seniority: Literal["junior", "mid", "senior"]
    smokes: bool
    drinks: DrinkHabit
    wants_children: ChildrenPref
    marital_status: MaritalStatus
    interests: List[str] = Field(default_factory=list)
    bio: str


class ShareRecord(BaseModel):
    share_id: str
    date: str
    client_id: str
    profile_id: str
    matchmaker: Literal["A", "B"]
    outcome: Literal["accepted", "rejected"]
    feedback_text: str = ""


class Tag(BaseModel):
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str


class TaggedReason(BaseModel):
    """Exactly the JSON contract the LLM must return (plus `source`, set by us)."""

    tags: List[Tag]
    is_vague: bool
    sentiment: Literal["mild", "strong"]
    source: Literal["llm", "keyword"] = "keyword"

    def categories(self) -> List[str]:
        return [t.category for t in self.tags]


class Violation(BaseModel):
    rule: str  # machine key, e.g. "smoking"
    category: str  # taxonomy category
    message: str  # human readable, e.g. "Smokes - client deal-breaker"
    learned: bool = False
