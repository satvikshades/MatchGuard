"""Generate reproducible mock data for MatchGuard (fixed seed, no real people).

Writes data/clients.json, profiles.json, share_history.csv, reason_taxonomy.json and
resets data/learned_preferences.json.

The share history is constructed (not just sampled) so the headline numbers are exact:
120 shares, 37 accepted (30.8%), matchmaker A 23/52 (44%), B 14/68 (21%), and 29 of 83
rejections (34.9%) violate the client's stated preferences.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.filters import violations  # noqa: E402
from core.models import EDUCATION_LEVELS, Client, Profile, education_rank  # noqa: E402

SEED = 42
DATA = ROOT / "data"
rng = random.Random(SEED)

CITIES = ["Mumbai", "Delhi", "Bangalore", "Pune", "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Jaipur", "Gurgaon"]
COMMUNITIES = {
    "Hindu": ["Marathi", "Gujarati", "Punjabi", "Tamil", "Telugu", "Bengali", "Malayali", "Marwari", "Kannadiga", "Kayastha"],
    "Muslim": ["Sunni", "Shia"],
    "Sikh": ["Jat Sikh", "Khatri Sikh"],
    "Christian": ["Catholic", "Syrian Christian"],
    "Jain": ["Shwetambar", "Digambar"],
}
RELIGION_WEIGHTS = {"Hindu": 66, "Muslim": 10, "Sikh": 9, "Christian": 7, "Jain": 8}
DIETS = ["vegetarian", "non-vegetarian", "eggetarian", "vegan"]
PROFESSIONS = [
    ("software engineer", "a product startup"), ("product manager", "a fintech"), ("doctor", "a city hospital"),
    ("chartered accountant", "a Big 4 firm"), ("management consultant", "a strategy consulting firm"),
    ("lawyer", "a corporate law firm"), ("architect", "a design studio"), ("teacher", "an international school"),
    ("investment banker", "a global bank"), ("data scientist", "an e-commerce company"),
    ("marketing manager", "an FMCG company"), ("entrepreneur", "a D2C brand they co-founded"),
    ("professor", "a university"), ("designer", "a creative agency"), ("civil engineer", "an infrastructure firm"),
]
MALE_NAMES = ["Aarav", "Vivaan", "Aditya", "Arjun", "Reyansh", "Kabir", "Ishaan", "Rahul", "Siddharth", "Nikhil",
              "Varun", "Karthik", "Pranav", "Harsh", "Yash", "Dev", "Kunal", "Manish", "Rajat", "Sameer", "Tushar",
              "Abhishek", "Gaurav", "Akash", "Mohit", "Ankit", "Rohit", "Neeraj", "Imran", "Faisal", "Zaid",
              "Gurpreet", "Harpreet", "Jaspreet", "Joel", "Aaron", "Mihir", "Parth", "Omkar", "Shreyas"]
FEMALE_NAMES = ["Aanya", "Diya", "Ishita", "Riya", "Sanya", "Tanvi", "Nisha", "Pooja", "Neha", "Shreya", "Aditi",
                "Kriti", "Megha", "Divya", "Anjali", "Simran", "Ayesha", "Zara", "Fatima", "Sara", "Mehak", "Jasleen",
                "Ritika", "Pallavi", "Swati", "Nandini", "Lavanya", "Keerthi", "Aishwarya", "Bhavna", "Charu",
                "Gauri", "Isha", "Juhi", "Komal", "Madhuri", "Natasha", "Rhea", "Tara", "Vidya"]
INTEREST_LINES = {
    "travel": ["Has backpacked across the North-East and is planning Georgia next.",
               "Takes at least two trips a year, usually somewhere with mountains."],
    "food": ["Cooks a mean biryani and hosts friends most Sundays.",
             "Always hunting for the next great cafe in town."],
    "fitness": ["Runs half marathons and is usually up by 6.", "Plays badminton three evenings a week."],
    "books": ["Reads a book a week, mostly non-fiction and the odd thriller.", "Part of a monthly book club."],
    "music": ["Plays guitar and never misses a live gig.", "Trained in Hindustani classical as a kid and still sings."],
    "movies": ["Big on world cinema and long post-film discussions.", "Can quote most of Hera Pheri from memory."],
    "outdoors": ["Spends weekends trekking in the Sahyadris.", "Loves camping and stargazing trips."],
    "art": ["Paints watercolours on lazy weekends.", "Does pottery and loves gallery walks."],
    "pets": ["Has a golden retriever named Bruno.", "Fosters rescue cats."],
    "spirituality": ["Meditates daily and visits the temple with family on weekends."],
    "volunteering": ["Teaches kids on weekends with an NGO."],
    "dance": ["Learning salsa and is surprisingly good at it."],
}
VALUES_LINES = ["Close to family and looking for someone grounded.", "Wants a partner who is a best friend first.",
                "Values honesty and a good sense of humour.", "Looking for someone kind, curious and easy to talk to.",
                "Believes in building a life together, one slow Sunday at a time."]

# ----------------------------------------------------------------------------- clients
CLIENTS = [
    dict(id="C01", name="Priya", age=29, gender="F", city="Mumbai", religion="Hindu", community="Marathi",
         diet="non-vegetarian", education="Masters", profession="Brand strategist", interests=["travel", "books", "food"],
         stated_preferences=dict(age_min=29, age_max=36, height_min_cm=168, cities_ok=["Mumbai", "Pune"],
                                 open_to_relocation=False, religion=["Hindu", "Jain"], diet="any", education_min="Bachelors"),
         deal_breakers=dict(smoking=True, drinking=None, wants_children="yes", divorced_ok=True),
         about="I want someone who is kind and grounded, and who actually listens. I love to travel and would like a "
               "partner who's up for spontaneous weekend trips. Books and long conversations over chai matter more to "
               "me than fancy dinners. I'm close to my parents and I'd like someone who respects that."),
    dict(id="C02", name="Rohan", age=32, gender="M", city="Bangalore", religion="Hindu", community="Kannadiga",
         diet="non-vegetarian", education="Masters", profession="Engineering manager", interests=["fitness", "music", "outdoors"],
         stated_preferences=dict(age_min=26, age_max=32, height_min_cm=152, cities_ok=["Bangalore", "Hyderabad", "Chennai"],
                                 open_to_relocation=False, religion="any", diet="any", education_min="Bachelors"),
         deal_breakers=dict(smoking=True, drinking=False, wants_children="open", divorced_ok=True),
         about="I'm looking for a partner, not a co-worker - someone who has a life outside work and enjoys slow "
               "Sundays. I run and trek a lot, so it would be great if she enjoys the outdoors too. Music is a big part "
               "of my life. I'd love someone warm, funny and secure in herself."),
    dict(id="C03", name="Ananya", age=28, gender="F", city="Delhi", religion="Hindu", community="Punjabi",
         diet="non-vegetarian", education="Masters", profession="UX researcher", interests=["movies", "art", "food"],
         stated_preferences=dict(age_min=28, age_max=35, height_min_cm=170, cities_ok=["Delhi", "Gurgaon"],
                                 open_to_relocation=False, religion=["Hindu", "Sikh"], diet="any", education_min="Masters"),
         deal_breakers=dict(smoking=True, drinking=False, wants_children="open", divorced_ok=False),
         about="Honestly I'm not sure what I want, I'll know it when I see it. Someone confident but not arrogant. "
               "Someone who makes me laugh. I like movies, art and good food."),
    dict(id="C04", name="Arjun", age=31, gender="M", city="Mumbai", religion="Hindu", community="Gujarati",
         diet="vegetarian", education="Bachelors", profession="Family business (textiles)", interests=["travel", "movies", "food"],
         stated_preferences=dict(age_min=25, age_max=31, height_min_cm=155, cities_ok=["Mumbai", "Ahmedabad"],
                                 open_to_relocation=False, religion=["Hindu", "Jain"], diet=["vegetarian", "vegan"],
                                 education_min="Bachelors"),
         deal_breakers=dict(smoking=True, drinking=True, wants_children="yes", divorced_ok=True),
         about="I'm a vegetarian foodie and I'd love someone who enjoys cooking together. Family is important to me - "
               "I'm looking for someone who values it too but also has her own opinions. I love travelling and "
               "watching films on weekends."),
    dict(id="C05", name="Kavya", age=30, gender="F", city="Hyderabad", religion="Hindu", community="Telugu",
         diet="non-vegetarian", education="PhD", profession="Cardiologist", interests=["books", "art", "volunteering"],
         stated_preferences=dict(age_min=30, age_max=37, height_min_cm=170, cities_ok=["Hyderabad", "Bangalore", "Chennai"],
                                 open_to_relocation=True, religion="any", diet="any", education_min="Masters"),
         deal_breakers=dict(smoking=True, drinking=False, wants_children="no", divorced_ok=True),
         about="I'm a doctor and my work is demanding, so I need someone who is genuinely supportive of a career "
               "woman. I'm not planning to have children, so please only people who are okay with that. I enjoy "
               "reading, art galleries and weekend volunteering."),
    dict(id="C06", name="Vikram", age=34, gender="M", city="Delhi", religion="Sikh", community="Jat Sikh",
         diet="non-vegetarian", education="Bachelors", profession="Gym owner", interests=["fitness", "music", "dance"],
         stated_preferences=dict(age_min=27, age_max=33, height_min_cm=155, cities_ok=["Delhi", "Gurgaon", "Jaipur"],
                                 open_to_relocation=False, religion=["Sikh", "Hindu"], diet="any", education_min="Bachelors"),
         deal_breakers=dict(smoking=True, drinking=False, wants_children="yes", divorced_ok=True),
         about="Looking for someone with a big laugh and a bigger heart. I'm a fitness person and love bhangra nights "
               "with my friends. Family means everything to me and I want kids someday. Someone independent who still "
               "enjoys a loud family dinner."),
    dict(id="C07", name="Meera", age=27, gender="F", city="Chennai", religion="Hindu", community="Tamil",
         diet="vegetarian", education="Masters", profession="Chartered accountant", interests=["music", "spirituality", "books"],
         stated_preferences=dict(age_min=27, age_max=33, height_min_cm=168, cities_ok=["Chennai", "Bangalore"],
                                 open_to_relocation=False, religion=["Hindu"], diet=["vegetarian", "eggetarian"],
                                 education_min="Masters"),
         deal_breakers=dict(smoking=True, drinking=True, wants_children="yes", divorced_ok=False),
         about="I'm a Carnatic music enthusiast and fairly spiritual. I'd like someone gentle, patient and kind who "
               "respects tradition but is not rigid. A vegetarian household is important to me. I love reading and "
               "quiet evenings."),
    dict(id="C08", name="Aditya", age=33, gender="M", city="Pune", religion="Hindu", community="Marathi",
         diet="non-vegetarian", education="Masters", profession="Product designer", interests=["outdoors", "travel", "pets"],
         stated_preferences=dict(age_min=26, age_max=33, height_min_cm=155, cities_ok=["Pune", "Mumbai"],
                                 open_to_relocation=True, religion="any", diet="any", education_min="Bachelors"),
         deal_breakers=dict(smoking=False, drinking=False, wants_children="open", divorced_ok=True),
         about="I trek almost every weekend in the Sahyadris and have a dog named Biscuit. I want a partner who is "
               "curious, adventurous and down to earth. Someone who loves dogs and would happily come on a road trip "
               "at 5 am."),
    dict(id="C09", name="Sneha", age=31, gender="F", city="Kolkata", religion="Hindu", community="Bengali",
         diet="non-vegetarian", education="Masters", profession="Journalist", interests=["books", "movies", "food", "art"],
         stated_preferences=dict(age_min=31, age_max=38, height_min_cm=170, cities_ok=["Kolkata", "Bangalore", "Mumbai"],
                                 open_to_relocation=False, religion="any", diet="any", education_min="Masters"),
         deal_breakers=dict(smoking=True, drinking=False, wants_children="yes", divorced_ok=True),
         about="Looking for an intellectually curious man who reads and can hold an argument without taking it "
               "personally. I love adda over fish curry, old films and theatre. Kindness and a sense of humour are "
               "non-negotiable."),
    dict(id="C10", name="Karan", age=30, gender="M", city="Gurgaon", religion="Hindu", community="Punjabi",
         diet="non-vegetarian", education="Bachelors", profession="Sales lead", interests=["fitness", "travel", "food"],
         stated_preferences=dict(age_min=25, age_max=30, height_min_cm=158, cities_ok=["Gurgaon", "Delhi"],
                                 open_to_relocation=True, religion=["Hindu", "Sikh"], diet="any", education_min="Bachelors"),
         deal_breakers=dict(smoking=False, drinking=False, wants_children="yes", divorced_ok=False),
         about="I'm an easy-going guy who loves food, travel and cricket. I'd like someone ambitious and fun, who "
               "enjoys trying new places. Family-oriented but not old-fashioned."),
]

# Per-client share plan: (accepted clean, accepted-but-violating, avoidable rejections, other rejections)
PLAN = {"C01": (4, 0, 3, 5), "C02": (4, 1, 2, 5), "C03": (3, 0, 1, 8), "C04": (3, 0, 4, 5), "C05": (4, 0, 3, 5),
        "C06": (3, 1, 3, 5), "C07": (3, 0, 4, 5), "C08": (4, 0, 2, 6), "C09": (3, 1, 3, 5), "C10": (3, 0, 4, 5)}
# Matchmaker labels per share kind -> A: 23 accepted / 52, B: 14 accepted / 68
MM_BY_KIND = {"accept": "A" * 22 + "B" * 12, "accept_fp": "A" + "B" * 2,
              "avoid": "A" * 7 + "B" * 22, "reject": "A" * 22 + "B" * 32}
PASSING_PER_CLIENT = 9
EXTRA_PASSING = {"C04": 7, "C07": 7, "C05": 4}  # strict clients need a bigger compatible pool

TAXONOMY = {
    "age": ("Too old / too young / age gap", ["too old for me", "umar zyada hai", "age gap is too much"]),
    "height": ("Height too short or tall", ["too short", "height kam hai", "I asked for someone taller"]),
    "location_relocation": ("Distance, city, unwilling to relocate", ["too far", "not moving to Pune", "shift nahi karna"]),
    "religion_community": ("Religion, caste, community, kundli", ["different religion", "caste issue", "inter-religion"]),
    "diet": ("Veg / non-veg / vegan / Jain food", ["he's non-veg", "eats meat", "pure veg chahiye"]),
    "education": ("Degree or qualification level", ["only a graduate", "less qualified", "padhai kam hai"]),
    "career_income": ("Job, ambition, income, work-life balance", ["too career-focused", "earns less", "job not stable"]),
    "smoking": ("Smokes cigarettes, vapes, hookah", ["he smokes", "sutta peeta hai", "smoker"]),
    "drinking": ("Drinks alcohol", ["drinks every weekend", "daaru peeta hai", "social drinker"]),
    "children": ("Wants / doesn't want kids", ["doesn't want kids", "bacche nahi chahiye", "wants kids soon"]),
    "marital_status": ("Divorced, widowed, second marriage", ["he's divorced", "second marriage", "divorcee"]),
    "family_values": ("Family set-up, traditional vs modern, in-laws", ["joint family", "mama's boy", "very orthodox"]),
    "personality": ("Temperament, attitude, conversation", ["arrogant", "boring conversation", "akdu hai"]),
    "appearance": ("Looks, photos, style, physical attraction", ["not attractive", "photos look different", "dress sense"]),
    "vague_no_spark": ("No concrete reason given", ["no spark", "not feeling it", "kuch missing hai"]),
    "other": ("Anything that fits no other category", ["timing is bad", "already talking to someone"]),
}

# ----------------------------------------------------------------------------- feedback text
AVOIDABLE_FEEDBACK = {
    "smoking": ["{He} smokes. I clearly mentioned no smokers.", "Smoker hai yaar, I had said no smoking in my form itself",
                "saw a cigarette in {his} pics, thats a straight no. I told you this",
                "Smokes!! This was literally my first condition", "{He}'s a smoker - deal breaker, already mentioned it",
                "sutta peeta hai, nahi chalega. pehle hi bola tha", "Sorry but {he} smokes regularly. Not okay with that at all."],
    "drinking": ["{He} drinks every weekend, I said no alcohol", "daaru peeta hai, I had specifically said no",
                 "Drinks regularly from what I can see. I mentioned this already.",
                 "I don't want someone who drinks, it's in my preferences", "{He}'s a drinker, not for me. Please check my prefs."],
    "children_yes": ["{He} doesn't want kids, that's non-negotiable for me",
                     "Kids nahi chahiye usko? I definitely want children, mentioned it",
                     "Not wanting children is a deal breaker, I said this"],
    "children_no": ["{He} wants kids soon, I've said I don't want children",
                    "I told you I'm not planning to have kids. {He} clearly wants a family with children soon.",
                    "bacche chahiye usko, I said no kids for me"],
    "marital_status": ["{He}'s divorced, I said I'm not comfortable with that",
                       "Second marriage - I mentioned I'm not open to divorcees", "divorcee hai, maine pehle hi bola tha",
                       "Previously married, which I had said is a no for me"],
    "location": ["Too far, I'm not moving to {city}", "{city}?? I said {cities} only",
                 "Long distance won't work and {he} won't relocate", "Not willing to shift to {city}, mentioned this clearly",
                 "{city} mein settle nahi hona mujhe, and {he} won't move",
                 "distance is a problem, {he} is not open to relocating either"],
    "religion": ["Different religion, I mentioned I want someone {religion_pref}",
                 "{He}'s {p_religion}, I said this upfront, my family won't agree",
                 "Religion mismatch. Was in my preferences.", "Inter-religion is not something I'm open to, sorry"],
    "diet": ["{He}'s non-veg, I need a vegetarian partner, said so", "Eats meat, I'm pure veg. Mentioned clearly",
             "non vegitarian, nahi chalega", "Diet mismatch, I asked for veg only"],
    "age_old": ["Too old for me, {age} is outside my range", "{He} is {age}, I said max {age_max}",
                "Age gap is too much", "umar zyada hai, {age} is a lot"],
    "age_young": ["too young yaar, I said {age_min}+", "{He}'s only {age}, I asked for {age_min} and above",
                  "Bit too young for me, I had mentioned the range"],
    "height": ["{He}'s too short, I said {hmin} cm minimum", "Height is less than what I asked for",
               "kaafi chhota hai height mein", "{feet}? I asked for someone taller"],
    "education": ["Only {edu}, I wanted at least {edu_min}", "Education is lower than what I mentioned",
                  "Not enough qualification, I said {edu_min} minimum", "padhai kam hai, I wanted {edu_min} at least"],
}
TAILS = [" Also no spark tbh.", " Also felt a bit off on the call.", "", "", "", ""]
CLEAN_FEEDBACK = {
    "personality": ["Came across as arrogant on the call", "Too much attitude", "Seemed very full of {himself}",
                    "{He} was rude to the waiter apparently, red flag", "Boring conversation, very dry",
                    "Too loud and show-offy for me", "Felt very immature", "short tempered from what I heard",
                    "Bahut akdu hai", "nakhre bahut hai", "Doesn't smoke which is good, but conversation was so dry",
                    "Talks only about {himself}, zero curiosity about me"],
    "appearance": ["Not attractive to me honestly", "Photos look very different from real life",
                   "Dress sense not my thing", "Physically not my type", "dikhne mein theek nahi laga"],
    "family_values": ["Joint family, I want to live nuclear", "Too dependent on {his} parents for every decision",
                      "Family seems very orthodox", "ghar wale bahut strict lage", "Very traditional outlook, not my wavelength"],
    "vague": ["no spark", "Just not feeling it", "Not my type", "something felt off", "didn't click", "meh",
              "No chemistry", "pata nahi, kuch missing hai", "Feel nahi aaya", "Can't explain, just no", "not for me",
              "nahi jama", "vibe nahi aayi", "hmm not sure about this one, pass", "Nothing wrong exactly, just no connection",
              "doesnt drink, decent person, but no spark", "Idk, something about {him} didnt feel right", "not feelin it"],
    "mixed": ["Nice person but no spark, also bit arrogant", "Too serious and honestly no chemistry",
              "Good on paper. Family seemed very conservative and vibe nahi aayi", "Looks fine but conversation was boring"],
}
CLEAN_WEIGHTS = {"personality": 30, "appearance": 15, "family_values": 15, "vague": 28, "mixed": 12}
PRIYA_DRINKING = ["He drinks quite a lot going by his insta, not comfortable with that",
                  "Daaru party wala lagta hai, every weekend out drinking. Nahi yaar."]
ROHAN_CAREER = "Too career-focused, she'd have no time for a relationship. Works 80 hour weeks."
ANANYA_CONCRETE = "Came across as arrogant, too much attitude"


def pronouns(gender: str) -> dict:
    if gender == "M":
        return dict(he="he", He="He", his="his", him="him", himself="himself")
    return dict(he="she", He="She", his="her", him="her", himself="herself")


# ----------------------------------------------------------------------------- profiles
def weighted(choices: dict) -> str:
    return rng.choices(list(choices), weights=list(choices.values()))[0]


def random_profile(gender: str) -> dict:
    religion = weighted(RELIGION_WEIGHTS)
    diet = "vegetarian" if religion == "Jain" and rng.random() < 0.85 else weighted(
        {"vegetarian": 32, "non-vegetarian": 52, "eggetarian": 12, "vegan": 4})
    prof, company = rng.choice(PROFESSIONS)
    if gender == "M":
        age = int(min(40, max(25, round(rng.gauss(31, 3.6)))))
        height = int(min(192, max(158, round(rng.gauss(175, 6.5)))))
    else:
        age = int(min(37, max(23, round(rng.gauss(29, 3.2)))))
        height = int(min(178, max(148, round(rng.gauss(161, 6)))))
    return dict(
        gender=gender, age=age, height_cm=height, city=rng.choice(CITIES), open_to_relocation=rng.random() < 0.55,
        religion=religion, community=rng.choice(COMMUNITIES[religion]), diet=diet,
        education=weighted({"Diploma": 6, "Bachelors": 44, "Masters": 42, "PhD": 8}),
        profession=prof, company=company, seniority=weighted({"junior": 30, "mid": 45, "senior": 25}),
        smokes=rng.random() < 0.15, drinks=weighted({"never": 45, "socially": 45, "regularly": 10}),
        wants_children=weighted({"yes": 65, "open": 25, "no": 10}),
        marital_status=weighted({"never_married": 86, "divorced": 11, "widowed": 3}),
        interests=rng.sample(list(INTEREST_LINES), 3),
    )


def make_compatible(c: Client, p: dict) -> dict:
    """Repair a random profile so it passes every stated rule of client c."""
    sp, db = c.stated_preferences, c.deal_breakers
    p["gender"] = c.seeking
    p["age"] = rng.randint(sp.age_min, sp.age_max)
    p["height_cm"] = max(p["height_cm"], sp.height_min_cm + rng.randint(0, 9))
    if p["city"] not in sp.cities_ok and not sp.open_to_relocation and not p["open_to_relocation"]:
        p["city"] = rng.choice(sp.cities_ok)
    if sp.religion != "any" and p["religion"] not in sp.religion:
        p["religion"] = rng.choice(sp.religion)
        p["community"] = c.community if (p["religion"] == c.religion and rng.random() < 0.5) else rng.choice(COMMUNITIES[p["religion"]])
    if sp.diet != "any" and p["diet"] not in sp.diet:
        p["diet"] = rng.choice(sp.diet)
    if education_rank(p["education"]) < education_rank(sp.education_min):
        p["education"] = sp.education_min
    if db.smoking:
        p["smokes"] = False
    if db.drinking:
        p["drinks"] = "never"
    if db.wants_children != "open" and p["wants_children"] not in (db.wants_children, "open"):
        p["wants_children"] = db.wants_children
    if not db.divorced_ok and p["marital_status"] == "divorced":
        p["marital_status"] = "never_married"
    return p


def break_rule(c: Client, p: dict, rule: str) -> dict:
    """Make p violate exactly `rule` for client c (p must already be compatible)."""
    sp, db = c.stated_preferences, c.deal_breakers
    if rule == "smoking":
        p["smokes"] = True
    elif rule == "drinking":
        p["drinks"] = rng.choice(["socially", "regularly"])
    elif rule == "children":
        p["wants_children"] = "no" if db.wants_children == "yes" else "yes"
    elif rule == "marital_status":
        p["marital_status"] = "divorced"
    elif rule == "location":
        p["city"] = rng.choice([x for x in CITIES if x not in sp.cities_ok])
        p["open_to_relocation"] = False
    elif rule == "religion":
        p["religion"] = rng.choice([r for r in COMMUNITIES if r not in sp.religion])
        p["community"] = rng.choice(COMMUNITIES[p["religion"]])
        if sp.diet != "any":
            p["diet"] = rng.choice(sp.diet)
    elif rule == "diet":
        p["diet"] = "non-vegetarian"
    elif rule == "age":
        p["age"] = sp.age_max + rng.randint(3, 6) if rng.random() < 0.6 or sp.age_min < 26 else sp.age_min - rng.randint(2, 3)
    elif rule == "height":
        p["height_cm"] = sp.height_min_cm - rng.randint(3, 9)
    elif rule == "education":
        p["education"] = EDUCATION_LEVELS[education_rank(sp.education_min) - 1]
    return p


def available_rules(c: Client) -> list:
    sp, db = c.stated_preferences, c.deal_breakers
    rules = ["age", "height", "education"]
    if db.smoking:
        rules += ["smoking", "smoking"]  # the most common avoidable reason in practice
    if db.drinking:
        rules.append("drinking")
    if db.wants_children != "open":
        rules.append("children")
    if not db.divorced_ok:
        rules.append("marital_status")
    if not sp.open_to_relocation:
        rules += ["location", "location"]
    if sp.religion != "any":
        rules.append("religion")
    if sp.diet != "any":
        rules.append("diet")
    if sp.education_min == "Bachelors":
        rules.remove("education")  # only "Diploma" is below; keep it rare
    return rules


def bio_for(p: dict) -> str:
    title = ("Senior " + p["profession"]) if p["seniority"] == "senior" else p["profession"].capitalize()
    lines = [f"{title} at {p['company']} in {p['city']}."]
    lines.append(rng.choice(INTEREST_LINES[p["interests"][0]]))
    lines.append(rng.choice(INTEREST_LINES[p["interests"][1]]) if rng.random() < 0.5 else rng.choice(VALUES_LINES))
    return " ".join(lines)


def main() -> None:
    clients = [Client(**c) for c in CLIENTS]
    by_id = {c.id: c for c in clients}
    raw_profiles = []  # list of (dict, tag) where tag says what it was built for
    names = {"M": rng.sample(MALE_NAMES, len(MALE_NAMES)), "F": rng.sample(FEMALE_NAMES, len(FEMALE_NAMES))}

    planned_violations = {}  # client id -> list of (profile index, rule)
    fp_profiles = {}
    for c in clients:
        acc, fp, avoid, rej = PLAN[c.id]
        for i in range(PASSING_PER_CLIENT + EXTRA_PASSING.get(c.id, 0)):
            p = make_compatible(c, random_profile(c.seeking))
            if c.name == "Priya":  # two drinkers she will reject; everyone else she sees is a non-drinker
                p["drinks"] = ["regularly", "socially"][i] if i < 2 else "never"
            if c.name == "Rohan" and i < 2:  # two near-identical high-flying consultants
                p.update(profession="management consultant", company="a strategy consulting firm", seniority="senior")
            raw_profiles.append((p, f"pass:{c.id}:{i}"))
        rules = available_rules(c)
        rng.shuffle(rules)
        chosen = []
        for r in rules:
            if r not in chosen:
                chosen.append(r)
        while len(chosen) < avoid:
            chosen.append(rng.choice(rules))
        for r in chosen[:avoid]:
            p = break_rule(c, make_compatible(c, random_profile(c.seeking)), r)
            planned_violations.setdefault(c.id, []).append((len(raw_profiles), r))
            raw_profiles.append((p, f"avoid:{c.id}:{r}"))
        for _ in range(fp):
            p = make_compatible(c, random_profile(c.seeking))
            p["age"] = c.stated_preferences.age_max + 1
            fp_profiles[c.id] = len(raw_profiles)
            raw_profiles.append((p, f"fp:{c.id}"))

    for g in ("M", "F"):
        while sum(1 for p, _ in raw_profiles if p["gender"] == g) < 100:
            raw_profiles.append((random_profile(g), "random"))

    order = list(range(len(raw_profiles)))
    rng.shuffle(order)  # so profile ids don't reveal how they were built
    profiles, idx_to_pid = [], {}
    for n, i in enumerate(order, start=1):
        p, _ = raw_profiles[i]
        # Rohan's consultants get a work-heavy bio so the "career-focused" reaction is believable
        name = names[p["gender"]][n % len(names[p["gender"]])] + " " + rng.choice("ABCDGJKMNPRSTV") + "."
        if p["profession"] == "management consultant" and p["seniority"] == "senior" and p["gender"] == "F":
            bio = (f"Senior management consultant at a strategy consulting firm in {p['city']}. Works long hours and is "
                   f"aiming for partner in three years. {rng.choice(INTEREST_LINES[p['interests'][0]])}")
        else:
            bio = bio_for(p)
        rec = {k: v for k, v in p.items() if k != "company"}
        profiles.append(Profile(id=f"P{n:03d}", name=name, bio=bio, **rec))
        idx_to_pid[i] = f"P{n:03d}"
    prof_by_id = {p.id: p for p in profiles}

    # ------------------------------------------------------------------ build share slots
    slots = []  # dicts: client_id, kind, profile_id, feedback
    for c in clients:
        acc, fp, avoid, rej = PLAN[c.id]
        passing = [p for p in profiles if not violations(c, p)]
        used = set()

        def pick(pred):
            cands = [p for p in passing if p.id not in used and pred(p)]
            p = rng.choice(cands)
            used.add(p.id)
            return p

        pr = pronouns(c.seeking)
        is_mc = lambda p: p.profession == "management consultant" and p.seniority == "senior"  # noqa: E731

        # Special seeded cases first
        special_rejects = []
        if c.name == "Priya":
            drinkers = sorted([p for p in passing if p.drinks != "never"], key=lambda p: p.id)[:2]
            for p, text in zip(drinkers, PRIYA_DRINKING):
                used.add(p.id)
                special_rejects.append((p, text))
        if c.name == "Rohan":
            mcs = sorted([p for p in passing if is_mc(p)], key=lambda p: p.id)[:2]
            used.update(p.id for p in mcs)
            special_rejects.append((mcs[0], ROHAN_CAREER))
            slots.append(dict(client_id=c.id, kind="accept", profile_id=mcs[1].id, feedback="", tag="rohan_similar"))
            acc -= 1

        for _ in range(acc):
            p = pick(lambda p: (c.name != "Priya" or p.drinks == "never") and not (c.name == "Rohan" and is_mc(p)))
            slots.append(dict(client_id=c.id, kind="accept", profile_id=p.id, feedback=""))
        if c.id in fp_profiles:
            slots.append(dict(client_id=c.id, kind="accept_fp", profile_id=idx_to_pid[fp_profiles[c.id]], feedback=""))

        sp = c.stated_preferences
        for raw_idx, rule in planned_violations.get(c.id, []):
            p = prof_by_id[idx_to_pid[raw_idx]]
            key = rule
            if rule == "children":
                key = "children_" + c.deal_breakers.wants_children
            if rule == "age":
                key = "age_old" if p.age > sp.age_max else "age_young"
            feet = f"{p.height_cm // 30.48:.0f}'{round((p.height_cm / 2.54) % 12):.0f}\""
            text = rng.choice(AVOIDABLE_FEEDBACK[key]).format(
                **pr, city=p.city, cities=" or ".join(sp.cities_ok), religion_pref=" or ".join(sp.religion) if sp.religion != "any" else "",
                p_religion=p.religion, age=p.age, age_max=sp.age_max, age_min=sp.age_min, hmin=sp.height_min_cm,
                feet=feet, edu=p.education, edu_min=sp.education_min)
            tail = rng.choice(TAILS)
            if tail and text[-1] not in ".!?":
                text += "."
            text += tail
            slots.append(dict(client_id=c.id, kind="avoid", profile_id=p.id, feedback=text))

        for p, text in special_rejects:
            slots.append(dict(client_id=c.id, kind="reject", profile_id=p.id, feedback=text,
                              tag="rohan_career" if c.name == "Rohan" else "priya_drink"))
        n_clean = rej - len(special_rejects)
        if c.name == "Ananya":
            texts = rng.sample(CLEAN_FEEDBACK["vague"], n_clean - 1) + [ANANYA_CONCRETE]
        else:
            texts, seen = [], set()
            vague_budget = 2  # keep everyone else well below the 60% vague threshold
            while len(texts) < n_clean:
                kind = weighted(CLEAN_WEIGHTS)
                if kind == "vague":
                    if vague_budget == 0:
                        continue
                    vague_budget -= 1
                t = rng.choice(CLEAN_FEEDBACK[kind])
                if t in seen:
                    continue
                seen.add(t)
                texts.append(t)
        for t in texts:
            p = pick(lambda p: not (c.name == "Rohan" and is_mc(p)))
            slots.append(dict(client_id=c.id, kind="reject", profile_id=p.id, feedback=t.format(**pr)))

    assert len(slots) == 120, len(slots)

    # ------------------------------------------------------------------ matchmakers + dates
    for kind, labels in MM_BY_KIND.items():
        labels = list(labels)
        rng.shuffle(labels)
        ks = [s for s in slots if s["kind"] == kind]
        assert len(ks) == len(labels), (kind, len(ks), len(labels))
        for s, mm in zip(ks, labels):
            s["matchmaker"] = mm
    rng.shuffle(slots)
    start = date(2026, 9, 1)
    days = sorted(rng.randint(0, 29) for _ in slots)
    for s, d in zip(slots, days):
        s["date"] = (start + timedelta(days=d)).isoformat()
    # Rohan: the career-focused rejection must come before the similar acceptance
    rc = next(s for s in slots if s.get("tag") == "rohan_career")
    ra = next(s for s in slots if s.get("tag") == "rohan_similar")
    if rc["date"] >= ra["date"]:
        rc["date"], ra["date"] = ra["date"], rc["date"]
        if rc["date"] == ra["date"]:
            ra["date"] = (date.fromisoformat(ra["date"]) + timedelta(days=1)).isoformat()
    slots.sort(key=lambda s: (s["date"], s["client_id"]))

    rows = []
    for n, s in enumerate(slots, start=1):
        rows.append(dict(share_id=f"S{n:03d}", date=s["date"], client_id=s["client_id"], profile_id=s["profile_id"],
                         matchmaker=s["matchmaker"],
                         outcome="accepted" if s["kind"].startswith("accept") else "rejected",
                         feedback_text=s["feedback"]))

    # ------------------------------------------------------------------ write
    DATA.mkdir(exist_ok=True)
    (DATA / "clients.json").write_text(json.dumps([c.model_dump() for c in clients], indent=2))
    (DATA / "profiles.json").write_text(json.dumps([p.model_dump() for p in profiles], indent=2))
    with open(DATA / "share_history.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (DATA / "reason_taxonomy.json").write_text(json.dumps(
        {k: {"description": d, "examples": ex} for k, (d, ex) in TAXONOMY.items()}, indent=2))
    (DATA / "learned_preferences.json").write_text(json.dumps({"confirmed": {}, "dismissed": {}}, indent=2))

    # ------------------------------------------------------------------ sanity report
    acc = [r for r in rows if r["outcome"] == "accepted"]
    rej = [r for r in rows if r["outcome"] == "rejected"]
    avoidable = [r for r in rej if violations(by_id[r["client_id"]], prof_by_id[r["profile_id"]])]
    print(f"clients={len(clients)} profiles={len(profiles)} shares={len(rows)}")
    print(f"acceptance overall {len(acc)}/{len(rows)} = {len(acc)/len(rows):.1%}")
    for mm in "AB":
        n = [r for r in rows if r["matchmaker"] == mm]
        a = [r for r in n if r["outcome"] == "accepted"]
        print(f"  matchmaker {mm}: {len(a)}/{len(n)} = {len(a)/len(n):.1%}")
    print(f"avoidable rejections {len(avoidable)}/{len(rej)} = {len(avoidable)/len(rej):.1%}")
    for c in clients:
        print(f"  {c.name:7s} passing pool: {sum(1 for p in profiles if not violations(c, p))}")


if __name__ == "__main__":
    main()
