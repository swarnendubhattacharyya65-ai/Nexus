"""Institutional Intelligence tab: building occupancy patterns."""
import altair as alt
import streamlit as st

from nexus.institutional import (BUSY, BUSY_LEVEL, DAYS, MIN_HOURS, MIN_QUIET_SHARE, QUIET,
                                 building_summary, load_occupancy, weekly_profile)
from views.common import ACTUAL as BLUE

# One-hue ramp for the heatmap; the quiet end fades into the navy page.
RAMP = ["#0d366b", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"]


@st.cache_data(show_spinner="Reading occupancy ...")
def _data():
    occ = load_occupancy()
    return occ, building_summary(occ)


def show():
    occ, summary = _data()

    # ------------------------------------------------------------ findings
    st.subheader("Findings")
    energy = summary[summary["energy_note"] == ""].sort_values("quiet_vs_busy", ascending=False)
    if not energy.empty:
        top = energy.iloc[0]
        st.markdown(
            f"- **{top['building']}** draws the most energy when near-empty: a median "
            f"**{top['quiet_kwh']:.1f} kWh per hour** in quiet semester hours, "
            f"**{top['quiet_vs_busy']:.0%}** of the {top['busy_kwh']:.1f} kWh it draws when busy "
            f"({top['quiet_energy_hours']:,} quiet and {top['busy_energy_hours']:,} busy hours compared).")
    underused = summary.sort_values("quiet_in_class_hours", ascending=False).iloc[0]
    if underused["quiet_in_class_hours"] >= 0.05:
        st.markdown(
            f"- **{underused['building']}** is most often near-empty during semester working "
            f"hours (weekdays 09:00-17:00): **{underused['quiet_in_class_hours']:.0%}** of "
            f"{underused['class_hours']:,} such hours had fewer than "
            f"{QUIET * underused['busy_level']:.0f} people.")
    else:
        st.markdown("- No building was near-empty in more than 5% of semester working hours "
                    "(weekdays 09:00-17:00).")
    st.caption("Measured patterns, not causes. Section below shows the numbers and method.")

    # -------------------------------------------------------- weekly pattern
    st.subheader("When is each building in use?")
    c1, c2 = st.columns([1, 1])
    building = c1.selectbox("Building", sorted(occ["building"].unique()), key="inst_building")
    semester = c2.radio("Weeks", [True, False], horizontal=True, key="inst_period",
                        format_func=lambda w: "Semester weeks" if w else "Break weeks")
    profile = weekly_profile(occ, building, semester)
    if profile.empty:
        st.info("Insufficient data for this building and period.")
    else:
        heat = alt.Chart(profile).mark_rect(cornerRadius=2).encode(
            x=alt.X("hour_of_day:O", title="Hour of day",
                    scale=alt.Scale(paddingInner=0.08), axis=alt.Axis(labelAngle=0)),
            y=alt.Y("day:O", sort=DAYS, title=None, scale=alt.Scale(paddingInner=0.08)),
            color=alt.Color("people:Q", title="People (median)",
                            scale=alt.Scale(range=RAMP, domainMin=0)),
            tooltip=[alt.Tooltip("day:N", title="Day"),
                     alt.Tooltip("hour_of_day:O", title="Hour"),
                     alt.Tooltip("people:Q", title="People (median)", format=",.0f"),
                     alt.Tooltip("hours:Q", title="Hours of data")],
        ).properties(height=260)
        st.altair_chart(heat, width="stretch")
        st.caption("Median estimated people for each hour of the week, 2014-2017.")

    # ------------------------------------------------- energy when quiet
    st.subheader("Energy when near-empty")
    if energy.empty:
        st.info("Insufficient data to compare energy with occupancy.")
    else:
        bars = alt.Chart(energy).mark_bar(color=BLUE, cornerRadiusEnd=4).encode(
            x=alt.X("quiet_vs_busy:Q", title="Energy in quiet hours, as % of busy hours",
                    axis=alt.Axis(format="%", tickCount=5),
                    scale=alt.Scale(domain=[0, max(1.0, energy["quiet_vs_busy"].max())])),
            y=alt.Y("building:N", sort="-x", title=None, axis=alt.Axis(grid=False),
                    scale=alt.Scale(paddingInner=0.45)),
            tooltip=[alt.Tooltip("building:N", title="Building"),
                     alt.Tooltip("quiet_kwh:Q", title="Quiet hours, kWh/h", format=",.1f"),
                     alt.Tooltip("busy_kwh:Q", title="Busy hours, kWh/h", format=",.1f"),
                     alt.Tooltip("quiet_vs_busy:Q", title="Quiet as % of busy", format=".0%")],
        ).properties(height=alt.Step(40))  # 40 px per building, plus room for the axis
        st.altair_chart(bars, width="stretch")
    skipped = summary[summary["energy_note"] != ""]
    for r in skipped.itertuples():
        st.caption(f"{r.building}: not shown. {r.energy_note}.")

    # ------------------------------------------------------------ evidence
    with st.expander("Numbers and method"):
        table = summary.assign(
            busy_level=summary["busy_level"].round(),
            class_hours_people=summary["class_hours_people"].round(),
            night_people=summary["night_people"].round(),
            quiet_share=(summary["quiet_share"] * 100).round(),
            quiet_in_class_hours=(summary["quiet_in_class_hours"] * 100).round(),
            quiet_kwh=summary["quiet_kwh"].round(1),
            busy_kwh=summary["busy_kwh"].round(1),
            quiet_vs_busy=(summary["quiet_vs_busy"] * 100).round(),
        ).rename(columns={
            "building": "Building", "busy_level": "Busy level (people)",
            "class_hours_people": "Semester weekdays 09-17 (median people)",
            "night_people": "Semester nights 00-06 (median people)",
            "quiet_share": "Quiet hours %", "quiet_in_class_hours": "Quiet in weekday 09-17 %",
            "quiet_kwh": "Quiet kWh/h", "busy_kwh": "Busy kWh/h",
            "quiet_vs_busy": "Quiet as % of busy", "energy_note": "Note",
        }).drop(columns=["class_hours", "quiet_energy_hours", "busy_energy_hours"])
        st.dataframe(table, hide_index=True)
        st.markdown(
            f"- **Busy level:** the people count a building reaches or exceeds in its busiest "
            f"{1 - BUSY_LEVEL:.0%} of hours (95th percentile), over all hours with data.\n"
            f"- **Quiet hour:** fewer than {QUIET:.0%} of the busy level. "
            f"**Busy hour:** at least {BUSY:.0%} of it.\n"
            "- **Semester week:** a Monday-Sunday week in which at least 3 of the 5 weekdays "
            "are high-activity days in the institute calendar. All other weeks are break weeks.\n"
            "- **Energy comparison:** median kWh per hour in quiet vs busy hours, semester "
            "weeks only, so long holidays do not distort it. Needs at least "
            f"{MIN_HOURS} hours of each, otherwise it shows insufficient data. Buildings "
            f"near-empty in under {MIN_QUIET_SHARE:.0%} of hours are not compared: there, a "
            "quiet reading is more likely a Wi-Fi drop-out than an empty building.\n"
            "- **People** are Wi-Fi estimates. They overcount people with several devices "
            "(up to about 50 in Academic, about 20 elsewhere, per the dataset paper) and miss "
            "people not on Wi-Fi. In buildings that empty at night, missing 10-minute slots "
            "count as 0 people; elsewhere they stay blank (see Data & method).")
