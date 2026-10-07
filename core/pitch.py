"""Pitch drafter: a 2-line "why I chose this person for you" note in the client's own words.

Offline (default): matches sentences in the client's "about what I want" text to concrete lines in the
profile's bio, quotes the client, and rotates through several phrasings so drafts don't read like a mail merge.
Optional: an LLM writes the note instead; any failure falls back to the template.
Nothing is ever sent - drafts are only shown for the matchmaker to edit and copy.
"""
from __future__ import annotations

import random
import re
import zlib
from typing import Callable, List, Optional, Tuple

from .models import Client, Profile

THEMES = {
    "travel": r"travel\w*|trips?\b|road trip|explor\w*|backpack\w*",
    "food": r"\bfood\w*|\bcook\w*|chai|cafe\w*|fish curry|biryani|dinners?\b",
    "fitness": r"\brun\b|\bruns\b|running|fitness|gym|marathon\w*|badminton",
    "books": r"\bbooks?\b|\bread\w*",
    "music": r"music|carnatic|guitar|\bsing\w*|\bgigs?\b|hindustani",
    "movies": r"\bfilms?\b|movies?|cinema|theatre|hera pheri",
    "outdoors": r"\btrek\w*|outdoors|hik\w+|camping|stargazing|sahyadri\w*",
    "art": r"\bart\b|galler\w*|paint\w*|pottery|watercolou?rs?",
    "pets": r"\bdogs?\b|\bpets?\b|\bcats?\b|retriever",
    "spirituality": r"spiritual\w*|temple|meditat\w*",
    "volunteering": r"volunteer\w*|\bngo\b",
    "dance": r"\bdanc\w*|bhangra|salsa",
    "kindness": r"\bkind\w*|\bwarm\b|gentle|caring",
    "humour": r"laugh\w*|funny|humou?r",
    "grounded": r"grounded|down to earth|secure",
    "family": r"\bfamily\b|\bparents\b",
    "curiosity": r"curious|intellectual\w*|argument",
}
THEME_RX = {k: re.compile(v, re.I) for k, v in THEMES.items()}

OPENERS = [
    'You wrote "{quote}" - {name} {vp}, so I think you two would get along.',
    '{name} made me think of your note straight away ("{quote}"): {he} {vp}.',
    'When you said "{quote}", this is the kind of person I pictured - {name} {vp}.',
    '"{quote}" was the line I kept in mind, and {name} fits it: {he} {vp}.',
    'Remember telling me "{quote}"? {name} {vp}.',
    'I picked {name} with your words in mind - "{quote}" - because {he} {vp}.',
]
OPENERS_NO_MATCH = [
    'You told me "{quote}" - that is hard to judge from a profile, but on the things I can check {name} is a strong fit: {he} {fits}.',
    'I kept "{quote}" in mind, and {name} stood out: {he} {fits}.',
    '{name} is someone I would like you to meet with "{quote}" in mind - {he} {fits}.',
]
CLOSERS = [
    "{He}'s {age}, {a_prof} in {city}{reloc}, and {he} {extra}.",
    "On paper it works too: {age}, {prof}, based in {city}{reloc} - and {he} {extra}.",
    "The practical side checks out as well ({age}, {prof}, {city}{reloc}), and {he} {extra}.",
    "Also worth knowing: {he} is {age}, works as {a_prof} in {city}{reloc}, and {extra}.",
    "Beyond that, {he}'s a {age}-year-old {prof} in {city}{reloc_who} who {extra}.",
]
# Bio fragments that don't start with a verb need an "is" to read as "<name> is ...".
INTEREST_NOUNS = {"outdoors": "the outdoors", "pets": "animals", "movies": "films", "dance": "dancing"}
NEEDS_IS = {"close", "looking", "always", "part", "big", "learning", "into", "passionate", "happiest"}


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _quote(sentence: str, rx: re.Pattern) -> str:
    """Shortest natural clause of the client's sentence that contains the theme word, verbatim."""
    clauses = re.split(r",\s*|\s+-\s+|;\s*|\s+so\s+|\s+but\s+", sentence.rstrip(".!?"))
    for c in clauses:
        if rx.search(c):
            words = c.split()
            pre, post = "", ""
            if len(words) > 14:
                kw = len(c[: rx.search(c).start()].split())
                start = max(0, kw - 4)
                pre = "..." if start > 0 else ""
                post = "..." if start + 12 < len(words) else ""
                words = words[start:start + 12]
            q = " ".join(words).strip()
            if not (q.startswith("I ") or q.startswith("I'")):
                q = q[0].lower() + q[1:]
            return pre + q + post
    return sentence.rstrip(".!?")


def _vp(sentence: str) -> str:
    """Bio lines are verb-first fragments ("Has a golden retriever named Bruno.") -> "has a golden retriever named Bruno"."""
    s = sentence.rstrip(".!?")
    s = s[0].lower() + s[1:]
    return ("is " + s) if s.split()[0] in NEEDS_IS else s


