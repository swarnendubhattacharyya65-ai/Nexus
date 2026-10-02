"""Shared by every page: cached data loads, colours and small display helpers."""
import pandas as pd
import streamlit as st

from nexus.kpis import snapshot
from nexus.data import OUT
from nexus.resource import add_baseline, find_events, load_energy

# Chart colours, stepped for the navy page (validated: contrast >= 3:1, colour-blind safe pair).
ACTUAL = "#3987e5"     # measured series
FORECAST = "#d95926"   # forecast series
NEUTRAL = "#8b94a8"    # baselines, expected values, rules
UNUSUAL = "#ec835a"    # shading for flagged hours only


@st.cache_data(show_spinner="Calculating baselines ...")
def load():
    """Hourly energy with baselines and flags, plus the unusual events found in it."""
    df = add_baseline(load_energy())
    return df, find_events(df)


@st.cache_data(show_spinner=False)
def occupancy():
    return pd.read_parquet(OUT / "occupancy_hourly.parquet")


@st.cache_data(show_spinner="Comparing the week ...")
def week(week_end):
    df, events = load()
    return snapshot(df, events, occupancy(), pd.Timestamp(week_end))


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
