"""Recommendations tab: solutions ranked by the energy at stake, each with a staged action plan.

Everything follows the 'Week ending' date: the rules look at the 12 months ending there.
NEXUS measures the energy each problem involves. The savings estimate is that energy x a cut the
person chooses (default 10%), always labelled with the cut it assumes; NEXUS never predicts how
much a fix will achieve.
"""
import math

import pandas as pd
import streamlit as st

from nexus import playbook as pb
from nexus.recommend import (CAMPUS, DEFAULT_REDUCTION, KINDS, RULES, YEAR_DAYS, campus_year_kwh,
                             estimated_saving, last_year, window)
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


def _missing(kwh):
    return kwh is None or (isinstance(kwh, float) and math.isnan(kwh))


def saving_line(r, tariff, factor, reduction=DEFAULT_REDUCTION):
    """'Estimated savings at a 10% cut (your assumption): N kWh (≈ ₹...)', or '' if none applies."""
    saved = estimated_saving(r["at_stake_kwh"], r["worth_kind"], reduction)
    if saved is None:
        return ""
    return (f"Estimated savings at a {reduction:.0%} cut (your assumption): "
            f"**{saved:,.0f} kWh**{_money(saved, tariff, factor)}")


def stake_line(r, tariff, factor, campus, reduction=DEFAULT_REDUCTION):
    """What is at stake, from the data only, plus the savings estimate at the chosen cut."""
    kwh = r["at_stake_kwh"]
    if r["worth_kind"] == "" or _missing(kwh):
        return ""
    if r["worth_kind"] == "once":
        return f"**{kwh:,.0f} kWh** {r['at_stake_what']}{_money(kwh, tariff, factor)}."
    if r["worth_kind"] == "shift":
        return (f"**{kwh:,.0f} kWh** {r['at_stake_what']}. This lowers the peak; it does not save energy, "
                "and its value depends on whether your tariff charges for peak demand.")
    of_campus = f", {kwh / campus:.1%} of the campus's year" if campus else ""
    return (f"**{kwh:,.0f} kWh** {r['at_stake_what']}{of_campus}. "
            f"{saving_line(r, tariff, factor, reduction)}.")


def plan_markdown(r):
    blocks = []
    for stage in pb.STAGES:
        steps = [(what, who) for s, what, who in r["actions"] if s == stage]
        if steps:
            blocks.append(f"**{stage}**\n\n" + "\n".join(f"- {what} — *{who}*" for what, who in steps))
    return "\n\n".join(blocks)


def card(r, tariff, factor, campus, reduction, open_plan=False):
    with st.container(border=True):
        st.markdown(f"#### {r['title']} · {r['building']}")
        st.markdown(f":{KIND_COLOR[r['kind']]}-badge[{KIND_ICON[r['kind']]} {r['kind']}] "
                    f":gray[{pb.TYPE_LABEL[r['btype']]} · rule {r['rule']}]")
        st.markdown(f"**What the data shows.** {r['finding']}")
        stake = stake_line(r, tariff, factor, campus, reduction)
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


def checklist(recs, campus, college, period, reduction=DEFAULT_REDUCTION):
    """The whole plan as a Markdown checklist to download and share."""
    out = [f"# NEXUS action plan: {college}", "", f"Based on {period}.", "",
           "Things to check and try, from rules applied to the meter data. Causes are possibilities to rule "
           "out, not diagnoses. Amounts are the energy each problem involves, as measured. Estimated savings "
           f"assume a {reduction:.0%} cut (your assumption, not a prediction); only a site check can say "
           "what a fix really saves.", ""]
    for kind in KINDS:
        part = recs[recs["kind"] == kind]
        if part.empty:
            continue
        out += [f"## {kind}", ""]
        for r in part.to_dict("records"):
            out += [f"### {r['title']}: {r['building']}", "", r["finding"], ""]
            stake = stake_line(r, None, None, campus, reduction).replace("**", "")
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


def start_here(top, tariff, factor, campus, reduction):
    st.subheader("Start here")
    st.caption("The biggest opportunity of each of the three largest kinds. Amounts overlap (the always-on "
               "load is also part of near-empty hours), so don't add them up.")
    cols = st.columns(len(top))
    for col, r in zip(cols, top.to_dict("records")):
        kwh = r["at_stake_kwh"]
        with col.container(border=True):
            st.markdown(f":{KIND_COLOR[r['kind']]}[**{r['title']}**]  \n{r['building']}")
            st.html(f'<div style="font-family:Chakra Petch,sans-serif;font-size:1.45rem;font-weight:600;'
                    f'line-height:1.15">{kwh:,.0f}&nbsp;kWh</div>')
            st.caption(r["at_stake_what"] + (f" · {kwh / campus:.1%} of the campus's year" if campus else ""))
            saved = estimated_saving(kwh, r["worth_kind"], reduction)
            st.markdown(f"Estimated savings at a {reduction:.0%} cut: **{saved:,.0f} kWh**"
                        f"{_money(saved, tariff, factor)}")
            st.markdown(f"**First step:** {r['next_step']}")


