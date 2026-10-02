"""Shared by every page: the selected college, its analyses (computed once), colours, helpers.

IIIT-Delhi's results are cached for everyone. An uploaded college's results are kept only
in that visitor's session, so one visitor's data never reaches another.
"""
import pandas as pd
import streamlit as st

from nexus.dataset import IIITD, iiitd
from nexus.institutional import building_summary, load_occupancy
from nexus.kpis import default_week_end, snapshot
from nexus.predictive import backtest, daily_energy, day_types, evaluate, forecast
from nexus.recommend import build
from nexus.resource import add_baseline, find_events, load_energy

# Chart colours, stepped for the navy page (validated: contrast >= 3:1, colour-blind safe pair).
ACTUAL = "#3987e5"     # measured series
FORECAST = "#d95926"   # forecast series
NEUTRAL = "#8b94a8"    # baselines, expected values, rules
UNUSUAL = "#ec835a"    # shading for flagged hours only


# ------------------------------------------------------------- which college

def uploads():
    return st.session_state.setdefault("uploads", {})


def colleges():
    return [IIITD, *uploads()]


def college():
    name = st.session_state.get("college", IIITD)
    return name if name in colleges() else IIITD


def _code_version():
    """Fingerprint of the analysis code, so a deploy never reuses results cached by older code."""
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    h = hashlib.sha1()
    for f in sorted([*(root / "nexus").glob("*.py"), *(root / "views").glob("*.py")]):
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


VERSION = _code_version()


@st.cache_resource(show_spinner=False)
def _iiitd(version):
    return iiitd()


def dataset():
    name = college()
    return _iiitd(VERSION) if name == IIITD else uploads()[name]["dataset"]


@st.cache_resource(show_spinner="Running the analysis ...")
def _shared(kind, _fn, version):
    return _fn(_iiitd(version))


def compute(kind, fn, spinner="Working ..."):
    """fn(dataset) for the selected college, computed once. Results are shared: don't modify them."""
    name = college()
    if name == IIITD:
        return _shared(kind, fn, VERSION)
    memo = uploads()[name].setdefault("memo", {})
    if kind not in memo:
        with st.spinner(spinner):
            memo[kind] = fn(dataset())
    return memo[kind]


# ------------------------------------------------------------- the analyses

def _energy(ds):
    df = add_baseline(load_energy(ds), ds.warnings)
    return df, find_events(df)


def load():
    """Hourly energy with baselines and flags, plus the unusual events found in it."""
    return compute("energy", _energy, "Calculating baselines ...")


def occupancy():
    return dataset().occupancy


def _institutional(ds):
    if ds.occupancy is None or ds.occupancy.empty:
        return None, pd.DataFrame()
    occ = load_occupancy(ds)
    return occ, building_summary(occ, ds)


def institutional():
    """(hourly occupancy with calendar, per-building summary); (None, empty) without occupancy."""
    return compute("institutional", _institutional, "Reading occupancy ...")


def _predictive(ds):
    daily, types = daily_energy(ds), day_types(ds)
    return daily, types, evaluate(backtest(daily, types))


def predictive():
    return compute("predictive", _predictive, "Testing forecasts on past data ...")


def _recommendations(ds):
    _, events = load()
    _, summary = institutional()
    daily, types, evaluation = predictive()
    return build(events, summary, evaluation, daily, types, forecast, ds.calendar)


def recommendations():
    return compute("recommendations", _recommendations, "Applying recommendation rules ...")


def week(week_end):
    week_end = pd.Timestamp(week_end)
    df, events = load()
    return compute(f"week {week_end:%Y-%m-%d}",
                   lambda ds: snapshot(df, events, ds.occupancy, week_end, ds),
                   "Comparing the week ...")


def last_full_day():
    return compute("last day", default_week_end)


# ------------------------------------------------------------- display helpers

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
