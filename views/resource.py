"""Resource Intelligence page: each building's energy against its own baseline."""
import altair as alt
import pandas as pd
import streamlit as st

from nexus.resource import MIN_CHANGE, Z_LIMIT
from views import common
from views.common import ACTUAL, NEUTRAL as EXPECTED, UNUSUAL, events_table, legend


def event_ids(ev):
    """A stable name for each event, so search can open a specific one."""
    return ev["building"] + " " + ev["start"].dt.strftime("%Y-%m-%d %H:%M")


def show(df, events):
    analysed = df[df["flag"] != "unreliable meter"]
    buildings = sorted(analysed["building"].unique())
    first, last = df["hour"].min().date(), df["hour"].max().date()
    f1, f2, f3 = st.columns([1, 2, 1])
    building = f1.selectbox("Building", buildings, key="res_building")
    # Search can set the period; only give a default when nothing set it.
    default = {} if "res_period" in st.session_state else {"value": (first, last)}
    picked = f2.date_input("Period", min_value=first, max_value=last, key="res_period", **default)
    direction = f3.radio("Show events", ["higher", "lower"], horizontal=True,
                         format_func=lambda d: f"{d.capitalize()} than usual", key="res_direction")
    start = pd.Timestamp(picked[0])
    end = pd.Timestamp(picked[1] if len(picked) == 2 else last) + pd.Timedelta("1D")

    b = analysed[(analysed["building"] == building)
                 & (analysed["hour"] >= start) & (analysed["hour"] < end)]

    st.subheader(f"{building}: daily energy against its baseline")
    days = (b.assign(day=b["hour"].dt.normalize())
            .groupby("day").agg(actual=("kwh", "sum"), expected=("expected", "sum"),
                                hours=("kwh", "count"), with_baseline=("expected", "count")))
    days = days[(days["hours"] == 24) & (days["with_baseline"] == 24)].reset_index()
    if days.empty:
        st.info("Insufficient data: no complete days with a baseline in this period.")
    else:
        series = days.melt("day", ["actual", "expected"], var_name="series", value_name="kwh")
        series["series"] = series["series"].map({"actual": "Actual", "expected": "Expected"})
        names = ["Actual", "Expected"]
        lines = alt.Chart(series).mark_line(strokeWidth=2).encode(
            x=alt.X("day:T", title=None),
            y=alt.Y("kwh:Q", title="kWh per day"),
            color=alt.Color("series:N", scale=alt.Scale(domain=names, range=[ACTUAL, EXPECTED]),
                            legend=alt.Legend(orient="top", title=None)),
            strokeDash=alt.StrokeDash("series:N", scale=alt.Scale(domain=names, range=[[1, 0], [4, 3]]),
                                      legend=None),
        )
        nearest = alt.selection_point(nearest=True, on="pointerover", fields=["day"], empty=False)
        rule = alt.Chart(days).mark_rule(color=EXPECTED).encode(
            x="day:T",
            opacity=alt.condition(nearest, alt.value(0.4), alt.value(0)),
            tooltip=[alt.Tooltip("day:T", title="Day", format="%a %d %b %Y"),
                     alt.Tooltip("actual:Q", title="Actual kWh", format=",.0f"),
                     alt.Tooltip("expected:Q", title="Expected kWh", format=",.0f")],
        ).add_params(nearest)
        st.altair_chart(lines + rule, width="stretch")
        st.caption("Complete days only (24 hours measured, all with a baseline).")

    picked_events = events[(events["building"] == building)
                           & (events["direction"] == ("high" if direction == "higher" else "low"))
                           & (events["start"] >= start) & (events["start"] < end)]
    st.subheader(f"{direction.capitalize()}-than-usual events ({len(picked_events):,})")
    if picked_events.empty:
        st.info("No events of this kind in the selected building and period.")
    else:
        st.dataframe(events_table(picked_events), hide_index=True, height=250)

        picked_events = picked_events.assign(id=event_ids(picked_events))
        labels = {e.id: f"{e.start:%d %b %Y %H:%M}, {e.hours} h, {e.extra_kwh:+,.0f} kWh"
                  for e in picked_events.itertuples()}
        if st.session_state.get("res_event") not in labels:
            st.session_state.pop("res_event", None)   # e.g. an event outside the chosen period
        choice = st.selectbox("Look at one event", list(labels), format_func=labels.get,
                              key="res_event")
        e = picked_events.set_index("id").loc[choice]

        m1, m2, m3 = st.columns(3)
        m1.metric("Measured", f"{e['actual_kwh']:,.0f} kWh")
        m2.metric("Expected", f"{e['expected_kwh']:,.0f} kWh")
        m3.metric("Difference", f"{e['extra_kwh']:+,.0f} kWh", delta=f"{e['extra_pct']:+.0%}",
                  delta_color="inverse")
        st.markdown(
            f"**{e['start']:%A %d %B %Y, %H:%M}** to **{e['end']:%a %d %b, %H:%M}** ({e['hours']} hours"
            + (f", {e['activity']}-activity day" if common.dataset().has_calendar else "")
            + f"). Expected = the median of at least {e['samples']:.0f} "
            "comparable hours: same hour of day, same day type"
            + (" and same academic activity, " if common.dataset().has_calendar else " (working or not), ")
            + f"within 3 weeks either side. Flagged because each hour was more than {Z_LIMIT} times "
            f"the normal variation away and at least {MIN_CHANGE:.0%} different.")

        around = analysed[(analysed["building"] == building)
                          & (analysed["hour"] >= e["start"] - pd.Timedelta("2D"))
                          & (analysed["hour"] < e["end"] + pd.Timedelta("2D"))]
        x = alt.X("hour:T", title=None)
        band = alt.Chart(around).mark_area(color=EXPECTED, opacity=0.18).encode(
            x=x, y=alt.Y("low:Q", title="kWh per hour"), y2="high:Q")
        expected = alt.Chart(around).mark_line(color=EXPECTED, strokeWidth=2,
                                               strokeDash=[4, 3]).encode(x=x, y="expected:Q")
        actual = alt.Chart(around).mark_line(color=ACTUAL, strokeWidth=2).encode(x=x, y="kwh:Q")
        span = alt.Chart(pd.DataFrame({"start": [e["start"]], "end": [e["end"]]})).mark_rect(
            color=UNUSUAL, opacity=0.15).encode(x="start:T", x2="end:T")
        nearest_hour = alt.selection_point(nearest=True, on="pointerover", fields=["hour"], empty=False)
        hour_rule = alt.Chart(around).mark_rule(color=EXPECTED).encode(
            x=x,
            opacity=alt.condition(nearest_hour, alt.value(0.4), alt.value(0)),
            tooltip=[alt.Tooltip("hour:T", title="Hour", format="%a %d %b %H:%M"),
                     alt.Tooltip("kwh:Q", title="Measured kWh", format=",.1f"),
                     alt.Tooltip("expected:Q", title="Expected kWh", format=",.1f"),
                     alt.Tooltip("low:Q", title="Normal range from", format=",.1f"),
                     alt.Tooltip("high:Q", title="Normal range to", format=",.1f")],
        ).add_params(nearest_hour)
        legend(("━━", ACTUAL, "Measured"), ("╍╍", EXPECTED, "Expected"),
               ("■", "#c9c8c4", "Normal range (middle half of comparable hours)"),
               ("■", UNUSUAL, "Flagged hours"))
        st.altair_chart(span + band + expected + actual + hour_rule, width="stretch")

        st.warning("**This is a measured difference, not a diagnosed cause.** NEXUS flags it "
                   "for investigation. It could be equipment left running, an event, or a "
                   "meter fault; the data alone cannot tell which.")
        with st.expander("Hour-by-hour evidence"):
            rows = around[(around["hour"] >= e["start"]) & (around["hour"] < e["end"])]
            cols = ["hour", "kwh", "expected", "low", "high", "samples", "flag"]
            st.dataframe(rows[cols].round({"kwh": 1, "expected": 1, "low": 1, "high": 1}),
                         hide_index=True)