def show():
    ds = common.dataset()
    as_of = common.selected_week_end()
    start, end = window(as_of)
    df, _ = common.load()
    recs = common.recommendations(as_of)
    tariff, factor = st.session_state.get("tariff"), st.session_state.get("emission_factor")
    campus = campus_year_kwh(df, ds.warnings, as_of)
    cut = common.reduction()

    span = f"the 12 months from {start:%-d %b %Y} to {as_of:%-d %b %Y}"
    st.markdown(f":material/date_range: Based on **{span}**, ending with the **Week ending** date at the "
                "top. Change that date to see another year.")
    covered = last_year(df, ds.warnings, as_of)
    days = covered["hour"].dt.normalize().nunique() if len(covered) else 0
    if days < YEAR_DAYS - 1:
        st.info(f"Only {days} days of readings fall in these 12 months, so rules that need a longer "
                "record (the seasonal swing needs 9 months, the others 60 days) may be skipped, and "
                "yearly amounts are scaled up from the days there are.", icon=":material/info:")
    left, _ = st.columns([1, 1])
    with left:
        common.reduction_slider("reduction_recs")

    notes = ["NEXUS can't see inside buildings: causes are possibilities to rule out. Amounts are the "
             "energy each problem involves, as measured. Estimated savings are that energy x the cut "
             "you set above, not a prediction of what a fix will achieve."]
    if campus:
        notes.append(f"Campus energy in these 12 months: **{campus:,.0f} kWh** (buildings with reliable "
                     "meters, scaled to a full year where readings are missing).")
    if not tariff:
        notes.append("Add your electricity tariff in **More → Settings** to see rupees.")
    st.caption(" ".join(notes))

    if recs.empty:
        st.info("No rule was triggered in these 12 months.")
        return

    saves = recs[recs["worth_kind"] == "save"].sort_values("at_stake_kwh", ascending=False)
    top = saves.drop_duplicates("rule").head(3)          # three different kinds of fix
    if len(top):
        start_here(top, tariff, factor, campus, cut)

    # ------------------------------------------------------------ all recommendations
    st.subheader("All recommendations")
    counts = recs["kind"].value_counts()
    # options stay the same for every date, so a choice never disappears when the date changes
    pick = st.segmented_control("Show", ["All"] + KINDS, default="All", key="rec_kind",
                                format_func=lambda k: k if k == "All" else f"{k} ({counts.get(k, 0)})")
    buildings = sorted(df["building"].unique()) + [CAMPUS]
    where = st.multiselect("Buildings", buildings, placeholder="All buildings", key="rec_buildings")
    view = recs if pick in (None, "All") else recs[recs["kind"] == pick]
    if where:
        view = view[view["building"].isin(where)]
    if view.empty:
        st.caption("Nothing of this kind for these buildings in these 12 months.")
    first = set(top.index)
    for i, r in ordered(view).iterrows():
        card(r.to_dict(), tariff, factor, campus, cut, open_plan=i in first)

    st.download_button("Download the action plan (checklist)", checklist(ordered(recs), campus, ds.name, span, cut),
                       f"nexus-action-plan-{as_of:%Y-%m-%d}.md", "text/markdown",
                       icon=":material/download:", type="primary",
                       help="A Markdown checklist: opens in any text editor, Notion, GitHub or Google Docs.")

    with st.expander("How recommendations are made"):
        st.dataframe(pd.DataFrame(RULES, columns=["Rule", "Type", "Name", "Triggered when"]),
                     hide_index=True)
        st.markdown(
            "- **Dates:** every rule looks at the 12 months ending on the Week ending date. Unusual events "
            "are those that started in that window; the forecast is for the 14 days after it.\n"
            "- **Findings and amounts** come from the meter data with the thresholds in "
            "`nexus/recommend.py`. Buildings or periods without enough data are skipped, never guessed, "
            "and meters flagged unreliable are left out.\n"
            f"- **Estimated savings:** the energy each problem involves (measured) x the cut you set "
            f"(now {cut:.0%}; default {DEFAULT_REDUCTION:.0%}). Only energy-saving checks get one: a one-off "
            "event is not a recurring saving, and cutting the peak moves energy rather than saving it. "
            "How much a fix really saves can only be found on site.\n"
            "- **Causes and steps** come from `nexus/playbook.py`: general building-energy practice, adapted "
            "to the building's type. The type is guessed from its name (dorm/hostel → residence, "
            "dining/mess → dining hall, facilities/plant → plant).\n"
            f"- **24 °C AC setting:** {pb.BEE_24C} [Source]({pb.BEE_24C_URL})")
