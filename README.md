# MatchGuard

A working prototype for The Date Crew's matchmakers. It catches preference violations **before** a profile is
sent, turns free-text rejection feedback into structured reasons, learns new deal-breakers from repeated
rejections, and shows how many past rejections would have been avoided.

- **Runs fully offline.** The keyword tagger and the template pitch drafter are the main path. An LLM
  (Claude or Gemini) is an optional add-on.
- **No emails are ever sent.** Drafts are only shown for copying.
- **All data is mock data** made by a seeded generator. No real people are involved.

## What it demonstrates

| Tab | What it shows |
|---|---|
| 1 · Shortlist | Hard filter on stated preferences, deal-breakers and confirmed learned deal-breakers ("X of 200 excluded" with a breakdown). Top 15 by soft fit, each with a one-line "why this fits". |
| 2 · Pre-Send Check | Re-checks the send list. Each profile shows **PASS** or **BLOCKED** with the exact rule broken. A blocked profile needs an override reason (15+ characters), which is logged to `data/override_log.csv`. An optional pitch drafter writes a 2-line note in the client's own words. |
| 3 · Feedback Tagger & Learning | Tags feedback into a fixed taxonomy, with a confidence and the exact phrase that triggered each tag. Shows learned deal-breaker suggestions (confirm / dismiss), reversal warnings and vague-rejection flags. |
| 4 · Impact Dashboard | Funnel by matchmaker, the avoidable-rejection rate (computed from the data rules, not from tags), the "if MatchGuard had been used" simulation **including false positives**, and learning signals. |

### The offline tagger (`core/tagger.py`)
- **Synonyms:** sutta, beedi, vape, hookah → smoking; whisky, pegs, booze → drinking; mama's boy → family values.
- **Hinglish:** "daaru peeta hai", "umar zyada hai", "padhai kam hai", "vibe nahi aayi", "kuch missing hai", "ghar wale strict".
- **Typos:** regex variants plus 1-edit fuzzy matching on longer words ("smokr", "vegitarian", "arrogent", "relocte", "divorsed"). The fuzzy matcher won't turn "spoke" into "smoke".
- **Negation:** "doesn't smoke", "non-smoker", "never drinks or smokes", "daaru nahi peeta" and "quit smoking" are **not** tagged.
- **Acceptance:** "I don't mind that he drinks" and "looks fine" are not tagged, but "not okay with that" still is.
- **Mixed reasons:** text is split into clauses ("but", "lekin", "par", punctuation). Weak cues such as "pics" are dropped when a clear reason sits in the same clause.
- **Output:** every tag carries a confidence and evidence (the exact substring), plus `is_vague` and `sentiment` (mild/strong).

With an API key, the LLM gets the feedback and the taxonomy and must return strict JSON
(`{"tags": [{"category", "confidence", "evidence"}], "is_vague", "sentiment"}`). The JSON is validated with
pydantic. If parsing fails, it retries once and then falls back to the keyword tagger. Network or auth errors
fall back immediately.

## How to run

```bash
cd matchguard
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_mock_data.py     # writes data/*.json, data/share_history.csv
streamlit run app.py
```

Run the tests with `pytest`. There are 66 of them: filters, learning, metrics, tagger robustness, and a headless
walk through the whole demo script below.

Python 3.11 is the target. The code also runs on 3.9+ (it was built and tested on 3.9.6).

## Adding an API key (optional)

```bash
cp .env.example .env
# set ANTHROPIC_API_KEY=...  (then: pip install anthropic)
# or  GEMINI_API_KEY=...     (then: pip install google-genai)
```

The sidebar shows which mode is active. Without a key, or if the SDK is missing, the app shows
**"Running in offline mode (keyword tagger)"** and everything still works. Claude calls use
`claude-opus-5-5` at low effort with structured JSON output and server-side refusal fallback enabled. A
refusal or any API error falls back to the keyword tagger. Set `ANTHROPIC_MODEL` / `GEMINI_MODEL` to change
the model.

## Mock data (fixed seed 42)

