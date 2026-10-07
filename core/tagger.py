"""Turn free-text rejection feedback into structured reasons.

Primary path (works offline): a rule-based tagger that understands
  * synonyms and Hinglish ("daaru peeta hai", "umar zyada hai", "vibe nahi aayi"),
  * common typos ("smokr", "vegitarian", "arrogent") via regex variants + 1-edit fuzzy matching,
  * trait negation ("doesn't smoke", "non-smoker", "daaru nahi peeta") so they are NOT tagged,
  * acceptance ("I don't mind that he drinks", "looks fine") so they are NOT tagged,
  * mixed reasons, split on clause boundaries ("but", "lekin", "par", punctuation).

Optional path: an LLM (see core/llm.py) asked for strict JSON, validated with pydantic,
retried once, then falling back to the keyword tagger.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from .models import Tag, TaggedReason

# ----------------------------------------------------------------------------- lexicon
# (regex, weight). Weight ~= how sure we are that this phrase alone means this category.
STRONG, MED, WEAK = 0.9, 0.75, 0.5

LEXICON: Dict[str, List[Tuple[str, float]]] = {
    "age": [
        (r"\btoo\s+(old|young)\b", STRONG), (r"\bage\s*(gap|difference|diff)\b", STRONG),
        (r"\b(umar|umr|umra|umar)\b", 0.85), (r"\b(years?|yrs?)\s+(older|younger|elder)\b", 0.85),
        (r"\b(older|younger|elder)\s+than\b", 0.7), (r"\bmax\s*\d{2}\b", 0.7), (r"\b\d{2}\s*\+", 0.65),
        (r"\b(is|only|he'?s|she'?s)\s+(only\s+)?\d{2}\b(?!\s*(cm|hours?|hrs?|lpa|lakh|k\b|%))", 0.6),
        (r"\bage\b", 0.6), (r"\b(uncle|aunty|aunti)\b", 0.7), (r"\bthe\s+range\b", WEAK),
    ],
    "height": [
        (r"\b(too|bit|very|quite|kinda|thoda|bahut)\s+short\b(?![\s-]*temper)", STRONG),
        (r"\bshort\b(?![\s-]*temper)", 0.6), (r"\b(height|hieght|heigth|hight)\b", STRONG),
        (r"\b(taller|too\s+tall)\b", 0.8), (r"\b\d{3}\s*cm\b", 0.7),
        (r"\b[4-6]\s*'\s*\d{1,2}\b|\b[4-6]\s*(ft|feet)\b", 0.75),
        (r"\b(lamba|lambi|naata|naati|nata|nati)\b", 0.8), (r"\b(chhota|chota|chhoti|choti)\b", 0.45),
    ],
    "location_relocation": [
        (r"\btoo\s+far\b|\bfar\s+away\b|\blives?\s+far\b", STRONG),
        (r"\b(long[\s-]?)?(distance|distence|distanse)\b", 0.85), (r"\breloc\w*|\brelcoat\w*", STRONG),
        (r"\b(shift|shifting|move|moving)\s+(to|out|cities|city|abroad|base)\b", 0.8),
        (r"\bnot\s+(moving|shifting)\b|\bwon'?t\s+(move|shift|relocate)\b", STRONG),
        (r"\b(another|different|other)\s+city\b|\bdoosr[ae]\s+(sheher|shehar|city)\b", 0.85),
        (r"\bsettle\s+nahi\b|\bsettle\s+(in|down\s+in)\b", 0.6), (r"\b(nri|abroad|onsite)\b", 0.7),
        (r"\b(mumbai|bombay|delhi|bangalore|bengaluru|pune|hyderabad|chennai|kolkata|calcutta|ahmedabad|"
         r"jaipur|gurgaon|gurugram|noida)\b", 0.55), (r"\bcity\b", WEAK),
    ],
    "religion_community": [
        (r"\b(religio\w*|religous|relegion|relgion)\b", STRONG),
        (r"\binter[\s-]?(religion|religious|caste|faith)\b", 0.95),
        (r"\bdifferent\s+(religion|faith|caste|community)\b", 0.95),
        (r"\bcaste\b|\bcast\s+(issue|problem|different|mismatch)\b", STRONG), (r"\bcommunit\w*", 0.8),
        (r"\b(hindu|muslim|sikh|christian|jain|buddhist|parsi)\b", 0.7),
        (r"\b(brahmin|kshatriya|maratha|marwari|jat|rajput|baniya|agarwal|iyer|iyengar|nair|reddy|kayastha|"
         r"khatri|sunni|shia)\b", 0.7),
        (r"\b(kundli|kundali|manglik|gotra|biradari|jaati|dharam|dharm)\b|\bgunas?\s+(match|milan)\b", 0.85),
        (r"\bfaith\b", 0.6),
    ],
    "diet": [
        (r"\bnon[\s-]?ve[gj]\w*", STRONG), (r"\b(vegetarian|vegitarian|vegeterian|veggie|vegan|eggetarian)\b", 0.85),
        (r"\bpure\s+veg\b|\bveg\b", 0.85),
        (r"\b(eats?|eating|khata|khati|khaata)\s+(meat|chicken|mutton|fish|beef|pork|eggs?|non[\s-]?veg|anda|gosht|maans)\b", STRONG),
        (r"\b(meat|chicken|mutton|beef|pork)\b", 0.6), (r"\bjain\s+food\b|\b(sattvic|satvik)\b|\bonion\s+garlic\b", 0.85),
        (r"\bdiet\b|\bfood\s+habits?\b|\bkhana\s+peena\b", 0.7),
    ],
    "education": [
        (r"\b(educat\w*|eductaion|educaton)\b", STRONG), (r"\bqualifi\w*|\bqualif\w*", STRONG),
        (r"\b(under|un|less|not)[\s-]?qualified\b", 0.95),
        (r"\b(degree|graduate|graduation|post[\s-]?grad\w*|masters?|phd|ph\.d|mba|b\.?tech|m\.?tech|diploma|"
         r"bachelors?|dropout)\b|\b12th\s+pass\b", 0.7),
        (r"\b(padhai|padhaai|padha\s+likha|padhi\s+likhi|padhe\s+likhe)\b", STRONG),
        (r"\b(iit|iim|college|university)\b", 0.55),
    ],
    "career_income": [
        (r"\b(career|carrer|carreer)[\s-]?(focused|focussed|oriented|driven|minded)\b", 0.95),
        (r"\b(career|carrer|carreer)\w*", MED),
        (r"\bworkaholic\b|\bwork[\s-]?life\b|\b\d{2,3}\s*(hour|hr)s?\s+(work\s*)?weeks?\b|"
         r"\bworks?\s+(too\s+much|all\s+the\s+time|long\s+hours)\b|\bno\s+time\s+for\b|"
         r"\bbusy\s+with\s+work\b|\btoo\s+(ambitious|busy)\b", STRONG),
        (r"\b(salary|income|package|ctc|lpa|earns?|earning|kamata|kamati|kamai|paisa|paise|money|financially|"
         r"unemployed|jobless|naukri)\b", 0.85),
        (r"\bnot\s+settled\b|\bsettled\s+nahi\b|\bstable\s+job\b|\bjob\s+(is\s+)?(not\s+)?stable\b|\bunstable\b", 0.85),
        (r"\b(job|profession|startup|business)\b", 0.6), (r"\bambitio\w*", 0.7),
    ],
    "smoking": [
        (r"\bsmok\w*|\bsmoek\w*|\bsmkoe\w*", STRONG),
        (r"\bcig\w*|\bsigaret\w*|\bsutta\b|\bsuttebaaz\b|\b(beedi|bidi|tobacco|gutka|gutkha)\b", STRONG),
        (r"\bvap(e|es|ing)\b|\b(hookah|hukka|hookha|dhuan)\b", 0.85),
    ],
    "drinking": [
        (r"(?<!soft )(?<!cold )\b(drink|drinks|drinker|drinking|drinkr|drnks|drnk|dirnks|drinkes)\b"
         r"(?!\s+(coffee|tea|chai|water|juice|coke|milk))", STRONG),
        (r"\b(alcohol\w*|alchohol\w*|alcohal\w*|booze\w*|boozer|beer|whiske?y|vodka|wine|rum|pegs?|drunk|tipsy|"
         r"hangover)\b", STRONG),
        (r"\b(daaru|daru|darru|dāru|sharab\w*|sharaab\w*|talli)\b|\btight\s+ho\b", STRONG),
        (r"\bparty\s+animal\b|\bpub[\s-]?(crawl|hopping)\b|\bbar\s+hopping\b", 0.8),
        (r"\b(peeta|peeti|pita|piti|peete|pite)\s+(hai|h|he)\b", 0.6),
    ],
    "children": [
        (r"\b(kids?|child|children|childern|childs|baby|babies|bacche|bachche|bachhe|bache|bachon|bacchon)\b", STRONG),
        (r"\bchild[\s-]?free\b|\bfamily\s+planning\b|\bstart\s+a\s+family\b|\b(parent|mother|father)hood\b", STRONG),
    ],
    "marital_status": [
        (r"\bdivor\w*|\bdivo[sc]\w*", 0.95),
        (r"\b(second|2nd)\s+marriage\b|\bremarr\w*|\bpreviously\s+married\b|\bmarried\s+before\b|\bwas\s+married\b|"
         r"\balready\s+married\b|\bex[\s-]?(wife|husband|spouse)\b|\bwidow\w*|\bseparated\b|\btala+q\b|"
         r"\bshaadi\s+ho\s+(chuki|gayi|chuka)\b|\bpehle\s+shaadi\b", STRONG),
    ],
    "family_values": [
        (r"\bjoint\s+family\b|\bnuclear\b", 0.95), (r"\b(mama|mummy|mumma)'?s\s+boy\b|\bpapa'?s\s+(girl|princess)\b", 0.95),
        (r"\bin[\s-]?laws?\b|\b(saas|sasural)\b", 0.85),
        (r"\b(orthodox|conservative|traditional|old[\s-]?fashioned|too\s+modern|liberal|backward|regressive|patriarchal)\b", 0.85),
        (r"\bfamily\b(?!\s+(with\s+)?(children|kids|planning))", 0.6),
        (r"\b(parents|ghar\s*wale|gharwale|gharwaale|mummy|papa|maa\s+baap)\b", 0.7),
        (r"\bvalues\b|\bsansk[a]+r\w*|\bupbringing\b", 0.7),
        (r"\bdependent\s+on\s+(his|her|their)\s+parents\b|\bparents?\s+(are\s+)?too\s+involved\b", 0.95),
        (r"\bstrict\b", WEAK),
    ],
    "personality": [
        (r"\b(arrogant|arrogance|arrogent|arogant|rude|boring|bored|dull|dry|immature|childish|egoistic|egotistic|ego|"
         r"attitude|atitude|show[\s-]?off\w*|showoff\w*|loud|bossy|pushy|rigid|stubborn|selfish|cocky|pretentious|fake|"
         r"creepy|weird|awkward|introvert\w*|shy|aggressive|controlling|possessive|judgmental|judgemental|"
         r"condescending|negative|dominating|narcissist\w*)\b", 0.85),
        (r"\bshort[\s-]?temper\w*|\bbad\s+temper\w*|\b(angry|gussa|gussel)\b", STRONG),
        (r"\bfull\s+of\s+(himself|herself|themselves)\b|\btalks?\s+only\s+about\b|\bzero\s+curiosity\b|"
         r"\bno\s+sense\s+of\s+humou?r\b|\btoo\s+serious\b|\bred\s+flag\b", STRONG),
        (r"\b(akdu|akad\w*|nakhre\w*|nakhra\w*|ghamand\w*|badtameez\w*|bakbak|swabhav|nature|behaviou?r\w*|"
         r"conversation|personality|maturity)\b|\bbak\s+bak\b", 0.7),
    ],
    "appearance": [
        (r"\b(attractive|good[\s-]?looking|handsome|pretty|beautiful|cute|ugly)\b", 0.85),
        (r"\blooks?\b(?!\s+(like|for|at|into|forward))", 0.65), (r"\b(photos?|pics?|pictures?)\b", WEAK),
        (r"\b(fat|overweight|chubby|obese|skinny|bald|balding|beard|physique|physically|grooming|groomed|hygiene|"
         r"paunch|belly)\b|\bdress(ing)?\s+sense\b", 0.8),
        (r"\b(dikhne|dikhta|dikhti|shakal|shakl|surat|mota|moti|patla|patli|ganja)\b|\bsmart\s+nahi\b", 0.85),
    ],
    "vague_no_spark": [
        (r"\bno\s+spark\w*|\bspark\b|\bsprak\b|\bno\s+chemistry\b|\bchem[ei]?st?ry\b|\bno\s+connection\b|\bconnection\b", 0.85),
        (r"\bdid\s*n'?t\s+(click|connect|feel\s+right|work\s+out|feel)\b|\bdidnt\s+(click|connect|feel)\b", 0.85),
        (r"\bnot\s+(feeling|feelin|feelng)\s+it\b|\bnot\s+my\s+type\b|\bnot\s+for\s+me\b|\bnot\s+interested\b", 0.85),
        (r"\bsomething\s+(felt|feels|was|seemed)\s+off\b|\bfelt\s+(a\s+bit\s+)?off\b|\boff\s+vibe\b|\bvibe\w*", 0.85),
        (r"\b(meh|nope|idk)\b|\bjust\s+no\b|(?<!th )\bpass\b|\bnot\s+sure\b|\bcan'?t\s+(explain|put\s+my\s+finger)\b|"
         r"\bgut\s+feel\w*|\bnothing\s+wrong\b|\bjust\s+not\b", 0.8),
        (r"\bpata\s+nahi\b|\bkuch\s+(missing|kami)\b|\bfeel\s+nahi\b|\bnahi\s+jam\w*|\bjam[ai]\s+nahi\b|"
         r"\bjacha\s+nahi\b|\bnahi\s+jacha\b|\bclick\s+nahi\b|\bbaat\s+nahi\s+bani\b", 0.85),
    ],
    "other": [
        (r"\balready\s+(talking|seeing|dating|engaged)\b|\btiming\b|\bnot\s+ready\b|\bon\s+hold\b|\bbreak\s+from\b", 0.7),
    ],
}

# Words that tolerate one typo (or two for long words). Only tokens of 6+ letters with the same first letter
# are compared, which keeps "spoke" from becoming "smoke".
FUZZY_VOCAB: Dict[str, List[str]] = {
    "smoking": ["smoker", "smokes", "smoking", "cigarette", "cigarettes"],
    "drinking": ["drinks", "drinker", "drinking", "alcohol", "alcoholic", "sharab"],
    "diet": ["vegetarian", "nonvegetarian", "eggetarian"],
    "location_relocation": ["relocate", "relocation", "relocating", "distance"],
    "religion_community": ["religion", "religious", "community"],
    "education": ["education", "qualification", "qualified", "graduate", "postgraduate"],
    "career_income": ["career", "salary", "income", "ambitious", "workaholic"],
    "children": ["children"],
    "marital_status": ["divorced", "divorcee", "separated", "widowed", "widower"],
    "family_values": ["family", "traditional", "orthodox", "conservative", "parents"],
    "personality": ["arrogant", "boring", "immature", "attitude", "egoistic"],
    "appearance": ["attractive", "handsome", "photos", "pictures"],
    "vague_no_spark": ["chemistry", "connection"],
}
FUZZY_STOPWORDS = {"altitude", "spokes", "bowing", "boxing", "stroke", "string", "during", "things", "thinking",
                   "smiled", "smiles", "settle", "settled", "eligible", "decent", "drives", "driver"}

# Trait negation: "doesn't smoke", "non-smoker", "never drinks", "quit smoking", "not a drinker".
NEG_BEFORE = re.compile(
    r"\b(does\s*n'?t|doesnt|dont|don'?t|do\s+not|does\s+not|did\s*n'?t|never|is\s*n'?t|isnt|not\s+a|non[\s-]?|"
    r"no\s+longer|quit|gave\s+up|stopped|nahi|nahin|nhi|na)\s*(even\s+|really\s+|at\s+all\s+|ever\s+)?$"
    # coordination: "never drinks or smokes", "doesn't smoke or drink"
    r"|\b(never|does\s*n'?t|doesnt|dont|don'?t|do\s+not|does\s+not)\s+\w+\s+(or|nor|and)\s+$"
)
NEG_AFTER = re.compile(r"^\s*(nahi|nahin|nhi|nai)\s+(peeta|peeti|pita|piti|peete|karta|karti|leta|leti)\b")
TEETOTAL = re.compile(r"\b(teetotal\w*|sober|non[\s-]?(smoker|drinker))\b")
NEGATABLE = {"smoking", "drinking"}

# Acceptance: the phrase says the trait is NOT a problem.
ACCEPT_PREFIX = re.compile(
    r"\b(do\s*n'?t\s+mind|dont\s+mind|do\s+not\s+mind|(fine|ok|okay|cool|comfortable)\s+with|"
    r"no\s+(problem|issue)s?\s+with|happy\s+that)\b"
)
ACCEPT_SUFFIX = re.compile(
    r"\b(is|are|was|were|looks?|seems?)\s+(fine|ok|okay|good|great|nice|not\s+an?\s+(issue|problem|deal[\s-]?breaker))\b|"
    r"\b(theek|thik)\s+(hai|tha|lag\w*)\b|(?<!nahi )\bchalega\b"
)
NOT_BEFORE = re.compile(r"(not|n't|nahi|nhi|never)\s*$")
NOT_AFTER = re.compile(r"^\s*(nahi|nhi|not)\b")

CLAUSE_SPLIT = re.compile(r"[.;!?\n]+|,|\bbut\b|\bthough\b|\balthough\b|\bhowever\b|\blekin\b|\bmagar\b|\bpar\b|\balso\b")

STRONG_SENTIMENT = re.compile(
    r"!|\?\?|\b(clearly|already|literally|deal[\s-]?breaker|non[\s-]?negotiable|absolutely|at\s+all|straight\s+no|"
    r"red\s+flag|pehle\s+hi|bola\s+tha|i\s+(told|said|had\s+said|mentioned)|specifically|nahi\s+chalega|waste|"
    r"seriously|never\s+again|first\s+condition|please\s+check)\b"
)
STATED_BOOST = re.compile(r"\b(mentioned|i\s+said|told|already|clearly|in\s+my\s+(form|prefs|preferences)|pehle\s+hi|bola\s+tha|"
                          r"asked\s+for|deal[\s-]?breaker|non[\s-]?negotiable|was\s+in\s+my)\b")

CONCRETE = [c for c in LEXICON if c not in ("vague_no_spark", "other")]
_COMPILED = {c: [(re.compile(p), w) for p, w in pats] for c, pats in LEXICON.items()}


def _damerau(a: str, b: str) -> int:
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def _normalize(text: str) -> str:
    # Same length as the input so match offsets map straight back to the original (for evidence).
    return text.lower().replace("’", "'").replace("‘", "'").replace("`", "'")


def _clauses(norm: str) -> List[Tuple[int, int]]:
    spans, start = [], 0
    for m in CLAUSE_SPLIT.finditer(norm):
        if m.start() > start:
            spans.append((start, m.start()))
        start = m.end()
    if start < len(norm):
        spans.append((start, len(norm)))
    return [(s, e) for s, e in spans if norm[s:e].strip()]


def _accepted_windows(clause: str) -> List[Tuple[int, int]]:
    wins = []
    for m in ACCEPT_PREFIX.finditer(clause):
        if not NOT_BEFORE.search(clause[: m.start()]):
            wins.append((m.start(), m.end() + 35))
    for m in ACCEPT_SUFFIX.finditer(clause):
        if not NOT_BEFORE.search(clause[: m.start()]) and not NOT_AFTER.search(clause[m.end():]):
            wins.append((max(0, m.start() - 35), m.end()))
    return wins


def _is_negated(clause: str, start: int, end: int) -> bool:
    before = clause[max(0, start - 30): start]
    return bool(NEG_BEFORE.search(before) or NEG_AFTER.search(clause[end:end + 12]))


def keyword_tag(text: str) -> TaggedReason:
    """Rule-based tagger. Deterministic, no network."""
    text = text or ""
    norm = _normalize(text)
    hits: Dict[str, List[Tuple[float, int, int]]] = {}  # category -> [(weight, abs_start, abs_end)]

    for cs, ce in _clauses(norm):
        clause = norm[cs:ce]
        accepted = _accepted_windows(clause)
        clause_hits: Dict[str, List[Tuple[float, int, int, str]]] = {}
        for cat, pats in _COMPILED.items():
            for rx, w in pats:
                for m in rx.finditer(clause):
                    s, e = m.start(), m.end()
                    if any(a <= s < b for a, b in accepted):
                        continue
                    if cat in NEGATABLE and _is_negated(clause, s, e):
                        continue
                    clause_hits.setdefault(cat, []).append((w, s, e, rx.pattern))
        # Typo tolerance on tokens nothing else claimed
        for tm in re.finditer(r"[a-z]{6,}", clause):
            tok = tm.group()
            if tok in FUZZY_STOPWORDS or any(s <= tm.start() < e for hs in clause_hits.values() for _, s, e, _ in hs):
                continue
            for cat, vocab in FUZZY_VOCAB.items():
                for word in vocab:
                    if tok == word or tok[0] != word[0] or abs(len(tok) - len(word)) > 2:
                        continue
                    if _damerau(tok, word) <= (2 if len(word) >= 9 else 1):
                        if any(a <= tm.start() < b for a, b in accepted):
                            break
                        if cat in NEGATABLE and _is_negated(clause, tm.start(), tm.end()):
                            break
                        clause_hits.setdefault(cat, []).append((0.6, tm.start(), tm.end(), "fuzzy"))
                        break
        # Teetotaler / sober / non-smoker are explicit "doesn't" statements
        for m in TEETOTAL.finditer(clause):
            for cat in NEGATABLE:
                clause_hits[cat] = [h for h in clause_hits.get(cat, []) if not (m.start() <= h[1] < m.end() + 1)]
        # "sutta peeta hai" -> smoking, not drinking
        if "smoking" in clause_hits and "drinking" in clause_hits:
            clause_hits["drinking"] = [h for h in clause_hits["drinking"] if "peeta" not in h[3]]
        clause_hits = {c: hs for c, hs in clause_hits.items() if hs}
        # Weak cues (e.g. "pics", "city") don't count when a solid concrete reason is in the same clause
        solid = {c for c, hs in clause_hits.items() if c in CONCRETE and max(h[0] for h in hs) >= 0.6}
        for cat in list(clause_hits):
            if max(h[0] for h in clause_hits[cat]) < 0.6 and solid - {cat}:
                clause_hits[cat] = []
        for cat, hs in clause_hits.items():
            for w, s, e, _ in hs:
                hits.setdefault(cat, []).append((w, cs + s, cs + e))

    hits = {c: hs for c, hs in hits.items() if hs}
    boost = 0.05 if STATED_BOOST.search(norm) else 0.0
    concrete_found = any(c in CONCRETE for c in hits)
    tags: List[Tag] = []
    for cat, hs in hits.items():
        p_not = 1.0
        for w, _, _ in hs:
            p_not *= (1 - w)
        conf = 1 - p_not
        if cat in CONCRETE:
            conf += boost
        if cat == "vague_no_spark" and concrete_found:
            conf = min(conf, 0.5)  # "no spark, also he smokes" -> the smoking is the real reason
        best = max(hs, key=lambda h: (h[0], h[2] - h[1]))
        evidence = text[best[1]:best[2]].strip()
        tags.append(Tag(category=cat, confidence=round(min(conf, 0.98), 2), evidence=evidence))

    if not tags:
        snippet = text.strip()[:60]
        tags = [Tag(category="other", confidence=0.3, evidence=snippet)]
        is_vague = len(text.split()) <= 6
    else:
        is_vague = not concrete_found and not any(t.category == "other" for t in tags)

    tags.sort(key=lambda t: -t.confidence)
    caps = re.search(r"\b[A-Z]{3,}\b", text) and not re.search(r"\b(NRI|IIT|IIM|MBA|CTC|LPA|PHD)\b", text)
    sentiment = "strong" if (STRONG_SENTIMENT.search(norm) or caps) else "mild"
    return TaggedReason(tags=tags, is_vague=is_vague, sentiment=sentiment, source="keyword")


# ----------------------------------------------------------------------------- LLM path
LLM_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {"type": "array", "items": {
            "type": "object",
            "properties": {"category": {"type": "string"}, "confidence": {"type": "number"}, "evidence": {"type": "string"}},
            "required": ["category", "confidence", "evidence"], "additionalProperties": False}},
        "is_vague": {"type": "boolean"},
        "sentiment": {"type": "string", "enum": ["mild", "strong"]},
    },
    "required": ["tags", "is_vague", "sentiment"],
    "additionalProperties": False,
}


def build_llm_prompt(text: str, taxonomy: Dict[str, dict]) -> Tuple[str, str]:
    system = (
        "You classify rejection feedback from clients of an Indian matchmaking service. Feedback is often short, "
        "informal, in Hinglish, with typos. Tag every reason the client gives using ONLY these categories:\n"
        + "\n".join(f"- {k}: {v['description']} (e.g. {', '.join(v['examples'])})" for k, v in taxonomy.items())
        + "\n\nRules: a trait that is negated (\"doesn't smoke\", \"daaru nahi peeta\") or accepted "
        "(\"I don't mind that he drinks\") is NOT a reason. `evidence` must be the exact substring of the feedback "
        "that supports the tag. `confidence` is 0-1. `is_vague` is true when no concrete reason is given. "
        "`sentiment` is \"strong\" when the client is annoyed or says they already stated this, else \"mild\". "
        "Respond with JSON only: {\"tags\": [{\"category\": str, \"confidence\": float, \"evidence\": str}], "
        "\"is_vague\": bool, \"sentiment\": \"mild\"|\"strong\"}"
    )
    return system, f"Feedback: {text}"


def parse_llm_output(raw: str, taxonomy: Dict[str, dict]) -> TaggedReason:
    raw = raw.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw).strip()
    data = json.loads(raw)
    data["tags"] = [t for t in data.get("tags", []) if t.get("category") in taxonomy]
    for t in data["tags"]:
        t["confidence"] = max(0.0, min(1.0, float(t.get("confidence", 0.5))))
    data["source"] = "llm"
    result = TaggedReason.model_validate(data)
    if not result.tags:
        raise ValueError("LLM returned no valid tags")
    return result


def tag_feedback(text: str, taxonomy: Dict[str, dict],
                 llm_call: Optional[Callable[[str, str, dict], str]] = None) -> Tuple[TaggedReason, Optional[str]]:
    """Tag one piece of feedback. Returns (result, warning). Uses the LLM if given, else keywords.

    LLM flow: call -> validate -> on failure retry once -> on failure fall back to keyword tagger.
    """
    if llm_call is None or not (text or "").strip():
        return keyword_tag(text), None
    system, user = build_llm_prompt(text, taxonomy)
    last_err: Optional[Exception] = None
    for _ in range(2):
        try:
            return parse_llm_output(llm_call(system, user, LLM_JSON_SCHEMA), taxonomy), None
        except (ValidationError, ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
            last_err = e
        except Exception as e:  # network / auth / quota: don't retry, fall back now
            last_err = e
            break
    return keyword_tag(text), f"LLM tagging failed ({type(last_err).__name__}); used keyword tagger"
