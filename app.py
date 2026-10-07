"""MatchGuard - Streamlit prototype. Run: streamlit run app.py

All matching / learning logic lives in core/ (pure functions). This file is only UI + session state.
No emails are ever sent; all data is mock data.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core import llm
from core.data import DATA_DIR, load_clients, load_profiles, load_shares, load_taxonomy
from core.filters import ENFORCEABLE_LEARNED, RULE_LABELS, exclusion_breakdown, hard_filter, shortlist, violations
from core.learning import (CATEGORY_LABELS, describe_trait, learned_suggestions, load_learned, reversal_flags,
                           save_learned, vague_flags)
from core.metrics import avoidable_rejections, funnel, simulate
from core.pitch import draft_pitch
from core.tagger import keyword_tag, tag_feedback

LEARNED_PATH = DATA_DIR / "learned_preferences.json"
OVERRIDE_LOG = DATA_DIR / "override_log.csv"
MIN_OVERRIDE_CHARS = 15

st.set_page_config(page_title="MatchGuard", layout="wide")


# ----------------------------------------------------------------------------- data + state
@st.cache_data
def _load():
    return load_clients(), load_profiles(), load_shares(), load_taxonomy()


if not (DATA_DIR / "clients.json").exists():
    st.error("No mock data found. Run `python scripts/generate_mock_data.py` first.")
    st.stop()

CLIENTS, PROFILES, SHARES, TAXONOMY = _load()
CMAP = {c.id: c for c in CLIENTS}
PMAP = {p.id: p for p in PROFILES}

ss = st.session_state
ss.setdefault("learned", load_learned(LEARNED_PATH))
ss.setdefault("send_list", {})  # client_id -> [profile_id]
ss.setdefault("tagged", {})  # share_id -> TaggedReason
ss.setdefault("tag_warnings", [])
ss.setdefault("pitches", {})  # "cid|pid" -> text
ss.setdefault("pitch_source", {})
ss.setdefault("pitch_variant", {})
ss.setdefault("overrides", {})  # "cid|pid" -> reason


def learned_for(cid: str) -> list:
    return ss.learned["confirmed"].get(cid, [])


def persist_learned():
    save_learned(LEARNED_PATH, ss.learned)


def toggle_send(cid: str, pid: str):
    lst = ss.send_list.setdefault(cid, [])
    if ss.get(f"chk_{cid}_{pid}"):
        if pid not in lst:
            lst.append(pid)
    elif pid in lst:
        lst.remove(pid)


def forget_widgets(prefix: str):
    for k in [k for k in ss.keys() if str(k).startswith(prefix)]:
        del ss[k]


def profile_line(p) -> str:
    return f"{p.name} - {p.age}, {p.height_cm} cm, {p.city}, {p.profession} ({p.seniority})"


def fmt_pct(x: float) -> str:
    return f"{x:.0%}" if abs(x * 100 - round(x * 100)) < 1e-9 else f"{x:.1%}"


# ----------------------------------------------------------------------------- sidebar
st.sidebar.title("MatchGuard")
status = llm.status_message()
if llm.provider() is None:
    st.sidebar.warning(status)
else:
    st.sidebar.success(status)

client_names = {c.name: c.id for c in CLIENTS}
sel_name = st.sidebar.selectbox("Client", list(client_names), index=0)
CLIENT = CMAP[client_names[sel_name]]

st.sidebar.divider()
st.sidebar.caption("Demo controls")
if st.sidebar.button("Reset learned deal-breakers"):
    ss.learned = {"confirmed": {}, "dismissed": {}}
    persist_learned()
    st.rerun()
if st.sidebar.button("Clear all send lists"):
    ss.send_list, ss.pitches, ss.overrides = {}, {}, {}
    forget_widgets("chk_")
    forget_widgets("pitch_C")
    st.rerun()
st.sidebar.caption("No emails are ever sent. All people here are fictional.")

if llm.provider() is None:
    st.info("Running in offline mode (keyword tagger). Add an API key to `.env` to enable the optional LLM.", icon="ℹ️")

tab1, tab2, tab3, tab4 = st.tabs(["1 · Shortlist", "2 · Pre-Send Check", "3 · Feedback Tagger & Learning",
                                  "4 · Impact Dashboard"])


# ============================================================================= TAB 1
def client_card(c):
    sp, db = c.stated_preferences, c.deal_breakers
    left, right = st.columns(2)
    with left:
        st.markdown(f"**{c.name}**, {c.age}, {c.city} · {c.religion} ({c.community}) · {c.diet} · "
                    f"{c.education} · {c.profession}")
        st.markdown(
            f"- Age **{sp.age_min}-{sp.age_max}**, height **≥ {sp.height_min_cm} cm**\n"
            f"- Cities: **{', '.join(sp.cities_ok)}** · client open to relocating: **{'yes' if sp.open_to_relocation else 'no'}**\n"
            f"- Religion: **{sp.religion if sp.religion == 'any' else ', '.join(sp.religion)}** · "
            f"Diet: **{sp.diet if sp.diet == 'any' else ', '.join(sp.diet)}** · Education ≥ **{sp.education_min}**")
    with right:
        drinking = {True: "deal-breaker", False: "fine", None: "never discussed"}[db.drinking]
        st.markdown(
            "**Deal-breakers**\n"
            f"- Smoking: **{'deal-breaker' if db.smoking else 'fine'}** · Drinking: **{drinking}**\n"
            f"- Wants children: **{db.wants_children}** · Divorced OK: **{'yes' if db.divorced_ok else 'no'}**")
        lr = learned_for(c.id)
        if lr:
            st.markdown("**Learned (client confirmed):** " + ", ".join(
                f":orange[{CATEGORY_LABELS[x]}]" + ("" if x in ENFORCEABLE_LEARNED else " (note only)") for x in lr))
    with st.expander(f"{c.name} in their own words"):
        st.write(f"_{c.about}_")


with tab1:
    st.subheader(f"Shortlist for {CLIENT.name}")
    client_card(CLIENT)
    passing, excluded = hard_filter(CLIENT, PROFILES, learned_for(CLIENT.id))
    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Profiles excluded", f"{len(excluded)} of {len(PROFILES)}")
    m2.metric("Pass every rule", len(passing))
    m3.metric("On send list", len(ss.send_list.get(CLIENT.id, [])))

    with st.expander("Why profiles were excluded", expanded=False):
        bd = exclusion_breakdown(excluded)
        bdf = pd.DataFrame([{"Rule": RULE_LABELS.get(k.replace(" (learned)", ""), k) + (" (learned)" if "learned" in k else ""),
                             "Profiles": v} for k, v in bd.most_common()])
        st.caption("A profile can break several rules, so counts add up to more than the total excluded. "
                   "'Gender' = profiles of the gender the client isn't seeking.")
        c1, c2 = st.columns([3, 2])
        c1.bar_chart(bdf.set_index("Rule"), horizontal=True, height=320)
        c2.dataframe(bdf, hide_index=True, width="stretch")
        ex_rows = [{"ID": pid, "Profile": profile_line(PMAP[pid]),
                    "Violations": "; ".join(v.message for v in vs if v.rule != "gender")}
                   for pid, vs in excluded.items() if any(v.rule != "gender" for v in vs)]
        st.markdown(f"**Excluded {CLIENT.seeking == 'M' and 'men' or 'women'}** ({len(ex_rows)})")
        st.dataframe(pd.DataFrame(ex_rows), hide_index=True, width="stretch")

    st.markdown("#### Top 15 by soft fit")
    hdr = st.columns([0.6, 3.6, 0.8, 4.4, 1.2])
    for col, h in zip(hdr, ["ID", "Profile", "Fit", "Why this fits", "Send"]):
        col.caption(h)
    for p, score, why in shortlist(CLIENT, PROFILES, learned_for(CLIENT.id)):
        row = st.columns([0.6, 3.6, 0.8, 4.4, 1.2])
        row[0].write(p.id)
        row[1].write(profile_line(p))
        row[2].write(f"**{score}**")
        row[3].write(why)
        ck = f"chk_{CLIENT.id}_{p.id}"
        if ck not in ss:
            ss[ck] = p.id in ss.send_list.get(CLIENT.id, [])
        row[4].checkbox("Add to send list", key=ck, on_change=toggle_send, args=(CLIENT.id, p.id))


# ============================================================================= TAB 2
def log_override(c, p, rules, reason):
    new = not OVERRIDE_LOG.exists()
    with open(OVERRIDE_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "client_id", "client_name", "profile_id", "profile_name", "rule", "reason"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), c.id, c.name, p.id, p.name, rules, reason])


with tab2:
    st.subheader(f"Pre-send check for {CLIENT.name}")
    st.caption("Every profile is re-checked against stated preferences, deal-breakers and confirmed learned "
               "deal-breakers right before sending. Nothing is sent from here.")

    seek = [p for p in PROFILES if p.gender == CLIENT.seeking and p.id not in ss.send_list.get(CLIENT.id, [])]

    def label(pid):
        p = PMAP[pid]
        flags = [v.message.split(" - ")[0] for v in violations(CLIENT, p, learned_for(CLIENT.id))]
        habits = ", ".join(x for x in ["smokes" if p.smokes else "", f"drinks {p.drinks}" if p.drinks != "never" else "",
                                       p.marital_status.replace("_", " ") if p.marital_status != "never_married" else ""] if x)
        return f"{pid} · {profile_line(p)}" + (f" · {habits}" if habits else "") + (" · ⚠ " + "; ".join(flags) if flags else "")

    a1, a2 = st.columns([5, 1])
    choice = a1.selectbox("Add a profile found outside the shortlist (e.g. a referral)",
                          ["Choose a profile..."] + [label(p.id) for p in seek], key=f"manual_{CLIENT.id}")
    manual = "" if choice.startswith("Choose") else choice.split(" · ")[0]
    a2.write("")
    a2.write("")
    if a2.button("Add", disabled=not manual):
        ss.send_list.setdefault(CLIENT.id, []).append(manual)
        ss[f"chk_{CLIENT.id}_{manual}"] = True
        st.rerun()

    send = ss.send_list.get(CLIENT.id, [])
    if not send:
        st.info("Send list is empty. Tick profiles in Tab 1, or add one above.")
    results = []
    for pid in list(send):
        p = PMAP[pid]
        vs = violations(CLIENT, p, learned_for(CLIENT.id))
        key = f"{CLIENT.id}|{pid}"
        overridden = key in ss.overrides
        state = "PASS" if not vs else ("OVERRIDDEN" if overridden else "BLOCKED")
        results.append((p, vs, state))
        with st.container(border=True):
            h1, h2 = st.columns([6, 1])
            badge = {"PASS": ":green[**PASS**]", "BLOCKED": ":red[**BLOCKED**]", "OVERRIDDEN": ":orange[**OVERRIDDEN**]"}[state]
            h1.markdown(f"{badge} &nbsp; {pid} · {profile_line(p)}")
            if h2.button("Remove", key=f"rm_{key}"):
                send.remove(pid)
                ss.overrides.pop(key, None)
                ss.pitches.pop(key, None)
                forget_widgets(f"chk_{CLIENT.id}_{pid}")
                forget_widgets(f"pitch_{key}")
                st.rerun()
            for v in vs:
                st.markdown(f"- ✋ {v.message}")
            if state == "BLOCKED":
                reason = st.text_input("Override reason (required to send anyway, min 15 characters)",
                                       key=f"ovr_{key}", placeholder="e.g. Client said on call she is OK with social drinkers now")
                ok = len(reason.strip()) >= MIN_OVERRIDE_CHARS
                if st.button("Log override", key=f"ovrbtn_{key}", disabled=not ok):
                    log_override(CLIENT, p, "; ".join(v.message for v in vs), reason.strip())
                    ss.overrides[key] = reason.strip()
                    st.rerun()
                if reason and not ok:
                    st.caption(f"{MIN_OVERRIDE_CHARS - len(reason.strip())} more characters needed.")
            elif state == "OVERRIDDEN":
                st.caption(f"Override logged to data/override_log.csv: \"{ss.overrides[key]}\"")

    if send:
        n_pass = sum(1 for _, _, s in results if s == "PASS")
        n_block = sum(1 for _, _, s in results if s == "BLOCKED")
        n_ovr = sum(1 for _, _, s in results if s == "OVERRIDDEN")
        st.markdown(f"**{n_pass} pass · {n_block} blocked · {n_ovr} overridden** - "
                    f"{n_pass + n_ovr} cleared to send{'' if not n_block else ' (blocked profiles cannot be sent)'}.")

        st.divider()
        st.markdown("#### Pitch drafter (optional)")
        text_llm = llm.get_text_caller()
        st.caption("2-line note for each PASS profile in the client's own words. "
                   + ("Written by the LLM, template fallback on error." if text_llm else "Template mode (offline)."))
        if st.button("Draft pitches for PASS profiles", disabled=n_pass == 0):
            for p, _, s in results:
                if s == "PASS":
                    key = f"{CLIENT.id}|{p.id}"
                    text, src = draft_pitch(CLIENT, p, ss.pitch_variant.get(key, 0), text_llm)
                    ss.pitches[key], ss.pitch_source[key] = text, src
                    forget_widgets(f"pitch_{key}")
        for p, _, s in results:
            key = f"{CLIENT.id}|{p.id}"
            if s != "PASS" or key not in ss.pitches:
                continue
            if f"pitch_{key}" not in ss:
                ss[f"pitch_{key}"] = ss.pitches[key]
            st.text_area(f"{p.name} - draft ({ss.pitch_source.get(key, 'template')})", key=f"pitch_{key}", height=110)
            b1, b2 = st.columns([1, 5])
            if b1.button("Regenerate", key=f"regen_{key}"):
                ss.pitch_variant[key] = ss.pitch_variant.get(key, 0) + 1
                text, src = draft_pitch(CLIENT, p, ss.pitch_variant[key], text_llm)
                ss.pitches[key], ss.pitch_source[key] = text, src
                del ss[f"pitch_{key}"]
                st.rerun()
            b2.success("Draft ready to copy", icon="📋")


# ============================================================================= TAB 3
def render_tags(tr):
    return " · ".join(f"{CATEGORY_LABELS.get(t.category, t.category)} {t.confidence:.2f} “{t.evidence}”" for t in tr.tags)


with tab3:
    st.subheader("Feedback tagger")
    json_llm = llm.get_json_caller()
    st.caption("Tags free text into the fixed taxonomy with a confidence and the exact phrase that triggered it. "
               + ("Uses the LLM (strict JSON, validated, 1 retry, then keyword fallback)." if json_llm
                  else "Offline keyword tagger: synonyms, Hinglish, typos and negations ('doesn't smoke') handled."))
    t1, t2 = st.columns([3, 2])
    with t1:
        txt = st.text_area("Paste rejection feedback", placeholder="e.g. daaru peeta hai, I had said no. Also too far, not moving to Pune",
                           height=90)
        if st.button("Tag feedback", disabled=not txt.strip()):
            tr, warn = tag_feedback(txt, TAXONOMY, json_llm)
            ss["single_tag"] = (txt, tr, warn)
        if "single_tag" in ss:
            _, tr, warn = ss["single_tag"]
            if warn:
                st.warning(warn)
            st.dataframe(pd.DataFrame([{"Category": t.category, "Confidence": t.confidence, "Evidence": t.evidence}
                                       for t in tr.tags]), hide_index=True, width="stretch")
            st.markdown(f"Vague: **{tr.is_vague}** · Sentiment: **{tr.sentiment}** · Source: **{tr.source}**")
            with st.expander("JSON"):
                st.json(tr.model_dump())
    with t2:
        st.markdown("**Taxonomy**")
        st.dataframe(pd.DataFrame([{"Category": k, "Description": v["description"]} for k, v in TAXONOMY.items()]),
                     hide_index=True, width="stretch", height=260)

    st.divider()
    rejected = [s for s in SHARES if s.outcome == "rejected"]
    if st.button(f"Tag all historical feedback ({len(rejected)} rejections)", type="primary"):
        ss.tag_warnings = []
        bar = st.progress(0.0) if json_llm else None
        for i, s in enumerate(rejected):
            tr, warn = tag_feedback(s.feedback_text, TAXONOMY, json_llm)
            ss.tagged[s.share_id] = tr
            if warn:
                ss.tag_warnings.append(f"{s.share_id}: {warn}")
            if bar:
                bar.progress((i + 1) / len(rejected))
    if ss.tag_warnings:
        st.warning(f"{len(ss.tag_warnings)} items fell back to the keyword tagger (LLM error / invalid JSON).")

    if ss.tagged:
        rows = []
        for s in rejected:
            tr = ss.tagged.get(s.share_id)
            if tr:
                rows.append({"Share": s.share_id, "Date": s.date, "Client": CMAP[s.client_id].name,
                             "Feedback": s.feedback_text, "Tags": render_tags(tr), "Vague": tr.is_vague,
                             "Sentiment": tr.sentiment})
        with st.expander(f"Tagged historical feedback ({len(rows)})", expanded=False):
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        st.markdown("### Learning")
        sugg = learned_suggestions(CLIENTS, PMAP, SHARES, ss.tagged, ss.learned["confirmed"], ss.learned["dismissed"])
        revs = reversal_flags(CLIENTS, PMAP, SHARES, ss.tagged)
        vags = vague_flags(CLIENTS, SHARES, ss.tagged)

        st.markdown("**Learned deal-breaker suggestions**")
        if not sugg:
            st.caption("No new suggestions.")
        for sg in sugg:
            with st.container(border=True):
                st.markdown(f"💡 **{sg.client_name} has rejected {sg.count} profiles for "
                            f"{CATEGORY_LABELS[sg.category]}.** Ask {sg.client_name}: is this a new deal-breaker?")
                for sid, ev in zip(sg.share_ids, sg.evidence):
                    sh = next(x for x in SHARES if x.share_id == sid)
                    st.caption(f"{sid} · {sh.date} · {PMAP[sh.profile_id].name} - “{sh.feedback_text}” (matched: {ev})")
                b1, b2, _ = st.columns([1.3, 1, 4])
                if b1.button("Client confirmed", key=f"conf_{sg.client_id}_{sg.category}", type="primary"):
                    ss.learned["confirmed"].setdefault(sg.client_id, []).append(sg.category)
                    persist_learned()
                    st.rerun()
                if b2.button("Dismiss", key=f"dis_{sg.client_id}_{sg.category}"):
                    ss.learned["dismissed"].setdefault(sg.client_id, []).append(sg.category)
                    persist_learned()
                    st.rerun()

        confirmed = [(cid, cat) for cid, cats in ss.learned["confirmed"].items() for cat in cats]
        if confirmed:
            st.success("Confirmed learned deal-breakers (enforced in Tab 1 and Tab 2): " + ", ".join(
                f"{CMAP[cid].name} - {CATEGORY_LABELS[cat]}" for cid, cat in confirmed))

        st.markdown("**Reversal guard**")
        if not revs:
            st.caption("No reversals detected.")
        for f in revs:
            st.warning(
                f"↩️ **{f.client_name} rejected “{CATEGORY_LABELS[f.category]}” but accepted a similar profile on "
                f"{f.accepted_date}. Do not auto-filter; discuss with client.**\n\n"
                f"Rejected {PMAP[f.rejected_profile_id].name} ({f.trait}) on {f.rejected_date}: “{f.rejected_feedback}”  \n"
                f"Accepted {PMAP[f.accepted_profile_id].name} ({describe_trait(f.category, PMAP[f.accepted_profile_id])}) "
                f"on {f.accepted_date}.")

        st.markdown("**Vague-rejection flags**")
        if not vags:
            st.caption("No clients with mostly vague rejections.")
        for v in vags:
            st.error(f"🗣️ **{v.client_name}'s rejections are mostly vague ({v.vague} of {v.total}, {v.ratio:.0%}). "
                     f"Consider a coaching conversation before sending more profiles.**")
    else:
        st.info("Click **Tag all historical feedback** to run learning (suggestions, reversals, vague flags).")


# ============================================================================= TAB 4
with tab4:
    st.subheader("Impact dashboard (last 30 days, mock data)")
    f = funnel(SHARES)
    mm = f["by_matchmaker"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Profiles shared", f["shares"])
    k2.metric("Acceptance rate", fmt_pct(f["acceptance_rate"]), help=f"{f['accepted']} accepted")
    k3.metric("Matchmaker A", fmt_pct(mm.loc["A", "acceptance_rate"]), help=f"{int(mm.loc['A','accepted'])}/{int(mm.loc['A','shares'])}")
    k4.metric("Matchmaker B", fmt_pct(mm.loc["B", "acceptance_rate"]), help=f"{int(mm.loc['B','accepted'])}/{int(mm.loc['B','shares'])}")

    av = avoidable_rejections(SHARES, CMAP, PMAP)
    st.markdown("#### Avoidable rejections")
    a1, a2 = st.columns([1, 2])
    a1.metric("Rejections that broke a stated preference", fmt_pct(av["rate"]), help="Computed from data rules, not from tags")
    a1.caption(f"{av['avoidable']} of {av['rejected']} rejections: the profile violated the client's stated "
               "preferences or deal-breakers when it was shared.")
    avdf = pd.DataFrame([{"Rule broken": RULE_LABELS.get(k, k), "Rejections": v} for k, v in av["by_rule"].most_common()])
    a2.bar_chart(avdf.set_index("Rule broken"), horizontal=True, height=260)

    st.markdown("#### If MatchGuard had been used")
    use_learned = st.toggle("Include confirmed learned deal-breakers", value=True)
    sim = simulate(SHARES, CMAP, PMAP, ss.learned["confirmed"] if use_learned else None)
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Rejected profiles blocked", sim["blocked_rejected"], help=f"{fmt_pct(sim['rejections_avoided_pct'])} of rejections")
    s2.metric("Projected acceptance", fmt_pct(sim["projected_rate"]),
              delta=f"{(sim['projected_rate'] - sim['baseline_rate']) * 100:+.1f} pts vs {fmt_pct(sim['baseline_rate'])}")
    s3.metric("Accepted profiles also blocked", sim["blocked_accepted"], delta="false positives", delta_color="off")
    s4.metric("Shares after filtering", sim["remaining_shares"], help=f"{sim['remaining_accepted']} accepted")
    if sim["false_positive_details"]:
        st.caption("False positives - the client accepted these even though they broke a stated rule. "
                   "This is why overrides exist and why stated preferences should be reviewed, not just enforced:")
        st.dataframe(pd.DataFrame([{"Share": s.share_id, "Date": s.date, "Client": CMAP[s.client_id].name,
                                    "Profile": profile_line(PMAP[s.profile_id]),
                                    "Rule broken": "; ".join(v.message for v in vs)}
                                   for s, vs in sim["false_positive_details"]]), hide_index=True, width="stretch")
    cmp = pd.DataFrame({"Acceptance rate (%)": [round(sim["baseline_rate"] * 100, 1), round(sim["projected_rate"] * 100, 1)]},
                       index=["Actual", "With MatchGuard"])
    st.bar_chart(cmp, horizontal=True, height=160)

    st.markdown("#### Learning signals")
    tagged = ss.tagged or {s.share_id: keyword_tag(s.feedback_text) for s in SHARES if s.outcome == "rejected"}
    revs = reversal_flags(CLIENTS, PMAP, SHARES, tagged)
    sugg_all = learned_suggestions(CLIENTS, PMAP, SHARES, tagged)
    rev_shares = {r.rejected_share_id for r in revs}
    l1, l2, l3 = st.columns(3)
    l1.metric("Reversal rate", fmt_pct(len(rev_shares) / max(1, av["rejected"])),
              help="Share of rejections whose stated reason was contradicted by a later/earlier acceptance")
    l2.metric("Reversals", len(revs))
    l3.metric("Learned deal-breaker suggestions", len(sugg_all),
              help=f"{sum(len(v) for v in ss.learned['confirmed'].values())} confirmed so far")
    if not ss.tagged:
        st.caption("Based on keyword tags; run 'Tag all historical feedback' in Tab 3 to use the session's tags.")
    reason_counts = pd.Series([t.category for tr in tagged.values() for t in tr.tags if t.confidence >= 0.6]).value_counts()
    rdf = pd.DataFrame({"Category": [CATEGORY_LABELS.get(c, c) for c in reason_counts.index],
                        "Rejections": reason_counts.values}).set_index("Category")
    st.markdown("Rejection reasons (tagged, confidence ≥ 0.6)")
    st.bar_chart(rdf, horizontal=True, height=380)