def _wants(client: Client) -> List[Tuple[str, str]]:
    out = []
    for s in _sentences(client.about):
        for theme, rx in THEME_RX.items():
            if rx.search(s):
                out.append((theme, _quote(s, rx)))
    return out


def _bio_lines(profile: Profile) -> List[str]:
    # First line is the job/city line; "Looking for..." lines describe what *they* want, not who they are.
    return [s for s in _sentences(profile.bio)[1:] if not s.startswith(("Looking for", "Wants a partner"))]


def _extras(client: Client, p: Profile) -> List[str]:
    """Concrete, checkable points of fit, phrased as verb phrases ("she <phrase>")."""
    ex = []
    if p.community == client.community:
        ex.append(f"comes from the same {p.community} background as you")
    if p.city == client.city:
        ex.append(f"lives in {p.city} too")
    if client.diet == "vegetarian" and p.diet == "vegetarian":
        ex.append("is vegetarian like you")
    if not p.smokes and p.drinks == "never":
        ex.append("doesn't smoke or drink")
    elif not p.smokes:
        ex.append("doesn't smoke")
    if client.deal_breakers.wants_children == "yes" and p.wants_children == "yes":
        ex.append("wants children too")
    if p.education == client.education:
        ex.append(f"has a {p.education} degree like you")
    if set(p.interests) & set(client.interests):
        shared = sorted(set(p.interests) & set(client.interests))
        nouns = [INTEREST_NOUNS.get(x, x) for x in shared[:2]]
        ex.append(f"is into {' and '.join(nouns)} as much as you are")
    return ex


def template_pitch(client: Client, p: Profile, variant: int = 0) -> str:
    rng = random.Random(zlib.crc32(f"{client.id}|{p.id}|{variant}".encode()))
    he = "he" if p.gender == "M" else "she"
    first = p.name.split()[0]
    pairs = []  # (client quote, profile verb phrase)
    for theme, quote in _wants(client):
        for line in _bio_lines(p):
            if THEME_RX[theme].search(line):
                pairs.append((quote, _vp(line)))
    extras = _extras(client, p)
    rng.shuffle(extras)
    fallback = "meets every one of your stated preferences"

    if pairs:
        quote, vp = rng.choice(pairs)
        line1 = rng.choice(OPENERS).format(quote=quote, name=first, vp=vp, he=he)
        others = [v for q, v in pairs if v != vp]
        if others and rng.random() < 0.5:
            extras.insert(0, "also " + others[0])
    else:
        wants = _wants(client) or [("", _sentences(client.about)[0].rstrip("."))]
        quote = rng.choice(wants)[1]
        fits = extras[:2] or [fallback]
        extras = extras[2:]
        fits_text = fits[0] if len(fits) == 1 else f"{fits[0]} and {fits[1]}"
        line1 = rng.choice(OPENERS_NO_MATCH).format(quote=quote, name=first, he=he, fits=fits_text)
    # The closing line already states the city, so "lives in X too" would repeat it
    extras = [e for e in extras if not e.startswith("lives in")] or [fallback]

    reloc = ", open to relocating" if p.city != client.city and p.open_to_relocation else ""
    prof = p.profession.lower()
    a_prof = ("an " if prof[0] in "aeiou" else "a ") + prof
    line2 = rng.choice(CLOSERS).format(He=he.capitalize(), he=he, age=p.age, a_prof=a_prof, prof=prof,
                                       city=p.city, reloc=reloc, reloc_who=reloc + ("," if reloc else ""),
                                       extra=extras[0])
    return line1 + "\n" + line2


def llm_pitch_prompt(client: Client, p: Profile) -> Tuple[str, str]:
    system = ("You are a warm, professional matchmaker at an Indian matchmaking service writing a short note to "
              "your client about a profile you picked for them. Write exactly two lines, no greeting or sign-off, "
              "no emojis. Line 1 must quote or closely paraphrase the client's own words and connect them to a "
              "concrete detail from the profile. Line 2 covers practical fit. Use only facts given; never invent.")
    user = (f"Client {client.name} wrote, about what they want:\n\"{client.about}\"\n\n"
            f"Profile: {p.name}, {p.age}, {p.profession} in {p.city}"
            f"{', open to relocating' if p.open_to_relocation else ''}; {p.religion} ({p.community}); {p.diet}; "
            f"education {p.education}; smokes: {'yes' if p.smokes else 'no'}; drinks: {p.drinks}; "
            f"wants children: {p.wants_children}.\nBio: {p.bio}")
    return system, user


def draft_pitch(client: Client, p: Profile, variant: int = 0,
                llm_call: Optional[Callable[[str, str], str]] = None) -> Tuple[str, str]:
    """Returns (draft, source) where source is 'llm' or 'template'."""
    if llm_call is not None:
        try:
            text = llm_call(*llm_pitch_prompt(client, p)).strip()
            if text:
                return text, "llm"
        except Exception:
            pass
    return template_pitch(client, p, variant), "template"