- 10 clients, 200 profiles, and 120 shares over September 2026.
- Overall acceptance is 30.8%: matchmaker A 44.2% (23/52), matchmaker B 20.6% (14/68).
- **34.9%** of rejections (29/83) break a stated preference or deal-breaker. Their feedback says so
  naturally ("He smokes. I clearly mentioned no smokers.").
- Three accepted profiles also break a stated rule (age just outside the range). These are the honest false
  positives in the simulation.
- Seeded demo cases:
  - **Priya** has no stated drinking rule but rejected 2 drinkers for drinking.
  - **Rohan** rejected a senior management consultant as "too career-focused", then accepted another one 4 days later.
  - **Ananya** has 7 of 9 rejections that are vague.

Re-running the generator also resets `data/learned_preferences.json`.

## 2-minute demo script

1. **Tab 4 · Impact Dashboard.** "34.9% of rejections broke something the client had already told us."
   Under *If MatchGuard had been used*: 29 rejected profiles would have been blocked, and projected acceptance
   goes from 30.8% to 38.6%. Point out that **3 accepted profiles would also have been blocked**. These are
   shown on purpose: hard rules have a cost, which is why overrides exist.
2. **Tab 1 · Shortlist** (Priya is selected in the sidebar). Show "N of 200 excluded", open *Why profiles were
   excluded*, then walk through the top 15 and their "why this fits" lines. Tick a couple of profiles.
3. **Tab 2 · Pre-Send Check.** In *Add a profile found outside the shortlist*, pick an entry ending in
   "⚠ Smokes" and click **Add**. It shows **BLOCKED**: "Smokes - client deal-breaker". Type an override reason
   (15+ characters) and click **Log override**; the line appears in `data/override_log.csv`. Click **Draft
   pitches for PASS profiles**, edit a draft, and click **Regenerate** to get another phrasing.
4. **Tab 3 · Feedback Tagger & Learning.** Optionally paste "doesnt drink, decent guy, but too far - not
   moving to Pune" to show negation (no drinking tag) plus location. Click **Tag all historical feedback**.
   The card reads *"Priya has rejected 2 profiles for drinking. Ask Priya: is this a new deal-breaker?"*. Click
   **Client confirmed**, go back to **Tab 1**: the excluded count rises, and the breakdown shows
   "Drinks (learned)". No drinkers remain in the top 15.
5. **Tab 3** again. The reversal guard says *"Rohan rejected 'career-focused / income' but accepted a similar
   profile on 2026-09-15. Do not auto-filter; discuss with client."* (there's no auto-add button). The vague
   flag says *"Ananya's rejections are mostly vague (7 of 9, 78%). Consider a coaching conversation before
   sending more profiles."*

Use **Reset learned deal-breakers** in the sidebar to run the demo again.

## Project layout

```
app.py                      Streamlit UI (tabs, session state) - no business logic
core/models.py              pydantic: Client, Profile, ShareRecord, TaggedReason, Violation
core/filters.py             hard filter, exclusion breakdown, soft-fit score + explanation
core/tagger.py              keyword tagger (primary) + LLM JSON path with retry/fallback
core/learning.py            learned deal-breakers, reversal guard, vague flags, persistence
core/metrics.py             funnel, avoidable rejections, simulation
core/pitch.py               template pitch drafter (+ optional LLM)
core/llm.py                 optional provider wrapper (Claude / Gemini), lazy imports
core/data.py                loaders
scripts/generate_mock_data.py
tests/                      pytest
```

### Design notes
- **Learnable categories:** smoking, drinking, children, marital status, diet, and religion. These are
  traits the filter can enforce. A category only becomes a suggestion if the client hasn't already stated
  it, the rejected profiles actually have the trait, and there is no reversal for it.
- **Reversal guard:** a rejection reason is flagged when the same client accepted a profile with the same
  trait (same profession and seniority, same habit, and so on), either before or after the rejection.
- **Vague flag:** shown when more than 60% of a client's tagged rejections have no concrete reason (minimum
  3 rejections).
