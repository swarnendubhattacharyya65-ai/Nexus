"""NEXUS web app.

Run in the codespace:   streamlit run app.py
Reads only the small tables in data/processed/, so it also runs when deployed.
"""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from nexus.data import ENERGY_WARNINGS, OUT
from nexus.resource import MIN_CHANGE, Z_LIMIT, add_baseline, find_events, load_energy
from views import institutional as institutional_view
from views import predictive as predictive_view

ACTUAL = "#2a78d6"    # the measured series
EXPECTED = "#8c8b86"  # neutral grey for the baseline and its normal range
UNUSUAL = "#ec835a"   # shades the flagged hours only

st.set_page_config(page_title="NEXUS", layout="wide")


@st.cache_data(show_spinner="Calculating baselines ...")
def load():
    df = add_baseline(load_energy())
    return df, find_events(df)


def events_table(ev):
    """Events as a readable table: one row per event."""
    return pd.DataFrame({
        "Building": ev["building"],
        "Start": ev["start"].dt.strftime("%Y-%m-%d %H:%M"),
        "Hours": ev["hours"],
        "Actual kWh": ev["actual_kwh"].round(),
        "Expected kWh": ev["expected_kwh"].round(),
        "Extra kWh": ev["extra_kwh"].round(),
        "Extra %": (ev["extra_pct"] * 100).round(),
    })


def legend(*items):
    """A small legend: coloured mark, plain text label."""
    parts = [f'<span style="color:{color}">{mark}</span>&nbsp;{label}' for mark, color, label in items]
    st.markdown("&emsp;".join(parts), unsafe_allow_html=True)


# ------------------------------------------------------------------ header

st.title("NEXUS")
st.caption("Campus intelligence from the data an institution already generates")
st.info("**Demo data:** public electricity and Wi-Fi occupancy data from IIIT-Delhi, "
        "New Delhi (I-BLEND, 2013-2017). **This is not PES data.**")

if not (OUT / "energy_hourly.parquet").exists():
    st.error("No processed data found. In the codespace, run `python -m nexus.data` first.")
    st.stop()

df, events = load()
analysed = df[df["flag"] != "unreliable meter"]
high_events = events[events["direction"] == "high"]

overview, resource, inst_tab, pred_tab, method = st.tabs(
    ["Overview", "Resource Intelligence", "Institutional Intelligence",
     "Predictive Intelligence", "Data & method"])

# ---------------------------------------------------------------- overview

with overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buildings analysed", f"{analysed['building'].nunique()} of {df['building'].nunique()}")
    c2.metric("Period", f"{df['hour'].min():%Y}-{df['hour'].max():%Y}",
              help=f"{df['hour'].min():%d %b %Y} to {df['hour'].max():%d %b %Y}")
    c3.metric("Hours with a baseline", f"{analysed['flag'].isin(['normal', 'high', 'low']).sum():,}")
    c4.metric("Higher-than-usual events", f"{len(high_events):,}")
    for building, why in ENERGY_WARNINGS.items():
        st.warning(f"**{building} energy is not analysed.** {why}")

    st.subheader("Average energy per day")
    per_day = (analysed.assign(day=analysed["hour"].dt.normalize())
               .groupby(["building", "day"])["kwh"].agg(["sum", "count"]))
    per_day = per_day[per_day["count"] == 24]  # complete days only
    avg = per_day.groupby("building")["sum"].mean().reset_index(name="kwh_per_day")
    bars = alt.Chart(avg).mark_bar(color=ACTUAL, cornerRadiusEnd=4).encode(
        x=alt.X("kwh_per_day:Q", title="kWh per day (average over complete days)",
                axis=alt.Axis(tickCount=5)),
        y=alt.Y("building:N", sort="-x", title=None, axis=alt.Axis(grid=False),
                scale=alt.Scale(paddingInner=0.45)),
        tooltip=[alt.Tooltip("building:N", title="Building"),
                 alt.Tooltip("kwh_per_day:Q", title="kWh per day", format=",.0f")],
    ).properties(height=36 * len(avg))
    st.altair_chart(bars, width="stretch")

    st.subheader("Largest higher-than-usual events")
    st.dataframe(events_table(high_events.head(10)), hide_index=True)

# --------------------------------------------------------------- resource

with resource:
    buildings = sorted(analysed["building"].unique())
    first, last = df["hour"].min().date(), df["hour"].max().date()
    f1, f2, f3 = st.columns([1, 2, 1])
    building = f1.selectbox("Building", buildings)
    picked = f2.date_input("Period", (first, last), min_value=first, max_value=last)
    direction = f3.radio("Show events", ["higher", "lower"], horizontal=True,
                         format_func=lambda d: f"{d.capitalize()} than usual")
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

        labels = [f"{e.start:%d %b %Y %H:%M}  ·  {e.hours} h  ·  {e.extra_kwh:+,.0f} kWh"
                  for e in picked_events.itertuples()]
        choice = st.selectbox("Look at one event", range(len(labels)), format_func=lambda i: labels[i])
        e = picked_events.iloc[choice]

        m1, m2, m3 = st.columns(3)
        m1.metric("Measured", f"{e['actual_kwh']:,.0f} kWh")
        m2.metric("Expected", f"{e['expected_kwh']:,.0f} kWh")
        m3.metric("Difference", f"{e['extra_kwh']:+,.0f} kWh", delta=f"{e['extra_pct']:+.0%}",
                  delta_color="inverse")
        st.markdown(
            f"**{e['start']:%A %d %B %Y, %H:%M}** to **{e['end']:%a %d %b, %H:%M}** ({e['hours']} hours, "
            f"{e['activity']}-activity day). Expected = the median of at least {e['samples']:.0f} "
            "comparable hours: same hour of day, same day type and same academic activity, "
            f"within 3 weeks either side. Flagged because each hour was more than {Z_LIMIT} times "
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

# ----------------------------------------------------------------- method

with inst_tab:
    institutional_view.show()

with pred_tab:
    predictive_view.show()

with method:
    st.markdown(Path("DATA.md").read_text())
