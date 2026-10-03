"""Recommendations tab: solutions ranked by what is at stake, each with a staged action plan."""
import math

import pandas as pd
import streamlit as st

from nexus import playbook as pb
from nexus.recommend import KINDS, RULES, campus_year_kwh
from views import common

KIND_COLOR = {"Save energy": "green", "Cut peak": "orange", "Investigate": "blue", "Fix data": "red",
              "Plan": "violet"}
KIND_ICON = {"Save energy": ":material/bolt:", "Cut peak": ":material/trending_down:",
             "Investigate": ":material/search:", "Fix data": ":material/build:", "Plan": ":material/event:"}


def _money(kwh, tariff, factor):
    bits = []
    if tariff:
        bits.append(f"≈ ₹{kwh * tariff:,.0f} at your ₹{tariff:g}/kWh")
    if factor:
        bits.append(f"≈ {kwh * factor / 1000:,.1f} t CO₂")
    return f" ({', '.join(bits)})" if bits else ""


def stake_line(r, share, tariff, factor, campus):
    """What is at stake, in words. Savings are always the person's scenario, never a claim."""
    kwh = r["at_stake_kwh"]
    if r["worth_kind"] == "" or kwh is None or (isinstance(kwh, float) and math.isnan(kwh)):
        return ""
    if r["worth_kind"] == "once":
        return f"**{kwh:,.0f} kWh** extra in this one event{_money(kwh, tariff, factor)}."
    if r["worth_kind"] == "shift":
        return (f"**{kwh:,.0f} kWh a year** to move out of peak hours. This lowers the peak; it does not "
                "save energy, and its value depends on whether your tariff charges for peak demand.")
    saved = kwh * share
    of_campus = f", {saved / campus:.1%} of the campus's year" if campus else ""
    return (f"**{kwh:,.0f} kWh** {r['at_stake_what']}. If a fix cut that by {share:.0%}: "
            f"**{saved:,.0f} kWh a year**{of_campus}{_money(saved, tariff, factor)}.")


def plan_markdown(r):
    blocks = []
    for stage in pb.STAGES:
        steps = [(what, who) for s, what, who in r["actions"] if s == stage]
        if steps:
            blocks.append(f"**{stage}**\n\n" + "\n".join(f"- {what} — *{who}*" for what, who in steps))
    return "\n\n".join(blocks)


def card(r, share, tariff, factor, campus, open_plan=False):
    with st.container(border=True):
        st.markdown(f"#### {r['title']} · {r['building']}")
        st.markdown(f":{KIND_COLOR[r['kind']]}-badge[{KIND_ICON[r['kind']]} {r['kind']}] "
                    f":gray[{pb.TYPE_LABEL[r['btype']]} · rule {r['rule']}]")
        st.markdown(f"**What the data shows.** {r['finding']}")
        stake = stake_line(r, share, tariff, factor, campus)
        if stake:
            st.markdown(f"**What's at stake.** {stake}")
        if not open_plan:
            st.markdown(f"**First step.** {r['next_step']} — *{r['actions'][0][2]}*")
        with st.expander(f"Full solution plan · {len(r['actions'])} steps", expanded=open_plan,
                         icon=":material/checklist:"):
            st.markdown("**Common causes to rule out**\n" + "\n".join(f"- {c}" for c in r["causes"]))
            st.markdown(plan_markdown(r))
            st.markdown(f"**How you'll know it worked.** {r['verify']}")
            st.caption(r["evidence"])


def checklist(recs, share, campus, college):
    """The whole plan as a Markdown checklist to download and share."""
    out = [f"# NEXUS action plan: {college}", "",
           "Things to check and try, from rules applied to the meter data. Causes are possibilities to rule "
           f"out, not diagnoses. Savings assume a fix cuts the targeted energy by {share:.0%} (your setting).", ""]
    for kind in KINDS:
        part = recs[recs["kind"] == kind]
        if part.empty:
            continue
        out += [f"## {kind}", ""]
        for r in part.to_dict("records"):
            out += [f"### {r['title']}: {r['building']}", "", r["finding"], ""]
            stake = stake_line(r, share, None, None, campus).replace("**", "")
            if stake:
                out += [f"At stake: {stake}", ""]
            out += ["Causes to rule out: " + "; ".join(r["causes"]) + ".", ""]
            out += [f"- [ ] {stage}: {what} ({who})" for stage, what, who in r["actions"]]
            out += ["", f"How to know it worked: {r['verify']}", ""]
    return "\n".join(out)


