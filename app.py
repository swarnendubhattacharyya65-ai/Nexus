"""NEXUS web app.

Run in the codespace:   streamlit run app.py
Reads only the small tables in data/processed/, so it also runs when deployed.
"""
from pathlib import Path

import streamlit as st

from nexus.data import OUT

st.set_page_config(page_title="NEXUS", page_icon=":material/hub:", layout="wide")

from views import shell  # noqa: E402  (after set_page_config)

shell.style()
st.logo("static/logo.svg", size="large", icon_image="static/icon.svg")

if not (OUT / "energy_hourly.parquet").exists():
    st.error("No processed data found. In the codespace, run `python -m nexus.data` first.")
    st.stop()

from views import common, institutional, overview, predictive, recommend, resource  # noqa: E402
from nexus.predictive import HORIZON  # noqa: E402


# ------------------------------------------------------------------- pages

def overview_page():
    df, events = common.load()
    overview.show(df, events, common.week(st.session_state["week_end"]))


def resource_page():
    shell.page_header("Resource Intelligence",
                      "Each building's hourly electricity against its own baseline: the median "
                      "of comparable hours. Hours far outside the normal range are flagged.")
    resource.show(*common.load())


def institutional_page():
    shell.page_header("Institutional Intelligence",
                      "Building-level patterns from Wi-Fi connection counts. The data has no "
                      "rooms, timetables or capacities, so NEXUS does not report a utilization "
                      "rate: each building is compared with its own busiest hours instead.")
    institutional.show()


def predictive_page():
    shell.page_header("Predictive Intelligence",
                      f"Each building's daily energy forecast {HORIZON} days ahead with two "
                      "simple, transparent methods, tested on past data. Pick any date to see "
                      "what NEXUS would have forecast then, next to what actually happened.")
    predictive.show()


def recommendations_page():
    shell.page_header("Recommendations",
                      "Each suggestion comes from an explicit rule applied to the findings on "
                      "the other pages, and shows the numbers behind it.")
    recommend.show(common.load()[1])


def data_page():
    st.markdown(Path("DATA.md").read_text())


PAGES = {
    "overview": st.Page(overview_page, title="Overview", icon=":material/space_dashboard:",
                        url_path="overview", default=True),
    "resource": st.Page(resource_page, title="Resource Intelligence", icon=":material/bolt:",
                        url_path="resource"),
    "institutional": st.Page(institutional_page, title="Institutional Intelligence",
                             icon=":material/groups:", url_path="institutional"),
    "predictive": st.Page(predictive_page, title="Predictive Intelligence",
                          icon=":material/trending_up:", url_path="predictive"),
    "recommendations": st.Page(recommendations_page, title="Recommendations",
                               icon=":material/checklist:", url_path="recommendations"),
    "data": st.Page(data_page, title="Data & method", icon=":material/description:",
                    url_path="data"),
}

page = st.navigation({
    "Intelligence": [PAGES[k] for k in ["overview", "resource", "institutional", "predictive",
                                        "recommendations"]],
    "About the data": [PAGES["data"]],
})

# A search result was picked: go to its page (state was set by the button callback).
goto = st.session_state.pop("_goto", None)
if goto:
    st.switch_page(PAGES[goto])

with st.sidebar:
    st.caption("Data: I-BLEND, IIIT-Delhi (CC0). Public demo data, not PES data.")

shell.top_bar()
page.run()