def ordered(recs):
    """Kinds in a fixed order; inside each, the most at stake first."""
    rank = {k: i for i, k in enumerate(KINDS)}
    return recs.assign(_k=recs["kind"].map(rank), _s=recs["at_stake_kwh"].fillna(-1)).sort_values(
        ["_k", "_s", "size"], ascending=[True, False, False]).drop(columns=["_k", "_s"])


def show():
    recs = common.recommendations()
    ds = common.dataset()
    df, _ = common.load()
    tariff, factor = st.session_state.get("tariff"), st.session_state.get("emission_factor")
    campus = campus_year_kwh(df, ds.warnings)

    st.caption("NEXUS can't see inside buildings: causes are possibilities to rule out, and savings are "
               "a scenario you set below, never a promise.")
    if recs.empty:
        st.info("No rule was triggered by the current data.")
        return

    share = st.slider("If a fix works, assume it cuts the energy it targets by", 5, 50, 20, step=5,
                      format="%d%%", key="fix_share",
                      help="Your assumption, used for every 'if a fix cut that' figure. Only a site check "
                           "can say what is really achievable.") / 100
    notes = []
    if campus:
        notes.append(f"Campus energy in the last 12 months of data: **{campus:,.0f} kWh** (buildings with "
                     "reliable meters, scaled to a full year where readings are missing).")
    if not tariff:
        notes.append("Add your electricity tariff in **More → Settings** to see rupees next to each saving.")
    if notes:
        st.caption(" ".join(notes))

    # ------------------------------------------------------------ start here
    saves = recs[recs["worth_kind"] == "save"].sort_values("at_stake_kwh", ascending=False)
    top = saves.drop_duplicates("rule").head(3)          # three different kinds of fix
    if len(top):
        st.subheader("Start here")
        st.caption("The biggest opportunity of each of the three largest kinds. Amounts overlap (the "
                   "always-on load is also part of near-empty hours), so don't add them up.")
        cols = st.columns(len(top))
        for col, r in zip(cols, top.to_dict("records")):
            saved = r["at_stake_kwh"] * share
            with col.container(border=True):
                st.markdown(f":{KIND_COLOR[r['kind']]}[**{r['title']}**]  \n{r['building']}")
                st.html(f'<div style="font-family:Chakra Petch,sans-serif;font-size:1.45rem;font-weight:600;'
                        f'line-height:1.15">{saved:,.0f}&nbsp;kWh</div>')
                notes = [f"a year if cut by {share:.0%}"]
                if campus:
                    notes.append(f"{saved / campus:.1%} of the campus's year")
                if tariff:
                    notes.append(f"≈ ₹{saved * tariff:,.0f} at your tariff")
                st.caption(" · ".join(notes))
                st.markdown(f"**First step:** {r['next_step']}")

    # ------------------------------------------------------------ all recommendations
    st.subheader("All recommendations")
    counts = recs["kind"].value_counts()
    options = ["All"] + [k for k in KINDS if k in counts]
    pick = st.segmented_control("Show", options, default="All", key="rec_kind",
                                format_func=lambda k: k if k == "All" else f"{k} ({counts[k]})")
    buildings = sorted(recs["building"].unique())
    where = st.multiselect("Buildings", buildings, placeholder="All buildings", key="rec_buildings")
    view = recs if pick in (None, "All") else recs[recs["kind"] == pick]
    if where:
        view = view[view["building"].isin(where)]
    first = set(top.index)
    for i, r in ordered(view).iterrows():
        card(r.to_dict(), share, tariff, factor, campus, open_plan=i in first)

    st.download_button("Download the action plan (checklist)", checklist(ordered(recs), share, campus, ds.name),
                       f"nexus-action-plan-{share:.0%}.md".replace("%", "pct"), "text/markdown",
                       icon=":material/download:", type="primary",
                       help="A Markdown checklist: opens in any text editor, Notion, GitHub or Google Docs.")

    with st.expander("How recommendations are made"):
        st.dataframe(pd.DataFrame(RULES, columns=["Rule", "Type", "Name", "Triggered when"]),
                     hide_index=True)
        st.markdown(
            "- **Findings and amounts** come from the meter data with the thresholds in "
            "`nexus/recommend.py`. Buildings or periods without enough data are skipped, never guessed, "
            "and meters flagged unreliable are left out.\n"
            "- **Causes and steps** come from `nexus/playbook.py`: general building-energy practice, adapted "
            "to the building's type. The type is guessed from its name (dorm/hostel → residence, "
            "dining/mess → dining hall, facilities/plant → plant).\n"
            "- **Savings** are your scenario: the energy at stake × the reduction you set above. NEXUS "
            "does not promise them.\n"
            f"- **24 °C AC setting:** {pb.BEE_24C} [Source]({pb.BEE_24C_URL})")
